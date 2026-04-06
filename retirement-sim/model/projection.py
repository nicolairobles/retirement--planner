"""
Year-by-year projection orchestrator.

Mirrors the Excel `Projection` sheet:
  - For each year from base_year to base_year + (end_age - current_age):
      determine phase (Working vs Retired)
      compute salary, expenses, income streams
      compute return on previous-year bucket balances
      compute withdrawal (retirement phase, grossed-up)
      compute end balance O = J + K + G - L - M - N
      split O into per-bucket balances (S, T, R, Q, P)

Produces a list of YearRecord instances that match the Excel Projection columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .allocation import blended_401k_rate, bond_share
from .expenses import annual_expenses, expense_breakdown
from .income import (
    disability_annual_income,
    other_stream_annual_income,
    ss_annual_income,
)
from .inputs import SeedCase
from .property import (
    mortgage_balance,
    mortgage_interest_for_year,
    property_market_value,
    property_outflow,
)
from .returns import BucketBalances, blended_return_dollars
from .tax import tax_on_taxable_income
from .rmd import rmd_amount
from .vehicle import VehicleParams, vehicle_cost
from .withdrawal import retirement_withdrawal


@dataclass
class YearRecord:
    """One year's projection output, mirroring Projection columns A-W."""
    year: int                # A
    age: int                 # B
    phase: str               # C — "Working" or "Retired"
    salary: float            # D
    living_expenses: float   # E
    contrib_401k: float      # F
    net_savings: float       # G
    ss_income: float         # H
    disability_income: float # I
    start_balance: float     # J
    annual_return: float     # K
    withdrawal: float        # L
    property_cost: float = 0.0  # M
    vehicle_cost: float = 0.0   # N
    end_balance: float = 0.0    # O (portfolio only)
    # Per-bucket breakdown
    stocks: float = 0.0      # P
    bonds: float = 0.0       # Q
    crypto: float = 0.0      # R
    cash: float = 0.0        # S
    k401: float = 0.0        # T — Traditional 401(k)
    roth_401k: float = 0.0   # T2 — Roth 401(k), tracked separately
    roth_conversion: float = 0.0  # Traditional→Roth transfer this year (taxable)
    # Property
    property_value: float = 0.0    # U (market value)
    mortgage_bal: float = 0.0      # V
    total_nw: float = 0.0          # W = O + U - V (used for retirement trigger + outputs)
    # Tax layer (Track B)
    taxable_income: float = 0.0  # Y
    federal_tax: float = 0.0     # Z
    # Other income streams (user-configurable)
    other_income_1: float = 0.0
    other_income_2: float = 0.0
    # Custom asset buckets (user-configurable, end-of-year balances)
    custom_asset_1_balance: float = 0.0
    custom_asset_2_balance: float = 0.0
    custom_asset_3_balance: float = 0.0
    # Expense breakdown (for visual transparency)
    expense_base: float = 0.0           # non-housing + housing (inflated)
    expense_mortgage: float = 0.0       # mortgage P&I
    expense_healthcare: float = 0.0     # healthcare costs
    expense_ltc: float = 0.0            # long-term care


def _salary_for_year(year_idx: int, seed: SeedCase) -> float:
    """Return salary for projection year index (0-based), mirroring Excel D3:D56.

    D3-D6 are hardcoded (year1..year4). D7+ grows from D6 by growth_rate.
    """
    s = seed.salary
    if year_idx == 0:
        return s.year1
    if year_idx == 1:
        return s.year2
    if year_idx == 2:
        return s.year3
    if year_idx == 3:
        return s.year4
    # D7+: grows from year4 by growth_rate, compounded
    return s.year4 * (1.0 + s.growth_rate) ** (year_idx - 3)


def _cash_reserve_target(year: int, seed: SeedCase) -> float:
    """Cash reserve = months × inflation-adjusted monthly expenses.

    Excel: (B27 + B28) * B46 * (1+B30)^(year - base_year)
    """
    e = seed.expenses
    monthly_total = e.monthly_non_housing + e.monthly_rent
    infl_factor = (1.0 + e.inflation) ** (year - seed.base_year)
    return monthly_total * seed.cash_reserve.months * infl_factor


