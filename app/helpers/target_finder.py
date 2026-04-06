"""
Safe retirement finder.

Answers the question: "What is the earliest I can retire and have
my money last?"

Binary-searches the retirement net-worth target (which controls when
you stop working) and checks TWO conditions at each candidate:

  1. DETERMINISTIC: portfolio survives to end-of-plan with smooth returns
     and the user's specific healthcare/LTC assumptions (the conservative
     check that catches healthcare inflation).

  2. HISTORICAL (Monte Carlo): plan succeeds in >= 95% of historical
     sequences from 1928-2024 (catches market crashes, stagflation, etc.).

Both must pass. The result is the minimum target (earliest retirement)
where the plan is safe under both tests.
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
    """Result of the safe-retirement search."""
    found: bool
    target: float                  # recommended target ($)
    retirement_age: int | None     # deterministic retirement age at that target
    mc_success_rate: float         # historical MC success at that target
    det_survives: bool             # deterministic portfolio survives to end-of-plan
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


def _evaluate_target(
    inputs: dict, current_age: int,
    historical: list[HistoricalYear],
) -> tuple[bool, float, int | None, bool]:
    """Evaluate a target: returns (both_pass, mc_rate, det_age, det_survives)."""
    seed = build_seedcase_from_inputs(inputs, current_age=current_age)
    n_years = seed.years_simulated

    # Deterministic check: does the portfolio survive to end-of-plan?
    det_out = run_and_extract(seed)
    det_age = det_out.retirement_age
    det_survives = det_out.portfolio_exhausted_age is None and det_age is not None

    # Monte Carlo check: >= 95% historical success
    if n_years > len(historical):
        return False, 0.0, det_age, det_survives

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

    mc_rate = successes / total if total > 0 else 0.0
    both_pass = det_survives and mc_rate >= 0.95
    return both_pass, mc_rate, det_age, det_survives


def find_safe_target(
    inputs: dict,
    current_age: int,
    low: float = 500_000,
    high: float = 6_000_000,
    precision: float = 50_000,
) -> TargetFinderResult:
    """Find the minimum retirement target where BOTH deterministic and MC pass.

    A higher target means working longer (more saving), which makes the plan
    safer. This finds the sweet spot: earliest retirement that's still safe.
    """
    historical = _load_historical()
    iterations = 0

    # Check if high-end is achievable at all
    test_high = {**inputs, "in_RetirementTarget": high}
    both_pass, mc_rate, det_age, det_survives = _evaluate_target(
        test_high, current_age, historical,
    )
    iterations += 1
    if not both_pass:
        issues = []
        if not det_survives:
            issues.append(
                "portfolio runs out even with smooth returns (healthcare/LTC "
                "costs may be growing faster than the portfolio)"
            )
        if mc_rate < 0.95:
            issues.append(f"only {mc_rate:.0%} historical success")
        return TargetFinderResult(
            found=False, target=high, retirement_age=det_age,
            mc_success_rate=mc_rate, det_survives=det_survives,
            iterations=iterations,
            note=(
                f"Even a ${high/1_000_000:.1f}M target doesn't work: "
                + "; ".join(issues) + ". "
                "The issue isn't the target. Try: reducing healthcare assumptions, "
                "increasing savings, or extending your working years."
            ),
        )

    # Check if low-end already works
    test_low = {**inputs, "in_RetirementTarget": low}
    both_low, mc_low, age_low, det_low = _evaluate_target(
        test_low, current_age, historical,
    )
    iterations += 1
    if both_low:
        return TargetFinderResult(
            found=True, target=low, retirement_age=age_low,
            mc_success_rate=mc_low, det_survives=det_low,
            iterations=iterations,
            note=f"Even ${low/1_000_000:.1f}M is enough.",
        )

    # Binary search: find minimum target where both pass
    while high - low > precision:
        mid = (low + high) / 2.0
        test_mid = {**inputs, "in_RetirementTarget": mid}
        both_mid, _, _, _ = _evaluate_target(
            test_mid, current_age, historical,
        )
        iterations += 1
        if both_mid:
            high = mid
        else:
            low = mid

    # Final verify at `high` (known to work)
    final_target = round(high / 10_000) * 10_000
    final_inputs = {**inputs, "in_RetirementTarget": final_target}
    _, final_mc, final_age, final_det = _evaluate_target(
        final_inputs, current_age, historical,
    )
    iterations += 1

    return TargetFinderResult(
        found=True, target=final_target, retirement_age=final_age,
        mc_success_rate=final_mc, det_survives=final_det,
        iterations=iterations,
    )
