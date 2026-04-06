"""
Required Minimum Distributions (RMDs) from Traditional retirement accounts.

Starting at age 73 (SECURE Act 2.0 threshold), the IRS requires annual
withdrawals from Traditional 401(k) and IRA balances. The withdrawal amount
= balance / life_expectancy_divisor. Failure to take RMDs triggers a 25%
penalty.

This module provides the IRS Uniform Lifetime Table divisors (2022+ version).
Roth accounts are NOT subject to RMDs.
"""

from __future__ import annotations

# IRS Uniform Lifetime Table (2022+, per SECURE Act 2.0).
# Divisor by age. Withdraw balance / divisor.
# Source: IRS Publication 590-B, Appendix B, Table III.
IRS_UNIFORM_DIVISORS: dict[int, float] = {
    73: 26.5, 74: 25.5, 75: 24.6, 76: 23.7, 77: 22.9, 78: 22.0,
    79: 21.1, 80: 20.2, 81: 19.4, 82: 18.5, 83: 17.7, 84: 16.8,
    85: 16.0, 86: 15.2, 87: 14.4, 88: 13.7, 89: 12.9, 90: 12.2,
    91: 11.5, 92: 10.8, 93: 10.1, 94: 9.5, 95: 8.9, 96: 8.4,
    97: 7.8, 98: 7.3, 99: 6.8, 100: 6.4, 101: 6.0, 102: 5.6,
    103: 5.2, 104: 4.9, 105: 4.6, 106: 4.3, 107: 4.1, 108: 3.9,
    109: 3.7, 110: 3.5,
}

RMD_START_AGE = 73


def rmd_amount(traditional_balance: float, age: int) -> float:
    """Required minimum distribution for a given age and Traditional balance.

    Returns 0 if age < RMD_START_AGE or balance <= 0.
    Uses the IRS Uniform Lifetime Table.
    """
    if age < RMD_START_AGE or traditional_balance <= 0:
        return 0.0
    divisor = IRS_UNIFORM_DIVISORS.get(age)
    if divisor is None:
        # Age beyond table (111+): use conservative divisor
        divisor = 3.5
    return traditional_balance / divisor
