"""
Retirement Planner — Streamlit app (Planner page).

Entry point for the multi-page app. Interactive sidebar form + live
projection chart + scenario state card. All defaults are hypothetical
personas; no real user financial data is embedded.

Run locally:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))

from helpers.cache_keys import inputs_cache_key  # noqa: E402
from helpers.charts import (  # noqa: E402
    bucket_breakdown_chart,
    debt_payoff_chart,
    income_vs_expenses_chart,
    projection_chart,
)
from helpers.events import extract_events, events_by_year  # noqa: E402
from helpers.local_storage import (  # noqa: E402
    clear_localstorage,
    load_from_localstorage,
    save_to_localstorage,
)
from helpers.housing_comparison import compare_rent_vs_buy  # noqa: E402
from helpers.recommendations import generate_recommendations  # noqa: E402
from helpers.target_finder import find_safe_target  # noqa: E402
from helpers.scenario_card import render_scenario_card_v2  # noqa: E402
from helpers.seeds import PERSONA_AGES, build_seedcase_from_inputs, load_demo_cases  # noqa: E402
from helpers.theme import apply_altair_theme, inject_css  # noqa: E402
from helpers.widgets import money_input, percent_slider  # noqa: E402
from model.debt import DEBT_CATEGORIES  # noqa: E402
from model.outputs import run_and_extract  # noqa: E402
from model.tax import STATE_TAX_PRESETS  # noqa: E402
from helpers.chat_widget import render_chat_in_sidebar  # noqa: E402
from helpers.analytics import track_page_view, track_button, track_feature_toggle  # noqa: E402

# ---------- Page config ----------

st.set_page_config(
    page_title="Retirement Planner",
    layout="wide",
    initial_sidebar_state="auto",  # auto-collapses on mobile
)

# Apply custom design (CSS + unified chart theme)
inject_css()
apply_altair_theme()
track_page_view("planner")

st.title("Retirement Planner")
st.caption(
    "Edit any input in the sidebar. Everything updates instantly and auto-saves to this browser."
)

# ---------- Welcome / first-time orientation ----------

with st.expander("New here? Read this first (30 seconds)", expanded=False):
    st.markdown(
        """
        **What this is:** a retirement planner that shows, year by year, whether
        your savings actually reach retirement and then survive it. Edit any
        number on the left, the projection updates immediately.

        **How to use it:**
        1. Pick a template in the sidebar (Alex, Jordan, or Sam) or start editing
           your own numbers directly. Everything auto-saves to this browser.
        2. Watch the scenario card at the top: it shows your retirement age, final
           net worth, and maximum sustainable spending.
        3. Check **Top levers** below for three realistic changes that would move
           the needle on your plan.
        4. When ready, visit **Monte Carlo** (sidebar) to see how the plan holds
           up through actual historical sequences (Great Depression, 1970s
           stagflation, 2008 crash).

        **What makes this different from a retirement calculator:**
        - Models **taxes**, **Social Security**, **Roth vs Traditional split**,
          **RMDs**, **healthcare inflation**, **property** with mortgage
          amortization, and a **glide-path allocation** that shifts bonds as
          you age.
        - **Historical backtest** (not just one deterministic path): runs your
          plan through every start year 1928 to 2024.
        - **Dollar-exact parity** with a spreadsheet it replicates, plus 79
          unit tests and 23 scenario regressions.
        - Every number here is **hypothetical**. Type over any field in the
          sidebar, or load a persona to explore.

        **Not financial advice.** See the Methodology page for the full
        disclaimer.
        """
    )

# ---------- Load personas ----------

demo_cases = load_demo_cases()
demo_case_map = {c["id"]: c for c in demo_cases}

# ---------- Scenario state management ----------
#
# IMPORTANT: Streamlit widgets with `key=` read from st.session_state[key] on
# every rerun, IGNORING the `value` parameter after first render. This means:
#   - The `inputs` dict is populated FROM widget return values (widgets are the
#     source of truth for the current page render).
#   - To programmatically change a widget's value, you MUST set
#     st.session_state[widget_key] — setting only the inputs dict does nothing.
#   - When replacing the entire inputs dict (template load, reset), you must
#     ALSO clear all widget keys so they re-initialize from the new dict values.

# All widget keys used in the sidebar. When we programmatically replace the
# inputs dict (template load, reset), we delete these so widgets re-read
# their `value` parameter on the next render.
_WIDGET_KEYS = [
    "retirement_target", "salary_y1", "salary_y2", "salary_y3", "salary_y4",
    "salary_growth", "k401_contrib", "roth_pct", "non_housing", "rent",
    "k401_start", "roth401k_start", "invest_start", "cash_start", "crypto_start",
    "alloc_strategy", "fixed_stock", "max_bonds",
    "stock_ret", "bond_ret", "crypto_ret", "cash_ret", "inflation",
    "ss_elig", "ss_age", "ss_benefit",
    "other1_enabled", "other1_label", "other1_monthly", "other1_start", "other1_end",
    "other1_cola", "other1_tax",
    "other2_enabled", "other2_label", "other2_monthly", "other2_start", "other2_end",
    "other2_cola", "other2_tax",
    "custom1_enabled", "custom2_enabled", "custom3_enabled",
    "buy_prop", "prop_year", "prop_cost",
    "prop_tax_rate", "home_ins_rate", "maint_rate", "monthly_hoa", "prop_appr",
    "use_mortgage", "down_pct", "mtg_rate", "mtg_term",
    "closing_cost", "selling_cost",
    "vehicle_incl", "vehicle_cost", "vehicle_interval",
    "hc_enabled", "hc_pre", "hc_med", "hc_age", "hc_inf",
    "ltc_enabled", "ltc_monthly", "ltc_age", "ltc_dur",
    "rc_enabled", "rc_amt", "rc_start", "rc_end",
]


def _clear_widget_keys():
    """Delete all widget keys from session state so widgets re-initialize
    from their `value` parameter on the next render."""
    for k in _WIDGET_KEYS:
        st.session_state.pop(k, None)
    # Also clear derived state
    st.session_state.pop("_target_finder_result", None)

# One-time init: restore from localStorage or fall back to default template
if "inputs" not in st.session_state:
    # Try to restore from browser localStorage
    ls_data = load_from_localstorage()
    if ls_data and ls_data.get("inputs"):
        st.session_state.inputs = dict(ls_data["inputs"])
        st.session_state.current_age = int(ls_data.get("current_age", 35))
        st.session_state.scenario_name = ls_data.get("name", "My scenario")
        st.session_state._just_restored = True
    else:
        # Default to Alex template on first-ever load
        default_case = demo_case_map["alex-mid-career"]
        st.session_state.inputs = dict(default_case["inputs"])
        st.session_state.current_age = PERSONA_AGES["alex-mid-career"]
        st.session_state.scenario_name = "My scenario"

# Handle template-load button clicks (fire from buttons below)
if "_load_template" in st.session_state:
    template_id = st.session_state.pop("_load_template")
    template = demo_case_map.get(template_id)
    if template:
        track_button("template_loaded", template=template_id)
        st.session_state.inputs = dict(template["inputs"])
        st.session_state.current_age = PERSONA_AGES.get(template_id, 35)
        st.session_state.scenario_name = f"From {template['name'].split(' — ')[0]}"
        _clear_widget_keys()
        st.rerun()

# Handle clear-saved-data
if "_clear_saved" in st.session_state:
    st.session_state.pop("_clear_saved")
    clear_localstorage()
    # Reset to default
    default_case = demo_case_map["alex-mid-career"]
    st.session_state.inputs = dict(default_case["inputs"])
    st.session_state.current_age = PERSONA_AGES["alex-mid-career"]
    st.session_state.scenario_name = "My scenario"
    _clear_widget_keys()
    st.success("Cleared saved data. Starting fresh with Alex defaults.")
    st.rerun()

inputs = st.session_state.inputs

# (safe-target finder runs inline at the button location in the sidebar)

# ---------- One-time migration: legacy in_MonthlyOwnershipCost → components ----------
# Users who saved scenarios before the component restructure have the old single
# field. Reverse-engineer it into tax/ins/maint/HOA using national-avg ratios
# (tax 1.1%, ins 0.4%, maint 1.0%, HOA absorbs the rest).
if "in_MonthlyOwnershipCost" in inputs and "in_PropertyTaxRate" not in inputs:
    _legacy_monthly = float(inputs["in_MonthlyOwnershipCost"])
    _prop_cost = float(inputs.get("in_PropertyCost", 350_000))
    # Seed components from national avg
    inputs["in_PropertyTaxRate"] = 0.011
    inputs["in_HomeInsuranceRate"] = 0.004
    inputs["in_MaintenanceRate"] = 0.010
    # HOA absorbs the remainder (can be $0 or negative if legacy value was low)
    _pct_components = _prop_cost * (0.011 + 0.004 + 0.010) / 12
    _implied_hoa = max(0, _legacy_monthly - _pct_components)
    inputs["in_MonthlyHOA"] = round(_implied_hoa / 25) * 25  # round to $25
    del inputs["in_MonthlyOwnershipCost"]
    st.session_state._migrated_ownership = _legacy_monthly

if st.session_state.pop("_migrated_ownership", None) is not None:
    st.toast(
        "Housing cost inputs have been restructured into components "
        "(tax, insurance, maintenance, HOA). Please verify the values "
        "in Primary Residence match your market.",
        icon="🏠",
    )

# ---------- Sidebar: Chat + scenario name + templates ----------

if st.session_state.pop("_just_restored", False):
    st.sidebar.success("Restored your last session.")

# Chat assistant at top of sidebar
render_chat_in_sidebar()

# Scenario name — styled as prominent editable header
st.sidebar.markdown(
    '<p style="font-size: 0.7rem; font-weight: 600; color: #64748b; '
    'text-transform: uppercase; letter-spacing: 0.05em; margin: 0.5rem 0 0.25rem 0;">'
    'Scenario name</p>',
    unsafe_allow_html=True,
)
st.session_state.scenario_name = st.sidebar.text_input(
    "Scenario name",
    value=st.session_state.scenario_name,
    key="scenario_name_input",
    label_visibility="collapsed",
    placeholder="My plan",
    help="A label for your current scenario. Auto-saved as you edit.",
)
st.sidebar.caption("Auto-saved to this browser on every change.")

# Template loaders
with st.sidebar.expander("Load template", expanded=False):
    st.caption("Start fresh from a hypothetical persona. Overwrites your current inputs.")
    for c in demo_cases:
        cols = st.columns([3, 1])
        cols[0].markdown(f"**{c['name']}**  \n_{c.get('tagline', '')}_")
        if cols[1].button("Load", key=f"load_{c['id']}"):
            st.session_state._load_template = c["id"]
            st.rerun()

# ---------- Sidebar input form ----------

st.sidebar.markdown(
    '<p style="font-size: 0.7rem; font-weight: 600; color: #64748b; '
    'text-transform: uppercase; letter-spacing: 0.05em; margin: 1rem 0 0.25rem 0;">'
    'Essentials</p>',
    unsafe_allow_html=True,
)

with st.sidebar.expander("Personal", expanded=True):
    st.session_state.current_age = st.number_input(
        "Current age", min_value=18, max_value=80,
        value=int(st.session_state.current_age), step=1,
    )
    inputs["in_EndAge"] = st.number_input(
        "End-of-plan age", min_value=st.session_state.current_age + 5, max_value=110,
        value=int(inputs["in_EndAge"]), step=1,
    )
    inputs["in_RetirementTarget"] = money_input(
        "Retirement net-worth target",
        inputs["in_RetirementTarget"],
        min_value=100_000, max_value=10_000_000, step=50_000,
        key="retirement_target",
        help=(
            "The LIQUID portfolio value that triggers retirement. Home equity and "
            "illiquid custom assets do NOT count (you can't pay groceries with a house). "
            "Rule of thumb (4% rule): target = 25x your annual spending."
        ),
    )
    def _run_target_finder():
        """on_click callback — runs BEFORE the script body on the next rerun.
        Finds the earliest safe retirement by checking BOTH deterministic
        survival and historical Monte Carlo success."""
        track_button("find_safe_target_sidebar")
        result = find_safe_target(
            st.session_state.inputs, st.session_state.current_age,
        )
        if result.found:
            st.session_state.inputs["in_RetirementTarget"] = result.target
            st.session_state["retirement_target"] = float(result.target)
        st.session_state["_target_finder_result"] = {
            "found": result.found,
            "target": result.target,
            "age": result.retirement_age,
            "mc_rate": result.mc_success_rate,
            "det_survives": result.det_survives,
            "note": result.note,
        }

    st.button(
        "Find my earliest safe retirement",
        use_container_width=True,
        on_click=_run_target_finder,
        help=(
            "Finds the earliest age you can retire where your money lasts "
            "to end-of-plan. Checks both your specific plan (healthcare, "
            "LTC, taxes) AND 95%+ of historical market conditions."
        ),
    )

    # Show persistent result
    _tfr = st.session_state.get("_target_finder_result")
    if _tfr and _tfr.get("found") and _tfr.get("target"):
        if inputs["in_RetirementTarget"] == _tfr["target"]:
            st.success(
                f"Earliest safe retirement: **age {_tfr['age']}** "
                f"(target ${_tfr['target']/1_000_000:.2f}M, "
                f"{_tfr['mc_rate']:.0%} historical success, "
                f"portfolio lasts to end of plan)"
            )
        else:
            del st.session_state["_target_finder_result"]
    elif _tfr and not _tfr.get("found"):
        st.warning(f"{_tfr.get('note', 'No safe retirement found in search range.')}")

    # Show Bengen multiplier relative to current spending
    _annual_spend_now = (
        inputs.get("in_MonthlyNonHousing", 0) + inputs.get("in_MonthlyRent", 0)
    ) * 12
    if _annual_spend_now > 0:
        _multiplier = inputs["in_RetirementTarget"] / _annual_spend_now
        if _multiplier < 25:
            _tone = "tight: below 25x is the recommended minimum"
            _color = "#dc2626"
        elif _multiplier < 30:
            _tone = "safe per 4% rule"
            _color = "#16a34a"
        else:
            _tone = "conservative (only withdrawing 3.3%/yr)"
            _color = "#2563eb"
        st.caption(
            f"Target = **{_multiplier:.0f}x** your current spending "
            f"(${_annual_spend_now/1_000:.0f}K/yr). "
            f":grey[{_tone}]"
        )

with st.sidebar.expander("Income & Savings"):
    inputs["in_Year1Salary"] = money_input(
        "2025 salary",
        inputs.get("in_Year1Salary", inputs.get("in_Salary", 0)),
        max_value=1_000_000, step=1_000, key="salary_y1",
    )
    inputs["in_Year2Salary"] = money_input(
        "2026 salary",
        inputs.get("in_Year2Salary", inputs.get("in_Salary", 0)),
        max_value=1_000_000, step=1_000, key="salary_y2",
        help="Near-term salaries can diverge from long-term growth — e.g., a raise, job change, or gap year."
    )
    inputs["in_Year3Salary"] = money_input(
        "2027 salary", inputs.get("in_Year3Salary", inputs.get("in_Salary", 0)),
        max_value=1_000_000, step=1_000, key="salary_y3",
    )
    inputs["in_Year4Salary"] = money_input(
        "2028 salary", inputs.get("in_Year4Salary", inputs.get("in_Salary", 0)),
        max_value=1_000_000, step=1_000, key="salary_y4",
    )
    inputs["in_SalaryGrowth"] = percent_slider(
        "Salary growth (2029+)", inputs["in_SalaryGrowth"],
        min_pct=0.0, max_pct=10.0, step_pct=0.1, key="salary_growth",
    )
    inputs["in_401kContrib"] = money_input(
        "Annual 401(k) contribution", inputs["in_401kContrib"],
        max_value=50_000, step=500, key="k401_contrib",
    )
    inputs["in_RothContribPct"] = percent_slider(
        "Roth share of 401(k) contribution",
        inputs.get("in_RothContribPct", 0.0),
        min_pct=0.0, max_pct=100.0, step_pct=5.0, key="roth_pct",
        help=(
            "Split your 401(k) contribution between Traditional (pre-tax) and "
            "Roth (after-tax). 0% = all Traditional. 100% = all Roth. "
            "See Glossary for Traditional vs Roth explanation."
        ),
    )
    st.caption(
        "0% = Traditional (deduction today, tax withdrawals later). "
        "100% = Roth (no deduction today, tax-free withdrawals). "
        "[Glossary](/Glossary)"
    )

with st.sidebar.expander("Monthly Expenses"):
    inputs["in_MonthlyNonHousing"] = money_input(
        "Non-housing ($/mo)", inputs["in_MonthlyNonHousing"],
        max_value=20_000, step=100, key="non_housing",
    )
    inputs["in_MonthlyRent"] = money_input(
        "Housing / rent ($/mo)", inputs["in_MonthlyRent"],
        max_value=20_000, step=100, key="rent",
    )

with st.sidebar.expander("Starting Balances"):
    inputs["in_401kStart"] = money_input(
        "Traditional 401(k)", inputs["in_401kStart"], max_value=10_000_000, step=5_000, key="k401_start",
    )
    inputs["in_Roth401kStart"] = money_input(
        "Roth 401(k)", inputs.get("in_Roth401kStart", 0), max_value=10_000_000, step=5_000, key="roth401k_start",
    )
    inputs["in_InvestStart"] = money_input(
        "Investment account", inputs["in_InvestStart"], max_value=10_000_000, step=5_000, key="invest_start",
    )
    inputs["in_CashStart"] = money_input(
        "Cash", inputs["in_CashStart"], max_value=1_000_000, step=1_000, key="cash_start",
    )
    inputs["in_CryptoStart"] = money_input(
        "Crypto", inputs["in_CryptoStart"], max_value=1_000_000, step=1_000, key="crypto_start",
    )

st.sidebar.markdown(
    '<p style="font-size: 0.7rem; font-weight: 600; color: #64748b; '
    'text-transform: uppercase; letter-spacing: 0.05em; margin: 1rem 0 0.25rem 0;">'
    'Assumptions</p>',
    unsafe_allow_html=True,
)

with st.sidebar.expander("Allocation strategy"):
    st.caption(
        "How your portfolio splits between stocks (growth) and bonds (safety). "
        "[Glossary](/Glossary) explains Glide Path vs Fixed Mix."
    )
    use_fixed = st.radio(
        "Strategy",
        options=["Age-based glide path", "Fixed mix"],
        index=0 if inputs.get("in_UseFixedMix", "No") == "No" else 1,
        key="alloc_strategy",
        help=(
            "Glide path: bonds share automatically rises 2%/yr starting at age 20, "
            "capped at 'Max bonds'. Fixed mix: stocks stay at the chosen % your entire plan."
        ),
    )
    inputs["in_UseFixedMix"] = "Yes" if use_fixed == "Fixed mix" else "No"
    if inputs["in_UseFixedMix"] == "Yes":
        inputs["in_FixedStockPct"] = percent_slider(
            "Stocks % (excludes crypto)",
            inputs.get("in_FixedStockPct", 0.60),
            min_pct=0.0, max_pct=100.0, step_pct=5.0, key="fixed_stock",
        )
    else:
        inputs["in_MaxBonds"] = percent_slider(
            "Max bonds %", inputs.get("in_MaxBonds", 0.40),
            min_pct=20.0, max_pct=80.0, step_pct=5.0, key="max_bonds",
        )

with st.sidebar.expander("Returns & Inflation"):
    inputs["in_StockReturn"] = percent_slider(
        "Stock return (before inflation)", inputs["in_StockReturn"],
        min_pct=0.0, max_pct=15.0, step_pct=0.1, key="stock_ret",
    )
    inputs["in_BondReturn"] = percent_slider(
        "Bond return (before inflation)", inputs["in_BondReturn"],
        min_pct=0.0, max_pct=10.0, step_pct=0.1, key="bond_ret",
    )
    inputs["in_CryptoReturn"] = percent_slider(
        "Crypto return (before inflation)", inputs["in_CryptoReturn"],
        min_pct=0.0, max_pct=20.0, step_pct=0.5, key="crypto_ret",
    )
    inputs["in_CashReturn"] = percent_slider(
        "Cash return (before inflation)", inputs["in_CashReturn"],
        min_pct=0.0, max_pct=8.0, step_pct=0.1, key="cash_ret",
    )
    inputs["in_Inflation"] = percent_slider(
        "Inflation", inputs["in_Inflation"],
        min_pct=0.0, max_pct=8.0, step_pct=0.1, key="inflation",
    )

with st.sidebar.expander("Tax filing"):
    filing = st.radio(
        "Filing status",
        options=["Single", "Married filing jointly"],
        index=0 if inputs.get("in_FilingStatus", "single") == "single" else 1,
        key="filing_status",
        help="Married filing jointly has wider tax brackets and a higher standard deduction.",
    )
    inputs["in_FilingStatus"] = "married_filing_jointly" if filing == "Married filing jointly" else "single"
    preset_label = st.selectbox(
        "State income tax",
        options=list(STATE_TAX_PRESETS.keys()) + ["Custom"],
        index=0,
        key="state_tax_preset",
        help="Flat-rate approximation of state income tax. Good enough for planning.",
    )
    if preset_label == "Custom":
        inputs["in_StateTaxRate"] = percent_slider(
            "Custom state tax rate",
            inputs.get("in_StateTaxRate", 0.05),
            min_pct=0.0, max_pct=15.0, step_pct=0.1, key="custom_state_rate",
        )
    else:
        inputs["in_StateTaxRate"] = STATE_TAX_PRESETS[preset_label]
    inputs["in_StateTaxLabel"] = preset_label

st.sidebar.markdown(
    '<p style="font-size: 0.7rem; font-weight: 600; color: #64748b; '
    'text-transform: uppercase; letter-spacing: 0.05em; margin: 1rem 0 0.25rem 0;">'
    'Income sources</p>',
    unsafe_allow_html=True,
)

with st.sidebar.expander("Social Security"):
    ss_eligible = st.checkbox("Eligible for Social Security", value=(inputs["in_SSEligible"] == "Yes"), key="ss_elig")
    inputs["in_SSEligible"] = "Yes" if ss_eligible else "No"
    if ss_eligible:
        inputs["in_SSAge"] = st.number_input(
            "Age to start Social Security", min_value=62, max_value=70,
            value=int(inputs["in_SSAge"]), step=1, key="ss_age",
        )
        inputs["in_SSBenefit"] = money_input(
            "Monthly Social Security benefit (today's $)", inputs["in_SSBenefit"],
            max_value=5_000, step=50, key="ss_benefit",
        )

with st.sidebar.expander("Spouse / Partner"):
    st.caption(
        "Model a second earner. Adds their salary, Social Security, and 401(k) "
        "to the household. Make sure to set filing status to 'Married filing "
        "jointly' above for the correct tax brackets."
    )
    spouse_on = st.checkbox(
        "Include spouse/partner",
        value=(inputs.get("in_SpouseEnabled", "No") == "Yes"),
        key="spouse_enabled",
    )
    inputs["in_SpouseEnabled"] = "Yes" if spouse_on else "No"
    if spouse_on:
        inputs["in_SpouseAge"] = st.number_input(
            "Spouse's current age", min_value=18, max_value=80,
            value=int(inputs.get("in_SpouseAge", 35)), step=1, key="spouse_age",
        )
        inputs["in_SpouseSalary"] = money_input(
            "Spouse's annual salary",
            inputs.get("in_SpouseSalary", 80000),
            max_value=1_000_000, step=1_000, key="spouse_salary",
        )
        inputs["in_SpouseSalaryGrowth"] = percent_slider(
            "Spouse salary growth",
            inputs.get("in_SpouseSalaryGrowth", 0.03),
            min_pct=0.0, max_pct=10.0, step_pct=0.1, key="spouse_sal_growth",
        )
        st.markdown("**Spouse's retirement accounts**")
        inputs["in_Spouse401kStart"] = money_input(
            "Spouse 401(k) balance",
            inputs.get("in_Spouse401kStart", 0),
            max_value=5_000_000, step=5_000, key="spouse_k401_start",
        )
        inputs["in_Spouse401kContrib"] = money_input(
            "Spouse annual 401(k) contribution",
            inputs.get("in_Spouse401kContrib", 0),
            max_value=50_000, step=500, key="spouse_k401_contrib",
        )
        st.markdown("**Spouse's Social Security**")
        inputs["in_SpouseSSAge"] = st.number_input(
            "Spouse's Social Security claim age", min_value=62, max_value=70,
            value=int(inputs.get("in_SpouseSSAge", 67)), step=1, key="spouse_ss_age",
        )
        inputs["in_SpouseSSBenefit"] = money_input(
            "Spouse monthly Social Security (today's $)",
            inputs.get("in_SpouseSSBenefit", 2000),
            max_value=5_000, step=50, key="spouse_ss_benefit",
        )
        with st.expander("Survivor scenario (optional)"):
            st.caption(
                "If one spouse dies, expenses drop (one fewer person) and the "
                "surviving spouse takes the higher of the two Social Security benefits."
            )
            model_death = st.checkbox(
                "Model spouse passing away",
                value=bool(inputs.get("in_SpouseDeathAge")),
                key="spouse_death_toggle",
            )
            if model_death:
                inputs["in_SpouseDeathAge"] = st.number_input(
                    "Spouse's age at death",
                    min_value=int(inputs.get("in_SpouseAge", 35)) + 1,
                    max_value=100,
                    value=int(inputs.get("in_SpouseDeathAge", 80)),
                    step=1, key="spouse_death_age",
                )
                inputs["in_SpouseExpenseReduction"] = percent_slider(
                    "Expense reduction after death",
                    inputs.get("in_SpouseExpenseReduction", 0.30),
                    min_pct=0.0, max_pct=50.0, step_pct=5.0, key="spouse_exp_red",
                    help="How much household expenses drop when one spouse passes. 30% is typical.",
                )
            else:
                inputs.pop("in_SpouseDeathAge", None)

with st.sidebar.expander("Self-employment income"):
    st.caption(
        "Side business, freelance, or full-time self-employment. Runs alongside "
        "your W-2 salary (or replaces it if salary is $0). Includes self-employment "
        "tax (Social Security + Medicare) and SEP-IRA retirement contributions."
    )
    se_on = st.checkbox(
        "Include self-employment income",
        value=(inputs.get("in_SEEnabled", "No") == "Yes"),
        key="se_enabled",
    )
    inputs["in_SEEnabled"] = "Yes" if se_on else "No"
    if se_on:
        inputs["in_SEAnnualIncome"] = money_input(
            "Net self-employment income (today's $)",
            inputs.get("in_SEAnnualIncome", 50000),
            max_value=1_000_000, step=1_000, key="se_income",
            help="Your net profit after business expenses, before taxes.",
        )
        inputs["in_SEGrowthRate"] = percent_slider(
            "Annual growth rate",
            inputs.get("in_SEGrowthRate", 0.03),
            min_pct=0.0, max_pct=15.0, step_pct=0.5, key="se_growth",
        )
        c_sy, c_ey = st.columns(2)
        inputs["in_SEStartYear"] = c_sy.number_input(
            "Start year", min_value=2025, max_value=2080,
            value=int(inputs.get("in_SEStartYear", 2025)), step=1, key="se_start",
        )
        inputs["in_SEEndYear"] = c_ey.number_input(
            "End year", min_value=2025, max_value=2080,
            value=int(inputs.get("in_SEEndYear", 2060)), step=1, key="se_end",
        )
        st.markdown("**SEP-IRA contributions**")
        st.caption(
            "A SEP-IRA lets self-employed people save up to 25% of net income "
            "for retirement (pre-tax, same rules as a Traditional 401k)."
        )
        inputs["in_SEPIRAPct"] = percent_slider(
            "SEP-IRA contribution (%)",
            inputs.get("in_SEPIRAPct", 0.25),
            min_pct=0.0, max_pct=25.0, step_pct=1.0, key="sep_pct",
        )
        inputs["in_SEQBIEligible"] = "Yes" if st.checkbox(
            "Eligible for 20% business income deduction",
            value=(inputs.get("in_SEQBIEligible", "Yes") == "Yes"),
            key="qbi_elig",
            help="Most self-employed people qualify for a 20% deduction on qualified "
                 "business income (QBI). Reduces your taxable income.",
        ) else "No"
        # Live preview
        se_yr1 = float(inputs.get("in_SEAnnualIncome", 0))
        if se_yr1 > 0:
            se_tax_yr1 = se_yr1 * 0.153 if se_yr1 <= 168600 else 168600 * 0.153 + (se_yr1 - 168600) * 0.029
            sep_yr1 = min(se_yr1 * float(inputs.get("in_SEPIRAPct", 0.25)), 69000)
            st.markdown(
                f'<div style="background: #f0f9ff; border-left: 3px solid #2563eb; '
                f'padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.85rem; margin: 0.5rem 0;">'
                f'Year 1: SE tax <strong>${se_tax_yr1:,.0f}</strong>, '
                f'SEP-IRA <strong>${sep_yr1:,.0f}</strong></div>',
                unsafe_allow_html=True,
            )

with st.sidebar.expander("Other Income Streams", expanded=False):
    st.caption("Add custom income like rental, pension, alimony, side business, etc.")

    st.markdown("**Stream 1**")
    other1_on = st.checkbox(
        "Enable",
        value=(inputs.get("in_Other1Enabled", "No") == "Yes"),
        key="other1_enabled",
    )
    inputs["in_Other1Enabled"] = "Yes" if other1_on else "No"
    if other1_on:
        inputs["in_Other1Label"] = st.text_input(
            "Label", value=inputs.get("in_Other1Label", "Rental income"),
            key="other1_label",
        )
        inputs["in_Other1Monthly"] = money_input(
            "Monthly (today's $)", inputs.get("in_Other1Monthly", 1000),
            max_value=50_000, step=100, key="other1_monthly",
        )
        c1, c2 = st.columns(2)
        inputs["in_Other1StartYear"] = c1.number_input(
            "Start year", min_value=2025, max_value=2100,
            value=int(inputs.get("in_Other1StartYear", 2030)), step=1, key="other1_start",
        )
        inputs["in_Other1EndYear"] = c2.number_input(
            "End year", min_value=2025, max_value=2100,
            value=int(inputs.get("in_Other1EndYear", 2090)), step=1, key="other1_end",
        )
        inputs["in_Other1Cola"] = percent_slider(
            "Annual cost-of-living raise (%)", inputs.get("in_Other1Cola", 0.02),
            min_pct=0.0, max_pct=10.0, step_pct=0.1, key="other1_cola",
        )
        taxable1 = st.checkbox(
            "Taxable", value=(inputs.get("in_Other1Taxable", "Yes") == "Yes"), key="other1_tax",
        )
        inputs["in_Other1Taxable"] = "Yes" if taxable1 else "No"

    st.markdown("**Stream 2**")
    other2_on = st.checkbox(
        "Enable", value=(inputs.get("in_Other2Enabled", "No") == "Yes"), key="other2_enabled",
    )
    inputs["in_Other2Enabled"] = "Yes" if other2_on else "No"
    if other2_on:
        inputs["in_Other2Label"] = st.text_input(
            "Label", value=inputs.get("in_Other2Label", "Pension"), key="other2_label",
        )
        inputs["in_Other2Monthly"] = money_input(
            "Monthly (today's $)", inputs.get("in_Other2Monthly", 1000),
            max_value=50_000, step=100, key="other2_monthly",
        )
        c3, c4 = st.columns(2)
        inputs["in_Other2StartYear"] = c3.number_input(
            "Start year", min_value=2025, max_value=2100,
            value=int(inputs.get("in_Other2StartYear", 2055)), step=1, key="other2_start",
        )
        inputs["in_Other2EndYear"] = c4.number_input(
            "End year", min_value=2025, max_value=2100,
            value=int(inputs.get("in_Other2EndYear", 2090)), step=1, key="other2_end",
        )
        inputs["in_Other2Cola"] = percent_slider(
            "Annual cost-of-living raise (%)", inputs.get("in_Other2Cola", 0.02),
            min_pct=0.0, max_pct=10.0, step_pct=0.1, key="other2_cola",
        )
        taxable2 = st.checkbox(
            "Taxable", value=(inputs.get("in_Other2Taxable", "Yes") == "Yes"), key="other2_tax",
        )
        inputs["in_Other2Taxable"] = "Yes" if taxable2 else "No"

with st.sidebar.expander("Custom Assets", expanded=False):
    st.caption(
        "Investments that don't fit the core stocks/bonds/cash buckets. "
        "Give each one a name that's meaningful to you. **Examples:**"
    )
    st.caption(
        "• Rental property (real estate you don't live in)  \n"
        "• REIT (real estate investment trust — publicly traded)  \n"
        "• Private equity / angel investments  \n"
        "• Business equity you own  \n"
        "• Collectibles (art, wine, watches)  \n"
        "• Treasury bonds held to maturity  \n"
        "• Precious metals"
    )
    for n in (1, 2, 3):
        st.markdown(f"**Asset {n}**")
        enabled_val = inputs.get(f"in_Custom{n}Enabled", "No") == "Yes"
        enabled_new = st.checkbox("Enable", value=enabled_val, key=f"custom{n}_enabled")
        inputs[f"in_Custom{n}Enabled"] = "Yes" if enabled_new else "No"
        if enabled_new:
            inputs[f"in_Custom{n}Name"] = st.text_input(
                "Name",
                value=inputs.get(f"in_Custom{n}Name", f"Custom Asset {n}"),
                placeholder="e.g., Rental property, Side business, Art collection",
                key=f"custom{n}_name",
                help="Anything that grows at its own rate outside the core buckets.",
            )
            inputs[f"in_Custom{n}Start"] = money_input(
                "Starting balance", inputs.get(f"in_Custom{n}Start", 10_000),
                max_value=10_000_000, step=1_000, key=f"custom{n}_start",
            )
            inputs[f"in_Custom{n}Contrib"] = money_input(
                "Annual contribution (working yrs)",
                inputs.get(f"in_Custom{n}Contrib", 0),
                max_value=500_000, step=500, key=f"custom{n}_contrib",
            )
            inputs[f"in_Custom{n}Return"] = percent_slider(
                "Annual return (nominal)",
                inputs.get(f"in_Custom{n}Return", 0.05),
                min_pct=0.0, max_pct=20.0, step_pct=0.1, key=f"custom{n}_return",
            )
            liquid_val = inputs.get(f"in_Custom{n}Liquid", "Yes") == "Yes"
            inputs[f"in_Custom{n}Liquid"] = "Yes" if st.checkbox(
                "Liquid",
                value=liquid_val,
                key=f"custom{n}_liquid",
                help=(
                    "Liquid assets can pay retirement expenses AND count toward your "
                    "retirement-target trigger. Illiquid assets (collectibles, private "
                    "equity, primary residence equity) just appreciate and add to "
                    "estate value — they won't pay bills."
                ),
            ) else "No"
            if inputs[f"in_Custom{n}Liquid"] == "Yes":
                inputs[f"in_Custom{n}DrawPriority"] = st.select_slider(
                    "Draw order during retirement",
                    options=[1, 2, 3],
                    value=int(inputs.get(f"in_Custom{n}DrawPriority", 2)),
                    format_func=lambda v: {1: "1 · Draw first", 2: "2 · Middle", 3: "3 · Draw last"}[v],
                    key=f"custom{n}_priority",
                    help="If core portfolio can't cover expenses, liquid custom assets drain in priority order.",
                )

with st.sidebar.expander("Debts & Loans", expanded=False):
    st.caption(
        "Non-mortgage debts that reduce your net worth and require monthly payments. "
        "Payments are treated as mandatory expenses — they reduce savings while working "
        "and increase withdrawals in retirement. Student loan interest is tax-deductible "
        "(up to $2,500/year)."
    )
    for n in (1, 2, 3):
        st.markdown(f"**Debt {n}**")
        debt_enabled = inputs.get(f"in_Debt{n}Enabled", "No") == "Yes"
        debt_enabled_new = st.checkbox("Enable", value=debt_enabled, key=f"debt{n}_enabled")
        inputs[f"in_Debt{n}Enabled"] = "Yes" if debt_enabled_new else "No"
        if debt_enabled_new:
            inputs[f"in_Debt{n}Label"] = st.text_input(
                "Label",
                value=inputs.get(f"in_Debt{n}Label", f"Debt {n}"),
                placeholder="e.g., Chase Visa, Honda Civic, Sallie Mae",
                key=f"debt{n}_label",
            )
            cat_list = list(DEBT_CATEGORIES)
            current_cat = inputs.get(f"in_Debt{n}Category", "Other")
            cat_idx = cat_list.index(current_cat) if current_cat in cat_list else len(cat_list) - 1
            inputs[f"in_Debt{n}Category"] = st.selectbox(
                "Category", options=cat_list, index=cat_idx, key=f"debt{n}_category",
            )
            inputs[f"in_Debt{n}Balance"] = money_input(
                "Current balance", inputs.get(f"in_Debt{n}Balance", 10000),
                max_value=500_000, step=500, key=f"debt{n}_balance",
            )
            inputs[f"in_Debt{n}Rate"] = percent_slider(
                "Interest rate (APR)",
                inputs.get(f"in_Debt{n}Rate", 0.07),
                min_pct=0.0, max_pct=30.0, step_pct=0.1, key=f"debt{n}_rate",
            )
            inputs[f"in_Debt{n}MinPayment"] = money_input(
                "Monthly minimum payment",
                inputs.get(f"in_Debt{n}MinPayment", 200),
                max_value=10_000, step=25, key=f"debt{n}_min_payment",
            )
            inputs[f"in_Debt{n}ExtraPayment"] = money_input(
                "Extra monthly payment",
                inputs.get(f"in_Debt{n}ExtraPayment", 0),
                max_value=10_000, step=25, key=f"debt{n}_extra_payment",
                help="Additional payment above the minimum, applied directly to principal.",
            )

    # Payoff strategy — show when at least one debt is enabled
    _any_debt = any(inputs.get(f"in_Debt{n}Enabled") == "Yes" for n in (1, 2, 3))
    if _any_debt:
        st.markdown("---")
        st.markdown("**Payoff Strategy**")
        st.caption(
            "**Avalanche** attacks the highest-rate debt first (saves the most interest). "
            "**Snowball** attacks the lowest-balance debt first (fastest emotional wins). "
            "When one debt is paid off, its payment cascades to the next target."
        )
        strategy_options = {"No strategy": "none", "Avalanche (highest rate first)": "avalanche", "Snowball (lowest balance first)": "snowball"}
        current_strategy = inputs.get("in_DebtPayoffStrategy", "none")
        current_label = next((k for k, v in strategy_options.items() if v == current_strategy), "No strategy")
        selected_label = st.selectbox(
            "Strategy", options=list(strategy_options.keys()),
            index=list(strategy_options.keys()).index(current_label),
            key="debt_strategy",
        )
        inputs["in_DebtPayoffStrategy"] = strategy_options[selected_label]

        if inputs["in_DebtPayoffStrategy"] != "none":
            inputs["in_DebtExtraBudget"] = money_input(
                "Extra monthly budget for debt payoff",
                inputs.get("in_DebtExtraBudget", 200),
                max_value=10_000, step=25, key="debt_extra_budget",
                help="Monthly amount above all minimums, concentrated on the priority target. "
                     "When that debt pays off, this + its freed-up minimum roll to the next.",
            )
        else:
            inputs["in_DebtExtraBudget"] = 0

st.sidebar.markdown(
    '<p style="font-size: 0.7rem; font-weight: 600; color: #64748b; '
    'text-transform: uppercase; letter-spacing: 0.05em; margin: 1rem 0 0.25rem 0;">'
    'Life events & Assets</p>',
    unsafe_allow_html=True,
)

with st.sidebar.expander("Primary Residence"):
    st.caption(
        "Model a home you live in. Replaces rent with ownership costs after "
        "purchase; equity appreciates into net worth. "
        "**Investment/rental property?** Use a Custom Asset (appreciation) "
        "plus an Other Income stream (rental income) instead."
    )
    buy_prop = st.checkbox(
        "Include home purchase",
        value=(inputs.get("in_BuyProperty", "No") == "Yes"),
        key="buy_prop",
    )
    inputs["in_BuyProperty"] = "Yes" if buy_prop else "No"
    if buy_prop:
        c_py, c_pc = st.columns(2)
        inputs["in_PropertyYear"] = c_py.number_input(
            "Purchase year", min_value=2025, max_value=2080,
            value=int(inputs.get("in_PropertyYear", 2035)), step=1, key="prop_year",
        )
        inputs["in_PropertyCost"] = money_input(
            "Property cost", inputs.get("in_PropertyCost", 350000),
            min_value=50_000, max_value=10_000_000, step=10_000, key="prop_cost",
        )
        # Component-based ownership cost (property tax + insurance + maintenance + HOA)
        # — the user provides rates they can actually look up for their market.
        st.markdown("**Ongoing ownership cost**")
        st.caption(
            "These are things you CAN look up for your market. Rough ranges below."
        )
        inputs["in_PropertyTaxRate"] = percent_slider(
            "Property tax rate (% of value/yr)",
            inputs.get("in_PropertyTaxRate", 0.011),
            min_pct=0.0, max_pct=4.0, step_pct=0.05, key="prop_tax_rate",
            help=(
                "Look up your state. Low: HI 0.3%, CA 0.75%, FL 0.9%. "
                "Medium: national average 1.1%. High: TX 1.8%, NJ 2.2%, "
                "IL 2.3%. City taxes can add more."
            ),
        )
        inputs["in_HomeInsuranceRate"] = percent_slider(
            "Home insurance (% of value/yr)",
            inputs.get("in_HomeInsuranceRate", 0.004),
            min_pct=0.0, max_pct=2.0, step_pct=0.05, key="home_ins_rate",
            help=(
                "National average ~0.4% of home value/yr. Higher in coastal "
                "FL/LA/TX (hurricane) or wildfire zones (CA)."
            ),
        )
        inputs["in_MaintenanceRate"] = percent_slider(
            "Maintenance (% of value/yr)",
            inputs.get("in_MaintenanceRate", 0.010),
            min_pct=0.0, max_pct=3.0, step_pct=0.05, key="maint_rate",
            help=(
                "Industry rule of thumb: 1% of home value/yr for upkeep, repairs, "
                "and replacement reserves. Older homes run higher."
            ),
        )
        inputs["in_MonthlyHOA"] = money_input(
            "Homeowners association fees ($/mo)",
            inputs.get("in_MonthlyHOA", 0),
            min_value=0, max_value=5000, step=25, key="monthly_hoa",
            help="Monthly HOA (homeowners association) or condo association dues. $0 if none.",
        )
        # Strip legacy single-field if it's hanging around in state
        if "in_MonthlyOwnershipCost" in inputs:
            del inputs["in_MonthlyOwnershipCost"]
        # Compute and display the rolled-up monthly
        _prop_cost = float(inputs.get("in_PropertyCost", 350000))
        _tax = _prop_cost * inputs["in_PropertyTaxRate"]
        _ins = _prop_cost * inputs["in_HomeInsuranceRate"]
        _maint = _prop_cost * inputs["in_MaintenanceRate"]
        _total_monthly = (_tax + _ins + _maint) / 12 + inputs["in_MonthlyHOA"]
        _total_pct = (_total_monthly * 12 / _prop_cost * 100) if _prop_cost > 0 else 0
        st.markdown(
            f'<div style="background: #f0f9ff; border-left: 3px solid #2563eb; '
            f'padding: 0.5rem 0.75rem; border-radius: 4px; margin: 0.5rem 0; font-size: 0.85rem;">'
            f'<strong>Monthly carrying cost: ${_total_monthly:,.0f}/mo</strong> '
            f'<span style="color: #64748b;">({_total_pct:.1f}% of home value/yr)</span><br>'
            f'<span style="color: #64748b; font-size: 0.8rem;">'
            f'Tax ${_tax/12:,.0f} + Ins ${_ins/12:,.0f} + Maint ${_maint/12:,.0f} '
            f'+ HOA ${inputs["in_MonthlyHOA"]:,.0f}'
            f'</span></div>',
            unsafe_allow_html=True,
        )
        inputs["in_PropertyAppreciation"] = percent_slider(
            "Annual appreciation", inputs.get("in_PropertyAppreciation", 0.04),
            min_pct=0.0, max_pct=8.0, step_pct=0.1, key="prop_appr",
            help=(
                "Long-run US home price appreciation has been ~3.5-4.5% nominal "
                "(Case-Shiller 1987-2024). Pick 3% for conservative, 4% for average, "
                "5%+ for high-growth markets."
            ),
        )
        st.markdown("**Financing**")
        use_mortgage = st.checkbox(
            "Finance with mortgage",
            value=(inputs.get("in_MortgageYN", "No") == "Yes"),
            key="use_mortgage",
        )
        inputs["in_MortgageYN"] = "Yes" if use_mortgage else "No"
        if use_mortgage:
            inputs["in_DownPaymentPct"] = percent_slider(
                "Down payment", inputs.get("in_DownPaymentPct", 0.20),
                min_pct=5.0, max_pct=50.0, step_pct=1.0, key="down_pct",
            )
            inputs["in_MortgageRate"] = percent_slider(
                "Mortgage interest rate (%)", inputs.get("in_MortgageRate", 0.065),
                min_pct=2.0, max_pct=12.0, step_pct=0.1, key="mtg_rate",
                help="The annual interest rate on your mortgage. Use the rate from your loan offer.",
            )
            inputs["in_MortgageTerm"] = st.selectbox(
                "Mortgage term (years)", options=[15, 20, 30],
                index=[15, 20, 30].index(int(inputs.get("in_MortgageTerm", 30))),
                key="mtg_term",
            )
        st.markdown("**Transaction costs**")
        inputs["in_ClosingCostPct"] = percent_slider(
            "Buyer closing costs (% of price)",
            inputs.get("in_ClosingCostPct", 0.025),
            min_pct=0.0, max_pct=6.0, step_pct=0.1, key="closing_cost",
            help=(
                "Title insurance, inspection, origination fees, escrow, etc. "
                "National average 2-3% for buyers. Drains from your portfolio "
                "at purchase."
            ),
        )
        inputs["in_SellingCostPct"] = percent_slider(
            "Selling costs (% of future value)",
            inputs.get("in_SellingCostPct", 0.06),
            min_pct=0.0, max_pct=10.0, step_pct=0.5, key="selling_cost",
            help=(
                "Agent commissions (5-6%) + seller closing costs (1-2%) if you "
                "ever sell. Reduces the reported home equity to what you'd "
                "actually receive. The model doesn't trigger a sale, but "
                "it honestly reports what your equity is worth net of costs."
            ),
        )

with st.sidebar.expander("Vehicle"):
    inputs["in_IncludeVehicle"] = "Yes" if st.checkbox(
        "Include vehicle replacement costs",
        value=(inputs.get("in_IncludeVehicle", "Yes") == "Yes"), key="vehicle_incl",
    ) else "No"
    if inputs["in_IncludeVehicle"] == "Yes":
        inputs["in_VehicleCost"] = money_input(
            "Vehicle cost (today's $)", inputs["in_VehicleCost"],
            max_value=200_000, step=1_000, key="vehicle_cost",
        )
        inputs["in_VehicleInterval"] = st.number_input(
            "Replacement interval (years)", min_value=4, max_value=25,
            value=int(inputs["in_VehicleInterval"]), step=1, key="vehicle_interval",
        )

with st.sidebar.expander("Healthcare"):
    st.caption(
        "Monthly costs for health insurance **premiums + expected out-of-pocket** "
        "(deductibles, copays, coinsurance). All numbers in today's dollars; "
        "inflates ~4%/yr — faster than general prices."
    )
    hc_on = st.checkbox(
        "Model healthcare costs separately",
        value=(inputs.get("in_HealthcareEnabled", "No") == "Yes"),
        key="hc_enabled",
    )
    inputs["in_HealthcareEnabled"] = "Yes" if hc_on else "No"
    if hc_on:
        # Live preview — year-1 cost at current age
        hc_monthly_yr1 = float(inputs.get("in_HealthcarePreMedicare", 1000))
        hc_yr1 = hc_monthly_yr1 * 12
        st.markdown(
            f'<div style="background: #fef3c7; padding: 0.5rem 0.75rem; '
            f'border-radius: 4px; font-size: 0.85rem; color: #92400e; margin: 0.25rem 0;">'
            f'Adds <strong>${hc_yr1:,.0f}/yr</strong> (≈${hc_monthly_yr1:,.0f}/mo) in year 1, '
            f'rising ~4%/yr.</div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Before age 65 (pre-Medicare)**")
        st.caption(
            "Rough ranges (per person, monthly):  \n"
            "• Employer plan: **$100-400/mo** (employee share of premium)  \n"
            "• Marketplace with subsidy (healthcare.gov): **$200-600/mo**  \n"
            "• Marketplace without subsidy: **$600-1,200/mo** (premium alone)  \n"
            "• Plus out-of-pocket: ~$100-500/mo expected"
        )
        inputs["in_HealthcarePreMedicare"] = money_input(
            "Monthly cost before age 65",
            inputs.get("in_HealthcarePreMedicare", 1000),
            max_value=5_000, step=50, key="hc_pre",
        )
        st.markdown("**Age 65+ (Medicare)**")
        st.caption(
            "Rough ranges (per person, monthly):  \n"
            "• Medicare Part B: ~$175/mo  \n"
            "• Part D (drugs): ~$35-60/mo  \n"
            "• Medigap or Advantage: ~$150-300/mo  \n"
            "• Plus out-of-pocket: ~$100-200/mo expected"
        )
        inputs["in_HealthcareMedicare"] = money_input(
            "Monthly cost at age 65+",
            inputs.get("in_HealthcareMedicare", 600),
            max_value=5_000, step=50, key="hc_med",
        )
        inputs["in_HealthcareMedicareAge"] = st.number_input(
            "Medicare age", min_value=60, max_value=70,
            value=int(inputs.get("in_HealthcareMedicareAge", 65)), step=1, key="hc_age",
        )
        inputs["in_HealthcareInflation"] = percent_slider(
            "Healthcare inflation",
            inputs.get("in_HealthcareInflation", 0.05),
            min_pct=0.0, max_pct=10.0, step_pct=0.1, key="hc_inf",
        )

with st.sidebar.expander("Long-term Care Event"):
    st.caption(
        "**Long-term care** means nursing home, assisted living, or in-home help. "
        "70% of people 65+ need it; median cost ~$8K/mo; avg 3 years. Medicare "
        "(federal health insurance for 65+) doesn't cover it. [Glossary](/Glossary)."
    )
    ltc_on = st.checkbox(
        "Model LTC event",
        value=(inputs.get("in_LTCEnabled", "No") == "Yes"),
        key="ltc_enabled",
    )
    inputs["in_LTCEnabled"] = "Yes" if ltc_on else "No"
    if ltc_on:
        ltc_monthly = float(inputs.get("in_LTCMonthly", 8000))
        ltc_years = int(inputs.get("in_LTCDuration", 3))
        ltc_total = ltc_monthly * 12 * ltc_years
        st.markdown(
            f'<div style="background: #fef3c7; padding: 0.5rem 0.75rem; '
            f'border-radius: 4px; font-size: 0.85rem; color: #92400e; margin: 0.25rem 0;">'
            f'Adds about <strong>${ltc_total:,.0f}</strong> in today\'s dollars over '
            f'{ltc_years} years (grows with inflation by the time it hits).</div>',
            unsafe_allow_html=True,
        )
        inputs["in_LTCMonthly"] = money_input(
            "Monthly cost (today's $)",
            inputs.get("in_LTCMonthly", 8000),
            max_value=30_000, step=500, key="ltc_monthly",
        )
        c_sa, c_dur = st.columns(2)
        inputs["in_LTCStartAge"] = c_sa.number_input(
            "Start age", min_value=60, max_value=100,
            value=int(inputs.get("in_LTCStartAge", 82)), step=1, key="ltc_age",
        )
        inputs["in_LTCDuration"] = c_dur.number_input(
            "Duration (yrs)", min_value=1, max_value=15,
            value=int(inputs.get("in_LTCDuration", 3)), step=1, key="ltc_dur",
        )

with st.sidebar.expander("Roth Conversion Ladder"):
    st.caption(
        "Move money from Traditional → Roth each year during low-income years. "
        "You pay tax on each conversion (it counts as income that year), but the "
        "converted Roth money then grows tax-free forever AND avoids forced withdrawals later. "
        "[Glossary](/Glossary)."
    )
    rc_on = st.checkbox(
        "Enable annual Roth conversion",
        value=(inputs.get("in_RothConvEnabled", "No") == "Yes"),
        key="rc_enabled",
    )
    inputs["in_RothConvEnabled"] = "Yes" if rc_on else "No"
    if rc_on:
        # Live impact preview
        rc_yr = float(inputs.get("in_RothConvAmount", 20000))
        rc_sy = int(inputs.get("in_RothConvStartYear", 2040))
        rc_ey = int(inputs.get("in_RothConvEndYear", 2050))
        rc_n = max(rc_ey - rc_sy + 1, 0)
        rc_total = rc_yr * rc_n
        st.markdown(
            f'<div style="background: #fef3c7; padding: 0.5rem 0.75rem; '
            f'border-radius: 4px; font-size: 0.85rem; color: #92400e; margin: 0.25rem 0;">'
            f'Converts <strong>${rc_total:,.0f}</strong> total over {rc_n} years '
            f'({rc_sy}-{rc_ey}). Each year\'s conversion adds to that year\'s '
            f'taxable income.</div>',
            unsafe_allow_html=True,
        )
        inputs["in_RothConvAmount"] = money_input(
            "Amount converted each year (today's $)",
            inputs.get("in_RothConvAmount", 20000),
            max_value=500_000, step=1_000, key="rc_amt",
        )
        st.caption(
            "**Typical strategy:** start the year you retire early, end when "
            "Social Security begins (usually age 67). That's your low-income "
            "window when conversions are cheapest."
        )
        c_sy, c_ey = st.columns(2)
        inputs["in_RothConvStartYear"] = c_sy.number_input(
            "First conversion year",
            min_value=2025, max_value=2100,
            value=int(inputs.get("in_RothConvStartYear", 2040)), step=1, key="rc_start",
            help="Year you START converting. Typically your retirement year.",
        )
        inputs["in_RothConvEndYear"] = c_ey.number_input(
            "Last conversion year",
            min_value=2025, max_value=2100,
            value=int(inputs.get("in_RothConvEndYear", 2050)), step=1, key="rc_end",
            help="Year you STOP converting. Typically the year you start Social Security (age 67).",
        )

# ---------- Sidebar: reset button ----------

st.sidebar.divider()
if st.sidebar.button("↺ Reset all saved data", type="secondary", key="clear_ls_btn"):
    track_button("reset_all_data")
    st.session_state["_clear_saved"] = True
    st.rerun()
st.sidebar.caption("Wipes your browser's saved scenario and reloads Alex defaults.")

# ---------- Run model ----------

current_age = st.session_state.current_age
seed = build_seedcase_from_inputs(inputs, current_age=current_age)
outputs = run_and_extract(seed)
records = outputs.records

# Track which features are active (once per session, after first model run)
if "_features_tracked" not in st.session_state:
    st.session_state["_features_tracked"] = True
    from helpers.analytics import track_event
    track_event("features_snapshot",
        spouse=inputs.get("in_SpouseEnabled") == "Yes",
        self_employment=inputs.get("in_SEEnabled") == "Yes",
        property=inputs.get("in_BuyProperty") == "Yes",
        healthcare=inputs.get("in_HealthcareEnabled") == "Yes",
        ltc=inputs.get("in_LTCEnabled") == "Yes",
        roth_conversion=inputs.get("in_RothConvEnabled") == "Yes",
        vehicle=inputs.get("in_IncludeVehicle") == "Yes",
        has_debts=any(inputs.get(f"in_Debt{n}Enabled") == "Yes" for n in (1, 2, 3)),
    )

# ---------- Auto-save to localStorage (silent) ----------
# Runs on every interaction; persists current inputs to browser storage.
try:
    save_to_localstorage(
        inputs, current_age, name=st.session_state.get("scenario_name", "My scenario")
    )
except Exception:
    pass  # Best-effort only

# ---------- Scenario card at top ----------

render_scenario_card_v2(
    outputs,
    scenario_name=st.session_state.get("scenario_name", "My scenario"),
    current_age=current_age,
)

# ---------- Monte Carlo success-rate chip (cached) ----------

@st.cache_data(show_spinner="Updating Monte Carlo...")
def _quick_mc_success_rate(inputs_tuple, current_age: int) -> tuple[int, int]:
    """Return (successes, total_cycles) for current scenario.

    IMPORTANT: Neither argument starts with underscore, so Streamlit DOES hash
    them into the cache key. The cache invalidates whenever inputs or age change.
    """
    import sys
    from pathlib import Path
    import csv
    REPO_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
    from model.historical import HistoricalYear, run_historical_cycle
    from helpers.seeds import build_seedcase_from_inputs
    hist_path = REPO_ROOT / "retirement-sim" / "evals" / "external-benchmarks" / "historical-returns-annual.csv"
    hist = []
    with hist_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            hist.append(HistoricalYear(
                year=int(row["year"]),
                sp500_return=float(row["sp500_return"]),
                tbond_return=float(row["tbond_return"]),
                inflation=float(row["inflation"]),
            ))
    hist.sort(key=lambda y: y.year)
    seed = build_seedcase_from_inputs(dict(inputs_tuple), current_age=current_age)
    n_years = seed.years_simulated
    viable_starts = range(hist[0].year, hist[-1].year - n_years + 2)
    successes = 0
    total = 0
    for start in viable_starts:
        idx = start - hist[0].year
        hist_slice = hist[idx:idx + n_years]
        try:
            r = run_historical_cycle(seed, hist_slice)
            total += 1
            if r.succeeded:
                successes += 1
        except Exception:
            pass
    return successes, total

# Quick MC run, cached on input state
inputs_tuple_for_cache = inputs_cache_key(inputs)
mc_successes, mc_total = _quick_mc_success_rate(inputs_tuple_for_cache, current_age)

# Inline chip under the scenario card
if mc_total > 0:
    mc_rate = mc_successes / mc_total
    if mc_rate >= 0.95:
        chip_color = "#16a34a"
        chip_bg = "#dcfce7"
        verdict = "Historically safe"
    elif mc_rate >= 0.80:
        chip_color = "#d97706"
        chip_bg = "#fef3c7"
        verdict = "Borderline"
    else:
        chip_color = "#dc2626"
        chip_bg = "#fee2e2"
        verdict = "Historically risky"
    st.markdown(
        f'''
        <div style="display: flex; align-items: center; gap: 0.75rem; margin: 0.75rem 0;">
          <span style="background: {chip_bg}; color: {chip_color}; font-weight: 600;
                       padding: 0.35rem 0.75rem; border-radius: 999px; font-size: 0.85rem;">
            {verdict} · {mc_rate:.0%} historical success ({mc_successes}/{mc_total} cycles)
          </span>
          <a href="/Monte_Carlo" target="_self" style="font-size: 0.85rem; color: #2563eb; text-decoration: none;">
            See full Monte Carlo →
          </a>
        </div>
        ''',
        unsafe_allow_html=True,
    )

st.divider()

# ---------- Main content ----------

import pandas as pd

# Extract life events from the records
_debt_labels = (
    inputs.get("in_Debt1Label", "Debt 1"),
    inputs.get("in_Debt2Label", "Debt 2"),
    inputs.get("in_Debt3Label", "Debt 3"),
)
events = extract_events(records, end_age=int(inputs["in_EndAge"]), debt_labels=_debt_labels)
events_map = events_by_year(events)

# --- HERO: Year-by-year net worth chart (most important visual, above the fold) ---
st.altair_chart(
    projection_chart(records, events=events, height=420, base_year=2025, current_age=current_age),
    width='stretch',
)
st.caption(
    "Stacked by bucket. Hover for year details. The dark blue line traces "
    "your spendable portfolio (what you can actually draw from in retirement)."
)

# --- Plan summary: based on portfolio exhaustion, the real bottom line ---

if outputs.retirement_age is None:
    spend_summary = (
        "Your plan doesn't reach retirement target in this horizon. "
        "Try lowering the target, raising returns, or increasing savings."
    )
    spend_color = "#dc2626"
    spend_bg = "#fee2e2"
elif outputs.portfolio_exhausted_age:
    # Portfolio runs out — this is the real red flag
    years_lasted = outputs.portfolio_exhausted_age - outputs.retirement_age
    # Identify what's driving the cost
    retired_recs = [r for r in records if r.phase == "Retired"]
    has_hc = any(r.expense_healthcare > 0 for r in retired_recs)
    has_ltc = any(r.expense_ltc > 0 for r in retired_recs)
    cost_drivers = []
    if has_hc:
        # Find peak healthcare cost
        peak_hc = max(r.expense_healthcare for r in retired_recs)
        cost_drivers.append(f"healthcare inflating to ${peak_hc/1_000:.0f}K/yr")
    if has_ltc:
        peak_ltc = max(r.expense_ltc for r in retired_recs)
        cost_drivers.append(f"long-term care adding ${peak_ltc/1_000:.0f}K/yr")
    driver_text = (" Main cost drivers: " + " and ".join(cost_drivers) + ".") if cost_drivers else ""
    spend_summary = (
        f"**Portfolio runs out at age {outputs.portfolio_exhausted_age}** "
        f"(lasts {years_lasted} years after retiring at {outputs.retirement_age}). "
        f"After that, only Social Security covers expenses.{driver_text} "
        f"Consider: delaying retirement, increasing savings, or reducing healthcare/LTC assumptions."
    )
    spend_color = "#dc2626"
    spend_bg = "#fee2e2"
else:
    # Portfolio survives — show the cushion
    max_spend = getattr(outputs, "max_sustainable_spend", 0)
    base_annual = (inputs["in_MonthlyNonHousing"] + inputs["in_MonthlyRent"]) * 12
    if max_spend > 0 and base_annual > 0:
        cushion_pct = (max_spend - base_annual) / base_annual * 100
        if cushion_pct < 10:
            spend_summary = (
                f"**Thin margin:** your plan supports ${max_spend:,.0f}/yr in base spending "
                f"(your current: ${base_annual:,.0f}/yr). "
                f"Cushion: {cushion_pct:.0f}%. Small changes could tip the balance."
            )
            spend_color = "#d97706"
            spend_bg = "#fef3c7"
        else:
            spend_summary = (
                f"**Portfolio survives to end of plan.** "
                f"Base spending: ${base_annual:,.0f}/yr, plan supports up to "
                f"${max_spend:,.0f}/yr ({cushion_pct:.0f}% cushion)."
            )
            spend_color = "#16a34a"
            spend_bg = "#dcfce7"
    else:
        spend_summary = "**Portfolio survives to end of plan.**"
        spend_color = "#16a34a"
        spend_bg = "#dcfce7"

st.markdown(
    f'<div style="background: {spend_bg}; border-left: 3px solid {spend_color}; '
    f'padding: 0.75rem 1rem; border-radius: 4px; margin: 0.5rem 0 1rem 0;">{spend_summary}</div>',
    unsafe_allow_html=True,
)

# --- Top levers: actionable recommendations ---
@st.cache_data(show_spinner=False)
def _cached_recommendations(inputs_tuple, current_age, base_age, base_nw):
    """Cached recommendations lookup. Invalidates whenever inputs change."""
    return generate_recommendations(
        dict(inputs_tuple), current_age,
        base_age=base_age, base_nw=base_nw, top_n=3,
    )

try:
    recs = _cached_recommendations(
        inputs_tuple_for_cache, current_age, outputs.retirement_age, outputs.nw_at_end,
    )
except Exception:
    recs = []

if recs:
    st.subheader("Top levers for your plan")
    st.caption(
        "Realistic one-step changes, ranked by how much each moves your retirement age. "
        "Each tested against your current scenario, holding everything else constant."
    )
    for i, r in enumerate(recs, 1):
        st.markdown(
            f'<div style="background: #f8fafc; border-left: 3px solid #2563eb; '
            f'padding: 0.75rem 1rem; border-radius: 4px; margin: 0.5rem 0;">'
            f'<div style="font-weight: 600; color: #0f172a;">{i}. {r.action}</div>'
            f'<div style="color: #16a34a; font-size: 0.9rem; margin-top: 0.15rem;">'
            f'&rarr; {r.outcome}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.caption(
        "These are directional, not prescriptions. The **Sensitivity** page "
        "(sidebar) ranks every input and lets you pick your own metric."
    )
    st.divider()

# --- Housing impact: rent vs buy comparison (only when property enabled) ---
if inputs.get("in_BuyProperty", "No") == "Yes":
    @st.cache_data(show_spinner="Comparing rent vs buy...")
    def _cached_housing_compare(inputs_tuple, current_age):
        return compare_rent_vs_buy(dict(inputs_tuple), current_age)

    try:
        hc = _cached_housing_compare(inputs_tuple_for_cache, current_age)
    except Exception:
        hc = None

    if hc is not None:
        st.subheader("Housing impact — rent vs buy")
        st.caption(
            "Same scenario run twice: once with your property purchase, once without. "
            "The retirement target counts only **liquid** net worth (you can't pay "
            "grocery bills with your house), so buying typically delays retirement "
            "even when it builds wealth on paper."
        )

        # Side-by-side metric columns
        col_rent, col_buy = st.columns(2)

        def _fmt_age(age):
            return f"Age {age}" if age is not None else "Not reached"

        with col_rent:
            st.markdown("**Rent only** (no property)")
            st.metric("Retirement age", _fmt_age(hc.rent.retirement_age))
            st.metric(
                "Liquid NW at end", f"${hc.rent.liquid_nw_at_end/1_000_000:.2f}M",
                help="Spendable portfolio at end of plan — what you could actually draw from.",
            )
            st.metric(
                "Max sustainable spend", f"${hc.rent.max_sustainable_spend/1_000:.0f}K/yr",
                help="Annual spending (today's $) the plan supports to age end-of-plan.",
            )

        with col_buy:
            st.markdown("**Buy** (your current inputs)")
            age_delta = None
            if hc.buy.retirement_age is not None and hc.rent.retirement_age is not None:
                age_delta = hc.buy.retirement_age - hc.rent.retirement_age
            st.metric(
                "Retirement age", _fmt_age(hc.buy.retirement_age),
                delta=f"{age_delta:+d} yrs vs renting" if age_delta is not None else None,
                delta_color="inverse",  # later retirement = bad
            )
            liq_delta = hc.buy.liquid_nw_at_end - hc.rent.liquid_nw_at_end
            st.metric(
                "Liquid NW at end", f"${hc.buy.liquid_nw_at_end/1_000_000:.2f}M",
                delta=f"${liq_delta/1_000_000:+.2f}M vs renting",
                help="Spendable portfolio at end of plan — home equity excluded.",
            )
            spend_delta = hc.buy.max_sustainable_spend - hc.rent.max_sustainable_spend
            st.metric(
                "Max sustainable spend",
                f"${hc.buy.max_sustainable_spend/1_000:.0f}K/yr",
                delta=f"${spend_delta/1_000:+.0f}K/yr vs renting",
                help="Annual spending (today's $) the plan supports.",
            )

        # Home equity callout — the "upside" of buying
        if hc.buy.home_equity_at_end > 0:
            st.markdown(
                f'<div style="background: #f0f9ff; border-left: 3px solid #2563eb; '
                f'padding: 0.75rem 1rem; border-radius: 4px; margin: 0.5rem 0;">'
                f'<strong>Home equity at end of plan:</strong> '
                f'${hc.buy.home_equity_at_end/1_000_000:.2f}M '
                f'<span style="color: #64748b; font-size: 0.9rem;"> '
                f'(illiquid — realizable only by selling or downsizing)</span><br>'
                f'<strong>Total NW at end (buy):</strong> '
                f'${hc.buy.total_nw_at_end/1_000_000:.2f}M '
                f'<span style="color: #64748b; font-size: 0.9rem;"> '
                f'vs ${hc.rent.total_nw_at_end/1_000_000:.2f}M renting'
                f'</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Opportunity cost of down payment
        with st.expander("The down payment's opportunity cost"):
            st.markdown(
                f"""
                Your down payment is **${hc.down_payment:,.0f}**.

                If you instead invested that cash in stocks at your assumed return
                rate of **{inputs.get('in_StockReturn', 0.07)*100:.1f}%** for the
                remaining **{hc.years_simulated - (int(inputs.get('in_PropertyYear', 2035)) - 2025)} years**
                until end-of-plan, it would grow to
                **${hc.down_payment_opportunity_cost/1_000_000:.2f}M**.

                This is the **opportunity cost** of tying capital up in a down payment.
                Home equity has to beat this number (after maintenance, taxes,
                transaction costs) for buying to be wealth-maximizing.
                """
            )

        # Framing message — lifestyle vs financial
        with st.expander("Why buying delays liquid-portfolio retirement"):
            st.markdown(
                """
                **Retirement depends on your liquid portfolio**, not total net worth.
                The model won't let you retire on home equity — you can't pay grocery
                bills with a house. So:

                1. **Down payment drains the portfolio immediately** (lost years of
                   compounding on that cash).
                2. **Ongoing ownership costs + mortgage payments** often exceed what rent
                   would have been, so monthly savings drop.
                3. **Liquid NW takes longer to hit the retirement target** → later retirement.
                4. **Home equity accumulates on the side**, but it's illiquid wealth
                   until you sell or downsize.

                **Is buying still worth it?** That's a lifestyle + stability question
                more than a pure wealth-maximization one. Factors this model doesn't
                capture:

                - Tax benefits (mortgage interest deduction — though reduced since 2017)
                - Inflation hedge (locked mortgage payment vs rising rents)
                - Forced savings discipline (each mortgage payment builds equity)
                - Stability / control of your housing situation
                - Ability to downsize at retirement and release equity

                **When buying does "win" financially**: long hold periods (10+ years),
                high appreciation markets, and when your mortgage P&I roughly matches
                what rent would have been.
                """
            )
        st.divider()

# --- Debt summary (only shown when debts are active) ---
_starting_debt = records[0].total_debt_balance
if _starting_debt > 0.01 or records[0].expense_debt > 0:
    with st.expander("Debt overview", expanded=True):
        # Find payoff year: first year AFTER year 0 where debt reaches 0
        _payoff_rec = next(
            (r for r in records[1:] if r.total_debt_balance <= 0.01),
            None,
        )
        _total_payments = sum(r.expense_debt for r in records)
        _total_interest = max(0.0, _total_payments - _starting_debt)

        dcol1, dcol2, dcol3, dcol4 = st.columns(4)
        dcol1.metric(
            "Total debt today",
            f"${_starting_debt:,.0f}",
        )
        if _payoff_rec:
            dcol2.metric(
                "Debt-free by",
                f"{_payoff_rec.year} (age {_payoff_rec.age})",
            )
        else:
            dcol2.metric("Debt-free by", "Not in plan horizon")
        dcol3.metric(
            "Total interest paid",
            f"${_total_interest:,.0f}",
            help="Estimated total interest cost of carrying this debt until payoff.",
        )
        _strategy_label = {
            "none": "None", "avalanche": "Avalanche", "snowball": "Snowball",
        }.get(inputs.get("in_DebtPayoffStrategy", "none"), "None")
        dcol4.metric(
            "Payoff strategy",
            _strategy_label,
            help="Avalanche = highest rate first. Snowball = lowest balance first.",
        )

        # Per-debt payoff timeline
        _debt_details = []
        for _n, _bal_attr in [(1, "debt_1_balance"), (2, "debt_2_balance"), (3, "debt_3_balance")]:
            if inputs.get(f"in_Debt{_n}Enabled") == "Yes":
                _start_bal = getattr(records[0], _bal_attr, 0.0)
                if _start_bal > 0.01:
                    _payoff_yr = next(
                        (r for r in records[1:] if getattr(r, _bal_attr, 0.0) <= 0.01),
                        None,
                    )
                    _debt_details.append({
                        "Debt": inputs.get(f"in_Debt{_n}Label", f"Debt {_n}"),
                        "Balance": f"${_start_bal:,.0f}",
                        "APR": f"{float(inputs.get(f'in_Debt{_n}Rate', 0)) * 100:.1f}%",
                        "Payment/mo": f"${float(inputs.get(f'in_Debt{_n}MinPayment', 0)):,.0f}",
                        "Paid off": f"{_payoff_yr.year} (age {_payoff_yr.age})" if _payoff_yr else "Not in horizon",
                    })
        if _debt_details:
            st.dataframe(pd.DataFrame(_debt_details), hide_index=True, use_container_width=True)

        # Debt payoff chart
        _debt_chart = debt_payoff_chart(
            records,
            debt_labels=_debt_labels,
            height=250,
            base_year=2025,
            current_age=current_age,
        )
        if _debt_chart:
            st.altair_chart(_debt_chart, use_container_width=True)

# --- Expense breakdown: where is the money going? ---
# Compute year-1 and lifetime totals for each expense category.
yr1 = records[0]
lifetime_base = sum(r.expense_base for r in records)
lifetime_mortgage = sum(r.expense_mortgage for r in records)
lifetime_hc = sum(r.expense_healthcare for r in records)
lifetime_ltc = sum(r.expense_ltc for r in records)
lifetime_debt = sum(r.expense_debt for r in records)
lifetime_total = lifetime_base + lifetime_mortgage + lifetime_hc + lifetime_ltc + lifetime_debt

with st.expander("💵 Where does your money go? (expense breakdown)", expanded=False):
    st.caption(
        f"Total lifetime expenses over {len(records)} years: **${lifetime_total/1_000_000:.1f}M** (nominal). "
        "Each category inflates at its own rate."
    )
    exp_cols = st.columns(5 if lifetime_debt else 4)
    exp_cols[0].metric(
        "Living expenses",
        f"${yr1.expense_base/1_000:.0f}K / yr1",
        delta=f"${lifetime_base/1_000_000:.1f}M lifetime",
        delta_color="off",
        help="Non-housing + housing/rent, inflated at your general inflation rate.",
    )
    exp_cols[1].metric(
        "Mortgage payment",
        f"${yr1.expense_mortgage/1_000:.0f}K / yr1" if lifetime_mortgage else "—",
        delta=f"${lifetime_mortgage/1_000_000:.1f}M lifetime" if lifetime_mortgage else None,
        delta_color="off",
        help="Your fixed monthly mortgage payment (principal + interest) until the loan is paid off.",
    )
    exp_cols[2].metric(
        "Healthcare",
        f"${yr1.expense_healthcare/1_000:.0f}K / yr1" if lifetime_hc else "—",
        delta=f"${lifetime_hc/1_000_000:.1f}M lifetime" if lifetime_hc else None,
        delta_color="off",
        help="Pre-65 insurance + Medicare + supplements, inflated at healthcare rate (default 4%).",
    )
    exp_cols[3].metric(
        "Long-term care",
        f"${lifetime_ltc/1_000:.0f}K total" if lifetime_ltc else "—",
        delta=f"${lifetime_ltc/1_000_000:.1f}M lifetime" if lifetime_ltc else None,
        delta_color="off",
        help="Nursing home / assisted living / in-home care during the LTC event window.",
    )
    if lifetime_debt:
        exp_cols[4].metric(
            "Debt payments",
            f"${yr1.expense_debt/1_000:.0f}K / yr1",
            delta=f"${lifetime_debt/1_000_000:.1f}M lifetime",
            delta_color="off",
            help="Total debt payments (credit cards, student loans, auto loans, etc.). Drops to $0 when debts are paid off.",
        )
    if lifetime_total > 0:
        dist_parts = [
            f"{lifetime_base/lifetime_total*100:.0f}% living",
            f"{lifetime_mortgage/lifetime_total*100:.0f}% mortgage",
            f"{lifetime_hc/lifetime_total*100:.0f}% healthcare",
            f"{lifetime_ltc/lifetime_total*100:.0f}% long-term care",
        ]
        if lifetime_debt:
            dist_parts.append(f"{lifetime_debt/lifetime_total*100:.0f}% debt")
        st.caption(
            f"**Distribution:** "
            + " · ".join(dist_parts)
        )

st.subheader("Retirement income vs expenses")
st.altair_chart(
    income_vs_expenses_chart(records, height=340, base_year=2025, current_age=current_age),
    width='stretch',
)
st.caption(
    "Bars above zero = income (withdrawal, SS, disability, other). Bars below zero = "
    "expenses broken down by category. If income bars ≥ expense bars, you're "
    "covering your lifestyle."
)

# --- Details expander (bucket composition chart + year-by-year table) ---
with st.expander("More details — portfolio composition & year-by-year table"):
    st.subheader("Portfolio composition over time")
    custom_names = (
        inputs.get("in_Custom1Name", "Custom 1"),
        inputs.get("in_Custom2Name", "Custom 2"),
        inputs.get("in_Custom3Name", "Custom 3"),
    )
    st.altair_chart(
        bucket_breakdown_chart(
            records, custom_names=custom_names, height=320,
            base_year=2025, current_age=current_age,
        ),
        width='stretch',
    )
    st.caption("At age 59½ you can withdraw from your 401(k) penalty-free, so it combines with your other investments.")

    st.subheader("Year-by-year details")
    table_rows = []
    for r in records:
        year_events = events_map.get(r.year, [])
        event_labels = "; ".join(e.short_label for e in year_events) if year_events else ""
        row_is_key = bool(year_events)
        table_rows.append({
            "Year": r.year,
            "Age": r.age,
            "Phase": r.phase,
            "Event": event_labels or "—",
            "Salary": f"${r.salary:,.0f}" if r.salary else "—",
            "Expenses": f"${r.living_expenses:,.0f}",
            "  Living": f"${r.expense_base:,.0f}" if r.expense_base else "—",
            "  Mortgage": f"${r.expense_mortgage:,.0f}" if r.expense_mortgage else "—",
            "  Debt": f"${r.expense_debt:,.0f}" if r.expense_debt else "—",
            "  Healthcare": f"${r.expense_healthcare:,.0f}" if r.expense_healthcare else "—",
            "  Long-term Care": f"${r.expense_ltc:,.0f}" if r.expense_ltc else "—",
            "Withdrawal": f"${r.withdrawal:,.0f}" if r.withdrawal else "—",
            "Soc. Security": f"${r.ss_income:,.0f}" if r.ss_income else "—",
            "Disability": f"${r.disability_income:,.0f}" if r.disability_income else "—",
            "Other": f"${r.other_income_1 + r.other_income_2:,.0f}" if (r.other_income_1 + r.other_income_2) else "—",
            "Federal Tax": f"${r.federal_tax:,.0f}" if r.federal_tax else "—",
            "State Tax": f"${r.state_tax:,.0f}" if r.state_tax else "—",
            "Portfolio": f"${r.end_balance:,.0f}",
            "Roth 401(k)": f"${r.roth_401k:,.0f}" if r.roth_401k else "—",
            "Roth Conversion": f"${r.roth_conversion:,.0f}" if r.roth_conversion else "—",
            "Debt Balance": f"${r.total_debt_balance:,.0f}" if r.total_debt_balance else "—",
            "Net Worth": f"${r.total_nw:,.0f}",
            "_has_event": row_is_key,
        })
    df = pd.DataFrame(table_rows)

    def _highlight_events(row):
        return ['background-color: #fef3c7' if row['_has_event'] else '' for _ in row]

    styled = df.style.apply(_highlight_events, axis=1)
    st.dataframe(
        styled, width='stretch', hide_index=True,
        column_config={"_has_event": None},
        height=400,
    )
    st.caption("Amber rows mark life events.")

# Subtle footer disclaimer link
st.markdown(
    '<p style="text-align: center; font-size: 0.75rem; color: #94a3b8; margin-top: 2rem;">'
    'Educational tool only, not financial advice · '
    '<a href="/Methodology" target="_self" style="color: #94a3b8;">Methodology & disclaimer</a>'
    '</p>',
    unsafe_allow_html=True,
)
