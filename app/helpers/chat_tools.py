"""
Tool implementations for the chat feature.

These functions are called by the LLM when it uses tools to interact
with the retirement simulation.
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

logger = logging.getLogger(__name__)

from .seeds import build_seedcase_from_inputs
from .recommendations import generate_recommendations
from .target_finder import find_safe_target as _find_safe_target
from .widgets import format_money


def _get_inputs_and_age() -> tuple[dict, int]:
    """Get current inputs and age from session state."""
    inputs = st.session_state.get("inputs", {})
    current_age = st.session_state.get("current_age", 35)
    return inputs, current_age


def _run_projection(inputs: dict, current_age: int) -> Any:
    """Run the projection and return outputs."""
    from model.outputs import run_and_extract
    seed = build_seedcase_from_inputs(inputs, current_age=current_age)
    return run_and_extract(seed)


def get_current_scenario() -> dict:
    """Get the current retirement scenario inputs and projection results.

    Returns a summary dict with key metrics.
    """
    inputs, current_age = _get_inputs_and_age()

    if not inputs:
        return {
            "error": "No scenario loaded. Please set up your inputs on the Planner page first."
        }

    outputs = _run_projection(inputs, current_age)

    return {
        "current_age": current_age,
        "retirement_age": outputs.retirement_age,
        "years_until_retirement": (outputs.retirement_age - current_age) if outputs.retirement_age else None,
        "retirement_year": outputs.retirement_year,
        "max_sustainable_spend_annual": outputs.max_sustainable_spend,
        "max_sustainable_spend_monthly": outputs.max_sustainable_spend / 12 if outputs.max_sustainable_spend else None,
        "net_worth_at_end": outputs.nw_at_end,
        "liquid_net_worth_at_end": outputs.liquid_nw_at_end,
        "home_equity_at_end": outputs.home_equity_at_end,
        "portfolio_exhausted_age": outputs.portfolio_exhausted_age,
        "portfolio_survives": outputs.portfolio_exhausted_age is None,
        "lifetime_federal_tax": outputs.lifetime_federal_tax,
        "lifetime_state_tax": outputs.lifetime_state_tax,
        # Key inputs
        "monthly_spending_today": inputs.get("in_MonthlyNonHousing", 0),
        "monthly_rent": inputs.get("in_MonthlyRent", 0),
        "annual_401k_contribution": inputs.get("in_401kContrib", 0),
        "retirement_target": inputs.get("in_RetirementTarget", 0),
        "end_age": inputs.get("in_EndAge", 90),
    }


def run_what_if(
    monthly_spending: float | None = None,
    annual_401k_contribution: float | None = None,
    retirement_target: float | None = None,
) -> dict:
    """Run a what-if projection with modified parameters.

    Returns comparison between current and modified scenario.
    NOTE: Retirement age cannot be set directly — it is computed from
    retirement_target. To explore earlier retirement, lower the target
    or use find_safe_target().
    """
    inputs, current_age = _get_inputs_and_age()

    if not inputs:
        return {
            "error": "No scenario loaded. Please set up your inputs on the Planner page first."
        }

    # Run baseline
    baseline_outputs = _run_projection(inputs, current_age)

    # Create modified inputs
    modified_inputs = inputs.copy()
    changes_made = []

    if monthly_spending is not None:
        modified_inputs["in_MonthlyNonHousing"] = monthly_spending
        changes_made.append(f"monthly_spending=${monthly_spending:,.0f}")

    if annual_401k_contribution is not None:
        modified_inputs["in_401kContrib"] = annual_401k_contribution
        changes_made.append(f"401k_contribution=${annual_401k_contribution:,.0f}")

    if retirement_target is not None:
        modified_inputs["in_RetirementTarget"] = retirement_target
        changes_made.append(f"retirement_target=${retirement_target:,.0f}")

    # Run modified projection
    modified_outputs = _run_projection(modified_inputs, current_age)

    return {
        "changes_made": changes_made,
        "baseline": {
            "retirement_age": baseline_outputs.retirement_age,
            "max_sustainable_spend": baseline_outputs.max_sustainable_spend,
            "net_worth_at_end": baseline_outputs.nw_at_end,
            "portfolio_survives": baseline_outputs.portfolio_exhausted_age is None,
        },
        "modified": {
            "retirement_age": modified_outputs.retirement_age,
            "max_sustainable_spend": modified_outputs.max_sustainable_spend,
            "net_worth_at_end": modified_outputs.nw_at_end,
            "portfolio_survives": modified_outputs.portfolio_exhausted_age is None,
        },
        "difference": {
            "retirement_age_years": (
                (modified_outputs.retirement_age - baseline_outputs.retirement_age)
                if modified_outputs.retirement_age and baseline_outputs.retirement_age
                else None
            ),
            "net_worth_change": modified_outputs.nw_at_end - baseline_outputs.nw_at_end,
            "max_spend_change": (
                (modified_outputs.max_sustainable_spend - baseline_outputs.max_sustainable_spend)
                if modified_outputs.max_sustainable_spend and baseline_outputs.max_sustainable_spend
                else None
            ),
        },
    }


def get_recommendations(top_n: int = 3) -> list[dict]:
    """Get top actionable recommendations to improve the plan.

    Returns list of recommendation dicts with action and outcome.
    """
    inputs, current_age = _get_inputs_and_age()

    if not inputs:
        return [{
            "error": "No scenario loaded. Please set up your inputs on the Planner page first."
        }]

    # Get baseline for comparison
    baseline_outputs = _run_projection(inputs, current_age)

    # Generate recommendations
    recs = generate_recommendations(
        inputs=inputs,
        current_age=current_age,
        base_age=baseline_outputs.retirement_age,
        base_nw=baseline_outputs.nw_at_end,
        top_n=top_n,
    )

    if not recs:
        return [{
            "message": "Your plan looks solid! No significant improvements found with simple changes."
        }]

    return [
        {
            "action": rec.action,
            "outcome": rec.outcome,
            "category": rec.category,
        }
        for rec in recs
    ]


def find_safe_target() -> dict:
    """Find the minimum retirement target that passes stress tests.

    Uses binary search to find the lowest net worth target where:
    1. Deterministic projection survives to end of plan
    2. 95%+ of historical Monte Carlo sequences succeed
    """
    inputs, current_age = _get_inputs_and_age()

    if not inputs:
        return {
            "error": "No scenario loaded. Please set up your inputs on the Planner page first."
        }

    result = _find_safe_target(inputs, current_age)

    return {
        "found": result.found,
        "recommended_target": result.target if result.found else None,
        "recommended_target_formatted": format_money(result.target) if result.found else None,
        "retirement_age_at_target": result.retirement_age,
        "monte_carlo_success_rate": result.mc_success_rate,
        "deterministic_survives": result.det_survives,
        "note": result.note,
        "iterations": result.iterations,
    }


# Glossary definitions
GLOSSARY = {
    "roth": "**Roth 401(k)/IRA**: Post-tax contributions, but all growth and withdrawals are tax-free. Best if you expect higher taxes in retirement.",
    "roth ira": "**Roth IRA**: Individual retirement account with post-tax contributions. Withdrawals are tax-free in retirement. Income limits apply for contributions.",
    "roth 401k": "**Roth 401(k)**: Employer-sponsored retirement account with post-tax contributions. Like a Roth IRA but with higher contribution limits and no income restrictions.",
    "traditional": "**Traditional 401(k)/IRA**: Pre-tax contributions reduce your taxable income now, but withdrawals are taxed in retirement. Best if you expect lower taxes later.",
    "traditional ira": "**Traditional IRA**: Individual retirement account with potentially tax-deductible contributions. Withdrawals are taxed as ordinary income.",
    "traditional 401k": "**Traditional 401(k)**: Employer-sponsored retirement account with pre-tax contributions. Reduces current taxable income; withdrawals are taxed.",
    "rmd": "**RMD (Required Minimum Distribution)**: Mandatory withdrawals from Traditional retirement accounts starting at age 73 (per SECURE Act 2.0). Calculated using IRS life expectancy tables.",
    "4% rule": "**4% Rule**: A retirement guideline suggesting you can withdraw 4% of your portfolio annually (adjusted for inflation) and have a high probability of not running out of money over 30 years. Based on the Trinity Study.",
    "trinity study": "**Trinity Study**: Academic research showing that a 60/40 stock/bond portfolio with 4% initial withdrawal rate (adjusted for inflation) historically survived 30+ years in most scenarios.",
    "glide path": "**Glide Path**: An investment strategy that gradually shifts from stocks to bonds as you age. Reduces risk as you approach and enter retirement.",
    "monte carlo": "**Monte Carlo Simulation**: Testing your retirement plan against many possible market scenarios (or historical sequences) to see the probability of success.",
    "sequence of returns risk": "**Sequence of Returns Risk**: The danger that poor market returns early in retirement can devastate your portfolio, even if average returns are good.",
    "safe withdrawal rate": "**Safe Withdrawal Rate**: The percentage of your portfolio you can withdraw annually while maintaining a high probability of not running out of money.",
    "fire": "**FIRE (Financial Independence, Retire Early)**: A movement focused on aggressive saving and investing to retire well before traditional retirement age.",
    "roth conversion": "**Roth Conversion**: Moving money from a Traditional IRA/401(k) to a Roth account. You pay taxes now, but future growth and withdrawals are tax-free.",
    "roth conversion ladder": "**Roth Conversion Ladder**: A FIRE strategy of converting Traditional funds to Roth during low-income early retirement years, paying minimal taxes, then accessing those funds tax-free after 5 years.",
    "hsa": "**HSA (Health Savings Account)**: Triple tax-advantaged account for medical expenses. Contributions are pre-tax, growth is tax-free, and withdrawals for medical expenses are tax-free.",
    "401k": "**401(k)**: Employer-sponsored retirement savings plan with tax advantages. May include employer matching contributions. Annual contribution limit is $23,000 (2025) plus catch-up contributions if 50+.",
    "ira": "**IRA (Individual Retirement Account)**: Personal retirement savings account with tax advantages. Can be Traditional (pre-tax) or Roth (post-tax). Lower contribution limits than 401(k).",
    "social security": "**Social Security**: Federal retirement benefit based on your work history. Can claim as early as 62 (reduced) or delay until 70 (increased). Full retirement age is 66-67 for most people.",
    "medicare": "**Medicare**: Federal health insurance for people 65+. Part A (hospital) is usually free; Part B (medical) and Part D (drugs) have premiums.",
    "ltc": "**LTC (Long-Term Care)**: Extended care for people who can't perform daily activities independently. About 70% of people 65+ will need some form. Can be very expensive.",
    "net worth": "**Net Worth**: Total assets minus total liabilities. Includes investments, property, retirement accounts, minus any debts.",
    "asset allocation": "**Asset Allocation**: How you divide your investments among stocks, bonds, cash, and other assets. Key factor in risk and return.",
    "rebalancing": "**Rebalancing**: Periodically adjusting your portfolio back to your target asset allocation. Typically done annually or when allocations drift significantly.",
    "expense ratio": "**Expense Ratio**: Annual fee charged by mutual funds/ETFs as a percentage of assets. Lower is better. Index funds typically have the lowest ratios.",
    "index fund": "**Index Fund**: A mutual fund or ETF that tracks a market index (like S&P 500). Low cost, broad diversification, and historically outperforms most active managers.",
    "safe target": "**Safe Retirement Target (Earliest Safe Retirement)**: The minimum net-worth target at which you can retire and have your money last. Found via binary search between $500K–$6M, checking two conditions: (1) your portfolio survives a deterministic projection with your specific healthcare, tax, and LTC assumptions, and (2) your plan succeeds in 95%+ of all historical market sequences from 1928–2024. This is stricter than the 4% rule because it accounts for sequence-of-returns risk and your personal situation.",
    "earliest safe retirement": "**Earliest Safe Retirement**: The youngest age you can retire at and still have your portfolio last through your full plan. Calculated by finding the minimum net-worth target that passes both a deterministic stress test (your specific costs) and a historical Monte Carlo test (95%+ success across all market sequences since 1928). Use the 'Find my earliest safe retirement' button to calculate this.",
    "stress test": "**Stress Test**: In this app, testing your retirement plan against adverse conditions. The deterministic test checks if your portfolio survives with your specific healthcare and tax costs. The historical test replays your plan through every market sequence from 1928–2024 to see what percentage succeed.",
}


def lookup_glossary(term: str) -> dict:
    """Look up a retirement planning term in the glossary.

    Returns the definition if found, or suggests similar terms.
    """
    term_lower = term.lower().strip()

    # Direct lookup
    if term_lower in GLOSSARY:
        return {
            "term": term,
            "definition": GLOSSARY[term_lower],
        }

    # Partial match
    matches = [
        key for key in GLOSSARY.keys()
        if term_lower in key or key in term_lower
    ]

    if matches:
        # Return best match
        best_match = matches[0]
        return {
            "term": term,
            "closest_match": best_match,
            "definition": GLOSSARY[best_match],
        }

    # No match - list available terms
    return {
        "term": term,
        "error": f"Term '{term}' not found in glossary.",
        "available_terms": list(GLOSSARY.keys())[:10],
        "suggestion": "Try asking about: Roth, Traditional, RMD, 4% rule, glide path, or Monte Carlo.",
    }


# Field mapping: friendly names -> (input_key, widget_key, type, description)
FIELD_MAP = {
    # Age and timeline
    "current_age": ("current_age", None, int, "Your current age"),
    "end_age": ("in_EndAge", None, int, "Age when plan ends (life expectancy)"),
    "retirement_target": ("in_RetirementTarget", "retirement_target", float, "Net worth target to trigger retirement"),

    # Income
    "salary": ("in_Salary_Y1", "salary_y1", float, "Current annual salary"),
    "salary_year_1": ("in_Salary_Y1", "salary_y1", float, "Year 1 salary"),
    "salary_year_2": ("in_Salary_Y2", "salary_y2", float, "Year 2 salary"),
    "salary_year_3": ("in_Salary_Y3", "salary_y3", float, "Year 3 salary"),
    "salary_year_4": ("in_Salary_Y4", "salary_y4", float, "Year 4+ salary"),
    "salary_growth": ("in_SalaryGrowth", "salary_growth", float, "Annual salary growth rate (decimal, e.g., 0.03 for 3%)"),

    # Savings
    "annual_401k": ("in_401kContrib", "k401_contrib", float, "Annual 401(k) contribution"),
    "annual_401k_contribution": ("in_401kContrib", "k401_contrib", float, "Annual 401(k) contribution"),
    "roth_percentage": ("in_RothPct", "roth_pct", float, "Percentage of 401(k) going to Roth (decimal)"),

    # Spending
    "monthly_spending": ("in_MonthlyNonHousing", "non_housing", float, "Monthly non-housing spending"),
    "monthly_non_housing": ("in_MonthlyNonHousing", "non_housing", float, "Monthly non-housing spending"),
    "monthly_rent": ("in_MonthlyRent", "rent", float, "Monthly rent payment"),

    # Starting balances
    "starting_401k": ("in_401kStart", "k401_start", float, "Starting 401(k) balance"),
    "starting_roth": ("in_Roth401kStart", "roth401k_start", float, "Starting Roth 401(k) balance"),
    "starting_investments": ("in_InvestStart", "invest_start", float, "Starting taxable investment balance"),
    "starting_cash": ("in_CashStart", "cash_start", float, "Starting cash balance"),
    "starting_crypto": ("in_CryptoStart", "crypto_start", float, "Starting crypto balance"),

    # Returns
    "stock_return": ("in_StockReturn", "stock_ret", float, "Expected stock return (decimal)"),
    "bond_return": ("in_BondReturn", "bond_ret", float, "Expected bond return (decimal)"),

    # Social Security
    "social_security_age": ("in_SSAge", "ss_age", int, "Age to claim Social Security"),
    "social_security_benefit": ("in_SSBenefit", "ss_benefit", float, "Monthly Social Security benefit"),
}

# Validation rules: field -> (min, max, error_hint)
FIELD_VALIDATION = {
    "current_age": (18, 80, "Age must be between 18 and 80"),
    "end_age": (50, 120, "End age must be between 50 and 120"),
    "retirement_target": (0, 100_000_000, "Retirement target must be between $0 and $100M"),
    "salary": (0, 10_000_000, "Salary must be between $0 and $10M"),
    "salary_year_1": (0, 10_000_000, "Salary must be between $0 and $10M"),
    "salary_year_2": (0, 10_000_000, "Salary must be between $0 and $10M"),
    "salary_year_3": (0, 10_000_000, "Salary must be between $0 and $10M"),
    "salary_year_4": (0, 10_000_000, "Salary must be between $0 and $10M"),
    "salary_growth": (-0.5, 0.5, "Salary growth should be between -50% and 50% (use decimal: 0.03 for 3%)"),
    "annual_401k": (0, 75_000, "401(k) contribution must be between $0 and $75,000"),
    "annual_401k_contribution": (0, 75_000, "401(k) contribution must be between $0 and $75,000"),
    "roth_percentage": (0, 1, "Roth percentage must be between 0 and 1 (0.5 = 50%)"),
    "monthly_spending": (0, 100_000, "Monthly spending must be between $0 and $100,000"),
    "monthly_non_housing": (0, 100_000, "Monthly spending must be between $0 and $100,000"),
    "monthly_rent": (0, 50_000, "Monthly rent must be between $0 and $50,000"),
    "starting_401k": (0, 50_000_000, "Starting 401(k) must be between $0 and $50M"),
    "starting_roth": (0, 50_000_000, "Starting Roth must be between $0 and $50M"),
    "starting_investments": (0, 100_000_000, "Starting investments must be between $0 and $100M"),
    "starting_cash": (0, 10_000_000, "Starting cash must be between $0 and $10M"),
    "starting_crypto": (0, 10_000_000, "Starting crypto must be between $0 and $10M"),
    "stock_return": (-0.5, 0.5, "Stock return should be between -50% and 50% (use decimal: 0.07 for 7%)"),
    "bond_return": (-0.5, 0.5, "Bond return should be between -50% and 50% (use decimal: 0.04 for 4%)"),
    "social_security_age": (62, 70, "Social Security age must be between 62 and 70"),
    "social_security_benefit": (0, 10_000, "Social Security benefit must be between $0 and $10,000/month"),
}


def set_input(field: str, value: float | int | str) -> dict:
    """Set a single input field in the user's retirement plan.

    Args:
        field: The field name to set (e.g., "current_age", "monthly_spending", "annual_401k")
        value: The value to set

    Returns:
        Dict with success status and confirmation message
    """
    field_lower = field.lower().replace(" ", "_").replace("-", "_")

    # Find matching field
    field_info = FIELD_MAP.get(field_lower)
    if not field_info:
        # Try partial matching
        matches = [k for k in FIELD_MAP.keys() if field_lower in k or k in field_lower]
        if matches:
            field_info = FIELD_MAP[matches[0]]
            field_lower = matches[0]
        else:
            return {
                "error": f"Unknown field: {field}",
                "available_fields": list(FIELD_MAP.keys())[:15],
                "hint": "Try: current_age, monthly_spending, annual_401k, retirement_target, salary",
            }

    input_key, widget_key, field_type, description = field_info

    # Convert value to correct type
    try:
        typed_value = field_type(value)
    except (ValueError, TypeError):
        return {"error": f"Invalid value '{value}' for {field}. Expected {field_type.__name__}."}

    # Validate value is within acceptable range
    if field_lower in FIELD_VALIDATION:
        min_val, max_val, error_hint = FIELD_VALIDATION[field_lower]
        if typed_value < min_val or typed_value > max_val:
            return {
                "error": f"Value {typed_value} is out of range for {field}.",
                "hint": error_hint,
                "valid_range": {"min": min_val, "max": max_val},
            }

    # Cross-field validation
    inputs = st.session_state.get("inputs", {})
    current_age = st.session_state.get("current_age", 35)

    if field_lower == "end_age" and typed_value <= current_age:
        return {
            "error": f"End age ({typed_value}) must be greater than current age ({current_age}).",
            "hint": "Set end age to at least current age + 1.",
        }

    if field_lower == "current_age":
        end_age = inputs.get("in_EndAge", 95)
        if typed_value >= end_age:
            return {
                "error": f"Current age ({typed_value}) must be less than end age ({end_age}).",
                "hint": "Either lower current age or increase end age first.",
            }

    if field_lower == "social_security_age" and typed_value < current_age:
        return {
            "error": f"Social Security age ({typed_value}) cannot be less than current age ({current_age}).",
            "hint": "Set Social Security age to current age or later.",
        }

    # Handle current_age specially (it's in session_state directly, not in inputs)
    if input_key == "current_age":
        st.session_state.current_age = typed_value
        return {
            "success": True,
            "field": field,
            "value": typed_value,
            "message": f"Set {description} to {typed_value}",
        }

    # Set in inputs dict. If inputs is missing, try to restore from localStorage
    # before giving up — never silently create an empty dict, which would clobber
    # any saved scenario sitting in the browser.
    if "inputs" not in st.session_state:
        from .local_storage import restore_inputs_from_localstorage
        restore_inputs_from_localstorage()
    if "inputs" not in st.session_state:
        return {
            "error": "No scenario loaded. Please set up your inputs on the Planner page first.",
        }

    st.session_state.inputs[input_key] = typed_value

    # Also set widget key if it exists (so UI updates)
    if widget_key:
        st.session_state[widget_key] = typed_value

    # Format confirmation message
    if field_type == float and typed_value >= 1000:
        formatted_value = f"${typed_value:,.0f}"
    elif field_type == float and typed_value < 1:
        formatted_value = f"{typed_value:.1%}"
    else:
        formatted_value = str(typed_value)

    return {
        "success": True,
        "field": field,
        "value": typed_value,
        "message": f"Set {description} to {formatted_value}",
    }


def execute_tool(name: str, args: dict) -> Any:
    """Execute a tool by name with given arguments.

    Args:
        name: Tool function name
        args: Arguments dict from LLM

    Returns:
        Tool result (dict or list)
    """
    tools = {
        "set_input": set_input,
        "get_current_scenario": get_current_scenario,
        "run_what_if": run_what_if,
        "get_recommendations": get_recommendations,
        "find_safe_target": find_safe_target,
        "lookup_glossary": lookup_glossary,
    }

    if name not in tools:
        logger.warning(f"Unknown tool requested: {name}")
        return {"error": f"Unknown tool: {name}"}

    logger.info(f"Executing tool: {name} with args: {args}")
    try:
        result = tools[name](**args)
        logger.info(f"Tool {name} result: {str(result)[:200]}...")
        return result
    except Exception as e:
        logger.error(f"Tool {name} execution failed: {e}", exc_info=True)
        return {"error": f"Tool execution failed: {str(e)}"}
