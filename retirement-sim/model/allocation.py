"""
Glide-path allocation — age-based target mix for stocks, bonds, crypto.

Mirrors Excel Assumptions!B52:D52 formulas:
  Stocks % = (1 - CryptoPct) * (1 - bond_share(age))
  Bonds %  = (1 - CryptoPct) * bond_share(age)
  Crypto % = CryptoPct

Where bond_share(age) = MIN((age - 20) * 0.02, MaxBonds).

These percentages are of the INVESTABLE POOL — i.e., total portfolio minus
cash reserve minus (pre-59.5) 401(k). Cash and 401(k) are separate buckets
handled elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllocationParams:
    """Allocation strategy parameters.

    Two modes:
      1. Glide path (use_fixed_mix=False, default): bonds share ramps with age
         via MIN((age - 20) * 2%, max_bonds). Matches Excel behavior.
      2. Fixed mix (use_fixed_mix=True): user sets fixed_stock_pct. Stocks stay
         at that % for the entire plan; bonds fill the rest of the non-crypto pool.
    """
    crypto_pct: float = 0.05       # fixed crypto share of investable pool
    max_bonds: float = 0.40         # cap on bond share (glide-path mode)
    bond_start_age: int = 20        # age at which bond share begins (glide path)
    bond_ramp_rate: float = 0.02    # bonds grow 2% per year of age (glide path)
    use_fixed_mix: bool = False     # toggle: True = fixed allocation
    fixed_stock_pct: float = 0.60   # stocks % when use_fixed_mix=True (of non-crypto pool)


def bond_share(age: int, params: AllocationParams | None = None) -> float:
    """Fraction of the non-crypto investable pool that goes to bonds at a given age.

    Glide-path mode: MIN((age - 20) * 0.02, MaxBonds)
    Fixed-mix mode: 1 - fixed_stock_pct
    """
    if params is None:
        params = AllocationParams()
    if params.use_fixed_mix:
        return max(0.0, min(1.0 - params.fixed_stock_pct, 1.0))
    raw = (age - params.bond_start_age) * params.bond_ramp_rate
    return max(0.0, min(raw, params.max_bonds))


def glide_path_percentages(age: int, params: AllocationParams | None = None) -> dict[str, float]:
    """Target percentages of investable pool for stocks/bonds/crypto at a given age.

    These sum to 1.0 and apply to the "investable pool" = total portfolio minus
    cash reserve minus 401(k) (when 401(k) is locked, i.e., pre-59.5).

    Excel:
      Stocks % = (1 - CryptoPct) * (1 - bond_share)
      Bonds %  = (1 - CryptoPct) * bond_share
      Crypto % = CryptoPct
    """
    if params is None:
        params = AllocationParams()
    bshare = bond_share(age, params)
    non_crypto = 1.0 - params.crypto_pct
    return {
        "stocks": non_crypto * (1.0 - bshare),
        "bonds": non_crypto * bshare,
        "crypto": params.crypto_pct,
    }


def blended_401k_rate(age: int, stock_return: float, bond_return: float, params: AllocationParams | None = None) -> float:
    """Blended 401(k) return using the same stock/bond glide ratio.

    Excel: k401_rate = (1 - bshare) * stock_return + bshare * bond_return

    The 401(k) is invested internally along the glide-path stock/bond split
    (ignoring the crypto allocation).
    """
    if params is None:
        params = AllocationParams()
    bshare = bond_share(age, params)
    return (1.0 - bshare) * stock_return + bshare * bond_return
