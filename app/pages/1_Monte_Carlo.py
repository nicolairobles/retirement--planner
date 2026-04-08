"""
Monte Carlo page — historical backtest.
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
from helpers.charts import mc_cycles_strip_chart, monte_carlo_distribution_chart  # noqa: E402
from helpers.scenario_card import render_scenario_card_v2  # noqa: E402
from helpers.seeds import build_seedcase_from_inputs  # noqa: E402
from helpers.theme import apply_altair_theme, inject_css  # noqa: E402
from model.historical import HistoricalYear, run_historical_cycle  # noqa: E402
from model.outputs import run_and_extract  # noqa: E402
from helpers.chat_widget import render_chat_in_sidebar  # noqa: E402
from helpers.analytics import track_page_view  # noqa: E402

st.set_page_config(page_title="Monte Carlo", layout="wide")
inject_css()
apply_altair_theme()

render_chat_in_sidebar()
track_page_view("monte_carlo")

st.title("Historical Monte Carlo")

# ---------- Big plain-language explainer ----------

with st.container():
    st.markdown(
        """
        **What this page does:** takes your current scenario and runs it through every
        historical starting year from 1928 onward, using **actual** stock returns, bond
        returns, and inflation from that period. Each "cycle" answers: *"if I had
        retired in year X with this plan, would I have made it?"*

        **Why it matters:** the Planner uses smooth average returns (like 7% stocks
        every year). Real markets are volatile. The Great Depression, 1970s stagflation,
        and the 2008 crash each produce very different outcomes. This page shows you
        how your plan performs across the full sweep of real market history, not just
        one idealized path.
        """
    )

st.divider()

# ---------- Load historical data ----------

@st.cache_data
def load_historical():
    import csv
    path = REPO_ROOT / "retirement-sim" / "evals" / "external-benchmarks" / "historical-returns-annual.csv"
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(HistoricalYear(
                year=int(row["year"]),
                sp500_return=float(row["sp500_return"]),
                tbond_return=float(row["tbond_return"]),
                inflation=float(row["inflation"]),
            ))
    return sorted(rows, key=lambda y: y.year)


historical = load_historical()

# ---------- Read current scenario from session state ----------

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
    "This page analyzes the scenario shown above. To change it, edit inputs on the "
    "**Planner** page and return here."
)
st.divider()

# ---------- Run Monte Carlo ----------

@st.cache_data
def run_mc(inputs_tuple, current_age):
    """Run all viable historical cycles. Cached on inputs hash.

    IMPORTANT: arg names must NOT start with underscore, or Streamlit will
    skip hashing them and return the same result for every call.
    """
    inputs_dict = dict(inputs_tuple)
    seed = build_seedcase_from_inputs(inputs_dict, current_age=current_age)
    n_years = seed.years_simulated
    min_year = historical[0].year
    max_year = historical[-1].year
    results = []
    for start in range(min_year, max_year - n_years + 2):
        slice_idx = start - min_year
        hist_slice = historical[slice_idx:slice_idx + n_years]
        try:
            r = run_historical_cycle(seed, hist_slice)
            results.append(r)
        except Exception:
            pass
    return results


inputs_tuple = inputs_cache_key(inputs)
with st.spinner("Running historical cycles…"):
    results = run_mc(inputs_tuple, current_age)

if not results:
    st.error(
        "No historical cycles could complete — your plan horizon may be longer than "
        "available historical data (1928-2024)."
    )
    st.stop()

# ---------- Top-level verdict ----------

successes = sum(1 for r in results if r.succeeded)
terminals_real = sorted([r.terminal_nw_real for r in results])
n = len(results)
success_rate = successes / n


def pctl(arr, p):
    idx = int(round((p / 100) * (len(arr) - 1)))
    return arr[idx]


# Verdict banner
if success_rate >= 0.95:
    st.success(
        f"**{success_rate:.0%} historical success rate** — your plan survived "
        f"{successes} of {n} historical sequences including the Great Depression, "
        f"stagflation, and 2008. **Historically safe.**"
    )
elif success_rate >= 0.80:
    st.warning(
        f"**{success_rate:.0%} historical success rate** — your plan survived "
        f"{successes} of {n} historical sequences. **Borderline**: some sequences "
        f"exhaust the portfolio. Consider higher savings, lower spending, or "
        f"delayed retirement."
    )
else:
    st.error(
        f"**{success_rate:.0%} historical success rate** — your plan failed in "
        f"{n - successes} of {n} historical sequences. **Historically risky** as "
        f"currently configured."
    )

st.divider()

# ---------- Summary metrics ----------

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Historical cycles", n,
    help="Number of different historical starting years we tested your plan through. "
         "Starting in 1928, stepping forward one year at a time.",
)
col2.metric(
    "Success rate", f"{success_rate*100:.1f}%",
    help="Percentage of historical sequences where your portfolio survived to end-of-plan "
         "without exhausting. Success means: retirement was reached AND spendable "
         "portfolio stayed above $0 throughout retirement.",
)
col3.metric(
    "Median terminal (real)", f"${pctl(terminals_real, 50)/1_000_000:.2f}M",
    help="In half the historical cycles your plan ended with MORE than this, and in "
         "half it ended with LESS. Values are in today's dollars (adjusted for the "
         "inflation that actually happened in each historical cycle).",
)
col4.metric(
    "Worst terminal (real)", f"${min(terminals_real)/1_000_000:.2f}M",
    help="The single worst-ever historical outcome. This is usually a cycle that started "
         "right before a major crash (1929, 1973, 2000).",
)

st.divider()

# ---------- Per-cycle strip chart ----------

st.subheader("Each historical start year, survived or failed")
st.altair_chart(mc_cycles_strip_chart(results, height=340), width='stretch')
st.caption(
    "**Each dot = one historical starting year.** X-axis is when you would have "
    "retired (1928, 1929, 1930...). Y-axis is where that cycle landed in today's "
    "dollars. Green = survived to end-of-plan, red = ran out of money. "
    "Look for **clusters of red** — those are historically rough eras to retire into."
)

st.divider()

# ---------- Distribution chart ----------

st.subheader("Distribution of terminal net worth")

years_retired_count = det_outputs.records[-1].year - det_outputs.records[0].year
infl = inputs.get("in_Inflation", 0.03)
det_real = det_outputs.nw_at_end / ((1 + infl) ** years_retired_count)

st.altair_chart(
    monte_carlo_distribution_chart(
        terminals_real, deterministic_value=det_real, height=320,
    ),
    width='stretch',
)
st.markdown(
    """
    **How to read this:**
    - Each **bar** counts how many historical starting years ended with a terminal
      net worth in that range, running your plan through that period's actual returns.
    - The **amber dashed line** shows where your deterministic plan (using the smooth
      return assumptions you set on the Planner) lands on this distribution.
    - **Wide spread = high sensitivity to starting year.** Narrow spread = the plan
      is robust regardless of when you retire.
    """
)

# ---------- Bengen 4% Rule comparison ----------

st.divider()
st.subheader("4% Rule sanity check")
st.caption(
    "The **4% Rule** (a.k.a. Bengen / Trinity Study): a classic 1994 guideline. "
    "It says you can safely retire when your portfolio ≥ 25× your annual spending. "
    "See [Glossary](/Glossary) for the full explanation."
)

current_annual_spend = (inputs["in_MonthlyNonHousing"] + inputs["in_MonthlyRent"]) * 12
bengen_safe_portfolio = current_annual_spend * 25  # 4% rule = 25x spending

# Portfolio at retirement (first retired year's start balance)
retirement_portfolio = None
for r in det_outputs.records:
    if r.phase == "Retired":
        retirement_portfolio = r.start_balance
        break

col_a, col_b, col_c = st.columns(3)
col_a.metric(
    "Your portfolio at retirement",
    f"${retirement_portfolio/1_000_000:.2f}M" if retirement_portfolio else "—",
    help="Start-of-year portfolio balance in the first retired year (nominal).",
)
col_b.metric(
    "Bengen-safe portfolio (25× spending)",
    f"${bengen_safe_portfolio/1_000_000:.2f}M",
    help="The 4% Rule says a portfolio ≥ 25× your annual spending can sustain 30 years of inflation-adjusted withdrawals with ~95% historical success.",
)
if retirement_portfolio:
    ratio = retirement_portfolio / bengen_safe_portfolio
    if ratio >= 1.5:
        verdict = f"✅ Well above ({ratio:.1f}× Bengen minimum)"
    elif ratio >= 1.0:
        verdict = f"✅ Meets Bengen ({ratio:.2f}× minimum)"
    else:
        verdict = f"⚠️ Below Bengen ({ratio:.2f}× minimum)"
    col_c.metric("4% Rule check", verdict)
st.caption(
    "The 4% Rule is a rough sanity check — our full-model Monte Carlo above is more "
    "accurate because it includes taxes, glide path, and your specific income streams."
)

st.divider()

# ---------- Percentile table ----------

st.subheader("Distribution percentiles")
st.caption(
    "Terminal spendable net worth across all historical cycles, shown in today's "
    "dollars at retirement-start. **Lower percentiles** are worse-case scenarios "
    "(bad-luck historical starts). **Higher percentiles** are best-case scenarios."
)

pct_df = pd.DataFrame({
    "Percentile": [
        "Worst ever", "5th", "10th", "25th",
        "Median (50th)", "75th", "90th", "Best ever", "Average",
    ],
    "Meaning": [
        "Single worst historical outcome",
        "5% of cycles ended below this",
        "10% of cycles ended below this (bad-luck scenario)",
        "25% of cycles ended below this",
        "Half ended below, half above",
        "Top 25% of cycles",
        "Top 10% of cycles (good-luck scenario)",
        "Single best historical outcome",
        "Average across all cycles",
    ],
    "Savings at end (today's $)": [
        min(terminals_real), pctl(terminals_real, 5), pctl(terminals_real, 10),
        pctl(terminals_real, 25), pctl(terminals_real, 50), pctl(terminals_real, 75),
        pctl(terminals_real, 90), max(terminals_real), sum(terminals_real)/n,
    ],
})
pct_df["Savings at end (today's $)"] = pct_df["Savings at end (today's $)"].apply(lambda v: f"${v:,.0f}")
st.dataframe(pct_df, width='stretch', hide_index=True)

# ---------- Worst / best / failures ----------

worst = min(results, key=lambda r: r.terminal_nw_real)
best = max(results, key=lambda r: r.terminal_nw_real)

st.divider()
st.subheader("Extreme cycles")

col_a, col_b = st.columns(2)
with col_a:
    st.markdown(
        f"**🔻 Worst sequence:** started in **{worst.start_hist_year}**  \n"
        f"Terminal net worth: **${worst.terminal_nw_real:,.0f}** (real)"
    )
    st.caption(
        "This cycle started with the worst sequence of returns and inflation in the dataset. "
        "If you think your future might look similar, this is your floor."
    )
with col_b:
    st.markdown(
        f"**🔺 Best sequence:** started in **{best.start_hist_year}**  \n"
        f"Terminal net worth: **${best.terminal_nw_real:,.0f}** (real)"
    )
    st.caption(
        "This cycle started with the best sequence in the dataset. Don't plan on it, "
        "but it shows the upside."
    )

failures = [r for r in results if not r.succeeded]
if failures:
    st.divider()
    st.subheader("Failed cycles")
    st.caption(
        "Cycles where the portfolio reached $0 during retirement, OR retirement was "
        "never reached. You'd have needed to adapt: cut spending, downsize, work longer, "
        "or sell illiquid assets."
    )
    st.markdown(
        "**Starting years that failed:** " +
        ", ".join(str(r.start_hist_year) for r in failures)
    )

st.divider()
st.caption(
    "**Methodology:** historical data from 1928 to 2024 using actual U.S. stock market "
    "returns (S&P 500), government bond returns (10-year Treasury), and official inflation "
    "data (Bureau of Labor Statistics). Crypto and cash use your assumed returns (no long "
    "historical record exists). The full model is applied to every cycle: your shifting "
    "stock/bond mix, federal taxes, tax-adjusted withdrawals, property, and vehicle costs."
)
