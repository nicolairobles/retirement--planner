"""
High-level projection outputs — mirror Excel Assumptions!B142-B147.

These wrap a list of YearRecord and extract the key metrics:
  - retirement_year / retirement_age: first year where phase flips to Retired
  - nw_at_end: terminal Total NW (Excel W column at end-age row)
  - max_sustainable_spend: Excel's PMT-based max-spend calculation
  - lifetime_federal_tax: sum of Z column across all years
"""

from __future__ import annotations

from dataclasses import dataclass

from .inputs import SeedCase
from .projection import YearRecord  # noqa: F401  (used by dataclass field type)


@dataclass
class ProjectionOutputs:
    retirement_year: int | None
    retirement_age: int | None
    nw_at_end: float
    active_spend: float
    lifetime_federal_tax: float
    final_record: YearRecord
    records: list[YearRecord]
    portfolio_exhausted_age: int | None = None   # first age where portfolio hit 0 during retirement
    home_equity_at_end: float = 0.0
    liquid_nw_at_end: float = 0.0   # spendable NW at end (excludes home equity + illiquid custom)
    max_sustainable_spend: float = 0.0   # annual spend in today's $ that plan supports at 0 terminal
    lifetime_state_tax: float = 0.0

    @property
    def retired(self) -> bool:
        return self.retirement_year is not None

    @property
    def portfolio_exhausted(self) -> bool:
        return self.portfolio_exhausted_age is not None


def extract_outputs(records: list[YearRecord], seed: SeedCase) -> ProjectionOutputs:
    """Extract high-level outputs from a projection."""
    # Find retirement
    retired_idx = next(
        (i for i, r in enumerate(records) if r.phase == "Retired"), None
    )
    if retired_idx is not None:
        retirement_year = records[retired_idx].year
        retirement_age = records[retired_idx].age
    else:
        retirement_year = None
        retirement_age = None

    # Active spend = first retirement year's living expenses (closest to Excel B145)
    # Excel B145 is either Active Spend input or Maximize override.
    # For deterministic model, active spend equals expenses at retirement.
    if retired_idx is not None:
        active_spend_nominal = records[retired_idx].living_expenses
        # Deflate to base year for comparison with Excel B145 (today's dollars)
        years_since_base = records[retired_idx].year - seed.base_year
        active_spend = active_spend_nominal / (1 + seed.expenses.inflation) ** years_since_base
    else:
        active_spend = 0.0

    # Find terminal record (where age == end_age)
    final = records[-1]

    lifetime_tax = sum(r.federal_tax for r in records)
    lifetime_state = sum(r.state_tax for r in records)

    # Track first age where portfolio hit 0 during retirement
    exhausted_age = None
    if retired_idx is not None:
        for r in records[retired_idx:]:
            if r.end_balance <= 1.0:
                exhausted_age = r.age
                break

    # Home equity + liquid NW at end
    # Reduce home equity by selling costs (agent commissions, closing costs)
    # so the reported value represents what you'd actually receive if sold.
    raw_equity = max(final.property_value - final.mortgage_bal, 0.0)
    selling_cost_pct = seed.prop.selling_cost_pct if seed.prop.buy_property else 0.0
    home_equity_end = raw_equity * (1.0 - selling_cost_pct)
    # Spendable = core portfolio + Roth 401k (tax-free, counts as spendable)
    # Include spouse 401k + Roth as spendable (shared household finances)
    liquid_nw_end = (
        final.end_balance + final.roth_401k
        + final.spouse_k401 + final.spouse_roth_401k
    )

    # Max sustainable annual spend (today's dollars)
    # Computed via binary search: what constant real spending level exactly
    # depletes the portfolio at end-of-plan? This is the key planning number.
    max_spend = _compute_max_sustainable_spend(seed)

    return ProjectionOutputs(
        retirement_year=retirement_year,
        retirement_age=retirement_age,
        nw_at_end=final.total_nw,  # Total NW including property equity
        active_spend=active_spend,
        lifetime_federal_tax=lifetime_tax,
        final_record=final,
        records=records,
        portfolio_exhausted_age=exhausted_age,
        home_equity_at_end=home_equity_end,
        liquid_nw_at_end=liquid_nw_end,
        max_sustainable_spend=max_spend,
        lifetime_state_tax=lifetime_state,
    )


def _compute_max_sustainable_spend(seed: SeedCase) -> float:
    """Binary search for the max annual spend (today's $) the plan supports.

    Replaces user's monthly expenses with a candidate spend level, re-runs
    the projection, and finds the largest value where spendable portfolio
    stays non-zero throughout retirement.
    """
    from dataclasses import replace
    from .expenses import ExpenseParams
    from .projection import run_projection

    # Binary search: low = $0 (always works), high = 5x current or $500K
    current_monthly_total = seed.expenses.monthly_non_housing + seed.expenses.monthly_rent
    low = 0.0
    high = max(current_monthly_total * 12 * 5, 500_000)

    def portfolio_survives(annual_spend: float) -> bool:
        # Split spend between non-housing and rent proportionally
        monthly = annual_spend / 12.0
        ratio = (seed.expenses.monthly_non_housing / current_monthly_total
                 if current_monthly_total > 0 else 0.4)
        new_expenses = replace(
            seed.expenses,
            monthly_non_housing=monthly * ratio,
            monthly_rent=monthly * (1 - ratio),
        )
        test_seed = replace(seed, expenses=new_expenses)
        test_records = run_projection(test_seed)
        # Find retirement phase
        retired_records = [r for r in test_records if r.phase == "Retired"]
        if not retired_records:
            # Plan never retires at this spend level — counts as "doesn't survive"
            return False
        # Check that portfolio stays > 0 throughout retirement
        return all(r.end_balance > 1.0 for r in retired_records)

    # Binary search ~20 iterations = $0.50 precision
    for _ in range(20):
        if high - low < 100:
            break
        mid = (low + high) / 2.0
        if portfolio_survives(mid):
            low = mid
        else:
            high = mid
    return low


def run_and_extract(seed: SeedCase) -> ProjectionOutputs:
    """Convenience: run projection and extract outputs in one call."""
    from .projection import run_projection
    records = run_projection(seed)
    return extract_outputs(records, seed)
