"""
Methodology, limitations, and disclaimer.
"""

import sys
from pathlib import Path

import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from helpers.theme import apply_altair_theme, inject_css  # noqa: E402

st.set_page_config(page_title="Methodology", layout="wide")
inject_css()
apply_altair_theme()
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
- **No required minimum distributions (RMDs)** at age 73 (would force taxable 401(k) withdrawals).
- **No state income tax** (add separately if applicable).
- **Fixed asset-class returns** in the deterministic projection. Monte Carlo
  varies them historically.
- **No AMT, NIIT, QBI**, or other special tax provisions.
- **Cash and crypto returns** held constant in Monte Carlo (no long
  historical series).

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
