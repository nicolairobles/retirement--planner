"""
Unified input container for a retirement scenario.

Bundles all the dataclasses from other modules into one SeedCase that
the projection orchestrator can consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .allocation import AllocationParams
from .expenses import ExpenseParams, HealthcareParams, LTCParams, PropertyParams
from .income import DisabilityParams, SSParams
from .returns import ReturnParams
from .tax import TaxParams
from .vehicle import VehicleParams


@dataclass(frozen=True)
class CashReserveParams:
    """Cash reserve held at fixed months of inflated monthly expenses."""
    months: int = 6                  # in_CashReserveMonths
    cash_return: float = 0.02        # in_CashReturn (on the reserve)


@dataclass(frozen=True)
class RetirementTriggerParams:
    """When the simulation flips from Working to Retired."""
    net_worth_target: float = 1_300_000.0    # in_RetirementTarget
    k401_access_age: float = 59.5             # in_401kAccessAge


@dataclass(frozen=True)
class CustomAssetBucket:
    """User-defined asset outside the core stocks/bonds/crypto/cash/401k buckets.

    Examples: REIT, angel investments, collectibles, treasuries, private equity.
    Holds its own balance, grows at its own return rate, optionally accepts
    annual contributions. If `liquid`, can be drawn down during retirement
    AND counts toward the retirement-target trigger. If illiquid, it just
    appreciates and adds to estate value (it can't pay bills).
    """
    enabled: bool = False
    name: str = "Custom Asset"
    starting_balance: float = 0.0
    annual_contribution: float = 0.0
    return_rate: float = 0.05
    liquid: bool = True
    draw_priority: int = 2  # 1 = draw first, 3 = draw last (when liquid)


@dataclass(frozen=True)
class OtherIncomeStream:
    """Generic annual income stream (rental, pension, side business, alimony, etc.).

    Amount is expressed in TODAY'S dollars; grown annually by `cola`.
    Runs from `start_year` (inclusive) to `end_year` (exclusive).
    """
    enabled: bool = False
    label: str = "Other Income"
    monthly_today: float = 0.0    # amount in today's dollars, per month
    cola: float = 0.02             # annual growth (typically tracks CPI)
    start_year: int = 2030
    end_year: int = 2090
    taxable: bool = True           # adds to taxable_income in Moderate scope


@dataclass(frozen=True)
class StartingBalances:
    """Portfolio state at the start of the plan.

    The `k401` field represents the TRADITIONAL 401(k) balance.
    `roth_401k` is the Roth portion.
    """
    k401: float = 99_711.0           # in_401kStart — Traditional 401(k)
    roth_401k: float = 0.0            # in_Roth401kStart — Roth 401(k)
    investments: float = 190_000.0   # in_InvestStart
    cash: float = 60_000.0            # in_CashStart
    crypto: float = 25_000.0         # in_CryptoStart


@dataclass(frozen=True)
class RothConversionParams:
    """Annual Roth conversion ladder.

    Converts `amount_per_year` from Traditional 401(k) to Roth 401(k) each year
    between start_year and end_year (inclusive). Each conversion is a taxable
    event in the year it happens (Traditional → Roth).

    Typical use case: retire at 50, convert Traditional balances in low-income
    years before SS kicks in at 67, pay tax at low marginal rates.
    """
    enabled: bool = False
    amount_per_year: float = 0.0   # today's dollars, grows with inflation
    start_year: int = 2040
    end_year: int = 2050


@dataclass(frozen=True)
class SalarySchedule:
    """Explicit year-by-year salaries for the first N years, then growth-based.

    Mirrors Excel's Projection!D3:D6 hardcoding with D7+ growth formula.
    """
    year1: float = 102_000.0     # Projection!D3 (year = base_year, typically 2025)
    year2: float = 102_000.0     # D4
    year3: float = 102_000.0     # D5
    year4: float = 102_000.0     # D6
    growth_rate: float = 0.03    # in_SalaryGrowth (applies to D7+)
    annual_401k_contrib: float = 23_000.0  # in_401kContrib (total, split by roth_contribution_pct)
    roth_contribution_pct: float = 0.0     # 0.0 = all Traditional, 1.0 = all Roth

    @property
    def traditional_contrib(self) -> float:
        """Portion of annual_401k_contrib that goes to Traditional 401(k) (pre-tax)."""
        return self.annual_401k_contrib * (1.0 - self.roth_contribution_pct)

    @property
    def roth_contrib(self) -> float:
        """Portion of annual_401k_contrib that goes to Roth 401(k) (after-tax)."""
        return self.annual_401k_contrib * self.roth_contribution_pct


@dataclass(frozen=True)
class SeedCase:
    """All parameters needed to run a projection."""
    # Timing
    base_year: int = 2025            # in_CurrentYear (from B8)
    current_age: int = 37            # in_CurrentAge (from B7)
    end_age: int = 90                # in_EndAge

    # Component parameter bundles
    starting_balances: StartingBalances = field(default_factory=StartingBalances)
    salary: SalarySchedule = field(default_factory=SalarySchedule)
    expenses: ExpenseParams = field(default_factory=ExpenseParams)
    prop: PropertyParams = field(default_factory=PropertyParams)
    returns: ReturnParams = field(default_factory=ReturnParams)
    allocation: AllocationParams = field(default_factory=AllocationParams)
    cash_reserve: CashReserveParams = field(default_factory=CashReserveParams)
    ss: SSParams = field(default_factory=SSParams)
    disability: DisabilityParams = field(default_factory=DisabilityParams)
    tax: TaxParams = field(default_factory=TaxParams)
    retirement: RetirementTriggerParams = field(default_factory=RetirementTriggerParams)
    vehicle: VehicleParams = field(default_factory=VehicleParams)
    other_income_1: OtherIncomeStream = field(default_factory=OtherIncomeStream)
    other_income_2: OtherIncomeStream = field(default_factory=OtherIncomeStream)
    custom_asset_1: CustomAssetBucket = field(default_factory=CustomAssetBucket)
    custom_asset_2: CustomAssetBucket = field(default_factory=CustomAssetBucket)
    custom_asset_3: CustomAssetBucket = field(default_factory=CustomAssetBucket)
    roth_conversion: RothConversionParams = field(default_factory=RothConversionParams)
    healthcare: HealthcareParams = field(default_factory=HealthcareParams)
    ltc: LTCParams = field(default_factory=LTCParams)

    @property
    def total_starting_portfolio(self) -> float:
        """Sum of all starting buckets — equals Excel J3 after Fix #7."""
        b = self.starting_balances
        return b.k401 + b.investments + b.cash + b.crypto

    @property
    def end_year(self) -> int:
        """Calendar year the plan ends (age = end_age)."""
        return self.base_year + self.end_age - self.current_age

    @property
    def years_simulated(self) -> int:
        """Number of years in the projection (inclusive)."""
        return self.end_age - self.current_age + 1
