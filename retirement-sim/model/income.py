"""
Income streams: Social Security + SSDI (Disability).

Mirrors Excel Projection columns H (SS) and I (Disability).

**SS** (Excel H): starts at `base_year + SSAge - current_age`, grows with SSCola
compounded from BASE YEAR.

**Disability** (Excel I): runs from DisabStartYear to (DisabEndYear exclusive,
which equals SS start year by default), grows with DisabCola compounded from
DisabStartYear.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SSParams:
    """Social Security parameters."""
    eligible: bool = True
    benefit_monthly_today: float = 3350.0   # in_SSBenefit, monthly in base-year dollars
    cola: float = 0.02                       # in_SSCola
    start_age: int = 67                      # in_SSAge
    current_age: int = 37                    # in_CurrentAge (from B7)
    base_year: int = 2025                    # in_BaseYear (from B8)

    @property
    def start_year(self) -> int:
        """Calendar year SS benefits begin."""
        return self.base_year + self.start_age - self.current_age


@dataclass(frozen=True)
class DisabilityParams:
    """SSDI parameters."""
    eligible: bool = True
    benefit_monthly: float = 2800.0          # in_DisabBenefit, monthly in DisabStartYear $
    cola: float = 0.025                       # in_DisabCola
    start_year: int = 2030                    # in_DisabStartYear
    end_year: int = 2055                      # converts to SS at FRA; defaults to SS start


def ss_annual_income(year: int, params: SSParams) -> float:
    """Social Security income for a calendar year.

    Excel: IF(Eligible AND year >= start_year, benefit * 12 * (1+COLA)^(year - base_year), 0)

    Note: COLA compounds from base_year (2025), not from start_year. So when the benefit
    first begins, it has already been inflating for (start_year - base_year) years.
    """
    if not params.eligible or year < params.start_year:
        return 0.0
    return params.benefit_monthly_today * 12 * (1.0 + params.cola) ** (year - params.base_year)


def other_stream_annual_income(year: int, stream, base_year: int = 2025) -> float:
    """Annual dollar amount from a generic OtherIncomeStream in a given year.

    Benefit is stated as monthly in today's dollars; grows with COLA from
    base_year. Zero outside [start_year, end_year).
    """
    if not stream.enabled:
        return 0.0
    if year < stream.start_year or year >= stream.end_year:
        return 0.0
    return stream.monthly_today * 12 * (1.0 + stream.cola) ** (year - base_year)


def disability_annual_income(year: int, params: DisabilityParams) -> float:
    """Disability (SSDI) income for a calendar year.

    Excel: IF(Eligible AND start_year <= year < end_year,
              benefit * 12 * (1+COLA)^(year - start_year), 0)

    COLA compounds from start_year. `end_year` is exclusive (disability ceases
    when SS begins at full retirement age).
    """
    if not params.eligible:
        return 0.0
    if year < params.start_year or year >= params.end_year:
        return 0.0
    return params.benefit_monthly * 12 * (1.0 + params.cola) ** (year - params.start_year)
