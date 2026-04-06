"""
Save/load custom personas.

Four persistence tiers:
  1. **Session-only**: adds a custom persona to the dropdown for this browser tab.
     Lost on page reload. Useful for rapid iteration.
  2. **localStorage (auto-save)**: silently saves current scenario on every change,
     auto-restores on page reload. Per-browser, private to user.
  3. **JSON download/upload**: portable files, work across devices.
  4. **Shareable URL**: base64-encoded scenario in query param — bookmark or share.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

SESSION_CUSTOM_KEY = "custom_personas"
LOCALSTORAGE_KEY = "retirement_planner_scenario_v1"


def session_custom_personas() -> list[dict]:
    """Return list of custom personas saved in current session (may be empty)."""
    import streamlit as st
    return st.session_state.get(SESSION_CUSTOM_KEY, [])


def save_session_persona(name: str, inputs: dict, current_age: int, tagline: str = "") -> None:
    """Add a custom persona to session state."""
    import streamlit as st
    personas = st.session_state.get(SESSION_CUSTOM_KEY, [])
    custom_id = f"custom-{len(personas) + 1}-{name.lower().replace(' ', '-')[:20]}"
    personas.append({
        "id": custom_id,
        "name": name,
        "tagline": tagline or f"Saved {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "inputs": dict(inputs),
        "current_age": int(current_age),
    })
    st.session_state[SESSION_CUSTOM_KEY] = personas


def export_scenario_json(name: str, inputs: dict, current_age: int) -> str:
    """Return a JSON string representing the current scenario, for download."""
    payload = {
        "schema_version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "name": name,
        "current_age": int(current_age),
        "inputs": inputs,
    }
    return json.dumps(payload, indent=2)


def import_scenario_json(blob: bytes | str) -> tuple[str, int, dict[str, Any]]:
    """Parse an uploaded scenario JSON.

    Returns (name, current_age, inputs). Raises ValueError on bad input.
    """
    try:
        data = json.loads(blob)
    except Exception as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict) or "inputs" not in data:
        raise ValueError("Missing 'inputs' field in scenario file")

    name = str(data.get("name", "Imported Scenario"))
    current_age = int(data.get("current_age", 35))
    inputs = data["inputs"]
    if not isinstance(inputs, dict):
        raise ValueError("'inputs' must be a JSON object")
    return name, current_age, inputs


def encode_scenario_to_url_param(inputs: dict, current_age: int, name: str = "") -> str:
    """Encode a scenario into a URL-safe base64 string for query params.

    Usable in `?s=<encoded>` → shareable bookmarkable links.
    """
    payload = {"n": name, "a": current_age, "i": inputs}
    raw = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_scenario_from_url_param(encoded: str) -> tuple[str, int, dict[str, Any]] | None:
    """Decode a scenario from URL query param. Returns None if invalid."""
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or "i" not in payload:
            return None
        return (
            str(payload.get("n", "Shared Scenario")),
            int(payload.get("a", 35)),
            dict(payload["i"]),
        )
    except Exception:
        return None