def _split_buckets(
    end_balance: float,
    age: int,
    k401_value: float,
    cash_target: float,
    seed: SeedCase,
) -> BucketBalances:
    """Split end-balance O into per-bucket balances (S, T, R, Q, P).

    Excel order: S (cash), T (401k), R (crypto), Q (bonds), P (stocks residual).
    """
    if end_balance <= 0:
        return BucketBalances()

    # S: cash = min(target, O)
    cash = min(cash_target, end_balance)

    # T: 401k — cap at O, and zero if age >= access_age
    if age >= seed.retirement.k401_access_age:
        k401 = 0.0
    else:
        k401 = min(k401_value, end_balance)

    # R: crypto = (O - S - T) * crypto_pct
    rem_after_cash_k401 = max(end_balance - cash - k401, 0.0)
    crypto = rem_after_cash_k401 * seed.allocation.crypto_pct

    # Q: bonds = (O - S - T - R) * bshare
    bshare = bond_share(age, seed.allocation)
    rem_after_crypto = max(rem_after_cash_k401 - crypto, 0.0)
    bonds = rem_after_crypto * bshare

    # P: stocks = residual
    stocks = max(end_balance - bonds - crypto - cash - k401, 0.0)

    return BucketBalances(stocks=stocks, bonds=bonds, crypto=crypto, cash=cash, k401=k401)


def _initial_k401_balance(seed: SeedCase, year_idx: int) -> float:
    """401k balance target for year_idx (drives T column cap).

    Excel T3: (in_401kStart + F3) * (1 + k401_rate(age))
    Excel T4+: (T_prev + F4) * (1 + k401_rate(age))
    Capped at O in both cases, zero if age >= access_age.
    """
    # This function isn't used directly in the projection loop — T is
    # updated inline. Kept here as documentation of Excel's approach.
    raise NotImplementedError


