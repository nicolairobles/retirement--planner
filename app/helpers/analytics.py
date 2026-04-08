"""
Persistent chat analytics — JSONL log file + in-memory session tracking.

Events are appended to a JSONL file (one JSON object per line) so they
survive across user sessions within a deployment.  On Streamlit Cloud the
filesystem is ephemeral (lost on redeploy/sleep), but persists across
user sessions while the app is running — good enough for operational
monitoring.  For permanent storage, swap _write_to_log() for an external
sink (Supabase, Google Sheets, etc.).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

# Log file lives next to the app — writable on Streamlit Cloud
_LOG_DIR = Path(__file__).resolve().parent.parent / "analytics"
_LOG_FILE = _LOG_DIR / "chat_events.jsonl"


def _get_session_id() -> str:
    """Return a stable ID for this browser session (created once per session)."""
    if "_analytics_session_id" not in st.session_state:
        st.session_state["_analytics_session_id"] = uuid.uuid4().hex[:12]
    return st.session_state["_analytics_session_id"]


def _write_to_log(record: dict) -> None:
    """Append a single JSON record to the log file (fire-and-forget)."""
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        # Never let analytics break the app
        logger.debug("Failed to write analytics event", exc_info=True)


def track_event(event: str, **data) -> None:
    """Record an analytics event (in-memory + persistent log)."""
    record = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "session": _get_session_id(),
        **data,
    }

    # In-memory (per-session, for get_analytics_summary)
    if "_chat_analytics" not in st.session_state:
        st.session_state["_chat_analytics"] = []
    st.session_state["_chat_analytics"].append(record)

    # Persistent (survives across sessions within a deployment)
    _write_to_log(record)


# --------------- Convenience helpers ---------------

def track_page_view(page: str) -> None:
    """Track a page view (deduplicated per session — only fires once per page)."""
    seen_key = "_analytics_pages_seen"
    if seen_key not in st.session_state:
        st.session_state[seen_key] = set()
    if page not in st.session_state[seen_key]:
        st.session_state[seen_key].add(page)
        track_event("page_view", page=page)


def track_button(name: str, **data) -> None:
    """Track a button click."""
    track_event("button_click", button=name, **data)


def track_feature_toggle(feature: str, enabled: bool) -> None:
    """Track when a user enables/disables a major feature section."""
    track_event("feature_toggle", feature=feature, enabled=enabled)


# --------------- Reading / summarizing ---------------

def get_analytics_summary() -> dict:
    """Summarize the current session's analytics."""
    events = st.session_state.get("_chat_analytics", [])
    tool_uses = [e for e in events if e["event"] == "tool_call"]
    messages = [e for e in events if e["event"] == "message"]
    errors = [e for e in events if e["event"] == "error"]
    tool_counts = Counter(e.get("tool") for e in tool_uses)
    return {
        "total_messages": len(messages),
        "total_tool_calls": len(tool_uses),
        "tool_breakdown": dict(tool_counts),
        "errors": len(errors),
    }


def read_all_events(limit: int = 500) -> list[dict]:
    """Read the most recent events from the persistent log.

    Returns up to *limit* events, newest first.
    """
    if not _LOG_FILE.exists():
        return []
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        events = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                events.append(json.loads(line))
        events.reverse()
        return events
    except Exception:
        logger.debug("Failed to read analytics log", exc_info=True)
        return []


def get_global_summary() -> dict:
    """Summarize ALL events across all sessions (from persistent log)."""
    events = read_all_events(limit=5000)
    if not events:
        return {"total_events": 0}

    sessions = set(e.get("session", "") for e in events)
    messages = [e for e in events if e["event"] == "message"]
    user_msgs = [e for e in messages if e.get("role") == "user"]
    tool_uses = [e for e in events if e["event"] == "tool_call"]
    errors = [e for e in events if e["event"] == "error"]
    page_views = [e for e in events if e["event"] == "page_view"]
    button_clicks = [e for e in events if e["event"] == "button_click"]
    feature_snaps = [e for e in events if e["event"] == "features_snapshot"]

    tool_counts = Counter(e.get("tool") for e in tool_uses)
    provider_counts = Counter(e.get("provider") for e in messages if e.get("provider"))
    page_counts = Counter(e.get("page") for e in page_views)
    button_counts = Counter(e.get("button") for e in button_clicks)

    # Aggregate feature usage from snapshots
    feature_usage: dict[str, int] = {}
    for snap in feature_snaps:
        for key in ("spouse", "self_employment", "property", "healthcare",
                     "ltc", "roth_conversion", "vehicle", "has_debts"):
            if snap.get(key):
                feature_usage[key] = feature_usage.get(key, 0) + 1

    return {
        "total_events": len(events),
        "unique_sessions": len(sessions),
        "total_user_messages": len(user_msgs),
        "total_tool_calls": len(tool_uses),
        "tool_breakdown": dict(tool_counts),
        "provider_breakdown": dict(provider_counts),
        "page_views": dict(page_counts),
        "button_clicks": dict(button_counts),
        "feature_usage": feature_usage,
        "errors": len(errors),
        "first_event": events[-1].get("ts") if events else None,
        "last_event": events[0].get("ts") if events else None,
    }
