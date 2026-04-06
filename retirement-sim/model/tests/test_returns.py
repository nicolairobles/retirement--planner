"""
Returns module parity tests vs Excel Projection!K formula.

Excel (K4+): P_prev * stock + Q_prev * bond + R_prev * crypto + S_prev * cash + T_prev * k401_rate
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.returns import (  # noqa: E402
    BucketBalances,
    ReturnParams,
    blended_portfolio_rate,
    blended_return_dollars,
)


class TestBlendedReturnDollars(unittest.TestCase):

    def test_empty_portfolio_zero_return(self):
        buckets = BucketBalances()
        self.assertEqual(blended_return_dollars(buckets, 50), 0.0)

    def test_stocks_only(self):
        """$100K stocks at 8% → $8,000 return."""
        buckets = BucketBalances(stocks=100_000)
        result = blended_return_dollars(buckets, 50)  # age irrelevant for pure stocks
        self.assertAlmostEqual(result, 8000.0, places=2)

    def test_bonds_only(self):
        buckets = BucketBalances(bonds=100_000)
        result = blended_return_dollars(buckets, 50)
        self.assertAlmostEqual(result, 4000.0, places=2)

    def test_crypto_only(self):
        buckets = BucketBalances(crypto=100_000)
        result = blended_return_dollars(buckets, 50)
        self.assertAlmostEqual(result, 6000.0, places=2)

    def test_cash_only(self):
        buckets = BucketBalances(cash=100_000)
        result = blended_return_dollars(buckets, 50)
        self.assertAlmostEqual(result, 2000.0, places=2)

    def test_k401_at_age_40_uses_blended(self):
        """At age 40, k401_rate = 0.6*0.08 + 0.4*0.04 = 0.064. $100K → $6,400."""
        buckets = BucketBalances(k401=100_000)
        result = blended_return_dollars(buckets, 40)
        self.assertAlmostEqual(result, 6400.0, places=2)

    def test_mixed_portfolio_excel_parity(self):
        """Example from base-current at retirement (age 48):
        Stocks $410,231 + Bonds $273,488 + Crypto $35,985 + Cash $20,159 + 401k $572,704
        At 8% stock, 4% bond, 6% crypto, 2% cash, k401_rate at age 48 = 0.064
        Dollar return = 410231*0.08 + 273488*0.04 + 35985*0.06 + 20159*0.02 + 572704*0.064
                      = 32818.48 + 10939.52 + 2159.10 + 403.18 + 36653.06 = 82,973.34
        """
        buckets = BucketBalances(
            stocks=410_231,
            bonds=273_488,
            crypto=35_985,
            cash=20_159,
            k401=572_704,
        )
        result = blended_return_dollars(buckets, 48)
        expected = (
            410_231 * 0.08 + 273_488 * 0.04 + 35_985 * 0.06
            + 20_159 * 0.02 + 572_704 * 0.064
        )
        self.assertAlmostEqual(result, expected, places=1)

    def test_custom_returns(self):
        buckets = BucketBalances(stocks=100_000)
        low_returns = ReturnParams(stock_return=0.05, bond_return=0.03, crypto_return=0.02, cash_return=0.01)
        result = blended_return_dollars(buckets, 50, low_returns)
        self.assertAlmostEqual(result, 5000.0, places=2)


class TestBlendedPortfolioRate(unittest.TestCase):

    def test_empty_portfolio_zero_rate(self):
        self.assertEqual(blended_portfolio_rate(BucketBalances(), 50), 0.0)

    def test_all_stocks_rate_equals_stock_return(self):
        buckets = BucketBalances(stocks=100_000)
        self.assertAlmostEqual(blended_portfolio_rate(buckets, 50), 0.08, places=6)

    def test_mixed_rate(self):
        """$500K stocks + $500K bonds → blended = ($40K + $20K) / $1M = 6%."""
        buckets = BucketBalances(stocks=500_000, bonds=500_000)
        self.assertAlmostEqual(blended_portfolio_rate(buckets, 50), 0.06, places=6)


class TestBucketBalances(unittest.TestCase):

    def test_total(self):
        b = BucketBalances(stocks=100, bonds=50, crypto=25, cash=10, k401=200)
        self.assertEqual(b.total, 385)

    def test_default_all_zero(self):
        self.assertEqual(BucketBalances().total, 0.0)


if __name__ == "__main__":
    unittest.main()
