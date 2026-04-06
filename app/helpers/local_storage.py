"""
Browser localStorage integration for auto-save / auto-restore.

Uses streamlit-local-storage (synchronous component) to avoid the async race
condition that streamlit-js-eval suffers from. Data lives in the user's
browser only; never transmitted anywhere.
"""

from __future__ import annotations

import json

import streamlit as st
from streamlit_local_storage import LocalStorage

from .persistence import LOCALSTORAGE_KEY


def _get_store() -> LocalStorage:
    """Return cached LocalStorage instance."""
    if "_ls_store" not in st.session_state:
        st.session_state["_ls_store"] = LocalStorage()
    return st.session_state["_ls_store"]


def load_from_localstorage() -> dict | None:
    """Read the saved scenario from browser localStorage.

    Returns {"name", "current_age", "inputs"} dict, or None if nothing saved.
    Synchronous — returns real data on first call.
    """
    ls = _get_store()
    try:
        raw = ls.getItem(LOCALSTORAGE_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict) or "inputs" not in payload:
            return None
        return payload
    except Exception:
        return None


def save_to_localstorage(inputs: dict, current_age: int, name: str = "Current scenario") -> None:
    """Write the scenario to browser localStorage (silent, fire-and-forget)."""
    payload = {"name": name, "current_age": int(current_age), "inputs": inputs}
    try:
        ls = _get_store()
        ls.setItem(LOCALSTORAGE_KEY, json.dumps(payload), key=f"ls_set_{LOCALSTORAGE_KEY}")
    except Exception:
        pass


def clear_localstorage() -> None:
    """Remove saved scenario from browser localStorage."""
    try:
        ls = _get_store()
        ls.deleteItem(LOCALSTORAGE_KEY, key=f"ls_del_{LOCALSTORAGE_KEY}")
    except Exception:
        pass
