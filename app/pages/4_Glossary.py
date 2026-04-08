"""
Glossary page — plain-language definitions for every term used in the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from helpers.theme import apply_altair_theme, inject_css  # noqa: E402
from helpers.chat_widget import render_chat_in_sidebar  # noqa: E402
from helpers.analytics import track_page_view  # noqa: E402

st.set_page_config(page_title="Glossary", layout="wide")
inject_css()
apply_altair_theme()

render_chat_in_sidebar()
track_page_view("glossary")

st.title("Glossary")
st.caption(
    "Plain-language definitions for every term in the app. If you've seen a term you "
    "didn't recognize, it's probably here."
)

st.divider()

# ---------- Section: Retirement Account Types ----------

st.header("Retirement account types")

st.subheader("Traditional 401(k)")
st.markdown(
    """
**In plain English:** money goes in **before taxes**. You don't pay income tax on it
today. It grows without being taxed. Then, **when you take it out in retirement,
you pay income tax on it.**

**Why it might be right for you:** if you're a high earner now and expect to be in
a **lower tax bracket** in retirement, Traditional saves you more in tax today than
you'll owe later.

**Contribution limits (2025):** $23,500/year (or $31,000 if you're 50+).
    """
)

st.subheader("Roth 401(k) / Roth IRA")
st.markdown(
    """
**In plain English:** money goes in **after taxes** (from your regular paycheck).
You've already paid tax on it. It grows without being taxed. When you take it out
in retirement, **you pay ZERO tax on it** — including all the growth.

**Why it might be right for you:** if you're in a **low tax bracket now** (young
earner, sabbatical year, early career) or expect to be in a **higher bracket in
retirement** (rare but possible if you'll have lots of taxable income), Roth saves
you more tax over your lifetime.

**The tradeoff:** Roth shrinks your paycheck more today because you don't get the
upfront deduction. You'll have less to live on or invest elsewhere.

**Simple rule of thumb:** If your current tax rate > retirement tax rate, use
Traditional. If < retirement rate, use Roth. Most people are in-between and split.
    """
)

st.subheader("Roth Conversion Ladder")
st.markdown(
    """
**In plain English:** a strategy where you **move money from Traditional → Roth**
during low-income years (usually between retirement and age 67), paying tax on the
conversion amount at a low bracket.

**Why it matters:** if you retire early (e.g., age 50) before Social Security kicks
in (age 67), your taxable income during those years might be very low. Converting
Traditional to Roth during that window lets you pay tax at a lower rate than you
would later — and the converted Roth money then grows tax-free forever and isn't
subject to RMDs (see below).

**This is a classic FIRE (Financial Independence) strategy.** It's not for everyone,
but it can save hundreds of thousands in taxes for early retirees.
    """
)

st.divider()

# ---------- Section: Concepts ----------

st.header("Concepts you'll see")

st.subheader("RMD (Required Minimum Distribution)")
st.markdown(
    """
**In plain English:** starting at age **73**, the IRS **forces** you to withdraw a
minimum amount from your Traditional 401(k) and IRA each year — whether you need
the money or not. You pay income tax on whatever comes out. **Roth accounts are
EXEMPT from RMDs** (a major Roth advantage).

**How much:** the IRS publishes a table. At age 73 you must withdraw
`balance ÷ 26.5` (≈3.8%). At 80 it's `balance ÷ 20.2` (≈5%). At 90 it's
`balance ÷ 12.2` (≈8%).

**Why you should care:** if you have a large Traditional balance and frugal
lifestyle, RMDs can force you into a **higher tax bracket** than you'd choose —
sometimes called "RMD tax torpedo." This is one reason people do Roth conversions
earlier: to shrink their Traditional balance before RMDs hit.

**Penalty for skipping:** 25% of the missed RMD amount (recently reduced from 50%).
    """
)

st.subheader("Bengen 4% Rule (a.k.a. the Trinity Study)")
st.markdown(
    """
**In plain English:** a famous retirement rule-of-thumb from 1994. It says:
**"If your portfolio is ≥ 25× your annual spending, you can safely retire."**

**Why 25×?** Because 1/25 = 4%. The rule is: withdraw 4% of your portfolio in year
1, adjust that amount for inflation each year after. Historically, a 60/40
stock/bond portfolio followed this way survived 30 years with ~95% success.

**Why you should care:** it's the single most popular retirement heuristic. If
someone says "the 4% rule" they mean this. Our Monte Carlo page shows whether your
scenario beats or falls short of this benchmark.

**Limitations:** assumes 30-year retirement, 60/40 mix, US historical returns, no
taxes, no spending variability. Our full model is more accurate, but the 4% Rule
is a useful sanity check.
    """
)

st.subheader("LTC (Long-Term Care)")
st.markdown(
    """
**In plain English:** help you need when you can't manage basic daily tasks
yourself — bathing, dressing, eating, moving around. It can mean in-home care, an
assisted living facility, or a nursing home.

**Why it matters:** ~70% of people 65+ will need some form of LTC. Median cost in
2024: **$9K/month for a nursing home**, $6K for assisted living, $5K for in-home
care. Medicare does NOT cover long-term care (common misconception). Medicaid only
covers it if you've already spent your savings down.

**Average duration:** about 3 years, but ~14% need it for 5+ years.

**Planning options:** self-insure (budget for it), LTC insurance ($1-4K/yr
premiums), hybrid life insurance with LTC rider, or count on Medicaid.

**Our model:** the LTC toggle lets you add a one-time event (N years × $X/mo at
age Y) to see how it affects your plan. Default: $8K/mo × 3 years at age 82.
    """
)

st.subheader("HSA (Health Savings Account)")
st.markdown(
    """
**In plain English:** a savings account with **triple tax advantage**: money goes
in pre-tax, grows tax-free, and comes out tax-free for qualified medical expenses.
After age 65, you can withdraw for ANY purpose (though non-medical withdrawals are
taxed as income, like a Traditional 401(k)).

**Who can use it:** you need a high-deductible health plan (HDHP). Contribution
limits 2025: $4,300/yr (individual) or $8,550/yr (family).

**Why it matters:** many people treat HSA as a "stealth retirement account" — pay
medical expenses out of pocket today, let the HSA grow for decades, then use it
tax-free for retirement healthcare.

**Our model:** use a Custom Asset slot to model an HSA for now. Dedicated HSA
support is deferred.
    """
)

st.subheader("MAGI (Modified Adjusted Gross Income)")
st.markdown(
    """
**In plain English:** a version of your income the IRS uses to decide if you qualify
for certain tax benefits. It's your Adjusted Gross Income (AGI) plus a few things
added back (usually doesn't matter for most people; MAGI ≈ AGI).

**Why you might see it:** Roth IRA contributions phase out above certain MAGI
thresholds (2025: $161K single, $240K married filing jointly). Other deductions
and credits also use MAGI cutoffs.

**Our model doesn't track MAGI** — we simplify income-phase-out rules. Noted here
because you might see the term elsewhere.
    """
)

st.divider()

# ---------- Section: Investment strategy ----------

st.header("Investment strategy terms")

st.subheader("Glide Path")
st.markdown(
    """
**In plain English:** a schedule that automatically shifts your portfolio to be
**more conservative as you get older**. Younger = more stocks (growth). Older =
more bonds (safety).

**Common formula:** bonds % = (your age − 20) × 2%, capped at some maximum (40%,
60%, or 70% depending on strategy). At age 40: 40% bonds. At age 60: 60% bonds
(if uncapped).

**Our default:** bonds grow 2%/yr starting at age 20, capped at 40%. You can
switch to a "Fixed mix" in the sidebar if you prefer.
    """
)

st.subheader("Fixed Mix (Fixed Asset Allocation)")
st.markdown(
    """
**In plain English:** you pick one stock/bond split and **stay at it your entire
life**. No age-based shift. E.g., "70% stocks, 30% bonds, forever."

**Why use it:** more growth-oriented, simpler to understand. Works if you have
high risk tolerance and long horizon.

**Our default ratio:** 60% stocks / 40% bonds, adjustable in the sidebar.
    """
)

st.subheader("Bond Tent")
st.markdown(
    """
**In plain English:** a middle-ground strategy. Your bond % is **highest at
retirement** (say 60%), then **decreases** afterward (back to 40% by age 80).

**Why it works:** the riskiest years for a retirement plan are the 5 years before
and after retirement (sequence-of-returns risk). A bond tent protects you during
that danger zone, then lets you re-expose to stocks for long-term growth.

**Our model:** not yet implemented. On the backlog.
    """
)

st.subheader("Guyton-Klinger Guardrails")
st.markdown(
    """
**In plain English:** a spending strategy that **adjusts your withdrawals based on
how your portfolio is doing**. If markets crash, cut spending 10%. If markets boom,
increase spending 10%. Keeps your withdrawal rate inside a safe "guardrail."

**Why it's better than fixed 4%:** real retirees don't spend a fixed amount every
year — they naturally cut back during bad times. Guyton-Klinger formalizes that
flexibility, allowing higher safe withdrawal rates (typically 5-5.5% vs 4%).

**Our model:** not yet implemented. On the backlog.
    """
)

st.divider()

# ---------- Section: Debt & Liabilities ----------

st.header("Debt & liabilities")

st.subheader("APR (Annual Percentage Rate)")
st.markdown(
    """
**In plain English:** the yearly interest rate your lender charges. A credit card
at 20% APR means you owe about 1.67% of the remaining balance each month in
interest. The higher the APR, the more expensive the debt.

**Why it matters for retirement:** high-APR debt (credit cards, personal loans)
eats into your savings faster than almost any investment can grow. A 20% credit
card is effectively a -20% return on that money. Paying it off first is usually
the highest-return "investment" available.
    """
)

st.subheader("Amortization")
st.markdown(
    """
**In plain English:** the process of paying off a loan with regular fixed
payments over time. Each payment is split between **interest** (what you owe
the lender) and **principal** (reducing what you actually owe). Early payments
are mostly interest; later ones are mostly principal.

**Our model:** walks 12 monthly payments per year for each debt, tracking the
exact interest/principal split. When the balance reaches $0, payments stop —
so expenses drop automatically.
    """
)

st.subheader("Avalanche Method")
st.markdown(
    """
**In plain English:** a debt payoff strategy. Pay **minimums on everything**,
then throw all extra money at the debt with the **highest interest rate**. When
that debt is paid off, its freed-up payment "cascades" to the next highest rate.

**Why it's optimal:** saves the most total interest. Mathematically, this is
always the cheapest way to eliminate debt.

**Tradeoff:** the highest-rate debt might also be the largest, so the first
victory can take a long time — which some people find discouraging.
    """
)

st.subheader("Snowball Method")
st.markdown(
    """
**In plain English:** like Avalanche, but you target the **smallest balance**
first instead of the highest rate. You get a "win" (debt fully paid off) faster,
which builds momentum.

**Why people use it:** behavioral research shows snowball users are more likely
to stick with the plan and finish paying off all debts, even though it costs
slightly more in total interest.

**Our model supports both.** Enable a payoff strategy in the sidebar under
"Debts & Loans" to compare the impact on your retirement timeline.
    """
)

st.subheader("Student Loan Interest Deduction")
st.markdown(
    """
**In plain English:** the IRS lets you deduct up to **$2,500/year** of student
loan interest from your taxable income (IRC §221). It's an "above-the-line"
deduction — you get it whether or not you itemize.

**Income phase-out:** begins at $80K MAGI single / $165K married filing jointly
(2025). Our model applies the deduction without phase-out for simplicity.

**Why it matters:** at a 22% marginal rate, a $2,500 deduction saves ~$550/year
in federal tax. It's automatic in our model for any debt categorized as
"Student Loan."
    """
)

st.divider()

# ---------- Section: Our app's specific terms ----------

st.header("Terms specific to this app")

st.subheader("Spendable NW vs Total NW")
st.markdown(
    """
**Spendable NW** = portfolio + liquid custom assets + Roth 401(k) − outstanding
debt. Money you can actually pay bills with, net of obligations.

**Total NW** = Spendable NW + home equity + illiquid custom assets. Includes
everything, but some isn't available for spending without selling assets.

We use **Spendable NW** for retirement triggers and plan viability. Home equity
doesn't pay the grocery bill, and outstanding debt reduces what's available.
    """
)

st.subheader("Liquid vs Illiquid Custom Assets")
st.markdown(
    """
**Liquid:** can be drawn down to cover retirement expenses. Counts toward your
retirement target. Examples: REIT, publicly traded stocks, Treasury bonds.

**Illiquid:** appreciates and adds to net worth, but can't pay bills without
selling. Doesn't count toward retirement target. Examples: art collection, private
equity, closely-held business, collectibles.
    """
)

st.subheader("Portfolio Exhaustion")
st.markdown(
    """
When your spendable portfolio hits **$0** during retirement. Doesn't mean you
starve — you still have Social Security, disability, and possibly home equity —
but you're fully dependent on those fixed-income streams.
    """
)

st.divider()

st.markdown(
    """
### Still confused?

Many of these concepts have full Wikipedia pages or IRS publications. This
glossary aims for *enough* understanding to use the app, not financial-planner
expertise. For real decisions, talk to a fee-only fiduciary financial planner.
    """
)