def run_projection(seed: SeedCase) -> list[YearRecord]:
    """Run a deterministic year-by-year projection of a SeedCase.

    Returns a list of YearRecord with one entry per simulated year.
    Mirrors Excel Projection!A3:W56.
    """
    records: list[YearRecord] = []
    retired = False
    prev_buckets = BucketBalances()  # No prior-year balances in year 1
    k401_running = seed.starting_balances.k401        # Traditional 401(k), pre-access-age
    roth_401k_running = seed.starting_balances.roth_401k  # Roth 401(k), tax-free
    # Traditional balance that persists PAST access age for RMD tracking.
    # After access age, k401_running goes to 0 (merged into buckets), but we
    # still need to know how much of `end_balance` is Traditional for RMDs.
    traditional_running = seed.starting_balances.k401
    # Custom asset running balances (tracked outside the core waterfall)
    custom_balances = [
        seed.custom_asset_1.starting_balance if seed.custom_asset_1.enabled else 0.0,
        seed.custom_asset_2.starting_balance if seed.custom_asset_2.enabled else 0.0,
        seed.custom_asset_3.starting_balance if seed.custom_asset_3.enabled else 0.0,
    ]
    custom_assets = [seed.custom_asset_1, seed.custom_asset_2, seed.custom_asset_3]

    for year_idx in range(seed.years_simulated):
        year = seed.base_year + year_idx
        age = seed.current_age + year_idx

        # ----- Phase determination -----
        # Retired if: already retired, OR prior-year spendable NW >= target.
        #
        # Spendable NW = core portfolio + liquid custom assets ONLY.
        # Excludes: home equity (can't pay bills without selling), illiquid
        # custom assets (wealth you can't eat).
        #
        # This prevents the model from declaring "retirement" when most of
        # the user's net worth is locked up in real estate or collectibles.
        if not retired and records:
            prev = records[-1]
            liquid_custom = sum(
                bal for ca, bal in zip(
                    custom_assets,
                    [prev.custom_asset_1_balance, prev.custom_asset_2_balance, prev.custom_asset_3_balance],
                ) if ca.enabled and ca.liquid
            )
            # Spendable = core portfolio + liquid custom + Roth 401(k) (tax-free, spendable)
            spendable_nw = prev.end_balance + liquid_custom + prev.roth_401k
            if spendable_nw >= seed.retirement.net_worth_target:
                retired = True
        phase = "Retired" if retired else "Working"

        # ----- Income streams -----
        ss = ss_annual_income(year, seed.ss)
        disability = disability_annual_income(year, seed.disability)
        other_1 = other_stream_annual_income(year, seed.other_income_1, seed.base_year)
        other_2 = other_stream_annual_income(year, seed.other_income_2, seed.base_year)
        other_taxable = (
            (other_1 if seed.other_income_1.taxable else 0.0)
            + (other_2 if seed.other_income_2.taxable else 0.0)
        )
        other_nontaxable = (
            (other_1 if not seed.other_income_1.taxable else 0.0)
            + (other_2 if not seed.other_income_2.taxable else 0.0)
        )
        total_other = other_1 + other_2

        # ----- Salary (working) or zero (retired) -----
        if phase == "Working":
            salary = _salary_for_year(year_idx, seed)
            k401_contrib = seed.salary.annual_401k_contrib  # total (Trad + Roth)
            trad_contrib = seed.salary.traditional_contrib
            roth_contrib = seed.salary.roth_contrib
        else:
            salary = 0.0
            k401_contrib = 0.0
            trad_contrib = 0.0
            roth_contrib = 0.0

        # ----- Roth conversion (Traditional → Roth, taxable event) -----
        rc = seed.roth_conversion
        conversion_this_year = 0.0
        if rc.enabled and rc.start_year <= year <= rc.end_year:
            # Inflate the conversion amount from today's $ to this year's nominal
            inflated_conv = rc.amount_per_year * (
                (1.0 + seed.expenses.inflation) ** (year - seed.base_year)
            )
            # Can only convert what's actually in Traditional (use traditional_running
            # which tracks Traditional both pre- and post-access-age)
            conversion_this_year = min(inflated_conv, traditional_running)
            # Move from Traditional → Roth
            k401_running = max(k401_running - conversion_this_year, 0.0)
            traditional_running -= conversion_this_year
            roth_401k_running += conversion_this_year

        # ----- Living expenses -----
        exp_breakdown = expense_breakdown(year, seed.expenses, seed.prop, seed.healthcare, age, seed.ltc)
        expenses = exp_breakdown["total"]

        # ----- Portfolio return -----
        if year_idx == 0:
            # Special case: no prior-year buckets. Build allocation from starting balances.
            # Excel K3 builds a synthetic allocation from J3 + starting 401k.
            starting_portfolio = seed.total_starting_portfolio
            cash_target_y0 = _cash_reserve_target(year, seed)

            cash_d = min(cash_target_y0, starting_portfolio)
            k401_val_y0 = (
                seed.starting_balances.k401 + k401_contrib
                if age < seed.retirement.k401_access_age
                else 0.0
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
            annual_return = blended_return_dollars(synthetic, age, seed.returns, seed.allocation)
        else:
            # Excel K column uses PREVIOUS year's age for k401_rate in the return calc.
            # Rationale: the 401k balance carried into this year was invested under
            # the prior year's glide-path allocation, so it earns at that rate.
            annual_return = blended_return_dollars(prev_buckets, age - 1, seed.returns, seed.allocation)

        # ----- Start balance (J) -----
        if year_idx == 0:
            start_balance = seed.total_starting_portfolio
        else:
            start_balance = records[-1].end_balance

        # ----- Mortgage interest deduction -----
        # Post-TCJA (2018+): mortgage interest on up to $750K principal is
        # deductible IF you itemize. We compare interest vs standard deduction
        # and use whichever is larger.
        prop = seed.prop
        mtg_interest = mortgage_interest_for_year(
            year=year, buy_property=prop.buy_property,
            purchase_year=prop.purchase_year, property_cost=prop.cost,
            use_mortgage=prop.mortgage, down_payment=prop.down_payment,
            annual_rate=prop.mortgage_rate, term_years=prop.mortgage_term_years,
        )

        # ----- Federal tax on working-year salary -----
        # Tax calc: Traditional contrib is pre-tax (reduces taxable income).
        # Roth contrib is AFTER-tax (doesn't reduce taxable income).
        # Roth conversion (if any) adds to taxable income.
        std_ded = seed.tax.std_deduction(year)
        # Itemize vs standard: use whichever deduction is larger.
        # Post-TCJA the standard deduction is high enough that mortgage interest
        # only helps when it exceeds ~$15K (typically early mortgage years on
        # larger loans).
        effective_deduction = max(std_ded, mtg_interest)
        if phase == "Working":
            taxable_working = max(
                salary - trad_contrib + conversion_this_year - effective_deduction, 0.0
            )
            fed_tax_working = tax_on_taxable_income(taxable_working, year, seed.tax)
            # Net savings = salary - expenses - full 401k contrib (both types) - federal tax
            # (Both contribs leave the paycheck, only Traditional gets the tax benefit)
            net_savings = salary - expenses - k401_contrib - fed_tax_working
        else:
            # Retirement: still may have Roth conversion, which is taxable
            taxable_working = max(conversion_this_year - effective_deduction, 0.0) if conversion_this_year > 0 else 0.0
            fed_tax_working = tax_on_taxable_income(taxable_working, year, seed.tax) if taxable_working > 0 else 0.0
            net_savings = 0.0

        # ----- Withdrawal (retirement) -----
        if phase == "Retired":
            withdrawal, fed_tax_retired = retirement_withdrawal(
                spending_target=expenses,
                ss_income=ss,
                disability_income=disability,
                year=year,
                start_balance=start_balance,
                annual_return=annual_return,
                net_savings=0.0,
                tax_params=seed.tax,
                other_taxable_income=other_taxable,
                other_nontaxable_income=other_nontaxable,
            )
            # ----- RMD enforcement (age 73+) -----
            # If the natural withdrawal is less than the required RMD on the
            # Traditional balance, force the RMD amount. Extra RMD is forced
            # into spending or reinvestment, AND it's fully taxable.
            rmd_req = rmd_amount(traditional_running, age)
            rmd_forced_extra = max(rmd_req - withdrawal, 0.0)
            if rmd_forced_extra > 0:
                withdrawal += rmd_forced_extra
                # Reduce traditional balance by the forced amount
                traditional_running = max(traditional_running - rmd_forced_extra, 0.0)

            # Taxable income = W + SS + disability + other_taxable - deduction
            # (Roth withdrawals are subtracted from W later if implemented;
            # for now W is all traditional, so fully taxable.)
            # Use effective_deduction (max of std_ded, mortgage interest) already computed above
            taxable_retired = max(
                withdrawal + ss + disability + other_taxable - effective_deduction, 0.0
            )
            taxable_income = taxable_retired
            # If RMD forced extra taxable income, recompute tax
            if rmd_forced_extra > 0:
                federal_tax = tax_on_taxable_income(taxable_retired, year, seed.tax)
            else:
                federal_tax = fed_tax_retired
        else:
            withdrawal = 0.0
            taxable_income = taxable_working
            federal_tax = fed_tax_working

        # ----- Property outflow (M) and Vehicle cost (N) -----
        property_cost_this_year = property_outflow(
            year=year,
            buy_property=prop.buy_property,
            purchase_year=prop.purchase_year,
            property_cost=prop.cost,
            use_mortgage=prop.mortgage,
            down_payment=prop.down_payment,
            closing_cost_pct=prop.closing_cost_pct,
        )
        vehicle_this_year = vehicle_cost(
            year=year, age=age, params=seed.vehicle,
            inflation=seed.expenses.inflation, base_year=seed.base_year,
        )

        # ----- End balance (O) -----
        end_balance = max(
            start_balance + annual_return + net_savings - withdrawal
            - property_cost_this_year - vehicle_this_year,
            0.0,
        )

        # Reduce traditional balance proportionally to its share of the
        # pre-withdrawal portfolio, when a withdrawal occurs. This approximates
        # the tax fact that a portion of the withdrawal came from Traditional.
        if withdrawal > 0 and phase == "Retired":
            pre_withdrawal = start_balance + annual_return + net_savings
            if pre_withdrawal > 0:
                trad_share = min(traditional_running / pre_withdrawal, 1.0)
                trad_drawn = withdrawal * trad_share
                traditional_running = max(traditional_running - trad_drawn, 0.0)

        # ----- Update running 401k balances (Traditional + Roth) -----
        k401_rate = blended_401k_rate(
            age, seed.returns.stock_return, seed.returns.bond_return, seed.allocation
        )
        if age < seed.retirement.k401_access_age:
            # Pre-access: k401_running tracks the in-bucket 401k, mirrors traditional_running
            k401_running = (k401_running + trad_contrib) * (1.0 + k401_rate)
            traditional_running = k401_running
            roth_401k_running = (roth_401k_running + roth_contrib) * (1.0 + k401_rate)
        else:
            # Post-access: k401_running goes to 0 (merged into regular buckets).
            # But traditional_running keeps growing to track the Traditional portion
            # so we can apply RMDs. Roth stays separate (tax-free forever).
            k401_running = 0.0
            traditional_running = traditional_running * (1.0 + k401_rate)
            roth_401k_running = roth_401k_running * (1.0 + k401_rate)

        # ----- Per-bucket split -----
        cash_target = _cash_reserve_target(year, seed)
        buckets = _split_buckets(end_balance, age, k401_running, cash_target, seed)

        # Reconcile k401_running with the capped bucket value for next year's growth
        k401_running = buckets.k401

        # ----- Property market value (U) and mortgage balance (V) -----
        prop_market_value = property_market_value(
            year=year, buy_property=prop.buy_property,
            purchase_year=prop.purchase_year, property_cost=prop.cost,
            appreciation=prop.appreciation,
        )
        mtg_balance = mortgage_balance(
            year=year, buy_property=prop.buy_property,
            purchase_year=prop.purchase_year, property_cost=prop.cost,
            use_mortgage=prop.mortgage, down_payment=prop.down_payment,
            annual_rate=prop.mortgage_rate, term_years=prop.mortgage_term_years,
        )
        # ----- Custom asset buckets -----
        # Working years: add contributions, then grow at return rate.
        # Retirement years: grow at return rate (no contributions).
        # If the core portfolio couldn't fully cover the grossed-up withdrawal need,
        # draw the shortfall from liquid custom assets (proportionally).
        for i, ca in enumerate(custom_assets):
            if not ca.enabled:
                continue
            contrib = ca.annual_contribution if phase == "Working" else 0.0
            custom_balances[i] = (custom_balances[i] + contrib) * (1.0 + ca.return_rate)

        # If retired AND the withdrawal was capped below the true need, try to make
        # up the shortfall from liquid custom assets. (The withdrawal function caps
        # at J+K+G, so any shortfall = uncapped_need - actual_withdrawal.)
        # We detect this by comparing to a simple estimate: did end_balance hit 0?
        # Simpler: re-derive the grossed-up need and compute the shortfall.
        if phase == "Retired":
            from .withdrawal import retirement_withdrawal as _retire_calc
            # Recompute what the NEEDED withdrawal was (uncapped) by giving a huge cap
            needed_w, _ = _retire_calc(
                spending_target=expenses,
                ss_income=ss, disability_income=disability,
                year=year, start_balance=1e15, annual_return=0, net_savings=0,
                tax_params=seed.tax,
                other_taxable_income=other_taxable,
                other_nontaxable_income=other_nontaxable,
            )
            shortfall = max(needed_w - withdrawal, 0.0)
            # Roth 401(k) draws LAST (after core portfolio AND custom assets)
            # because Roth withdrawals are tax-free — preserve the tax-free
            # compounding as long as possible.
            if shortfall > 0:
                # Draw from liquid custom assets by user-configured priority.
                # Priority 1 drains first, 3 drains last. Ties broken by larger balance.
                liquid_idx = [
                    i for i, ca in enumerate(custom_assets)
                    if ca.enabled and ca.liquid and custom_balances[i] > 0
                ]
                liquid_idx.sort(key=lambda i: (custom_assets[i].draw_priority, -custom_balances[i]))
                for i in liquid_idx:
                    take = min(shortfall, custom_balances[i])
                    custom_balances[i] -= take
                    withdrawal += take
                    shortfall -= take
                    if shortfall <= 0:
                        break
            # If still short, tap Roth 401(k) (tax-free withdrawal)
            if shortfall > 0 and roth_401k_running > 0:
                take = min(shortfall, roth_401k_running)
                roth_401k_running -= take
                withdrawal += take
                shortfall -= take

        custom_total = sum(custom_balances)
        total_nw = end_balance + prop_market_value - mtg_balance + custom_total + roth_401k_running

        records.append(YearRecord(
            year=year, age=age, phase=phase,
            salary=salary, living_expenses=expenses, contrib_401k=k401_contrib,
            net_savings=net_savings, ss_income=ss, disability_income=disability,
            other_income_1=other_1, other_income_2=other_2,
            start_balance=start_balance, annual_return=annual_return,
            withdrawal=withdrawal,
            property_cost=property_cost_this_year, vehicle_cost=vehicle_this_year,
            end_balance=end_balance,
            stocks=buckets.stocks, bonds=buckets.bonds, crypto=buckets.crypto,
            cash=buckets.cash, k401=buckets.k401,
            roth_401k=roth_401k_running, roth_conversion=conversion_this_year,
            property_value=prop_market_value, mortgage_bal=mtg_balance, total_nw=total_nw,
            taxable_income=taxable_income, federal_tax=federal_tax,
            custom_asset_1_balance=custom_balances[0],
            custom_asset_2_balance=custom_balances[1],
            custom_asset_3_balance=custom_balances[2],
            expense_base=exp_breakdown["base"],
            expense_mortgage=exp_breakdown["mortgage"],
            expense_healthcare=exp_breakdown["healthcare"],
            expense_ltc=exp_breakdown["ltc"],
        ))

        prev_buckets = buckets

    return records
