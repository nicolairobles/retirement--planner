"""
Altair chart helpers for the Streamlit app.

Design principles:
  - Every chart tells a story (annotated life events, reference lines)
  - Rich hover tooltips with full context (age, phase, all income streams)
  - Consistent unified palette (see theme.py)
  - Plain-language labels; no jargon in axis titles
  - Data-ink ratio: remove decoration, keep information
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .events import LifeEvent, primary_chart_events

# ──────────────────────────────────────────────────────────────────
# Semantic color palette — one color per CONCEPT across ALL charts.
#
# Design constraints:
#   1. Each concept gets exactly one color; the same hex never means
#      two different things in two different charts.
#   2. Colors are perceptually distinct — no two adjacent stacked
#      categories should be confusable (hue + lightness separation).
#   3. Tailwind-600 base for vividness on white backgrounds.
#
# Concepts and their assignments:
#   Stocks / Portfolio (core)    — blue-600       #2563eb
#   Bonds                        — sky-600        #0284c7
#   401(k) Traditional           — indigo-500     #6366f1
#   Roth 401(k)                  — emerald-500    #10b981
#   Crypto                       — amber-500      #f59e0b
#   Cash                         — slate-400      #94a3b8
#   Home equity (locked)         — stone-500      #78716c
#   Custom assets                — fuchsia-500    #d946ef
#   Social Security              — green-700      #15803d
#   Disability income            — teal-600       #0d9488
#   Other income                 — cyan-500       #06b6d4
#   Portfolio withdrawal         — blue-500       #3b82f6
#   Living expenses              — slate-300      #cbd5e1
#   Mortgage P&I                 — violet-500     #8b5cf6
#   Healthcare                   — rose-600       #e11d48
#   Long-term care               — red-800        #991b1b
#   Retirement event marker      — amber-600      #d97706
#   Other life events            — purple-600     #9333ea
#   Expense total (generic)      — red-600        #dc2626
# ──────────────────────────────────────────────────────────────────

# Asset buckets (stacked areas: projection + breakdown charts)
C_STOCKS = "#2563eb"        # blue-600
C_BONDS = "#14b8a6"         # teal-500 (55+ deg from stocks blue)
C_401K = "#6366f1"          # indigo-500
C_ROTH = "#10b981"          # emerald-500
C_CRYPTO = "#f59e0b"        # amber-500
C_CASH = "#94a3b8"          # slate-400
C_HOME_EQUITY = "#78716c"   # stone-500 (muted, illiquid)
C_CUSTOM = "#d946ef"        # fuchsia-500

# Income streams (income/expense bars)
C_WITHDRAWAL = "#3b82f6"    # blue-500 (lighter than stocks — same family)
C_SS = "#15803d"            # green-700 (dark enough to not clash with emerald Roth)
C_DISABILITY = "#0d9488"    # teal-600
C_OTHER_INCOME = "#f59e0b"  # amber-500 (warm, distinct from teal disability)

# Expense categories (negative bars)
C_LIVING = "#cbd5e1"        # slate-300 (largest bar, stays subtle)
C_MORTGAGE = "#8b5cf6"      # violet-500
C_HEALTHCARE = "#e11d48"    # rose-600 (distinct from living)
C_LTC = "#a16207"           # yellow-700 (warm, 50+ deg from rose-600)

# Debt
C_DEBT_1 = "#ef4444"        # red-500
C_DEBT_2 = "#f97316"        # orange-500
C_DEBT_3 = "#eab308"        # yellow-500

# Event annotations
C_RETIRE_EVENT = "#d97706"  # amber-600
C_INCOME_EVENT = "#15803d"  # green-700 (matches SS)
C_OUTFLOW_EVENT = "#dc2626" # red-600
C_MILESTONE = "#9333ea"     # purple-600


def debt_payoff_chart(
    records: list,
    debt_labels: tuple[str, str, str] = ("Debt 1", "Debt 2", "Debt 3"),
    height: int = 280,
    base_year: int = 2025,
    current_age: int = 35,
) -> alt.Chart | None:
    """Stacked area chart showing debt balances declining to zero over time.

    Returns None if no debt is active (so the caller can skip rendering).
    """
    # Only include years where at least one debt has a balance
    rows = []
    for r in records:
        if r.debt_1_balance > 0.01 or r.debt_2_balance > 0.01 or r.debt_3_balance > 0.01:
            for bal, label, color_idx in [
                (r.debt_1_balance, debt_labels[0], 0),
                (r.debt_2_balance, debt_labels[1], 1),
                (r.debt_3_balance, debt_labels[2], 2),
            ]:
                if bal > 0.01:
                    rows.append({
                        "year": r.year,
                        "age": r.age,
                        "debt": label,
                        "balance": bal,
                    })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    unique_debts = df["debt"].unique().tolist()
    colors_map = {debt_labels[0]: C_DEBT_1, debt_labels[1]: C_DEBT_2, debt_labels[2]: C_DEBT_3}
    domain = [d for d in unique_debts]
    range_ = [colors_map.get(d, C_DEBT_1) for d in domain]

    label_expr = (
        f"datum.value + ' (' + (datum.value - {base_year} + {current_age}) + ')'"
    )

    chart = alt.Chart(df).mark_area(
        interpolate="monotone",
        opacity=0.75,
    ).encode(
        x=alt.X(
            "year:Q", title="Year (age)",
            axis=alt.Axis(format="d", tickCount=10, labelExpr=label_expr),
        ),
        y=alt.Y("balance:Q", title="Outstanding balance", axis=alt.Axis(format="$,.0f"), stack="zero"),
        color=alt.Color(
            "debt:N",
            scale=alt.Scale(domain=domain, range=range_),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("year:Q", title="Year", format="d"),
            alt.Tooltip("debt:N", title="Debt"),
            alt.Tooltip("balance:Q", title="Balance", format="$,.0f"),
        ],
    ).properties(height=height)

    return chart


def projection_chart(
    records: list,
    events: list[LifeEvent] | None = None,
    height: int = 400,
    base_year: int = 2025,
    current_age: int = 35,
) -> alt.Chart:
    """Annotated year-by-year net-worth chart split by liquidity.

    - Stacked area: Portfolio (core) + Roth 401(k) + Home Equity + Custom Assets
    - X-axis shows both year and age
    - Vertical rules + labels for key life events
    """
    # Build stackable rows (one row per visible bucket per year)
    stack_rows = []
    for r in records:
        incomes = []
        if r.salary > 0:
            incomes.append(f"Salary ${r.salary:,.0f}")
        if r.ss_income > 0:
            incomes.append(f"SS ${r.ss_income:,.0f}")
        if r.disability_income > 0:
            incomes.append(f"Disability ${r.disability_income:,.0f}")
        if r.withdrawal > 0:
            incomes.append(f"Withdrew ${r.withdrawal:,.0f}")
        tooltip_summary = " · ".join(incomes) if incomes else "—"

        home_equity = max(r.property_value - r.mortgage_bal, 0.0)
        custom_total = (
            r.custom_asset_1_balance + r.custom_asset_2_balance + r.custom_asset_3_balance
        )
        roth_balance = getattr(r, "roth_401k", 0.0)

        common = {
            "year": r.year, "age": r.age, "phase": r.phase,
            "income_summary": tooltip_summary,
            "expenses": r.living_expenses,
            "total_nw": r.total_nw,
        }
        # Core portfolio always shown (even at 0)
        stack_rows.append({**common, "bucket": "Portfolio (core)", "amount": r.end_balance, "order": 1})
        if roth_balance > 0:
            stack_rows.append({**common, "bucket": "Roth 401(k) (tax-free)", "amount": roth_balance, "order": 2})
        if home_equity > 0:
            stack_rows.append({**common, "bucket": "Home equity (locked)", "amount": home_equity, "order": 3})
        if custom_total > 0:
            stack_rows.append({**common, "bucket": "Custom assets", "amount": custom_total, "order": 4})

    df = pd.DataFrame(stack_rows)

    # Constrain x-axis to actual data range + build age-annotated tick labels
    min_year = min(r.year for r in records)
    max_year = max(r.year for r in records)
    # Label expression: computes age from (year - base_year + current_age)
    label_expr = (
        f"datum.value + ' (' + (datum.value - {base_year} + {current_age}) + ')'"
    )

    stacked = alt.Chart(df).mark_area(opacity=0.85).encode(
        x=alt.X(
            "year:Q", title="Year (age)",
            axis=alt.Axis(format="d", tickCount=10, labelExpr=label_expr),
            scale=alt.Scale(domain=[min_year, max_year], nice=False),
        ),
        y=alt.Y("amount:Q", title="Net worth", axis=alt.Axis(format="$,.0f"), stack="zero"),
        color=alt.Color(
            "bucket:N",
            scale=alt.Scale(
                domain=["Portfolio (core)", "Roth 401(k) (tax-free)", "Home equity (locked)", "Custom assets"],
                range=[C_STOCKS, C_ROTH, C_HOME_EQUITY, C_CUSTOM],
            ),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
        order=alt.Order("order:Q", sort="ascending"),
        tooltip=[
            alt.Tooltip("year:Q", title="Year"),
            alt.Tooltip("age:Q", title="Age"),
            alt.Tooltip("phase:N", title="Phase"),
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("amount:Q", title="Amount", format="$,.0f"),
            alt.Tooltip("total_nw:Q", title="Total NW", format="$,.0f"),
            alt.Tooltip("expenses:Q", title="Expenses", format="$,.0f"),
            alt.Tooltip("income_summary:N", title="This year"),
        ],
    )

    # Spendable-NW line: outlines the top of the Portfolio (spendable) area
    # so users can see at a glance which portion is liquid vs locked.
    spendable_rows = [{"year": r.year, "spendable": r.end_balance} for r in records]
    spendable_df = pd.DataFrame(spendable_rows)
    spendable_line = alt.Chart(spendable_df).mark_line(
        color="#1e40af",  # darker blue than C_STOCKS area fill
        size=2,
        strokeDash=[1, 0],  # solid
    ).encode(
        x="year:Q",
        y="spendable:Q",
        tooltip=[
            alt.Tooltip("year:Q", title="Year"),
            alt.Tooltip("spendable:Q", title="Spendable portfolio", format="$,.0f"),
        ],
    )

    layers = [stacked, spendable_line]

    # Annotate life events
    if events:
        primary = primary_chart_events(events)
        if primary:
            # Color per category
            cat_color = {
                "retirement": C_RETIRE_EVENT,
                "income": C_INCOME_EVENT,
                "outflow": C_OUTFLOW_EVENT,
                "milestone": C_MILESTONE,
            }
            event_rows = []
            # Stagger label positions to avoid overlap when events cluster
            for idx, e in enumerate(primary):
                event_rows.append({
                    "year": e.year, "label": e.short_label,
                    "full_label": e.label, "category": e.category,
                    "label_y": 10 + (idx % 3) * 18,  # 3 tiers: 10, 28, 46
                })
            events_df = pd.DataFrame(event_rows)

            # Style: outflows (recurring) get dimmer rules; narrative events get stronger rules
            rule_size_map = {
                "retirement": 2.0, "income": 1.5, "milestone": 1.5, "outflow": 1.0,
            }
            rule_opacity_map = {
                "retirement": 0.75, "income": 0.6, "milestone": 0.6, "outflow": 0.35,
            }
            events_df["rule_size"] = events_df["category"].map(rule_size_map).fillna(1.0)
            events_df["rule_opacity"] = events_df["category"].map(rule_opacity_map).fillna(0.5)

            rules = alt.Chart(events_df).mark_rule(strokeDash=[5, 3]).encode(
                x="year:Q",
                size=alt.Size("rule_size:Q", legend=None, scale=None),
                opacity=alt.Opacity("rule_opacity:Q", legend=None, scale=None),
                color=alt.Color(
                    "category:N",
                    scale=alt.Scale(
                        domain=list(cat_color.keys()),
                        range=list(cat_color.values()),
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("year:Q", title="Year"),
                    alt.Tooltip("full_label:N", title="Event"),
                ],
            )
            labels = alt.Chart(events_df).mark_text(
                align="left", baseline="top", dx=4,
                fontSize=9, fontWeight=600,
            ).encode(
                x="year:Q",
                y=alt.Y("label_y:Q", scale=None, axis=None),
                text="label:N",
                color=alt.Color(
                    "category:N",
                    scale=alt.Scale(
                        domain=list(cat_color.keys()),
                        range=list(cat_color.values()),
                    ),
                    legend=None,
                ),
            )
            layers.extend([rules, labels])

    # No .interactive() — pan/zoom conflicts with explicit x-axis domain.
    # resolve_scale: x='shared' keeps all layers on the same x-axis.
    # color='independent' prevents event annotation categories (retirement,
    # income, outflow, milestone) from merging into the data legend.
    return alt.layer(*layers).resolve_scale(x='shared', color='independent').properties(height=height)


def income_vs_expenses_chart(
    records: list,
    height: int = 320,
    base_year: int = 2025,
    current_age: int = 35,
) -> alt.Chart:
    """Retirement-years income sources vs expense breakdown.

    - Positive stacked bars: income sources (withdrawal, SS, disability, other)
    - Negative stacked bars: expense breakdown (base, mortgage, healthcare, LTC)
    - Red-shaded background: years where portfolio is exhausted
    """
    retirement_rows = [r for r in records if r.phase == "Retired"]
    if not retirement_rows:
        return alt.Chart(pd.DataFrame({"x": [0]})).mark_text(
            text="Plan doesn't reach retirement in this scenario.",
            fontSize=12, color="#475569",
        ).encode()

    rows = []
    for r in retirement_rows:
        # Income (positive)
        if r.withdrawal > 0:
            rows.append({"year": r.year, "category": "Portfolio withdrawal", "amount": r.withdrawal, "kind": "income"})
        if r.ss_income > 0:
            rows.append({"year": r.year, "category": "Social Security", "amount": r.ss_income, "kind": "income"})
        if r.disability_income > 0:
            rows.append({"year": r.year, "category": "Disability", "amount": r.disability_income, "kind": "income"})
        if (r.other_income_1 + r.other_income_2) > 0:
            rows.append({
                "year": r.year, "category": "Other income",
                "amount": r.other_income_1 + r.other_income_2, "kind": "income",
            })
        # Expenses (negative — plotted below zero)
        if r.expense_base > 0:
            rows.append({"year": r.year, "category": "Living expenses", "amount": -r.expense_base, "kind": "expense"})
        if r.expense_mortgage > 0:
            rows.append({"year": r.year, "category": "Mortgage P&I", "amount": -r.expense_mortgage, "kind": "expense"})
        if r.expense_healthcare > 0:
            rows.append({"year": r.year, "category": "Healthcare", "amount": -r.expense_healthcare, "kind": "expense"})
        if r.expense_ltc > 0:
            rows.append({"year": r.year, "category": "Long-term care", "amount": -r.expense_ltc, "kind": "expense"})
        if r.expense_debt > 0:
            rows.append({"year": r.year, "category": "Debt payments", "amount": -r.expense_debt, "kind": "expense"})
    df = pd.DataFrame(rows)

    domain = [
        "Portfolio withdrawal", "Social Security", "Disability", "Other income",
        "Living expenses", "Mortgage P&I", "Healthcare", "Long-term care", "Debt payments",
    ]
    range_ = [
        C_WITHDRAWAL, C_SS, C_DISABILITY, C_OTHER_INCOME,
        C_LIVING, C_MORTGAGE, C_HEALTHCARE, C_LTC, C_DEBT_1,
    ]

    # Constrain x-axis to actual data range (avoids Altair's wild auto-scaling)
    min_year = min(r.year for r in retirement_rows) - 1
    max_year = max(r.year for r in retirement_rows) + 1
    label_expr = (
        f"datum.value + ' (' + (datum.value - {base_year} + {current_age}) + ')'"
    )

    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X(
            "year:Q", title="Year (age)",
            axis=alt.Axis(format="d", tickCount=10, labelExpr=label_expr),
            scale=alt.Scale(domain=[min_year, max_year], nice=False),
        ),
        y=alt.Y("amount:Q", title="Dollars (↑ income, ↓ expenses)", axis=alt.Axis(format="$,.0f"), stack="zero"),
        color=alt.Color(
            "category:N",
            scale=alt.Scale(domain=domain, range=range_),
            legend=alt.Legend(title=None, orient="bottom", columns=4),
        ),
        tooltip=[
            alt.Tooltip("year:Q", title="Year"),
            alt.Tooltip("category:N", title="Category"),
            alt.Tooltip("amount:Q", title="Amount", format="$,.0f"),
        ],
    )

    # Shade years where portfolio is exhausted
    exhausted_rows = [r for r in retirement_rows if r.end_balance <= 1.0]
    layers = [bars]
    if exhausted_rows:
        start_year = exhausted_rows[0].year
        end_year = exhausted_rows[-1].year
        # Field must be named `year` to SHARE the scale with bars.
        # If we use different field names, Altair creates independent
        # scales with auto-domains and the x-axis blows out.
        shade_df = pd.DataFrame([{"year": start_year, "year_end": end_year}])
        shade = alt.Chart(shade_df).mark_rect(
            color="#fecaca", opacity=0.25,
        ).encode(
            x=alt.X("year:Q",
                    scale=alt.Scale(domain=[min_year, max_year], nice=False)),
            x2="year_end:Q",
        )
        layers = [shade, bars]

    # No .interactive() — pan/zoom would override the explicit x-axis domain.
    # Explicit resolve='shared' ensures all layers use the same x-axis scale.
    return alt.layer(*layers).resolve_scale(x='shared').properties(height=height)


def bucket_breakdown_chart(
    records: list,
    custom_names: tuple[str, str, str] = ("Custom 1", "Custom 2", "Custom 3"),
    height: int = 320,
    base_year: int = 2025,
    current_age: int = 35,
) -> alt.Chart:
    """Portfolio composition over time as stacked area.

    Includes core buckets (stocks/bonds/401k/crypto/cash) AND any enabled
    custom asset buckets. Uses fixed color mapping for consistency.
    """
    # Determine which custom buckets have non-zero balances
    has_custom_1 = any(r.custom_asset_1_balance > 0 for r in records)
    has_custom_2 = any(r.custom_asset_2_balance > 0 for r in records)
    has_custom_3 = any(r.custom_asset_3_balance > 0 for r in records)

    rows = []
    for r in records:
        buckets_this_year = [
            ("Stocks", r.stocks),
            ("Bonds", r.bonds),
            ("401(k)", r.k401),
            ("Crypto", r.crypto),
            ("Cash", r.cash),
        ]
        if has_custom_1:
            buckets_this_year.append((custom_names[0], r.custom_asset_1_balance))
        if has_custom_2:
            buckets_this_year.append((custom_names[1], r.custom_asset_2_balance))
        if has_custom_3:
            buckets_this_year.append((custom_names[2], r.custom_asset_3_balance))
        for name, val in buckets_this_year:
            rows.append({"year": r.year, "bucket": name, "amount": val})
    df = pd.DataFrame(rows)

    domain = ["Stocks", "Bonds", "401(k)", "Crypto", "Cash"]
    range_ = [C_STOCKS, C_BONDS, C_401K, C_CRYPTO, C_CASH]
    # Append custom-asset colors if enabled
    extra_colors = [C_CUSTOM, "#a855f7", "#14b8a6"]  # fuchsia, purple, teal
    for i, (has, cname) in enumerate(zip(
        [has_custom_1, has_custom_2, has_custom_3], custom_names
    )):
        if has:
            domain.append(cname)
            range_.append(extra_colors[i])

    min_year = min(r.year for r in records)
    max_year = max(r.year for r in records)
    label_expr = (
        f"datum.value + ' (' + (datum.value - {base_year} + {current_age}) + ')'"
    )
    return alt.Chart(df).mark_area(opacity=0.85).encode(
        x=alt.X(
            "year:Q", title="Year (age)",
            axis=alt.Axis(format="d", tickCount=10, labelExpr=label_expr),
            scale=alt.Scale(domain=[min_year, max_year], nice=False),
        ),
        y=alt.Y("amount:Q", title="Balance", axis=alt.Axis(format="$,.0f"), stack=True),
        color=alt.Color(
            "bucket:N",
            scale=alt.Scale(domain=domain, range=range_),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("year:Q", title="Year"),
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("amount:Q", title="Balance", format="$,.0f"),
        ],
    ).properties(height=height)


def monte_carlo_distribution_chart(
    terminals_real: list[float],
    deterministic_value: float | None = None,
    height: int = 320,
) -> alt.Chart:
    """Histogram of terminal-NW distribution + optional reference line for deterministic result."""
    df = pd.DataFrame({"terminal_real": terminals_real})
    hist = alt.Chart(df).mark_bar(color=C_STOCKS, opacity=0.8).encode(
        x=alt.X("terminal_real:Q", bin=alt.Bin(maxbins=25),
                title="Terminal real net worth", axis=alt.Axis(format="$,.0f")),
        y=alt.Y("count()", title="Historical cycles"),
    )
    if deterministic_value is not None:
        ref_df = pd.DataFrame({"value": [deterministic_value]})
        rule = alt.Chart(ref_df).mark_rule(color=C_RETIRE_EVENT, size=2, strokeDash=[4, 3]).encode(
            x="value:Q",
        )
        label = alt.Chart(ref_df).mark_text(
            align="left", dx=6, dy=-10, fontSize=11, fontWeight=600, color=C_RETIRE_EVENT,
        ).encode(
            x="value:Q", y=alt.value(10), text=alt.value("Your deterministic plan"),
        )
        return (hist + rule + label).properties(height=height).interactive()
    return hist.properties(height=height).interactive()


def mc_cycles_strip_chart(results: list, height: int = 340) -> alt.Chart:
    """Strip plot: every historical starting year as a dot.

    X = starting year, Y = terminal real NW, color = success/failure.
    Shows at a glance which eras were survivable and which weren't.
    """
    rows = []
    for r in results:
        rows.append({
            "start_year": r.start_hist_year,
            "terminal_real": r.terminal_nw_real,
            "succeeded": "Survived" if r.succeeded else "Failed",
        })
    df = pd.DataFrame(rows)

    # Domain zoomed to the actual year range (with 1-year padding)
    min_year = min(r.start_hist_year for r in results) - 1
    max_year = max(r.start_hist_year for r in results) + 1

    return alt.Chart(df).mark_circle(size=100, opacity=0.85).encode(
        x=alt.X(
            "start_year:Q",
            title="Historical start year",
            axis=alt.Axis(format="d", tickCount=10),
            scale=alt.Scale(domain=[min_year, max_year], nice=False),
        ),
        y=alt.Y(
            "terminal_real:Q",
            title="Terminal real net worth",
            axis=alt.Axis(format="$,.0f"),
        ),
        color=alt.Color(
            "succeeded:N",
            scale=alt.Scale(
                domain=["Survived", "Failed"],
                range=[C_SS, C_OUTFLOW_EVENT],
            ),
            legend=alt.Legend(title=None, orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("start_year:Q", title="Started in"),
            alt.Tooltip("succeeded:N", title="Result"),
            alt.Tooltip("terminal_real:Q", title="Terminal NW", format="$,.0f"),
        ],
    ).properties(height=height).interactive()


def tornado_chart(entries: list[dict], height: int = 400) -> alt.Chart:
    """Horizontal bar chart of sensitivity impact magnitudes.

    `entries` should contain already-human-readable `name` values.
    """
    df = pd.DataFrame([
        {
            "input": e["name"],
            "impact": e["impact"],
            "low": e["low_output"],
            "high": e["high_output"],
        }
        for e in entries
    ])
    return alt.Chart(df).mark_bar(color=C_STOCKS).encode(
        x=alt.X(
            "impact:Q",
            title="How much this input swings the outcome",
            axis=alt.Axis(format="$,.0f"),
        ),
        y=alt.Y(
            "input:N", sort="-x", title=None,
            axis=alt.Axis(
                labelLimit=260,     # give long labels room (default ~180)
                labelFontSize=11,
                labelPadding=6,
            ),
        ),
        tooltip=[
            alt.Tooltip("input:N", title="Input"),
            alt.Tooltip("impact:Q", title="Swing in outcome", format="$,.0f"),
            alt.Tooltip("low:Q", title="Outcome when input is LOW", format="$,.0f"),
            alt.Tooltip("high:Q", title="Outcome when input is HIGH", format="$,.0f"),
        ],
    ).properties(height=height, padding={"left": 10, "right": 10}).interactive()
