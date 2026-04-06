"""
Tax module parity tests vs the Excel `TaxBracket` LAMBDA.

Excel truth values captured from v1.6_tax.xlsx during Track B build:
  TaxBracket(64000, 2025) = 8994.00
  TaxBracket(64000, 2035) = 7569.49 (same nominal income, 10 years of 2.5% bracket indexation)

Also verifies internal consistency: bracket boundaries, zero/negative inputs, gross-up convergence.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

# Allow running tests directly without installing the package.
MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.tax import (  # noqa: E402
    TaxParams,
    gross_up_withdrawal,
    tax_on_taxable_income,
)


class TestTaxBracketExcelParity(unittest.TestCase):
    """Python output must match the Excel TaxBracket LAMBDA for known values."""

    def test_64k_in_2025_matches_excel(self):
        """$64K taxable in 2025 → $8,994 (Excel: $8,994.00)."""
        result = tax_on_taxable_income(64_000, 2025)
        # Expected: 1192.50 (10% on first 11925) + 4386 (12% on next 36550) + 3415.50 (22% on 15525) = 8994.00
        self.assertAlmostEqual(result, 8994.00, places=2)

    def test_64k_in_2035_matches_excel(self):
        """$64K taxable in 2035 → ~$7,569.49 (Excel value). Indexation pushes into lower brackets."""
        result = tax_on_taxable_income(64_000, 2035)
        self.assertAlmostEqual(result, 7569.49, places=2)

    def test_zero_income_zero_tax(self):
        self.assertEqual(tax_on_taxable_income(0, 2025), 0.0)

    def test_negative_income_treated_as_zero(self):
        self.assertEqual(tax_on_taxable_income(-5000, 2025), 0.0)

    def test_tier1_exact_boundary(self):
        """At exactly $11,925 (top of 10% bracket), tax = $1,192.50."""
        self.assertAlmostEqual(tax_on_taxable_income(11_925, 2025), 1192.50, places=2)

    def test_tier2_exact_boundary(self):
        """At exactly $48,475 (top of 12% bracket), tax = $5,578.50."""
        self.assertAlmostEqual(tax_on_taxable_income(48_475, 2025), 5578.50, places=2)

    def test_tier3_exact_boundary(self):
        """At exactly $103,350 (top of 22% bracket), tax = $17,651.00."""
        self.assertAlmostEqual(tax_on_taxable_income(103_350, 2025), 17651.00, places=2)

    def test_tier4_exact_boundary(self):
        self.assertAlmostEqual(tax_on_taxable_income(197_300, 2025), 40199.00, places=2)

    def test_tier5_exact_boundary(self):
        self.assertAlmostEqual(tax_on_taxable_income(250_525, 2025), 57231.00, places=2)

    def test_tier6_exact_boundary(self):
        """$626,350 (top of 35% bracket, start of 37% bracket).

        IRS-published value is $188,769.25, but that's a rounded table value.
        Exact bracket math gives $188,769.75 = $57,231 + $375,825 × 0.35.
        Excel's LAMBDA evaluates the tier-6 branch at this exact boundary → $188,769.75.
        We match Excel (parity > IRS rounding). $0.50 discontinuity with tier 7 is accepted.
        """
        self.assertAlmostEqual(tax_on_taxable_income(626_350, 2025), 188769.75, places=2)

    def test_tier7_just_above_boundary_uses_irs_cum(self):
        """Just above $626,350, tier 7 uses IRS-published cum ($188,769.25).

        This creates a $0.50 drop when crossing from tier 6 to tier 7 (matches Excel).
        """
        # tax(626_350.01) should be ~$188,769.25 + 0.01 × 0.37 ≈ $188,769.25
        result = tax_on_taxable_income(626_351, 2025)
        expected = 188_769.25 + 1.0 * 0.37
        self.assertAlmostEqual(result, expected, places=2)

    def test_top_bracket_37pct(self):
        """$1M taxable in 2025: $188,769.25 + (1M - 626,350) × 0.37 = $327,024.75."""
        expected = 188_769.25 + (1_000_000 - 626_350) * 0.37
        self.assertAlmostEqual(tax_on_taxable_income(1_000_000, 2025), expected, places=2)

    def test_within_tier_low(self):
        """$5,000 is within tier 1: tax = 5000 × 0.10 = $500."""
        self.assertAlmostEqual(tax_on_taxable_income(5_000, 2025), 500.00, places=2)

    def test_within_tier_mid(self):
        """$30,000 is within tier 2: tax = 1192.50 + (30000-11925) × 0.12 = 1192.50 + 2169 = $3,361.50."""
        self.assertAlmostEqual(tax_on_taxable_income(30_000, 2025), 3361.50, places=2)

    def test_indexation_at_2030(self):
        """Brackets in 2030 scale by (1.025)^5 = 1.1314."""
        idx = (1.025) ** 5
        # $64K taxable in 2030
        # tier 1 top: 11925 * idx = 13,492.20
        # tier 2 top: 48475 * idx = 54,844.32
        # tier 3 top: 103350 * idx = 116,929.71
        # 64000 falls in tier 3 (22% marginal)
        # cum at tier 3 bottom: 5578.50 * idx = 6,312.06
        # tax = 6312.06 + (64000 - 54844.32) * 0.22 = 6312.06 + 2014.25 = 8326.30
        expected = 5578.50 * idx + (64_000 - 48_475 * idx) * 0.22
        self.assertAlmostEqual(tax_on_taxable_income(64_000, 2030), expected, places=2)


class TestTaxParams(unittest.TestCase):

    def test_indexation_at_base_year_is_1(self):
        p = TaxParams()
        self.assertAlmostEqual(p.indexation_factor(2025), 1.0, places=6)

    def test_indexation_compounds(self):
        p = TaxParams(bracket_indexation=0.025, base_year=2025)
        self.assertAlmostEqual(p.indexation_factor(2030), 1.025 ** 5, places=6)

    def test_indexation_negative_years(self):
        """Pre-base-year gives indexation < 1."""
        p = TaxParams(bracket_indexation=0.025, base_year=2025)
        self.assertAlmostEqual(p.indexation_factor(2020), 1.025 ** -5, places=6)

    def test_std_deduction_indexed(self):
        p = TaxParams(std_deduction_base=15_000, bracket_indexation=0.025, base_year=2025)
        self.assertAlmostEqual(p.std_deduction(2025), 15_000.0, places=2)
        self.assertAlmostEqual(p.std_deduction(2035), 15_000 * (1.025) ** 10, places=2)

    def test_zero_indexation_keeps_brackets_flat(self):
        p = TaxParams(bracket_indexation=0.0)
        # No indexation → tax(64000, 2050) should equal tax(64000, 2025) under this params set
        t1 = tax_on_taxable_income(64_000, 2025, p)
        t2 = tax_on_taxable_income(64_000, 2050, p)
        self.assertAlmostEqual(t1, t2, places=2)


class TestGrossUpWithdrawal(unittest.TestCase):
    """Grossed-up withdrawal should converge so that (W + other - tax) ≈ net_need."""

    def test_zero_need_zero_tax(self):
        w, tax = gross_up_withdrawal(0, 0, 2036)
        self.assertAlmostEqual(w, 0.0, places=2)
        self.assertAlmostEqual(tax, 0.0, places=2)

    def test_gross_up_with_no_other_income_no_tax_below_stddeduction(self):
        """If net_need < std_deduction, no tax applies."""
        # 2025 std deduction = $15,000. If net_need is $10k and other income is $0, taxable = 0.
        w, tax = gross_up_withdrawal(10_000, 0, 2025)
        self.assertAlmostEqual(w, 10_000, places=2)
        self.assertEqual(tax, 0.0)

    def test_gross_up_fixed_point_approximates(self):
        """Two-pass gross-up should satisfy W + other - tax(W + other - std) ≈ net_need within $100."""
        net_need = 30_000
        other = 40_000
        year = 2036
        p = TaxParams()
        w, tax = gross_up_withdrawal(net_need, other, year, p, passes=2)
        # Verify: W - tax ≈ net_need (assuming other income covers its own tax contribution)
        # Check: (W + other) - tax should equal (net_need + other)
        # Simpler check: the after-tax income should cover net_need + other - tax_on_other
        taxable = max(0, w + other - p.std_deduction(year))
        actual_tax = tax_on_taxable_income(taxable, year, p)
        # Post-tax income available for expenses = W + other - actual_tax
        # Expenses = net_need + other (net_need was defined as expenses - other)
        after_tax_available = w + other - actual_tax
        target = net_need + other
        # 2-pass approximation: residual should be small (<$100 for reasonable tax rates)
        self.assertLess(abs(after_tax_available - target), 100)

    def test_gross_up_3_passes_converges_closer(self):
        """More passes → tighter convergence."""
        net_need = 30_000
        other = 40_000
        year = 2036
        p = TaxParams()
        _, _ = gross_up_withdrawal(net_need, other, year, p, passes=2)
        w3, _ = gross_up_withdrawal(net_need, other, year, p, passes=3)
        # Evaluate residual for 3-pass
        taxable3 = max(0, w3 + other - p.std_deduction(year))
        tax3 = tax_on_taxable_income(taxable3, year, p)
        residual3 = abs((w3 + other - tax3) - (net_need + other))
        self.assertLess(residual3, 20)  # 3-pass converges to within $20


if __name__ == "__main__":
    unittest.main()
