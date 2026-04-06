"""
Allocation parity tests vs Excel's glide-path formulas.

Excel:
  bond_share(age) = MIN((age - 20) * 0.02, MaxBonds)
  stocks_pct = (1 - CryptoPct) * (1 - bond_share)
  bonds_pct  = (1 - CryptoPct) * bond_share
  crypto_pct = CryptoPct
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.allocation import (  # noqa: E402
    AllocationParams,
    blended_401k_rate,
    bond_share,
    glide_path_percentages,
)


class TestBondShare(unittest.TestCase):

    def test_age_20_zero_bonds(self):
        self.assertEqual(bond_share(20), 0.0)

    def test_age_21_two_percent(self):
        self.assertAlmostEqual(bond_share(21), 0.02, places=6)

    def test_age_40_forty_percent_at_cap(self):
        """At age 40, (40-20)*0.02 = 0.40 = MaxBonds → capped."""
        self.assertAlmostEqual(bond_share(40), 0.40, places=6)

    def test_age_60_capped_at_maxbonds(self):
        self.assertAlmostEqual(bond_share(60), 0.40, places=6)

    def test_age_90_capped_at_maxbonds(self):
        self.assertAlmostEqual(bond_share(90), 0.40, places=6)

    def test_below_start_age_zero(self):
        self.assertEqual(bond_share(15), 0.0)
        self.assertEqual(bond_share(0), 0.0)

    def test_custom_max_bonds(self):
        p = AllocationParams(max_bonds=0.70)  # Vanguard-style landing
        self.assertAlmostEqual(bond_share(55, p), 0.70, places=6)  # capped
        self.assertAlmostEqual(bond_share(50, p), 0.60, places=6)  # not yet capped


class TestGlidePathPercentages(unittest.TestCase):

    def test_sum_to_one(self):
        for age in [20, 30, 37, 50, 67, 90]:
            pcts = glide_path_percentages(age)
            total = pcts["stocks"] + pcts["bonds"] + pcts["crypto"]
            self.assertAlmostEqual(total, 1.0, places=6, msg=f"age {age} doesn't sum to 1")

    def test_crypto_always_fixed(self):
        for age in [20, 30, 48, 67, 90]:
            pcts = glide_path_percentages(age)
            self.assertAlmostEqual(pcts["crypto"], 0.05, places=6)

    def test_age_37_excel_row_A52(self):
        """Excel Assumptions!B52 at age 37: stocks = (1 - 0.05) * (1 - MIN(17*0.02, 0.4)) = 0.95 * (1 - 0.34) = 0.627
        bonds = 0.95 * 0.34 = 0.323
        crypto = 0.05
        """
        pcts = glide_path_percentages(37)
        self.assertAlmostEqual(pcts["stocks"], 0.95 * (1 - 0.34), places=6)
        self.assertAlmostEqual(pcts["bonds"], 0.95 * 0.34, places=6)
        self.assertAlmostEqual(pcts["crypto"], 0.05, places=6)

    def test_age_48_excel_parity(self):
        """At age 48: bshare = min(28*0.02, 0.4) = 0.40 (capped). Stocks = 0.95*0.60 = 0.57"""
        pcts = glide_path_percentages(48)
        self.assertAlmostEqual(pcts["stocks"], 0.95 * 0.60, places=6)
        self.assertAlmostEqual(pcts["bonds"], 0.95 * 0.40, places=6)

    def test_age_90_excel_parity(self):
        """At age 90: bshare capped at 0.40. Same as age 40+."""
        pcts = glide_path_percentages(90)
        self.assertAlmostEqual(pcts["stocks"], 0.57, places=6)
        self.assertAlmostEqual(pcts["bonds"], 0.38, places=6)


class TestBlended401kRate(unittest.TestCase):
    """401(k) blended rate uses the glide-path stock/bond split (ignoring crypto)."""

    def test_age_20_all_stocks(self):
        """At age 20, bshare=0, so k401_rate = stock_return."""
        self.assertAlmostEqual(blended_401k_rate(20, 0.08, 0.04), 0.08, places=6)

    def test_age_40_capped(self):
        """At age 40, bshare=0.40, so k401_rate = 0.60 * 0.08 + 0.40 * 0.04 = 0.064."""
        self.assertAlmostEqual(blended_401k_rate(40, 0.08, 0.04), 0.064, places=6)

    def test_age_48_excel_parity(self):
        """At age 48 (capped bshare=0.40): 0.60 * 0.08 + 0.40 * 0.04 = 0.064."""
        self.assertAlmostEqual(blended_401k_rate(48, 0.08, 0.04), 0.064, places=6)


if __name__ == "__main__":
    unittest.main()
