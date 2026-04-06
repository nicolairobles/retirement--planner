"""
Federal income tax layer — Moderate scope.

Mirrors the Excel `TaxBracket` LAMBDA defined in v1.6_tax.xlsx:
  =LAMBDA(ti,year,
    LET(t,MAX(0,ti),
        idx,(1+in_BracketIndexation)^(year-in_TaxBaseYear),
        IF(t<=11925*idx, t*0.1,
        IF(t<=48475*idx, 1192.5*idx+(t-11925*idx)*0.12,
        ...etc 7 tiers...
        ))))

Simplifications (matching Track B Moderate scope):
  - 2025 single-filer brackets hardcoded
  - All brackets + standard deduction scale uniformly by (1 + indexation)^(year - base_year)
  - No LTCG differential, no SS taxability rules, no RMD, no AMT, no state tax
  - All income treated as ordinary taxable income
"""

from __future__ import annotations

from dataclasses import dataclass

# 2025 single-filer brackets, base-year values.
# Each entry: (marginal rate, lower bound, cumulative tax at lower bound, upper bound).
# Values taken from IRS Rev. Proc. 2024-40 (2025 tax year, single filer).
# Match Excel `TaxBracket` LAMBDA hardcoded thresholds.
# Note: IRS published cumulative values have minor rounding vs pure bracket-walk arithmetic
# (e.g., $188,769.25 vs $188,769.75 at the 37% threshold — $0.50 difference from IRS rounding).
# We use IRS-published values directly to match Excel.
_BRACKETS_2025_SINGLE: list[tuple[float, float, float, float]] = [
    #rate  lower         cum_at_lower   upper
    (0.10,       0.0,          0.00,    11_925.0),
    (0.12,  11_925.0,      1_192.50,    48_475.0),
    (0.22,  48_475.0,      5_578.50,   103_350.0),
    (0.24, 103_350.0,     17_651.00,   197_300.0),
    (0.32, 197_300.0,     40_199.00,   250_525.0),
    (0.35, 250_525.0,     57_231.00,   626_350.0),
    (0.37, 626_350.0,    188_769.25,  float("inf")),
]


@dataclass(frozen=True)
class TaxParams:
    """Parameters that define a year's tax calculation."""
    std_deduction_base: float = 15_000.0     # 2025 single standard deduction
    bracket_indexation: float = 0.025         # ~2.5% annual bracket growth (IRS CPI indexation)
    base_year: int = 2025

    def indexation_factor(self, year: int) -> float:
        """Multiplier that scales base-year brackets + std deduction to `year`."""
        return (1.0 + self.bracket_indexation) ** (year - self.base_year)

    def std_deduction(self, year: int) -> float:
        """Standard deduction in `year`-dollars."""
        return self.std_deduction_base * self.indexation_factor(year)


def tax_on_taxable_income(
    taxable_income: float,
    year: int,
    params: TaxParams | None = None,
) -> float:
    """Federal tax on a given taxable income, using indexed 2025 single brackets.

    Equivalent to Excel: `TaxBracket(taxable_income, year)`.

    Args:
        taxable_income: Taxable income in `year`-dollars (AFTER standard deduction).
        year: The tax year.
        params: TaxParams (defaults to Moderate-scope 2025 single).

    Returns:
        Federal tax owed in `year`-dollars.

    Examples:
        >>> round(tax_on_taxable_income(64_000, 2025), 2)
        8994.0
        >>> round(tax_on_taxable_income(0, 2025), 2)
        0.0
    """
    if params is None:
        params = TaxParams()

    ti = max(0.0, taxable_income)
    idx = params.indexation_factor(year)

    # Find the bracket `ti` falls in. Use IRS-published cum_at_lower directly
    # rather than re-summing to avoid rounding drift.
    for rate, lower_base, cum_at_lower_base, upper_base in _BRACKETS_2025_SINGLE:
        upper = upper_base * idx
        if ti <= upper:
            lower = lower_base * idx
            cum = cum_at_lower_base * idx
            return cum + (ti - lower) * rate

    # Unreachable: last tier has infinite upper bound.
    raise RuntimeError("Tax bracket walk failed to terminate")


def gross_up_withdrawal(
    net_need: float,
    other_taxable_income: float,
    year: int,
    params: TaxParams | None = None,
    passes: int = 2,
) -> tuple[float, float]:
    """Given a net-of-tax spending need, find the gross withdrawal that covers it.

    Mirrors the Excel formula in `Projection!L` for retirement years:
      W0 = net_need
      TI_1 = W0 + other_taxable_income - StdDed
      Tax_1 = TaxBracket(TI_1, year)
      W1 = W0 + Tax_1
      TI_2 = W1 + other_taxable_income - StdDed
      Tax_2 = TaxBracket(TI_2, year)
      W_grossed = W0 + Tax_2

    Args:
        net_need: Spending need NOT covered by other income (i.e., expenses - SS - disability).
        other_taxable_income: SS + disability (treated as ordinary in Moderate scope).
        year: Tax year.
        params: TaxParams.
        passes: Number of fixed-point iterations (Excel uses 2).

    Returns:
        (grossed_up_withdrawal, federal_tax_on_total_income)
    """
    if params is None:
        params = TaxParams()

    net = max(0.0, net_need)
    std_ded = params.std_deduction(year)

    withdrawal = net
    tax = 0.0
    for _ in range(passes):
        taxable = max(0.0, withdrawal + other_taxable_income - std_ded)
        tax = tax_on_taxable_income(taxable, year, params)
        withdrawal = net + tax

    return withdrawal, tax
