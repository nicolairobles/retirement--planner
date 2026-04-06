"""
Persistent scenario-state card shown at the top of every page.

Uses custom CSS (see helpers/theme.py) for a polished hero card look rather
than Streamlit's default info banner.
"""

from __future__ import annotations

import streamlit as st

from .seeds import load_demo_cases
from .widgets import format_money


def render_scenario_card_v2(outputs, scenario_name: str, current_age: int) -> None:
    """Simpler scenario card that just shows the user's named scenario.

    No template-diff badge — the scenario IS the source of truth, not a
    modification of something else.
    """
    st.markdown(
        f'''
        <div class="hero-card">
          <div class="hero-card-header">
            <div>
              <p class="hero-card-title">Your scenario</p>
              <p class="hero-card-name">{scenario_name} · Age {current_age}</p>
            </div>
            <span class="hero-card-badge-clean">Auto-saved</span>
          </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # Key metrics — 4 columns, focused on what users actually act on
    col1, col2, col3, col4 = st.columns(4)
    ret_age_txt = f"{outputs.retirement_age}" if outputs.retirement_age else "—"
    years_left = (
        f"{outputs.retirement_age - current_age} yrs"
        if outputs.retirement_age else None
    )
    col1.metric(
        "Retire at age", ret_age_txt,
        delta=years_left,
        delta_color="off",
        help="The age when your liquid portfolio first reaches your target. "
             "Home equity doesn't count.",
    )
    max_spend = getattr(outputs, 'max_sustainable_spend', 0)
    col2.metric(
        "Max spend/yr",
        format_money(max_spend, compact=True) if max_spend > 0 else "—",
        help="The largest annual spending (today's dollars) your plan can sustain "
             "to end-of-plan without running out.",
    )
    liquid_txt = (
        format_money(outputs.liquid_nw_at_end, compact=True)
        if getattr(outputs, 'liquid_nw_at_end', 0) > 0 else "$0"
    )
    col3.metric(
        "Savings at end",
        liquid_txt,
        help="Spendable portfolio at end-of-plan. Excludes home value "
             "and assets that are hard to sell quickly.",
    )
    # Spend cushion — the single most actionable number
    inputs = st.session_state.get("inputs", {})
    current_annual = (
        float(inputs.get("in_MonthlyNonHousing", 0))
        + float(inputs.get("in_MonthlyRent", 0))
    ) * 12
    if max_spend > 0 and current_annual > 0:
        cushion_pct = (max_spend - current_annual) / current_annual * 100
        if cushion_pct >= 10:
            col4.metric(
                "Spend cushion", f"+{cushion_pct:.0f}%",
                help="How much more you could spend beyond your current level. "
                     "Above 10% is comfortable; below 0% means the plan can't "
                     "sustain your current spending.",
            )
        elif cushion_pct >= 0:
            col4.metric(
                "Spend cushion", f"+{cushion_pct:.0f}%",
                help="Thin margin. Small changes in spending or returns could "
                     "tip this into a shortfall.",
            )
        else:
            col4.metric(
                "Spend cushion", f"{cushion_pct:.0f}%",
                help="Your current spending exceeds what the plan can sustain. "
                     "Cut spending, save more, or delay retirement.",
            )
    else:
        col4.metric("Spend cushion", "—")


def _compute_modified(current_inputs: dict, persona_id: str) -> tuple[bool, int]:
    """Return (has_modifications, count_modified_fields)."""
    all_cases = load_demo_cases()
    persona = next((c for c in all_cases if c["id"] == persona_id), None)
    # Check session-custom personas too
    if persona is None:
        session_custom = st.session_state.get("custom_personas", [])
        persona = next((c for c in session_custom if c["id"] == persona_id), None)
    if persona is None:
        return False, 0
    original = persona["inputs"]
    diffs = 0
    for key, orig_val in original.items():
        cur = current_inputs.get(key)
        if cur is None:
            continue
        if isinstance(orig_val, (int, float)) and isinstance(cur, (int, float)):
            if abs(float(orig_val) - float(cur)) > 0.0001:
                diffs += 1
        elif orig_val != cur:
            diffs += 1
    return diffs > 0, diffs


def render_scenario_card(outputs, persona_name: str, persona_id: str, current_age: int) -> None:
    """Render a polished hero card at the top of a page."""
    inputs = st.session_state.get("inputs", {})
    modified, diff_count = _compute_modified(inputs, persona_id)

    # Hero card header
    badge_html = (
        f'<span class="hero-card-badge-mod">Modified · {diff_count} '
        f'field{"s" if diff_count != 1 else ""}</span>'
        if modified
        else '<span class="hero-card-badge-clean">Defaults</span>'
    )

    st.markdown(
        f'''
        <div class="hero-card">
          <div class="hero-card-header">
            <div>
              <p class="hero-card-title">Active Scenario</p>
              <p class="hero-card-name">{persona_name} · Age {current_age}</p>
            </div>
            {badge_html}
          </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    ret_age_txt = f"{outputs.retirement_age}" if outputs.retirement_age else "—"
    col1.metric("Retires at age", ret_age_txt)
    col2.metric(
        "Years to go",
        f"{outputs.retirement_age - current_age}" if outputs.retirement_age else "—",
    )
    # Show spendable NW — what user can actually draw from
    liquid_txt = (
        format_money(outputs.liquid_nw_at_end, compact=True)
        if getattr(outputs, 'liquid_nw_at_end', 0) > 0 else "$0"
    )
    col3.metric(
        "Spendable NW at end",
        liquid_txt,
        help="Portfolio balance at end-of-plan. Excludes home equity (locked) and illiquid custom assets.",
    )
    col4.metric("Lifetime fed tax", format_money(outputs.lifetime_federal_tax, compact=True))


def render_reset_button(persona_id: str) -> None:
    """Render a 'Reset to persona defaults' button when inputs are modified."""
    inputs = st.session_state.get("inputs", {})
    modified, _ = _compute_modified(inputs, persona_id)
    if modified:
        if st.button("Reset to persona defaults", type="secondary"):
            if "last_persona" in st.session_state:
                del st.session_state["last_persona"]
            st.rerun()
