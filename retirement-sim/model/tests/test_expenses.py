"""Expenses module parity tests vs Excel Projection column E."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.expenses import ExpenseParams, PropertyParams, annual_expenses  # noqa: E402


class TestAnnualExpenses(unittest.TestCase):

    def test_base_year_no_property(self):
        """At base year, no inflation applied, no property: ($1000 + $1500) × 12 = $30,000."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        result = annual_expenses(2025, exp)
        self.assertAlmostEqual(result, 30_000, places=2)

    def test_one_year_later_inflates_3pct(self):
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        result = annual_expenses(2026, exp)
        expected = 30_000 * 1.03
        self.assertAlmostEqual(result, expected, places=2)

    def test_ten_years_later_compounds(self):
        """Year 2035: 30000 * 1.03^10 = 40,317."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        result = annual_expenses(2035, exp)
        expected = 30_000 * (1.03) ** 10
        self.assertAlmostEqual(result, expected, places=2)

    def test_excel_e14_parity(self):
        """Excel E14 at base_current (2036, age 48): should be about $41,527."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        result = annual_expenses(2036, exp)
        expected = 30_000 * (1.03) ** 11
        self.assertAlmostEqual(result, expected, places=2)
        # Verify absolute value too
        self.assertAlmostEqual(result, 41527, delta=5)

    def test_zero_inflation_flat_expenses(self):
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.0, base_year=2025)
        for yr in [2025, 2036, 2078]:
            self.assertAlmostEqual(annual_expenses(yr, exp), 30_000, places=2)


class TestPropertyExpenses(unittest.TestCase):

    def test_before_purchase_uses_rent(self):
        """Before purchase year, rent applies."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        prop = PropertyParams(buy_property=True, purchase_year=2035, monthly_ownership_cost=2000)
        # 2030: still renting
        result = annual_expenses(2030, exp, prop)
        expected = (1000 + 1500) * 12 * (1.03) ** 5
        self.assertAlmostEqual(result, expected, places=2)

    def test_after_purchase_uses_ownership_cost(self):
        """After purchase year, ownership_cost replaces rent."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        prop = PropertyParams(buy_property=True, purchase_year=2035, monthly_ownership_cost=2000)
        # 2036: ownership kicks in
        result = annual_expenses(2036, exp, prop)
        expected = (1000 + 2000) * 12 * (1.03) ** 11
        self.assertAlmostEqual(result, expected, places=2)

    def test_buy_property_no_switches_rent(self):
        """buy_property=False keeps rent regardless of year."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        prop = PropertyParams(buy_property=False, purchase_year=2035, monthly_ownership_cost=2000)
        result = annual_expenses(2036, exp, prop)
        expected = (1000 + 1500) * 12 * (1.03) ** 11
        self.assertAlmostEqual(result, expected, places=2)

    def test_mortgage_active_adds_p_and_i(self):
        """With mortgage, P&I added to expenses during amortization period.

        P&I is now a computed property of PropertyParams (from cost, down_pct,
        rate, term). Expected: $280K principal @ 6.5% 30yr = $1,769.64/mo.
        """
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        prop = PropertyParams(
            buy_property=True, purchase_year=2035, cost=350000, monthly_ownership_cost=2000,
            mortgage=True, down_payment_pct=0.20, mortgage_rate=0.065, mortgage_term_years=30,
        )
        result = annual_expenses(2036, exp, prop)
        expected_pi_monthly = prop.mortgage_monthly_p_and_i
        base = (1000 + 2000) * 12 * (1.03) ** 11
        self.assertAlmostEqual(result, base + expected_pi_monthly * 12, places=2)
        # Sanity-check computed P&I is reasonable
        self.assertAlmostEqual(expected_pi_monthly, 1769.79, places=1)

    def test_mortgage_ends_after_term(self):
        """Mortgage P&I drops off after term expires."""
        exp = ExpenseParams(monthly_non_housing=1000, monthly_rent=1500, inflation=0.03, base_year=2025)
        prop = PropertyParams(
            buy_property=True, purchase_year=2035, cost=350000, monthly_ownership_cost=2000,
            mortgage=True, down_payment_pct=0.20, mortgage_rate=0.065, mortgage_term_years=30,
        )
        # 2065 = 30 years after 2035 → mortgage term exhausted (exclusive)
        result = annual_expenses(2065, exp, prop)
        base = (1000 + 2000) * 12 * (1.03) ** 40
        self.assertAlmostEqual(result, base, places=2)  # no mortgage added


if __name__ == "__main__":
    unittest.main()
