"""
Grossed-up retirement withdrawal calculation.

Mirrors Excel Projection column L (retirement years only):
  net_need = MAX(spending_target - SS - disability, 0)
  (two-pass fixed-point iteration)
  tax_estimate = TaxBracket(net_need + SS + disability - std_deduction_indexed)
  W1 = net_need + tax_estimate
  (second pass)
  tax2 = TaxBracket(W1 + SS + disability - std_deduction_indexed)
  W_grossed = net_need + tax2
  withdrawal = MIN(W_grossed, J + K + G)  # capped at available funds

Where J = start-of-year balance, K = year's return, G = working-year net savings
(G is 0 during retirement).
"""

from __future__ import annotations

from .tax import TaxParams, gross_up_withdrawal


def retirement_withdrawal(
    spending_target: float,
    ss_income: float,
    disability_income: float,
    year: int,
    start_balance: float,
    annual_return: float,
    net_savings: float = 0.0,
    tax_params: TaxParams | None = None,
    grossup_passes: int = 2,
    other_taxable_income: float = 0.0,
    other_nontaxable_income: float = 0.0,
) -> tuple[float, float]:
    """Compute grossed-up retirement withdrawal, capped at available funds.

    Returns (withdrawal, federal_tax_on_total_income).

    Args:
        spending_target: Target annual spending (nominal dollars this year).
        ss_income: Social Security annual (taxable under Moderate scope).
        disability_income: SSDI annual (taxable under Moderate scope).
        year: Calendar year (for tax bracket indexation).
        start_balance: J column — start-of-year portfolio.
        annual_return: K column — this year's dollar return.
        net_savings: G column — working-year net savings (0 in retirement).
        tax_params: TaxParams.
        grossup_passes: Number of fixed-point iterations (Excel = 2).
        other_taxable_income: Additional income stream(s) treated as taxable.
        other_nontaxable_income: Additional income stream(s) treated as non-taxable.

    Note: cap at (start_balance + annual_return + net_savings) before any
    withdrawal. In retirement, net_savings = 0 so the cap is J + K.
    """
    if tax_params is None:
        tax_params = TaxParams()

    all_income_in = ss_income + disability_income + other_taxable_income + other_nontaxable_income
    net_need = max(0.0, spending_target - all_income_in)
    total_taxable_other = ss_income + disability_income + other_taxable_income

    w_grossed, tax = gross_up_withdrawal(
        net_need, total_taxable_other, year, tax_params, passes=grossup_passes
    )

    max_withdrawable = start_balance + annual_return + net_savings
    withdrawal = min(w_grossed, max(0.0, max_withdrawable))

    # If capped below what we needed, tax estimate was computed on uncapped W.
    # Recompute tax at the actual withdrawal for accuracy.
    if withdrawal < w_grossed:
        std_ded = tax_params.std_deduction(year)
        from .tax import tax_on_taxable_income
        taxable = max(0.0, withdrawal + total_taxable_other - std_ded)
        tax = tax_on_taxable_income(taxable, year, tax_params)

    return withdrawal, tax
