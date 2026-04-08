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


# ---------- Chat Feature Storage ----------

CHAT_HISTORY_KEY = "retirement_planner_chat_history"
CHAT_SETTINGS_KEY = "retirement_planner_chat_settings"
CHAT_USAGE_KEY = "retirement_planner_chat_usage"

# Free tier daily message limit (localStorage — polite speed bump, not security)
FREE_TIER_DAILY_LIMIT = 75


def load_chat_history() -> list[dict]:
    """Load chat history from localStorage.

    Returns list of message dicts with "role" and "content".
    """
    ls = _get_store()
    try:
        raw = ls.getItem(CHAT_HISTORY_KEY)
    except Exception:
        return []
    if not raw:
        return []
    try:
        history = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(history, list):
            return history
        return []
    except Exception:
        return []


def save_chat_history(messages: list[dict]) -> None:
    """Save chat history to localStorage."""
    try:
        ls = _get_store()
        ls.setItem(CHAT_HISTORY_KEY, json.dumps(messages), key=f"ls_set_{CHAT_HISTORY_KEY}")
    except Exception:
        pass


def clear_chat_history() -> None:
    """Clear chat history from localStorage."""
    try:
        ls = _get_store()
        ls.deleteItem(CHAT_HISTORY_KEY, key=f"ls_del_{CHAT_HISTORY_KEY}")
    except Exception:
        pass


def load_chat_settings() -> dict:
    """Load chat settings from localStorage.

    Returns dict with keys: provider, api_key, model, ollama_url
    """
    ls = _get_store()
    try:
        raw = ls.getItem(CHAT_SETTINGS_KEY)
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        settings = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(settings, dict):
            return settings
        return {}
    except Exception:
        return {}


def save_chat_settings(settings: dict) -> None:
    """Save chat settings to localStorage."""
    try:
        ls = _get_store()
        ls.setItem(CHAT_SETTINGS_KEY, json.dumps(settings), key=f"ls_set_{CHAT_SETTINGS_KEY}")
    except Exception:
        pass


def _get_today_key() -> str:
    """Get today's date as a string key (UTC)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_daily_message_count() -> int:
    """Get today's message count for free tier tracking.

    Returns 0 if no messages sent today or data is stale.
    """
    ls = _get_store()
    try:
        raw = ls.getItem(CHAT_USAGE_KEY)
    except Exception:
        return 0
    if not raw:
        return 0
    try:
        usage = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(usage, dict):
            today = _get_today_key()
            if usage.get("date") == today:
                return usage.get("count", 0)
        return 0  # Stale data, reset
    except Exception:
        return 0


def increment_message_count() -> int:
    """Increment today's message count and return new count."""
    today = _get_today_key()
    current = get_daily_message_count()
    new_count = current + 1
    try:
        ls = _get_store()
        usage = {"date": today, "count": new_count}
        ls.setItem(CHAT_USAGE_KEY, json.dumps(usage), key=f"ls_set_{CHAT_USAGE_KEY}")
    except Exception:
        pass
    return new_count


def get_remaining_free_messages() -> int:
    """Get remaining free tier messages for today."""
    used = get_daily_message_count()
    return max(0, FREE_TIER_DAILY_LIMIT - used)


def is_free_tier_exhausted() -> bool:
    """Check if free tier limit is reached for today."""
    return get_daily_message_count() >= FREE_TIER_DAILY_LIMIT
