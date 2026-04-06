"""
Per-bucket returns and blended portfolio return.

Mirrors Excel Projection!K formula which computes annual dollar return across
all buckets (stocks, bonds, crypto, cash, 401k) given their current balances.
"""

from __future__ import annotations

from dataclasses import dataclass

from .allocation import AllocationParams, blended_401k_rate


@dataclass(frozen=True)
class ReturnParams:
    """Per-asset annual returns (nominal)."""
    stock_return: float = 0.08     # in_StockReturn
    bond_return: float = 0.04      # in_BondReturn
    crypto_return: float = 0.06    # in_CryptoReturn
    cash_return: float = 0.02      # in_CashReturn


@dataclass(frozen=True)
class BucketBalances:
    """Balances across the five buckets at a point in time."""
    stocks: float = 0.0
    bonds: float = 0.0
    crypto: float = 0.0
    cash: float = 0.0
    k401: float = 0.0

    @property
    def total(self) -> float:
        return self.stocks + self.bonds + self.crypto + self.cash + self.k401


def blended_return_dollars(
    buckets: BucketBalances,
    age: int,
    returns: ReturnParams | None = None,
    alloc: AllocationParams | None = None,
) -> float:
    """Compute the total dollar return across all buckets for one year.

    Excel (K4+): P_prev * stock + Q_prev * bond + R_prev * crypto + S_prev * cash + T_prev * k401_rate

    Where k401_rate depends on the glide path at `age`.
    """
    if returns is None:
        returns = ReturnParams()
    if alloc is None:
        alloc = AllocationParams()

    k401_rate = blended_401k_rate(age, returns.stock_return, returns.bond_return, alloc)

    return (
        buckets.stocks * returns.stock_return
        + buckets.bonds * returns.bond_return
        + buckets.crypto * returns.crypto_return
        + buckets.cash * returns.cash_return
        + buckets.k401 * k401_rate
    )


def blended_portfolio_rate(
    buckets: BucketBalances,
    age: int,
    returns: ReturnParams | None = None,
    alloc: AllocationParams | None = None,
) -> float:
    """Effective portfolio-level return rate (dollar return / total balance).

    Useful for reporting and for sanity-checking cFIREsim-style analyses.
    Returns 0 if portfolio is empty.
    """
    total = buckets.total
    if total <= 0:
        return 0.0
    return blended_return_dollars(buckets, age, returns, alloc) / total
