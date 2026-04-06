"""Withdrawal module tests — grossed-up withdrawal + availability cap."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.tax import TaxParams, tax_on_taxable_income  # noqa: E402
from model.withdrawal import retirement_withdrawal  # noqa: E402


class TestRetirementWithdrawal(unittest.TestCase):

    def test_no_spending_no_withdrawal(self):
        w, tax = retirement_withdrawal(0, 0, 0, 2036, 1_000_000, 40_000)
        self.assertAlmostEqual(w, 0.0, places=2)
        self.assertAlmostEqual(tax, 0.0, places=2)

    def test_income_covers_spending_no_withdrawal(self):
        """If SS + disability >= spending, no portfolio withdrawal needed (but income is still taxed)."""
        w, tax = retirement_withdrawal(
            spending_target=30_000, ss_income=40_000, disability_income=0,
            year=2055, start_balance=1_000_000, annual_return=40_000,
        )
        # net_need = max(30000 - 40000, 0) = 0, so W grosses up to 0 + tax
        # But our income is still taxed: TI = 0 + 40000 - std_ded_2055
        # Actually: if net_need = 0, W starts at 0 and grosses up by tax on (0 + 40000 - std_ded)
        # std_ded in 2055 = 15000 * (1.025)^30 ≈ 31,458
        # TI = 40000 - 31458 = 8542
        # tax = 8542 * 0.10 = 854
        # W after 1 pass = 0 + 854 = 854
        # 2nd pass: TI = 854 + 40000 - 31458 = 9396
        # tax = 9396 * 0.10 = 940
        # W = 0 + 940 = 940
        # Our withdrawal covers the tax owed on the untaxed SS income.
        self.assertGreater(w, 0)
        self.assertLess(w, 2_000)  # small amount, covering tax on SS surplus

    def test_grossed_up_covers_target_after_tax(self):
        """After-tax spending should match target, within 2-pass tolerance."""
        target = 40_000
        ss = 20_000
        disability = 0
        w, tax = retirement_withdrawal(target, ss, disability, 2040, 1_000_000, 60_000)
        # (W + SS + disab - tax) should approximately equal target
        # (withdrawal satisfies net_need after tax)
        after_tax_income = w + ss + disability - tax
        # target = expenses, so after_tax income should cover expenses
        self.assertAlmostEqual(after_tax_income, target, delta=100)

    def test_capped_at_available_funds(self):
        """If W grossed-up exceeds available, cap at (J+K+G)."""
        # Small portfolio, large spending target
        w, tax = retirement_withdrawal(
            spending_target=500_000, ss_income=0, disability_income=0,
            year=2040, start_balance=100_000, annual_return=5_000,
        )
        # Available = 100,000 + 5,000 = 105,000
        self.assertLessEqual(w, 105_000)

    def test_capped_withdrawal_recomputes_tax(self):
        """When withdrawal is capped, tax is recomputed at the ACTUAL withdrawal."""
        w, tax = retirement_withdrawal(
            spending_target=500_000, ss_income=0, disability_income=0,
            year=2040, start_balance=100_000, annual_return=5_000,
        )
        self.assertAlmostEqual(w, 105_000, places=2)
        # Verify tax is what you'd compute for this exact W
        tp = TaxParams()
        std_ded = tp.std_deduction(2040)
        expected_tax = tax_on_taxable_income(max(0, w - std_ded), 2040, tp)
        self.assertAlmostEqual(tax, expected_tax, places=2)

    def test_working_year_net_savings_included_in_cap(self):
        """When net_savings > 0 (working phase), cap = J + K + G."""
        w, tax = retirement_withdrawal(
            spending_target=50_000, ss_income=0, disability_income=0,
            year=2040, start_balance=100_000, annual_return=5_000, net_savings=20_000,
        )
        # Cap should now be 125,000 (100 + 5 + 20)
        self.assertLessEqual(w, 125_000)


if __name__ == "__main__":
    unittest.main()
