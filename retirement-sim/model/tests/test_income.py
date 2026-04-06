"""Income module parity tests vs Excel Projection columns H and I."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.income import (  # noqa: E402
    DisabilityParams,
    SSParams,
    disability_annual_income,
    ss_annual_income,
)


class TestSSIncome(unittest.TestCase):

    def test_not_eligible_returns_zero(self):
        p = SSParams(eligible=False)
        self.assertEqual(ss_annual_income(2055, p), 0.0)
        self.assertEqual(ss_annual_income(2080, p), 0.0)

    def test_before_start_year_returns_zero(self):
        p = SSParams(benefit_monthly_today=3350, cola=0.02, start_age=67, current_age=37, base_year=2025)
        # start_year = 2025 + 67 - 37 = 2055
        self.assertEqual(ss_annual_income(2054, p), 0.0)
        self.assertEqual(ss_annual_income(2040, p), 0.0)

    def test_at_start_year_excel_parity(self):
        """SS at start_year 2055: $3350 * 12 * (1.02)^30 = ~$72,816."""
        p = SSParams(benefit_monthly_today=3350, cola=0.02, start_age=67, current_age=37, base_year=2025)
        result = ss_annual_income(2055, p)
        expected = 3350 * 12 * (1.02) ** 30
        self.assertAlmostEqual(result, expected, places=2)

    def test_grows_with_cola_compounded_from_base_year(self):
        """At year 2060: $3350 * 12 * (1.02)^35."""
        p = SSParams(benefit_monthly_today=3350, cola=0.02, start_age=67, current_age=37, base_year=2025)
        result = ss_annual_income(2060, p)
        expected = 3350 * 12 * (1.02) ** 35
        self.assertAlmostEqual(result, expected, places=2)

    def test_zero_cola(self):
        p = SSParams(benefit_monthly_today=3350, cola=0.0, start_age=67, current_age=37, base_year=2025)
        # No growth: same nominal value regardless of year
        self.assertAlmostEqual(ss_annual_income(2055, p), 3350 * 12, places=2)
        self.assertAlmostEqual(ss_annual_income(2080, p), 3350 * 12, places=2)


class TestDisabilityIncome(unittest.TestCase):

    def test_not_eligible_returns_zero(self):
        p = DisabilityParams(eligible=False)
        self.assertEqual(disability_annual_income(2035, p), 0.0)

    def test_before_start_year_returns_zero(self):
        p = DisabilityParams(eligible=True, start_year=2030, end_year=2055)
        self.assertEqual(disability_annual_income(2029, p), 0.0)

    def test_after_end_year_returns_zero(self):
        """end_year is EXCLUSIVE (disability ends when SS begins)."""
        p = DisabilityParams(eligible=True, start_year=2030, end_year=2055)
        self.assertEqual(disability_annual_income(2055, p), 0.0)
        self.assertEqual(disability_annual_income(2060, p), 0.0)

    def test_at_start_year(self):
        """At start_year, COLA exponent = 0, so benefit = monthly * 12."""
        p = DisabilityParams(benefit_monthly=2800, cola=0.025, start_year=2030, end_year=2055)
        self.assertAlmostEqual(disability_annual_income(2030, p), 2800 * 12, places=2)

    def test_cola_compounds_from_start_year(self):
        """At year 2035 (5 years after start): $2800 * 12 * (1.025)^5."""
        p = DisabilityParams(benefit_monthly=2800, cola=0.025, start_year=2030, end_year=2055)
        result = disability_annual_income(2035, p)
        expected = 2800 * 12 * (1.025) ** 5
        self.assertAlmostEqual(result, expected, places=2)

    def test_last_year_of_eligibility(self):
        """At year end_year - 1 (2054 in default), still paying."""
        p = DisabilityParams(benefit_monthly=2800, cola=0.025, start_year=2030, end_year=2055)
        result = disability_annual_income(2054, p)
        expected = 2800 * 12 * (1.025) ** 24
        self.assertAlmostEqual(result, expected, places=2)


if __name__ == "__main__":
    unittest.main()
