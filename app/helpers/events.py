"""
Extract life-event milestones from a list of YearRecord.

Events are used to annotate charts and highlight rows in tables. Each event
is a (year, age, label, short_label) tuple.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LifeEvent:
    year: int
    age: int
    label: str           # full label (e.g., "Retirement starts")
    short_label: str     # concise for chart annotations (e.g., "Retires")
    category: str        # "retirement" | "income" | "milestone" | "outflow"


def extract_events(records: list, end_age: int, k401_access_age: float = 59.5) -> list[LifeEvent]:
    """Scan records for notable life events."""
    events: list[LifeEvent] = []
    prev_phase = None
    prev_ss = 0.0
    prev_disab = 0.0
    prev_other1 = 0.0
    prev_other2 = 0.0

    for r in records:
        # Phase flip → retirement
        if prev_phase == "Working" and r.phase == "Retired":
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label="Retirement starts",
                short_label=f"Retires at {r.age}",
                category="retirement",
            ))

        # SS begins
        if r.ss_income > 0 and prev_ss == 0:
            monthly = r.ss_income / 12
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label=f"Social Security begins (~${monthly:,.0f}/mo)",
                short_label="SS begins",
                category="income",
            ))

        # SS disappears (edge case, e.g., user toggles eligibility - unlikely mid-plan)
        # Disability begins
        if r.disability_income > 0 and prev_disab == 0:
            monthly = r.disability_income / 12
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label=f"Disability begins (~${monthly:,.0f}/mo)",
                short_label="Disability",
                category="income",
            ))

        # Disability ends
        if prev_disab > 0 and r.disability_income == 0:
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label="Disability ends (converts to SS)",
                short_label="Disability ends",
                category="income",
            ))

        # Other income 1 begins
        if r.other_income_1 > 0 and prev_other1 == 0:
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label="Other income stream 1 begins",
                short_label="Other inc",
                category="income",
            ))

        # Other income 2 begins
        if r.other_income_2 > 0 and prev_other2 == 0:
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label="Other income stream 2 begins",
                short_label="Other inc 2",
                category="income",
            ))

        # 401k access age crossed (year where age becomes >= access age)
        if r.age == int(k401_access_age) or (
            k401_access_age != int(k401_access_age) and r.age == int(k401_access_age) + 1
        ):
            # Only fire once at the transition
            if not any(e.category == "milestone" and "401(k)" in e.label for e in events):
                events.append(LifeEvent(
                    year=r.year, age=r.age,
                    label=f"401(k) unlocks at age {k401_access_age}",
                    short_label="401k unlocks",
                    category="milestone",
                ))

        # Property purchase
        if r.property_cost > 0:
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label=f"Property purchase (${r.property_cost:,.0f} outflow)",
                short_label="Buy property",
                category="outflow",
            ))

        # Vehicle purchase
        if r.vehicle_cost > 0:
            events.append(LifeEvent(
                year=r.year, age=r.age,
                label=f"Vehicle purchase (${r.vehicle_cost:,.0f})",
                short_label="New vehicle",
                category="outflow",
            ))

        prev_phase = r.phase
        prev_ss = r.ss_income
        prev_disab = r.disability_income
        prev_other1 = r.other_income_1
        prev_other2 = r.other_income_2

    return events


def events_by_year(events: list[LifeEvent]) -> dict[int, list[LifeEvent]]:
    """Group events by year for fast lookup."""
    result: dict[int, list[LifeEvent]] = {}
    for e in events:
        result.setdefault(e.year, []).append(e)
    return result


def primary_chart_events(events: list[LifeEvent], max_events: int = 12) -> list[LifeEvent]:
    """Select events for main-chart annotation.

    Keep all retirement + income + milestone events (narrative backbone).
    For outflows (vehicles, property), keep all — they illustrate the
    recurring impact on the plan.
    """
    priority = {
        "retirement": 1,
        "income": 2,      # SS / disability start
        "milestone": 3,   # 401k unlocks
        "outflow": 4,     # vehicles, property — show all
    }
    sorted_events = sorted(events, key=lambda e: (priority.get(e.category, 99), e.year))
    return sorted(sorted_events[:max_events], key=lambda e: e.year)
