"""
Annual living expenses — inflation-adjusted from base-year values.

Mirrors Excel Projection column E:
  Expenses = MAX((NonHousing + housing_cost(year)) * 12 * (1+Inflation)^(year-base_year), 0)
             + IF(mortgage_active, Mortgage_P_and_I * 12, 0)

Where housing_cost switches from MonthlyRent to MonthlyOwnershipCost once a
property is purchased.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpenseParams:
    """Living expense inputs."""
    monthly_non_housing: float = 1000.0     # in_MonthlyNonHousing
    monthly_rent: float = 1500.0             # in_MonthlyRent
    inflation: float = 0.03                  # in_Inflation
    base_year: int = 2025                    # in_BaseYear


@dataclass(frozen=True)
class LTCParams:
    """Long-term care event.

    Models a period of N years of elevated expenses (nursing home, in-home care,
    memory care facility). Median cost 2024: ~$9K/mo nursing home, ~$6K/mo
    assisted living, ~$5K/mo in-home care.

    70% of 65+ will need some form of LTC at some point; average duration 3 yrs.
    """
    enabled: bool = False
    monthly_cost: float = 8000.0       # today's dollars
    start_age: int = 82                # when LTC kicks in
    duration_years: int = 3            # how long LTC lasts


@dataclass(frozen=True)
class HealthcareParams:
    """Healthcare cost modeling (separate from general non-housing expenses).

    Pre-Medicare years (age < medicare_age): marketplace insurance +
    out-of-pocket. After medicare_age: Medicare Part B + D + Medigap.

    Healthcare inflates faster than general CPI (~5% vs ~3%), so it gets its
    own inflation rate.
    """
    enabled: bool = False
    monthly_pre_medicare: float = 1000.0   # $/mo before age 65 (today's dollars)
    monthly_medicare: float = 600.0         # $/mo from age 65+ (today's dollars)
    medicare_age: int = 65
    healthcare_inflation: float = 0.04      # annual inflation rate (healthcare-specific, BLS avg ~3.5%)


@dataclass(frozen=True)
class PropertyParams:
    """Property purchase + mortgage parameters."""
    buy_property: bool = False              # in_BuyProperty
    purchase_year: int = 2035                # in_PropertyYear
    cost: float = 350_000.0                  # in_PropertyCost
    monthly_ownership_cost: float = 2000.0   # in_MonthlyOwnershipCost (replaces rent after purchase)
    appreciation: float = 0.02               # in_PropertyAppreciation
    mortgage: bool = False                   # in_MortgageYN
    down_payment_pct: float = 0.20           # in_DownPaymentPct
    mortgage_rate: float = 0.065             # in_MortgageRate
    mortgage_term_years: int = 30            # in_MortgageTerm
    closing_cost_pct: float = 0.025          # buyer closing costs (% of purchase price)
    selling_cost_pct: float = 0.06           # costs to sell (agent + closing, % of future value)

    @property
    def down_payment(self) -> float:
        return self.cost * self.down_payment_pct

    @property
    def mortgage_monthly_p_and_i(self) -> float:
        """Computed monthly P&I (Excel B71 formula).

        Only non-zero when both buy_property and mortgage are True.
        """
        if not (self.buy_property and self.mortgage):
            return 0.0
        principal = self.cost - self.down_payment
        if principal <= 0 or self.mortgage_rate <= 0 or self.mortgage_term_years <= 0:
            return 0.0
        monthly_rate = self.mortgage_rate / 12.0
        n_months = self.mortgage_term_years * 12
        factor = (1 + monthly_rate) ** n_months
        return principal * monthly_rate * factor / (factor - 1.0)


def housing_cost_monthly(year: int, expenses: ExpenseParams, prop: PropertyParams) -> float:
    """Monthly housing cost for a given year (in base-year dollars, pre-inflation).

    Rent if not buying (or before purchase year). Ownership cost after purchase.
    """
    if prop.buy_property and year >= prop.purchase_year:
        return prop.monthly_ownership_cost
    return expenses.monthly_rent


def expense_breakdown(
    year: int,
    expenses: ExpenseParams,
    prop: PropertyParams | None = None,
    healthcare: HealthcareParams | None = None,
    age: int | None = None,
    ltc: "LTCParams | None" = None,
) -> dict[str, float]:
    """Detailed breakdown of annual expenses by category.

    Returns a dict with keys: base, mortgage, healthcare, ltc, total.
    Useful for displaying where money is going.
    """
    if prop is None:
        prop = PropertyParams()

    housing = housing_cost_monthly(year, expenses, prop)
    inflated = (
        (expenses.monthly_non_housing + housing)
        * 12
        * (1.0 + expenses.inflation) ** (year - expenses.base_year)
    )
    base = max(0.0, inflated)

    mortgage_active = (
        prop.buy_property
        and prop.mortgage
        and year >= prop.purchase_year
        and (year - prop.purchase_year) < prop.mortgage_term_years
    )
    mortgage = prop.mortgage_monthly_p_and_i * 12 if mortgage_active else 0.0

    hc = 0.0
    if healthcare is not None and healthcare.enabled and age is not None:
        monthly_hc = healthcare.monthly_pre_medicare if age < healthcare.medicare_age else healthcare.monthly_medicare
        hc = monthly_hc * 12 * (1.0 + healthcare.healthcare_inflation) ** (year - expenses.base_year)

    ltc_cost = 0.0
    if ltc is not None and ltc.enabled and age is not None:
        if ltc.start_age <= age < ltc.start_age + ltc.duration_years:
            ltc_cost = (
                ltc.monthly_cost * 12
                * (1.0 + expenses.inflation) ** (year - expenses.base_year)
            )

    total = base + mortgage + hc + ltc_cost
    return {
        "base": base, "mortgage": mortgage, "healthcare": hc, "ltc": ltc_cost,
        "total": total,
    }


def annual_expenses(
    year: int,
    expenses: ExpenseParams,
    prop: PropertyParams | None = None,
    healthcare: HealthcareParams | None = None,
    age: int | None = None,
    ltc: "LTCParams | None" = None,
) -> float:
    """Annual living expenses for a calendar year (nominal dollars of that year).

    Composed of:
      - Non-housing + housing (general inflation)
      - Mortgage P&I during amortization (nominal, not inflated — fixed payment)
      - Healthcare (healthcare-specific inflation, pre-Medicare vs Medicare split)
    """
    if prop is None:
        prop = PropertyParams()

    housing = housing_cost_monthly(year, expenses, prop)
    inflated = (
        (expenses.monthly_non_housing + housing)
        * 12
        * (1.0 + expenses.inflation) ** (year - expenses.base_year)
    )
    base_expenses = max(0.0, inflated)

    # Mortgage P&I active only during amortization period
    mortgage_active = (
        prop.buy_property
        and prop.mortgage
        and year >= prop.purchase_year
        and (year - prop.purchase_year) < prop.mortgage_term_years
    )
    mortgage_annual = prop.mortgage_monthly_p_and_i * 12 if mortgage_active else 0.0

    # Healthcare costs (separate inflation rate, pre/post Medicare split)
    healthcare_annual = 0.0
    if healthcare is not None and healthcare.enabled and age is not None:
        if age < healthcare.medicare_age:
            monthly_hc = healthcare.monthly_pre_medicare
        else:
            monthly_hc = healthcare.monthly_medicare
        healthcare_annual = (
            monthly_hc * 12
            * (1.0 + healthcare.healthcare_inflation) ** (year - expenses.base_year)
        )

    # Long-term care event
    ltc_annual = 0.0
    if ltc is not None and ltc.enabled and age is not None:
        if ltc.start_age <= age < ltc.start_age + ltc.duration_years:
            # Inflate at general inflation (LTC costs grow ~3-5%/yr; use general)
            ltc_annual = (
                ltc.monthly_cost * 12
                * (1.0 + expenses.inflation) ** (year - expenses.base_year)
            )

    return base_expenses + mortgage_annual + healthcare_annual + ltc_annual
