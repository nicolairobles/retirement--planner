"""
Self-employment tax and deductions.

Models:
  - SE tax: 15.3% on first $168,600 (2025, indexed), 2.9% above
  - Deductible half of SE tax (above-the-line)
  - SEP-IRA contribution: up to 25% of net SE income, capped at $69K (2025)
  - QBI deduction: 20% of qualified business income (simplified, no phase-out)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SEIncomeParams:
    """Self-employment income parameters."""
    enabled: bool = False
    annual_net_income: float = 0.0    # net SE income in today's dollars
    growth_rate: float = 0.03         # annual growth of SE income
    start_year: int = 2025
    end_year: int = 2060              # year SE income stops (retirement, sells business, etc.)
    sep_ira_pct: float = 0.25         # SEP-IRA contribution rate (max 25%)
    sep_ira_annual_cap: float = 69_000.0  # 2025 IRS limit
    qbi_eligible: bool = True         # qualifies for 20% QBI deduction


# 2025 Social Security wage base for SE tax
_SS_WAGE_BASE_2025 = 168_600.0
_SS_WAGE_BASE_GROWTH = 0.03  # approximate annual indexation


def se_income_for_year(year: int, params: SEIncomeParams, base_year: int = 2025) -> float:
    """SE net income for a given year, inflated from today's dollars."""
    if not params.enabled or year < params.start_year or year >= params.end_year:
        return 0.0
    return params.annual_net_income * (1.0 + params.growth_rate) ** (year - base_year)


def se_tax(net_se_income: float, year: int, base_year: int = 2025) -> float:
    """Self-employment tax: 15.3% on earnings up to SS wage base, 2.9% above.

    The 15.3% is 12.4% Social Security + 2.9% Medicare.
    Above the wage base, only the 2.9% Medicare portion applies.
    """
    if net_se_income <= 0:
        return 0.0
    # Index the wage base forward
    wage_base = _SS_WAGE_BASE_2025 * (1.0 + _SS_WAGE_BASE_GROWTH) ** (year - base_year)
    if net_se_income <= wage_base:
        return net_se_income * 0.153
    return wage_base * 0.153 + (net_se_income - wage_base) * 0.029


def se_deduction(se_tax_amount: float) -> float:
    """Deductible half of SE tax (above-the-line deduction)."""
    return se_tax_amount * 0.5


def sep_ira_contribution(net_se_income: float, params: SEIncomeParams) -> float:
    """SEP-IRA contribution: min(income * rate, annual cap)."""
    if not params.enabled or net_se_income <= 0:
        return 0.0
    return min(net_se_income * params.sep_ira_pct, params.sep_ira_annual_cap)


def qbi_deduction(net_se_income: float, params: SEIncomeParams) -> float:
    """Qualified Business Income deduction: 20% of QBI (simplified, no phase-out).

    The actual QBI deduction has income-based phase-outs and specified-service
    trade restrictions. This simplified version is sufficient for planning.
    """
    if not params.enabled or not params.qbi_eligible or net_se_income <= 0:
        return 0.0
    return net_se_income * 0.20
