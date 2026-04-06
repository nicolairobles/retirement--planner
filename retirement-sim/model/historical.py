"""
Historical-sequence projection: runs the full Excel-parity model forward
using actual historical stock/bond returns and inflation instead of the
seed case's constant assumptions.

For Monte Carlo backtesting — given a historical starting year S, replay
the user's plan year-by-year using the actual returns from years S, S+1, ...

Preserves everything else from the deterministic model: glide path, tax
layer, grossed-up withdrawals, SS/SSDI timing, property/mortgage/vehicle.
Only the stock/bond/inflation values change per year.

Crypto return stays at seed.returns.crypto_return (no good historical series).
Cash return stays at seed.returns.cash_return.
"""

from __future__ import annotations

from dataclasses import dataclass

from .allocation import blended_401k_rate, bond_share
from .expenses import PropertyParams
from .income import disability_annual_income, ss_annual_income
from .inputs import SeedCase
from .property import (
    mortgage_balance,
    property_market_value,
    property_outflow,
)
from .returns import BucketBalances, ReturnParams, blended_return_dollars
from .tax import tax_on_taxable_income
from .vehicle import vehicle_cost
from .withdrawal import retirement_withdrawal


@dataclass
class HistoricalYear:
    """One historical year's economic data."""
    year: int
    sp500_return: float
    tbond_return: float
    inflation: float


@dataclass
class CycleResult:
    """Outcome of one historical-sequence cycle."""
    start_hist_year: int
    terminal_nw_real: float          # Terminal Total NW in START-YEAR real dollars
    terminal_nw_nominal: float       # Terminal Total NW in nominal dollars
    succeeded: bool                  # Did the portfolio survive to end_age?
    retired: bool                    # Did the plan ever reach retirement?
    retirement_age: int | None
    years_simulated: int
    cumulative_inflation: float      # To deflate nominal back to real


def _salary_for_year(year_idx: int, seed: SeedCase) -> float:
    s = seed.salary
    if year_idx == 0: return s.year1
    if year_idx == 1: return s.year2
    if year_idx == 2: return s.year3
    if year_idx == 3: return s.year4
    return s.year4 * (1.0 + s.growth_rate) ** (year_idx - 3)


