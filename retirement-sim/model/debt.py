"""
Non-mortgage debt modeling: amortization, balances, and payments.

Supports credit cards, student loans, auto loans, personal loans, and
other consumer debt. Each debt amortizes independently with its own
rate, minimum payment, and optional extra payment.

The mortgage on a primary residence is handled separately in property.py.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---- Debt categories (for UI grouping and tax-deductibility logic) ----
DEBT_CATEGORIES = (
    "Credit Card",
    "Student Loan",
    "Auto Loan",
    "Personal Loan",
    "Medical Debt",
    "Other",
)


@dataclass(frozen=True)
class DebtParams:
    """A single non-mortgage debt.

    Models a standard amortizing or revolving debt with fixed monthly
    payments. The balance decreases each year by (payments - interest).
    Payoff timing is derived from the balance, rate, and payment level.

    Tax deductibility: only student loan interest qualifies (up to
    $2,500/year federal deduction, subject to income phase-outs which
    we ignore for planning-scope simplicity).
    """
    enabled: bool = False
    label: str = "Debt"
    category: str = "Other"               # one of DEBT_CATEGORIES
    current_balance: float = 0.0           # outstanding principal today
    interest_rate: float = 0.0             # annual APR (e.g., 0.065 = 6.5%)
    minimum_payment: float = 0.0           # monthly minimum payment
    extra_monthly_payment: float = 0.0     # additional monthly principal payment


# ---- Student loan interest deduction cap (IRC §221) ----
STUDENT_LOAN_INTEREST_DEDUCTION_CAP = 2_500.0


def debt_monthly_payment(debt: DebtParams) -> float:
    """Total monthly payment (minimum + extra)."""
    return debt.minimum_payment + debt.extra_monthly_payment


def debt_annual_payment(debt: DebtParams, balance: float) -> float:
    """Annual payment for a debt, capped at the remaining balance + interest.

    Returns the actual dollar amount leaving the portfolio this year.
    If the balance is small enough to be fully repaid mid-year, the
    payment is capped so we don't overpay.
    """
    if not debt.enabled or balance <= 0:
        return 0.0

    monthly_rate = debt.interest_rate / 12.0
    monthly_pmt = debt_monthly_payment(debt)

    # Walk 12 months to get exact annual payment (handles mid-year payoff)
    total_paid = 0.0
    bal = balance
    for _ in range(12):
        if bal <= 0:
            break
        month_interest = bal * monthly_rate
        # Payment covers interest first, remainder goes to principal
        pmt = min(monthly_pmt, bal + month_interest)
        total_paid += pmt
        bal = bal + month_interest - pmt

    return total_paid


def debt_annual_interest(debt: DebtParams, balance: float) -> float:
    """Total interest accrued over the year on the given starting balance.

    Walks 12 monthly periods for accuracy (handles mid-year payoff).
    """
    if not debt.enabled or balance <= 0 or debt.interest_rate <= 0:
        return 0.0

    monthly_rate = debt.interest_rate / 12.0
    monthly_pmt = debt_monthly_payment(debt)

    total_interest = 0.0
    bal = balance
    for _ in range(12):
        if bal <= 0:
            break
        month_interest = bal * monthly_rate
        total_interest += month_interest
        pmt = min(monthly_pmt, bal + month_interest)
        bal = bal + month_interest - pmt

    return total_interest


def debt_end_of_year_balance(debt: DebtParams, start_balance: float) -> float:
    """Balance remaining at end of year after 12 months of payments.

    Walks the same monthly loop as the other functions for consistency.
    """
    if not debt.enabled or start_balance <= 0:
        return 0.0

    monthly_rate = debt.interest_rate / 12.0
    monthly_pmt = debt_monthly_payment(debt)

    bal = start_balance
    for _ in range(12):
        if bal <= 0:
            return 0.0
        month_interest = bal * monthly_rate
        pmt = min(monthly_pmt, bal + month_interest)
        bal = bal + month_interest - pmt

    return max(0.0, bal)


def debt_is_active(debt: DebtParams, balance: float) -> bool:
    """Whether this debt still has an outstanding balance."""
    return debt.enabled and balance > 0.01


# ---- Payoff strategies ----
PAYOFF_STRATEGIES = ("none", "avalanche", "snowball")


def _strategy_order(debts: list[DebtParams], balances: list[float], strategy: str) -> list[int]:
    """Return debt indices sorted by strategy priority.

    Avalanche: highest interest rate first (mathematically optimal).
    Snowball: lowest balance first (psychologically motivating).
    Only includes enabled debts with a positive balance.
    """
    active = [
        i for i, (d, b) in enumerate(zip(debts, balances))
        if d.enabled and b > 0.01
    ]
    if strategy == "avalanche":
        # Highest rate first; ties broken by smallest balance
        active.sort(key=lambda i: (-debts[i].interest_rate, balances[i]))
    elif strategy == "snowball":
        # Lowest balance first; ties broken by highest rate
        active.sort(key=lambda i: (balances[i], -debts[i].interest_rate))
    return active


def apply_debt_strategy(
    debts: list[DebtParams],
    balances: list[float],
    strategy: str,
    extra_monthly_budget: float,
) -> tuple[list[float], list[float], float]:
    """Simulate one year (12 months) of debt payments under a payoff strategy.

    When strategy is "avalanche" or "snowball", the extra_monthly_budget is
    concentrated on the priority-1 debt (plus each debt's minimum payment).
    When a debt pays off mid-year, freed-up minimum + extra cascade to the
    next target — this is the core snowball/avalanche behavior.

    When strategy is "none", each debt uses its own minimum_payment +
    extra_monthly_payment independently (no cascading).

    Returns:
        (new_balances, annual_payments, total_interest)
        - new_balances: end-of-year balance per debt
        - annual_payments: total paid per debt this year
        - total_interest: combined interest across all debts
    """
    n = len(debts)
    bals = list(balances)
    payments = [0.0] * n
    interest_total = 0.0

    if strategy == "none":
        # Independent per-debt payments (original behavior)
        for i, d in enumerate(debts):
            if not d.enabled or bals[i] <= 0:
                continue
            monthly_rate = d.interest_rate / 12.0
            monthly_pmt = d.minimum_payment + d.extra_monthly_payment
            for _ in range(12):
                if bals[i] <= 0:
                    break
                mi = bals[i] * monthly_rate
                interest_total += mi
                pmt = min(monthly_pmt, bals[i] + mi)
                payments[i] += pmt
                bals[i] = bals[i] + mi - pmt
            bals[i] = max(0.0, bals[i])
        return bals, payments, interest_total

    # Strategy-based: walk 12 months with cascading
    order = _strategy_order(debts, balances, strategy)
    minimums = [d.minimum_payment if d.enabled else 0.0 for d in debts]
    rates = [d.interest_rate / 12.0 for d in debts]

    for _ in range(12):
        # Determine which debts are still active
        active = [i for i in range(n) if debts[i].enabled and bals[i] > 0.01]
        if not active:
            break

        # Determine the priority target (first in strategy order that's still active)
        target_idx = None
        for i in order:
            if bals[i] > 0.01:
                target_idx = i
                break

        # Calculate available extra: the global extra budget, plus minimums
        # from debts that have already been paid off (freed-up cash)
        freed_minimums = sum(minimums[i] for i in range(n) if debts[i].enabled and bals[i] <= 0.01)
        total_extra = extra_monthly_budget + freed_minimums

        for i in active:
            mi = bals[i] * rates[i]
            interest_total += mi
            if i == target_idx:
                # Target gets minimum + all extra
                pmt = min(minimums[i] + total_extra, bals[i] + mi)
            else:
                # Non-targets get minimum only
                pmt = min(minimums[i], bals[i] + mi)
            payments[i] += pmt
            bals[i] = bals[i] + mi - pmt

    bals = [max(0.0, b) for b in bals]
    return bals, payments, interest_total


def student_loan_interest_deduction(debts: list[DebtParams], balances: list[float]) -> float:
    """Annual student loan interest deduction (capped at $2,500).

    Only debts with category == "Student Loan" qualify. The deduction is
    an above-the-line deduction (reduces AGI), not an itemized deduction.
    """
    total = 0.0
    for debt, bal in zip(debts, balances):
        if debt.enabled and debt.category == "Student Loan" and bal > 0:
            total += debt_annual_interest(debt, bal)
    return min(total, STUDENT_LOAN_INTEREST_DEDUCTION_CAP)
