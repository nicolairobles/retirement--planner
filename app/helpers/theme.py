"""
Shared visual design — CSS injection + unified Altair chart theme.

Color palette (slate + blue accents):
  --primary:    #2563eb (slate-blue-600)
  --primary-dk: #1e40af (blue-800)
  --accent:     #0891b2 (cyan-600)
  --success:    #16a34a (green-600)
  --warning:    #d97706 (amber-600)
  --danger:     #dc2626 (red-600)
  --slate-50:   #f8fafc
  --slate-100:  #f1f5f9
  --slate-600:  #475569
  --slate-900:  #0f172a

Typography: system font stack. Tight line-height. Clear hierarchy.
"""

from __future__ import annotations

import altair as alt
import streamlit as st

PALETTE = {
    "primary": "#2563eb",
    "primary_dk": "#1e40af",
    "accent": "#0891b2",
    "success": "#16a34a",
    "warning": "#d97706",
    "danger": "#dc2626",
    "slate_50": "#f8fafc",
    "slate_100": "#f1f5f9",
    "slate_200": "#e2e8f0",
    "slate_400": "#94a3b8",
    "slate_600": "#475569",
    "slate_900": "#0f172a",
}

# Chart color sequence (used across bucket chart, distribution, etc.)
CHART_PALETTE = [
    "#2563eb",  # blue
    "#0891b2",  # cyan
    "#7c3aed",  # violet
    "#16a34a",  # green
    "#d97706",  # amber
    "#dc2626",  # red
    "#475569",  # slate
]


def inject_css() -> None:
    """Inject custom CSS — runs once per page at top."""
    st.markdown(
        """
        <style>
        /* ---------- Page + typography ---------- */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
            max-width: 1200px;
        }
        h1, h2, h3, h4 {
            letter-spacing: -0.01em;
            font-weight: 600;
        }
        h1 {
            font-size: 2.25rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 0.25rem;
        }
        h2 {
            font-size: 1.5rem;
            margin-top: 2rem;
            margin-bottom: 0.75rem;
        }
        h3 {
            font-size: 1.125rem;
            margin-top: 1.25rem;
        }

        /* ---------- Hero scenario card ---------- */
        .hero-card {
            background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1rem;
        }
        .hero-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.75rem;
        }
        .hero-card-title {
            font-size: 0.875rem;
            font-weight: 500;
            color: #475569;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin: 0;
        }
        .hero-card-name {
            font-size: 1.125rem;
            font-weight: 600;
            color: #0f172a;
            margin: 0.125rem 0 0 0;
        }
        .hero-card-badge-mod {
            background: #fef3c7;
            color: #92400e;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.625rem;
            border-radius: 999px;
            white-space: nowrap;
        }
        .hero-card-badge-clean {
            background: #dcfce7;
            color: #166534;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.25rem 0.625rem;
            border-radius: 999px;
            white-space: nowrap;
        }

        /* ---------- Metric cards ---------- */
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 1rem 1.125rem;
            transition: border-color 120ms ease;
        }
        [data-testid="stMetric"]:hover {
            border-color: #cbd5e1;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
            font-weight: 500 !important;
            color: #64748b !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
            font-weight: 700 !important;
            color: #0f172a !important;
            letter-spacing: -0.01em;
        }

        /* ---------- Sidebar polish ---------- */
        [data-testid="stSidebar"] {
            background: #f8fafc;
            border-right: 1px solid #e2e8f0;
        }
        [data-testid="stSidebar"] .stCaption {
            font-size: 0.75rem;
            color: #64748b;
        }

        /* ---------- Buttons ---------- */
        .stButton button {
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.875rem;
            transition: all 120ms ease;
        }

        /* ---------- Caption text ---------- */
        .stCaption {
            color: #64748b;
        }

        /* ---------- Disclaimer box ---------- */
        .disclaimer {
            background: #f8fafc;
            border-left: 3px solid #94a3b8;
            padding: 0.75rem 1rem;
            border-radius: 4px;
            font-size: 0.8125rem;
            color: #475569;
            margin-top: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_altair_theme() -> None:
    """Register + enable a custom Altair theme used by every chart."""
    def _theme():
        return {
            "config": {
                "background": "#ffffff",
                "title": {"font": "sans-serif", "fontSize": 14, "fontWeight": 600, "color": "#0f172a", "anchor": "start"},
                "axis": {
                    "labelFont": "sans-serif", "titleFont": "sans-serif",
                    "labelColor": "#475569", "titleColor": "#0f172a",
                    "labelFontSize": 11, "titleFontSize": 12,
                    "domainColor": "#cbd5e1", "tickColor": "#cbd5e1",
                    "gridColor": "#f1f5f9", "gridOpacity": 1,
                },
                "legend": {
                    "labelFont": "sans-serif", "titleFont": "sans-serif",
                    "labelColor": "#475569", "titleColor": "#0f172a",
                    "labelFontSize": 11, "titleFontSize": 12,
                    "orient": "bottom",
                },
                "view": {"stroke": "transparent"},
                "range": {"category": CHART_PALETTE},
            }
        }
    alt.themes.register("custom", _theme)
    alt.themes.enable("custom")
