"""
Rent-vs-buy comparison helper.

Runs the retirement model twice — once with the user's property purchase
enabled, once forced off — and surfaces the delta. The goal is to make the
housing tradeoff explicit: buying a house delays liquid-portfolio retirement,
but builds home equity that shows up in total net worth.

Also computes the opportunity cost of the down payment (what that cash would
have grown to if invested at the stock return rate instead).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))

from helpers.seeds import build_seedcase_from_inputs  # noqa: E402
from model.outputs import run_and_extract  # noqa: E402


@dataclass
class HousingScenarioResult:
    """Outcome of one housing scenario (rent or buy)."""
    retirement_age: int | None
    liquid_nw_at_end: float        # spendable (excludes home equity)
    home_equity_at_end: float
    total_nw_at_end: float
    max_sustainable_spend: float


@dataclass
class HousingComparison:
    """Side-by-side rent vs buy outcomes for current scenario."""
    rent: HousingScenarioResult
    buy: HousingScenarioResult
    down_payment: float
    down_payment_opportunity_cost: float  # what DP would have grown to in stocks
    years_simulated: int


def _result_from_outputs(outputs) -> HousingScenarioResult:
    return HousingScenarioResult(
        retirement_age=outputs.retirement_age,
        liquid_nw_at_end=outputs.liquid_nw_at_end,
        home_equity_at_end=outputs.home_equity_at_end,
        total_nw_at_end=outputs.nw_at_end,
        max_sustainable_spend=outputs.max_sustainable_spend,
    )


def compare_rent_vs_buy(inputs: dict, current_age: int) -> HousingComparison:
    """Run model twice: as-entered (buy) and with property forced off (rent).

    Returns both outcomes plus the opportunity cost of the down payment.
    Only meaningful when in_BuyProperty == 'Yes' in the input dict.
    """
    # Scenario 1: AS ENTERED (buy)
    buy_inputs = dict(inputs)
    buy_seed = build_seedcase_from_inputs(buy_inputs, current_age=current_age)
    buy_outputs = run_and_extract(buy_seed)

    # Scenario 2: FORCE RENT (buy_property=No, mortgage=No)
    rent_inputs = {**inputs, "in_BuyProperty": "No", "in_MortgageYN": "No"}
    rent_seed = build_seedcase_from_inputs(rent_inputs, current_age=current_age)
    rent_outputs = run_and_extract(rent_seed)

    # Opportunity cost of down payment: what that cash would have grown to
    # in stocks over the time from purchase to end-of-plan.
    property_cost = float(inputs.get("in_PropertyCost", 350_000))
    down_payment_pct = float(inputs.get("in_DownPaymentPct", 0.20))
    mortgage_on = inputs.get("in_MortgageYN", "No") == "Yes"
    # If no mortgage, "down payment" = full cash purchase
    down_payment = property_cost * down_payment_pct if mortgage_on else property_cost

    purchase_year = int(inputs.get("in_PropertyYear", 2035))
    end_age = int(inputs.get("in_EndAge", 90))
    base_year = 2025
    end_year = base_year + (end_age - current_age)
    years_compounding = max(0, end_year - purchase_year)

    stock_return = float(inputs.get("in_StockReturn", 0.07))
    opportunity_cost = down_payment * (1 + stock_return) ** years_compounding

    return HousingComparison(
        rent=_result_from_outputs(rent_outputs),
        buy=_result_from_outputs(buy_outputs),
        down_payment=down_payment,
        down_payment_opportunity_cost=opportunity_cost,
        years_simulated=end_year - base_year,
    )