def run_historical_cycle(seed: SeedCase, hist_sequence: list[HistoricalYear]) -> CycleResult:
    """Run one historical-sequence cycle using the full model.

    `hist_sequence` must have at least `seed.years_simulated` entries.
    Returns a CycleResult with terminal NW and survival info.
    """
    if len(hist_sequence) < seed.years_simulated:
        raise ValueError(
            f"Historical sequence too short: need {seed.years_simulated} years, got {len(hist_sequence)}"
        )

    # Pre-compute cumulative inflation for nominal→real conversion
    cum_inflation = 1.0
    for i in range(seed.years_simulated):
        cum_inflation *= (1.0 + hist_sequence[i].inflation)

    retired = False
    prev_buckets = BucketBalances()
    k401_running = seed.starting_balances.k401
    records_nw: list[float] = []  # track total_nw per year
    records_spendable: list[float] = []  # spendable NW (portfolio only) for trigger + success check
    retirement_age: int | None = None

    # For per-year inflation tracking: cumulative inflation factor from base_year
    cum_inflation_to_year = 1.0  # starts at 1.0 for year 0
    running_prop = seed.prop

    for year_idx in range(seed.years_simulated):
        hist = hist_sequence[year_idx]
        # model year (nominal calendar) vs historical year — we use MODEL years
        # for timing events (SS, disability, property purchase) because those are
        # calendar-anchored in the user's life.
        model_year = seed.base_year + year_idx
        age = seed.current_age + year_idx

        # Construct per-year ReturnParams using historical returns
        per_year_returns = ReturnParams(
            stock_return=hist.sp500_return,
            bond_return=hist.tbond_return,
            crypto_return=seed.returns.crypto_return,  # no historical series
            cash_return=seed.returns.cash_return,       # kept constant
        )

        # ----- Phase -----
        # Use spendable NW (portfolio only) not total NW — home equity can't
        # trigger retirement because it can't pay bills.
        if not retired and records_spendable:
            if records_spendable[-1] >= seed.retirement.net_worth_target:
                retired = True
                retirement_age = age
        phase = "Retired" if retired else "Working"

        # ----- Income -----
        ss = ss_annual_income(model_year, seed.ss)
        disability = disability_annual_income(model_year, seed.disability)

        # ----- Salary + 401k contrib -----
        if phase == "Working":
            salary = _salary_for_year(year_idx, seed)
            k401_contrib = seed.salary.annual_401k_contrib
        else:
            salary = 0.0
            k401_contrib = 0.0

        # ----- Expenses (inflated using HISTORICAL cumulative inflation) -----
        e = seed.expenses
        housing = (
            running_prop.monthly_ownership_cost
            if running_prop.buy_property and model_year >= running_prop.purchase_year
            else e.monthly_rent
        )
        # cum_inflation_to_year was updated at END of previous year, so it represents
        # inflation from base_year to START of current year. Use it as the multiplier.
        base_expenses = (e.monthly_non_housing + housing) * 12 * cum_inflation_to_year
        mortgage_active = (
            running_prop.buy_property and running_prop.mortgage
            and model_year >= running_prop.purchase_year
            and (model_year - running_prop.purchase_year) < running_prop.mortgage_term_years
        )
        mortgage_annual = running_prop.mortgage_monthly_p_and_i * 12 if mortgage_active else 0.0
        # Healthcare (separate inflation, pre/post Medicare split)
        healthcare_annual = 0.0
        hc = seed.healthcare
        if hc.enabled:
            monthly_hc = hc.monthly_pre_medicare if age < hc.medicare_age else hc.monthly_medicare
            # Use model-year-based inflation (not cum historical inflation for this line)
            healthcare_annual = (
                monthly_hc * 12
                * (1.0 + hc.healthcare_inflation) ** (model_year - seed.base_year)
            )
        # Long-term care
        ltc_annual = 0.0
        ltc = seed.ltc
        if ltc.enabled and ltc.start_age <= age < ltc.start_age + ltc.duration_years:
            ltc_annual = (
                ltc.monthly_cost * 12
                * (1.0 + e.inflation) ** (model_year - seed.base_year)
            )
        expenses = max(0.0, base_expenses) + mortgage_annual + healthcare_annual + ltc_annual

        # ----- Portfolio return -----
        if year_idx == 0:
            starting_portfolio = seed.total_starting_portfolio
            months = seed.cash_reserve.months
            cash_target_y0 = (e.monthly_non_housing + e.monthly_rent) * months * cum_inflation_to_year
            cash_d = min(cash_target_y0, starting_portfolio)
            k401_val_y0 = (
                seed.starting_balances.k401 + k401_contrib
                if age < seed.retirement.k401_access_age else 0.0
            )
            inv = max(starting_portfolio - cash_d - k401_val_y0, 0.0)
            crypto_d = inv * seed.allocation.crypto_pct
            rem = inv - crypto_d
            bshare = bond_share(age, seed.allocation)
            bond_d = rem * bshare
            stock_d = rem - bond_d
            synthetic = BucketBalances(
                stocks=stock_d, bonds=bond_d, crypto=crypto_d,
                cash=cash_d, k401=k401_val_y0,
            )
            annual_return = blended_return_dollars(synthetic, age, per_year_returns, seed.allocation)
        else:
            annual_return = blended_return_dollars(prev_buckets, age - 1, per_year_returns, seed.allocation)

        # ----- Start balance + net savings -----
        if year_idx == 0:
            start_balance = seed.total_starting_portfolio
        else:
            start_balance = records_end_balance[-1]  # defined below

        if phase == "Working":
            std_ded = seed.tax.std_deduction(model_year)
            taxable_working = max(salary - k401_contrib - std_ded, 0.0)
            fed_tax_working = tax_on_taxable_income(taxable_working, model_year, seed.tax)
            net_savings = salary - expenses - k401_contrib - fed_tax_working
        else:
            net_savings = 0.0

        # ----- Withdrawal -----
        if phase == "Retired":
            withdrawal, _ = retirement_withdrawal(
                spending_target=expenses, ss_income=ss, disability_income=disability,
                year=model_year, start_balance=start_balance, annual_return=annual_return,
                net_savings=0.0, tax_params=seed.tax,
            )
        else:
            withdrawal = 0.0

        # ----- Property + Vehicle outflows -----
        property_cost_this_year = property_outflow(
            year=model_year, buy_property=running_prop.buy_property,
            purchase_year=running_prop.purchase_year, property_cost=running_prop.cost,
            use_mortgage=running_prop.mortgage, down_payment=running_prop.down_payment,
            closing_cost_pct=running_prop.closing_cost_pct,
        )
        vehicle_this_year = vehicle_cost(
            year=model_year, age=age, params=seed.vehicle,
            inflation=e.inflation, base_year=seed.base_year,
        )

        # ----- End balance + total NW -----
        end_balance = max(
            start_balance + annual_return + net_savings - withdrawal
            - property_cost_this_year - vehicle_this_year,
            0.0,
        )

        # Track end balances for next iteration
        if year_idx == 0:
            records_end_balance = [end_balance]
        else:
            records_end_balance.append(end_balance)

        # 401k running
        if age < seed.retirement.k401_access_age:
            k401_rate = blended_401k_rate(age, per_year_returns.stock_return, per_year_returns.bond_return, seed.allocation)
            k401_running = (k401_running + k401_contrib) * (1.0 + k401_rate)
        else:
            k401_running = 0.0

        # Per-bucket split
        months = seed.cash_reserve.months
        cash_target = (e.monthly_non_housing + e.monthly_rent) * months * cum_inflation_to_year
        if end_balance <= 0:
            buckets = BucketBalances()
        else:
            cash = min(cash_target, end_balance)
            k401_bucket = min(k401_running, end_balance) if age < seed.retirement.k401_access_age else 0.0
            rem_after_cash_k401 = max(end_balance - cash - k401_bucket, 0.0)
            crypto = rem_after_cash_k401 * seed.allocation.crypto_pct
            bshare = bond_share(age, seed.allocation)
            rem_after_crypto = max(rem_after_cash_k401 - crypto, 0.0)
            bonds = rem_after_crypto * bshare
            stocks = max(end_balance - bonds - crypto - cash - k401_bucket, 0.0)
            buckets = BucketBalances(stocks=stocks, bonds=bonds, crypto=crypto, cash=cash, k401=k401_bucket)
            k401_running = buckets.k401

        # Property market value + mortgage balance for total NW
        prop_mv = property_market_value(
            year=model_year, buy_property=running_prop.buy_property,
            purchase_year=running_prop.purchase_year, property_cost=running_prop.cost,
            appreciation=running_prop.appreciation,
        )
        mtg_bal = mortgage_balance(
            year=model_year, buy_property=running_prop.buy_property,
            purchase_year=running_prop.purchase_year, property_cost=running_prop.cost,
            use_mortgage=running_prop.mortgage, down_payment=running_prop.down_payment,
            annual_rate=running_prop.mortgage_rate, term_years=running_prop.mortgage_term_years,
        )
        total_nw = end_balance + prop_mv - mtg_bal
        records_nw.append(total_nw)
        records_spendable.append(end_balance)  # portfolio only (excludes home equity)
        prev_buckets = buckets

        # Update cum_inflation for NEXT year's expense calc (applies this year's inflation)
        cum_inflation_to_year *= (1.0 + hist.inflation)

    terminal_nw_nominal = records_nw[-1]
    terminal_portfolio_nominal = records_spendable[-1]
    # Deflate to start-year real using cumulative historical inflation
    terminal_nw_real = terminal_nw_nominal / cum_inflation

    # Success = retirement reached AND portfolio never hit 0 during retirement.
    # Home equity / illiquid assets can't substitute for liquid portfolio.
    # Check: did the spendable balance drop to 0 at any point post-retirement?
    portfolio_exhausted = False
    if retired:
        # Scan from retirement onward; if spendable ever hit 0, exhausted
        for sp in records_spendable:
            if sp <= 1.0:  # rounding tolerance
                portfolio_exhausted = True
                break
    succeeded = retired and not portfolio_exhausted

    return CycleResult(
        start_hist_year=hist_sequence[0].year,
        terminal_nw_real=terminal_nw_real,
        terminal_nw_nominal=terminal_nw_nominal,
        succeeded=succeeded,
        retired=retired,
        retirement_age=retirement_age,
        years_simulated=seed.years_simulated,
        cumulative_inflation=cum_inflation,
    )
