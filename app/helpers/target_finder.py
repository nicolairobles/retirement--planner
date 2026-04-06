"""
Safe retirement target finder.

Binary-searches the minimum retirement net-worth target that yields
>= success_threshold historical Monte Carlo success rate. Replaces the
user's manual loop of "bump target, check MC, repeat."
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))

from helpers.seeds import build_seedcase_from_inputs  # noqa: E402
from model.historical import HistoricalYear, run_historical_cycle  # noqa: E402
from model.outputs import run_and_extract  # noqa: E402


@dataclass
class TargetFinderResult:
    """Result of the safe-target binary search."""
    found: bool
    target: float                 # recommended target ($)
    success_rate: float            # historical MC success at that target
    retirement_age: int | None     # deterministic retirement age at that target
    tested_range: tuple[float, float]  # (low, high) $ tested
    iterations: int
    note: str = ""


def _load_historical() -> list[HistoricalYear]:
    path = REPO_ROOT / "retirement-sim" / "evals" / "external-benchmarks" / "historical-returns-annual.csv"
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(HistoricalYear(
                year=int(row["year"]),
                sp500_return=float(row["sp500_return"]),
                tbond_return=float(row["tbond_return"]),
                inflation=float(row["inflation"]),
            ))
    return sorted(rows, key=lambda y: y.year)


def _mc_success_rate(inputs: dict, current_age: int,
                     historical: list[HistoricalYear]) -> tuple[float, int]:
    """Run full-model historical MC; return (success_rate, retirement_age)."""
    seed = build_seedcase_from_inputs(inputs, current_age=current_age)
    n_years = seed.years_simulated
    if n_years > len(historical):
        return 0.0, None  # horizon exceeds history

    # Deterministic retirement age (use smooth returns)
    det_out = run_and_extract(seed)
    det_age = det_out.retirement_age

    # Historical cycles
    successes = 0
    total = 0
    for start in range(historical[0].year, historical[-1].year - n_years + 2):
        idx = start - historical[0].year
        hist_slice = historical[idx:idx + n_years]
        try:
            r = run_historical_cycle(seed, hist_slice)
            total += 1
            if r.succeeded:
                successes += 1
        except Exception:
            pass
    rate = successes / total if total > 0 else 0.0
    return rate, det_age


def find_safe_target(
    inputs: dict,
    current_age: int,
    success_threshold: float = 0.95,
    low: float = 500_000,
    high: float = 6_000_000,
    precision: float = 50_000,
) -> TargetFinderResult:
    """Binary-search minimum retirement target with >= success_threshold MC success.

    Args:
        inputs: current scenario input dict (will be modified in-memory per iteration).
        current_age: user's current age.
        success_threshold: required historical MC success rate (default 0.95).
        low/high: $ range to search.
        precision: $ precision for binary search (default $50K).

    Returns:
        TargetFinderResult with the recommended target, or found=False if
        even `high` doesn't hit the threshold.
    """
    historical = _load_historical()
    iterations = 0

    # Check if high-end is achievable at all
    test_high = {**inputs, "in_RetirementTarget": high}
    high_rate, _ = _mc_success_rate(test_high, current_age, historical)
    iterations += 1
    if high_rate < success_threshold:
        return TargetFinderResult(
            found=False, target=high, success_rate=high_rate,
            retirement_age=None, tested_range=(low, high),
            iterations=iterations,
            note=(
                f"Even a ${high/1_000_000:.1f}M target only reaches "
                f"{high_rate:.0%} success. Your plan's issue isn't the target — "
                f"look at spending, returns, or plan horizon."
            ),
        )

    # Check if low-end already works (lucky scenario)
    test_low = {**inputs, "in_RetirementTarget": low}
    low_rate, low_age = _mc_success_rate(test_low, current_age, historical)
    iterations += 1
    if low_rate >= success_threshold:
        return TargetFinderResult(
            found=True, target=low, success_rate=low_rate,
            retirement_age=low_age, tested_range=(low, high),
            iterations=iterations,
            note=f"Even ${low/1_000_000:.1f}M already meets {success_threshold:.0%} success.",
        )

    # Binary search
    while high - low > precision:
        mid = (low + high) / 2.0
        test_mid = {**inputs, "in_RetirementTarget": mid}
        rate, _ = _mc_success_rate(test_mid, current_age, historical)
        iterations += 1
        if rate >= success_threshold:
            high = mid  # target is achievable, try lower
        else:
            low = mid   # not achievable, need higher

    # Final verify at `high` (known to work)
    final_target = round(high / 10_000) * 10_000  # round to $10K
    final_inputs = {**inputs, "in_RetirementTarget": final_target}
    final_rate, final_age = _mc_success_rate(final_inputs, current_age, historical)
    iterations += 1

    return TargetFinderResult(
        found=True, target=final_target, success_rate=final_rate,
        retirement_age=final_age, tested_range=(low, high),
        iterations=iterations,
    )
