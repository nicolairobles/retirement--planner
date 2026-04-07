"""
Recommendations engine — surfaces top actionable levers for the user's plan.

Tests realistic, actionable deltas (not tornado-style ±50%) and returns
ranked suggestions focused on what the user can actually do: save more,
spend less, lower retirement target, shift allocation.

Each candidate re-runs the full model once. Pure Python; no Streamlit
dependency so it can be unit-tested without the UI layer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))

from helpers.seeds import build_seedcase_from_inputs  # noqa: E402
from model.outputs import run_and_extract  # noqa: E402


@dataclass
class Recommendation:
    """One actionable suggestion for improving the plan."""
    action: str          # what to do, human-readable
    outcome: str         # what happens, human-readable
    delta_score: float   # for sorting (combined age+nw score, higher = bigger win)
    category: str        # "save" | "spend" | "invest" | "retire-target"


def _run(inputs: dict, current_age: int) -> tuple[int | None, float]:
    """Run projection; return (retirement_age, nw_at_end)."""
    seed = build_seedcase_from_inputs(inputs, current_age=current_age)
    out = run_and_extract(seed)
    return out.retirement_age, out.nw_at_end


def _score(base_age: int | None, new_age: int | None,
           base_nw: float, new_nw: float) -> float:
    """Combined score for ranking: years-earlier dominates, NW is tiebreaker."""
    if base_age is not None and new_age is not None:
        age_delta = base_age - new_age  # positive = earlier
    else:
        age_delta = 0
    nw_delta = new_nw - base_nw
    # One year earlier is "worth" $1M in ranking; NW delta breaks ties.
    return age_delta * 1_000_000 + nw_delta


def _outcome_text(base_age: int | None, new_age: int | None,
                  base_nw: float, new_nw: float) -> str | None:
    """Render outcome text. Returns None if the edit doesn't help."""
    nw_delta = new_nw - base_nw
    if base_age is not None and new_age is not None:
        age_delta = base_age - new_age
        if age_delta > 0:
            yr = "year" if age_delta == 1 else "years"
            return f"Retire {age_delta} {yr} earlier (age {new_age} vs {base_age})"
        if age_delta == 0 and nw_delta > 25_000:
            return f"Same retirement age, end with ${nw_delta/1_000_000:+.2f}M more"
        return None
    # Base plan didn't reach retirement — any NW improvement helps
    if new_age is not None and base_age is None:
        return f"Reaches retirement at age {new_age} (base plan never did)"
    if nw_delta > 25_000:
        return f"End the plan with ${nw_delta/1_000_000:+.2f}M more in savings"
    return None


def generate_recommendations(
    inputs: dict,
    current_age: int,
    base_age: int | None,
    base_nw: float,
    top_n: int = 3,
) -> list[Recommendation]:
    """Generate top N actionable recommendations, ranked by retirement-age impact.

    Tests realistic single-lever edits. Pass in the base scenario's retirement
    age and ending NW so we don't re-run the baseline projection.
    """
    candidates: list[tuple[dict, str, str]] = []

    # --- Save more ---
    k401 = inputs.get("in_401kContrib", 0)
    if k401 < 23_000:  # under 2024 limit
        bump = 5000 if k401 + 5000 <= 23_000 else (23_000 - k401)
        if bump >= 1000:
            candidates.append((
                {**inputs, "in_401kContrib": k401 + bump},
                f"Save an extra ${bump:,}/yr in 401(k) (to ${k401 + bump:,}/yr)",
                "save",
            ))

    # --- Spend less: non-housing ---
    non_housing = inputs.get("in_MonthlyNonHousing", 0)
    if non_housing >= 500:
        candidates.append((
            {**inputs, "in_MonthlyNonHousing": non_housing - 200},
            f"Cut non-housing spend by $200/mo (to ${non_housing - 200:,}/mo)",
            "spend",
        ))

    # --- Spend less: housing ---
    rent = inputs.get("in_MonthlyRent", 0)
    if rent >= 800:
        candidates.append((
            {**inputs, "in_MonthlyRent": rent - 200},
            f"Cut housing cost by $200/mo (to ${rent - 200:,}/mo)",
            "spend",
        ))

    # --- Lower retirement target (work 'til a more modest number) ---
    target = inputs.get("in_RetirementTarget", 0)
    if target >= 800_000:
        new_target = target * 0.85
        candidates.append((
            {**inputs, "in_RetirementTarget": new_target},
            f"Lower retirement target 15% (to ${new_target/1_000_000:.1f}M)",
            "retire-target",
        ))

    # --- Shift allocation: 10% bonds → stocks ---
    # Only applies if glide path is active (not fixed-mix)
    use_fixed = inputs.get("in_UseFixedMix", "No") == "Yes"
    max_bonds = inputs.get("in_MaxBonds", 0.40)
    if not use_fixed and max_bonds >= 0.25:
        candidates.append((
            {**inputs, "in_MaxBonds": max_bonds - 0.10},
            f"Shift 10% more of your portfolio into stocks (bond ceiling to {(max_bonds-0.10)*100:.0f}%)",
            "invest",
        ))

    # --- Pay off debt faster (if any debt enabled) ---
    has_debt = any(
        inputs.get(f"in_Debt{n}Enabled") == "Yes"
        and float(inputs.get(f"in_Debt{n}Balance", 0)) > 0
        for n in (1, 2, 3)
    )
    if has_debt:
        # Test avalanche strategy with $200/mo extra budget
        current_strategy = inputs.get("in_DebtPayoffStrategy", "none")
        current_budget = float(inputs.get("in_DebtExtraBudget", 0))
        if current_strategy == "none" or current_budget < 200:
            new_budget = max(current_budget + 200, 200)
            candidates.append((
                {**inputs, "in_DebtPayoffStrategy": "avalanche", "in_DebtExtraBudget": new_budget},
                f"Throw ${new_budget:,.0f}/mo extra at debt (avalanche strategy)",
                "spend",
            ))

    # --- Run each candidate and score ---
    recs: list[Recommendation] = []
    for edit, action_text, category in candidates:
        new_age, new_nw = _run(edit, current_age)
        outcome = _outcome_text(base_age, new_age, base_nw, new_nw)
        if outcome is None:
            continue
        score = _score(base_age, new_age, base_nw, new_nw)
        if score <= 0:
            continue
        recs.append(Recommendation(
            action=action_text, outcome=outcome,
            delta_score=score, category=category,
        ))

    recs.sort(key=lambda r: r.delta_score, reverse=True)
    return recs[:top_n]
