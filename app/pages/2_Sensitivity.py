"""
Sensitivity page — tornado diagram ranking inputs by impact.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))

from helpers.cache_keys import inputs_cache_key  # noqa: E402
from helpers.charts import tornado_chart  # noqa: E402
from helpers.local_storage import restore_inputs_from_localstorage  # noqa: E402
from helpers.scenario_card import render_scenario_card_v2  # noqa: E402
from helpers.seeds import build_seedcase_from_inputs  # noqa: E402
from helpers.theme import apply_altair_theme, inject_css  # noqa: E402
from model.outputs import run_and_extract  # noqa: E402
from helpers.chat_widget import render_chat_in_sidebar  # noqa: E402
from helpers.analytics import track_page_view  # noqa: E402

st.set_page_config(page_title="Sensitivity", layout="wide")
inject_css()
apply_altair_theme()

# Restore scenario from browser localStorage before anything else reads it —
# the chat sidebar mutates st.session_state.inputs, so restore must run first.
restore_inputs_from_localstorage()

render_chat_in_sidebar()
track_page_view("sensitivity")

st.title("Sensitivity Analysis")

# ---------- Big plain-language explainer ----------

st.markdown(
    """
    **What this page does:** wiggles each input up and down from your current
    scenario, holding everything else fixed, and measures the impact on a chosen
    outcome. The result is a **tornado chart** — inputs ranked by how much they
    move the result.

    **Why it matters:** not every input deserves the same attention. Some
    assumptions (stock returns, your savings rate) can swing the outcome by
    millions. Others (cash return, disability COLA) barely move the needle.
    Use this to know where precision matters and where approximation is fine.
    """
)

st.divider()

# ---------- Scenario state ----------

if "inputs" not in st.session_state:
    st.warning("Open the **Planner** page first to set up a scenario.")
    st.stop()

inputs = st.session_state.inputs
current_age = st.session_state.current_age
scenario_name = st.session_state.get("scenario_name", "Your scenario")

det_seed = build_seedcase_from_inputs(inputs, current_age=current_age)
det_outputs = run_and_extract(det_seed)
render_scenario_card_v2(det_outputs, scenario_name, current_age)
st.caption(
    "This analysis runs against the scenario shown above. Edit inputs on the "
    "**Planner** page to re-analyze a different scenario."
)
st.divider()

# ---------- Controls ----------

col1, col2 = st.columns([2, 1])
with col1:
    metric = st.selectbox(
        "What outcome are we measuring?",
        options=[
            "Savings at end of plan",
            "Retirement age",
            "Lifetime federal tax",
        ],
        help="Pick which downstream result you care about. The tornado shows which "
             "inputs most affect this specific output.",
    )
with col2:
    top_n = st.number_input(
        "How many inputs to show", min_value=5, max_value=20, value=10, step=1,
        help="How many of the highest-impact inputs to display in the chart.",
    )

metric_map = {
    "Savings at end of plan": ("nw_at_end", lambda o: o.nw_at_end, "$"),
    "Retirement age": ("retirement_age", lambda o: o.retirement_age or 999, "years"),
    "Lifetime federal tax": ("lifetime_tax", lambda o: o.lifetime_federal_tax, "$"),
}
metric_key, extract, unit = metric_map[metric]

# ---------- Inputs to vary ----------

INPUTS_TO_VARY = [
    ("in_StockReturn", 0.25), ("in_BondReturn", 0.25), ("in_Inflation", 0.33),
    ("in_RetirementTarget", 0.30), ("in_MonthlyNonHousing", 0.50),
    ("in_MonthlyRent", 0.50), ("in_401kContrib", 0.50), ("in_Year2Salary", 0.50),
    ("in_Year4Salary", 0.50), ("in_SalaryGrowth", 0.50), ("in_401kStart", 0.50),
    ("in_InvestStart", 0.50), ("in_SSBenefit", 0.20), ("in_EndAge", 0.11),
]

# Dynamically add debt inputs when debts are enabled
for _n in (1, 2, 3):
    if inputs.get(f"in_Debt{_n}Enabled") == "Yes":
        _bal = float(inputs.get(f"in_Debt{_n}Balance", 0))
        _rate = float(inputs.get(f"in_Debt{_n}Rate", 0))
        if _bal > 0:
            INPUTS_TO_VARY.append((f"in_Debt{_n}Balance", 0.50))
        if _rate > 0:
            INPUTS_TO_VARY.append((f"in_Debt{_n}Rate", 0.50))

# Human-readable labels for each input (no jargon, no code-variable names)
INPUT_LABELS = {
    "in_StockReturn": "Stock return",
    "in_BondReturn": "Bond return",
    "in_CryptoReturn": "Crypto return",
    "in_CashReturn": "Cash return",
    "in_Inflation": "Inflation rate",
    "in_RetirementTarget": "Retirement target ($)",
    "in_MonthlyNonHousing": "Non-housing expenses ($/mo)",
    "in_MonthlyRent": "Housing cost ($/mo)",
    "in_401kContrib": "Annual 401(k) contribution",
    "in_Year1Salary": "2025 salary",
    "in_Year2Salary": "2026 salary",
    "in_Year3Salary": "2027 salary",
    "in_Year4Salary": "2028 salary",
    "in_SalaryGrowth": "Salary growth rate",
    "in_401kStart": "401(k) starting balance",
    "in_InvestStart": "Investment account start",
    "in_CashStart": "Cash savings start",
    "in_CryptoStart": "Crypto start",
    "in_SSBenefit": "Social Security benefit ($/mo)",
    "in_SSAge": "Social Security claim age",
    "in_DisabBenefit": "Disability benefit ($/mo)",
    "in_EndAge": "End-of-plan age",
    "in_VehicleCost": "Vehicle replacement cost",
    "in_VehicleInterval": "Vehicle replacement interval",
    "in_PropertyCost": "Property purchase price",
    "in_PropertyAppreciation": "Property appreciation rate",
    "in_MortgageRate": "Mortgage rate",
}

# Add debt labels dynamically using user-provided labels
for _n in (1, 2, 3):
    _lbl = inputs.get(f"in_Debt{_n}Label", f"Debt {_n}")
    INPUT_LABELS[f"in_Debt{_n}Balance"] = f"{_lbl} balance"
    INPUT_LABELS[f"in_Debt{_n}Rate"] = f"{_lbl} interest rate"


def pretty_label(key: str) -> str:
    """Return a human-readable label for an input key."""
    if key in INPUT_LABELS:
        return INPUT_LABELS[key]
    # Fallback: strip prefix, insert spaces around capitals
    name = key.replace("in_", "")
    import re
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    name = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", name)
    return name


@st.cache_data
def compute_tornado(inputs_tuple, current_age, metric_key):
    """Build the sensitivity tornado. Cached on all args.

    IMPORTANT: arg names must NOT start with underscore or Streamlit skips hashing.
    """
    base_inputs = dict(inputs_tuple)
    base_seed = build_seedcase_from_inputs(base_inputs, current_age=current_age)
    base_out = run_and_extract(base_seed)
    base_val = extract(base_out)

    entries = []
    for name, pct in INPUTS_TO_VARY:
        if name not in base_inputs or not isinstance(base_inputs[name], (int, float)) or base_inputs[name] == 0:
            continue
        base_val_input = base_inputs[name]
        if name == "in_EndAge":
            low = int(base_val_input - 10)
            high = int(base_val_input + 10)
        else:
            low = base_val_input * (1 - pct)
            high = base_val_input * (1 + pct)
        low_mod = {**base_inputs, name: low}
        high_mod = {**base_inputs, name: high}
        low_out = run_and_extract(build_seedcase_from_inputs(low_mod, current_age=current_age))
        high_out = run_and_extract(build_seedcase_from_inputs(high_mod, current_age=current_age))
        low_v = extract(low_out)
        high_v = extract(high_out)
        entries.append({
            "name": name, "low_output": low_v, "high_output": high_v,
            "impact": abs(high_v - low_v), "vary_pct": pct,
        })
    entries.sort(key=lambda e: e["impact"], reverse=True)
    return entries, base_val


inputs_tuple = inputs_cache_key(inputs)
with st.spinner("Running sensitivity analysis…"):
    entries, base_val = compute_tornado(inputs_tuple, current_age, metric_key)

# ---------- Base value metric ----------

if unit == "$":
    formatted = f"${base_val/1_000_000:.2f}M" if base_val >= 1_000_000 else f"${base_val:,.0f}"
else:
    formatted = f"{int(base_val)}"
st.metric(
    f"Your scenario's {metric.lower()}",
    formatted,
    help="This is what the model produces with all your current inputs. Every row "
         "below shows how this number would change if you moved ONE input.",
)

st.divider()

# ---------- Tornado chart ----------

st.subheader("Which inputs matter most")
# Replace code-variable names with human-readable labels for the chart
pretty_entries = [{**e, "name": pretty_label(e["name"])} for e in entries[:top_n]]
st.altair_chart(tornado_chart(pretty_entries, height=max(300, top_n * 30)), width='stretch')
st.caption(
    "**How to read:** each bar is ONE input. Its length = how far the outcome moves "
    "when that input swings from low to high. **Bars at the top are the most "
    "consequential**; bars at the bottom barely matter. Hover a bar for the low/high "
    "values that produced this range."
)

st.divider()

# ---------- Details table ----------

st.subheader("Impact ranking")
st.caption(
    f"Inputs ranked by how much they change **{metric.lower()}** when moved from low to "
    f"high. The bar length shows the size of the swing. The arrow shows whether raising "
    f"the input makes the outcome better (↑) or worse (↓)."
)

# Find max impact for bar scaling
max_impact = max(e["impact"] for e in entries[:top_n]) if entries else 1

table_rows = []
for i, e in enumerate(entries[:top_n], 1):
    if unit == "$":
        swing_str = f"${e['impact']:,.0f}"
    else:
        swing_str = f"{int(e['impact'])}"

    # Direction: is "higher output" better or worse for THIS metric?
    # - NW at end: higher is better
    # - Retirement age: higher is worse (delayed retirement)
    # - Lifetime federal tax: higher is worse
    higher_output_is_better = metric == "Savings at end of plan"

    if e["high_output"] > e["low_output"]:
        # Raising input → higher output
        if higher_output_is_better:
            direction = "↑ raising helps"
        else:
            direction = "↓ raising hurts"
    elif e["high_output"] < e["low_output"]:
        # Raising input → lower output
        if higher_output_is_better:
            direction = "↓ raising hurts"
        else:
            direction = "↑ raising helps"
    else:
        direction = "— no effect"

    # Bar (progress column)
    bar_fraction = e["impact"] / max_impact if max_impact > 0 else 0

    table_rows.append({
        "#": i,
        "Input": pretty_label(e["name"]),
        "Swing in outcome": bar_fraction,
        "Swing amount": swing_str,
        "Direction": direction,
    })

st.dataframe(
    pd.DataFrame(table_rows),
    width='stretch', hide_index=True,
    column_config={
        "#": st.column_config.NumberColumn(
            width="small",
            help="Rank by impact (1 = most consequential).",
        ),
        "Input": st.column_config.TextColumn(
            width="medium",
            help="The input that was varied. Everything else stayed fixed.",
        ),
        "Swing in outcome": st.column_config.ProgressColumn(
            width="medium",
            format="",
            min_value=0.0, max_value=1.0,
            help="Visual bar: longer = this input swings the outcome more.",
        ),
        "Swing amount": st.column_config.TextColumn(
            width="small",
            help=f"How much {metric.lower()} changes between the low and high tested values.",
        ),
        "Direction": st.column_config.TextColumn(
            width="medium",
            help="Does raising this input make your outcome better or worse?",
        ),
    },
)

with st.expander("Show detailed low/high values"):
    detail_rows = []
    for i, e in enumerate(entries[:top_n], 1):
        if unit == "$":
            low_str = f"${e['low_output']:,.0f}"
            high_str = f"${e['high_output']:,.0f}"
        else:
            low_str = f"{int(e['low_output'])}"
            high_str = f"{int(e['high_output'])}"
        detail_rows.append({
            "#": i,
            "Input": pretty_label(e["name"]),
            "Tested range": f"±{int(e['vary_pct']*100)}%",
            f"{metric} if LOW": low_str,
            f"{metric} if HIGH": high_str,
        })
    st.dataframe(pd.DataFrame(detail_rows), width='stretch', hide_index=True)

st.divider()
st.markdown(
    """
    **How to use this:**
    - **Top inputs deserve careful estimation.** If stock return or retirement
      target swings your plan by millions, get your assumption for those as close
      to reality as you can.
    - **Bottom inputs are fine to approximate.** No point agonizing over cash
      return to 3 decimal places if it moves the answer by $5K.
    - **Unexpected ranking?** An input you thought mattered doesn't. Or one you
      ignored dominates. That's usually the insight.
    """
)
