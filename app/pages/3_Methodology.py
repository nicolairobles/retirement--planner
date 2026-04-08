"""
Methodology, limitations, and disclaimer.
"""

import sys
from pathlib import Path

import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from helpers.theme import apply_altair_theme, inject_css  # noqa: E402
from helpers.chat_widget import render_chat_in_sidebar  # noqa: E402
from helpers.analytics import track_page_view  # noqa: E402

st.set_page_config(page_title="Methodology", layout="wide")
inject_css()
apply_altair_theme()

render_chat_in_sidebar()
track_page_view("methodology")
st.title("Methodology & Disclaimer")

st.header("What this tool does")

st.markdown(
    """
This tool runs a deterministic retirement projection year-by-year from your
current age to a chosen end age. For each year it computes:

- **Salary** (working years) using your specified year-1 through year-4 values,
  then growing at your salary-growth rate.
- **Living expenses** inflated annually from a base-year monthly budget.
- **401(k) contribution** (working years), subtracted from salary for taxes.
- **Federal income tax** using 2025 single-filer brackets, indexed annually.
- **Net savings** = salary − expenses − 401(k) − federal tax.
- **Portfolio return** via a glide-path allocation (stocks, bonds, crypto,
  cash, 401k) — bonds share grows 2%/year after age 20, capped at your
  maximum bonds percentage.
- **Retirement trigger**: flips from Working → Retired once Total NW (portfolio
  + property equity − mortgage) reaches your target.
- **Retirement withdrawal** grossed-up via a 2-pass fixed-point so that
  after-tax income (withdrawal + SS + disability − federal tax) covers
  inflation-adjusted expenses.
- **Social Security** starting at your claim age, growing with COLA.
- **Vehicle replacement** cycles during driving years.
- **Debt payments** as mandatory living expenses that reduce savings (working)
  and increase withdrawals (retired). Each debt amortizes monthly; when paid
  off, expenses drop automatically.
"""
)

st.header("Debt modeling")

st.markdown(
    """
Up to three non-mortgage debts (credit card, student loan, auto loan, personal
loan, medical debt, or custom). For each debt, the model:

1. **Walks 12 monthly payments** per year — interest accrues on the remaining
   balance, then the payment covers interest first and the remainder reduces
   principal. Mid-year payoff is handled correctly (no overpayment).
2. **Adds debt payments to living expenses.** During working years this reduces
   net savings; during retirement it increases the grossed-up withdrawal.
3. **Subtracts outstanding balances from Spendable NW** so debt delays the
   retirement trigger realistically.
4. **Student loan interest deduction** (IRC §221) — up to $2,500/year is
   deducted above-the-line from taxable income. Other debt interest is not
   deductible.
5. **Payoff strategies** (optional):
   - **Avalanche** — concentrates extra budget on the highest-rate debt first.
     Mathematically optimal (minimizes total interest).
   - **Snowball** — concentrates on the lowest-balance debt first. Faster
     psychological wins.
   - When a debt pays off, its freed-up minimum payment + extra budget
     **cascades** to the next target automatically.
"""
)

st.header("Historical Monte Carlo")

st.markdown(
    """
The **Monte Carlo** page replays your plan through every historical sequence
of stock, bond, and inflation returns from 1928 onward (Damodaran S&P 500 TR +
10-yr Treasury + BLS CPI). For each starting year it runs the full model
forward — glide path, tax layer, withdrawals — and records the terminal
real net worth. The resulting distribution answers:

- Does the plan survive historical worst cases?
- How does terminal wealth vary across history?
- Which historical starting years are most punishing?
"""
)

st.header("Conservative simplifications")

st.markdown(
    """
- **All retirement income treated as ordinary income** for tax. Reality has
  LTCG differential and 0/50/85% SS taxability rules.
- **Fixed asset-class returns** in the deterministic projection. Monte Carlo
  varies them historically.
- **No AMT, NIIT**, or other special tax provisions.
- **Cash and crypto returns** held constant in Monte Carlo (no long
  historical series).
- **Debt interest rates are fixed** — no variable-rate or refinancing modeling.
- **Student loan interest deduction** ignores income phase-outs (applies full
  deduction up to $2,500 regardless of MAGI).

Net effect: the deterministic projection tends to be **slightly conservative**
(overstates taxes), which is appropriate for planning.
"""
)

st.header("Limitations")

st.markdown(
    """
- **Historical returns ≠ future returns.** Past performance is not a guarantee.
- **Tax law changes.** Brackets, deductions, and SS rules change over decades.
- **Life events.** The model can't anticipate job loss, divorce, health shocks,
  windfalls — re-run with updated inputs as your situation changes.
- **Healthcare costs** are folded into "non-housing expenses"; this is crude for
  retirement years where healthcare can dominate.
- **Sequence-of-returns risk** is captured by Monte Carlo but the deterministic
  run assumes a smooth return path.
"""
)

st.header("⚠️ Disclaimer")

st.warning(
    """
**This tool is for educational and exploratory purposes only. It is not
financial, tax, investment, or retirement advice.**

The projections are model outputs based on your inputs and the assumptions
described above. They do not reflect any specific individual's situation and
should not be relied on for financial planning decisions.

Consult a qualified fee-only financial planner, a CPA, and/or your plan
administrator before making decisions about savings, investments, Social
Security claiming, or retirement timing.
"""
)

st.header("How the underlying model was built")

st.markdown(
    """
This tool is a Python port of an Excel retirement model. The port is verified
via a **dollar-exact parity test**: for 14 scenarios, the Python model's
outputs match the Excel workbook's outputs to the penny. The Python model has
79 unit tests, a full-model historical Monte Carlo, and sensitivity tooling.

The validation process caught 2 bugs in the Excel model along the way
(hardcoded starting balance and hardcoded near-term expenses). The Python
replica prevents regression in either implementation.

For technical details, see the repository README and implementation plan.
"""
)
