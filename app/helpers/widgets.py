"""
Reusable Streamlit widget helpers.

- money_input: number_input + live formatted caption ($95,000)
- percent_slider: display as integer % (0-15), store as decimal (0.00-0.15)
- format_money: consistent $ formatting
"""

from __future__ import annotations

import streamlit as st


def format_money(value: float, compact: bool = False) -> str:
    """Format a dollar value consistently.

    compact=True for big numbers (e.g. $1.5M), False for exact (e.g. $1,523,487).
    """
    if value is None:
        return "—"
    if compact:
        if abs(value) >= 1_000_000:
            return f"${value/1_000_000:.2f}M"
        if abs(value) >= 1_000:
            return f"${value/1_000:.0f}K"
    return f"${value:,.0f}"


def money_input(
    label: str,
    current: float,
    *,
    min_value: float = 0,
    max_value: float = 10_000_000,
    step: float = 1_000,
    key: str | None = None,
    help: str | None = None,
) -> float:
    """A number_input with a live formatted-currency caption underneath.

    The caption shows "= $95,000" or similar so users see both the raw
    editable number and the formatted dollar amount.
    """
    value = st.number_input(
        label, min_value=float(min_value), max_value=float(max_value),
        value=float(current), step=float(step), key=key, help=help,
        format="%.0f",
    )
    st.caption(f"= {format_money(value)}")
    return float(value)


def percent_slider(
    label: str,
    current_decimal: float,
    *,
    min_pct: float = 0.0,
    max_pct: float = 15.0,
    step_pct: float = 0.1,
    key: str | None = None,
    help: str | None = None,
) -> float:
    """A percent slider shown as 0-15 integer %, stored internally as decimal.

    `current_decimal` is the stored value (e.g. 0.07 for 7%).
    Returns the decimal representation for model consumption.
    """
    current_pct = current_decimal * 100
    # Clamp to slider range
    current_pct = max(min_pct, min(max_pct, current_pct))
    value_pct = st.slider(
        label, min_value=min_pct, max_value=max_pct,
        value=float(current_pct), step=step_pct, key=key, help=help,
        format="%.1f%%",
    )
    return value_pct / 100.0
