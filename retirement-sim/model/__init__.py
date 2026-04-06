"""
Python replica of the retirement simulator's Excel model.

Mirrors the logic in `Retirement_Plan_v1.6_tax.xlsx` so that:
  - historical Monte Carlo can use the full model (not cFIREsim-style simplifications)
  - sensitivity sweeps run without Excel recalc
  - Python-vs-Excel regression tests catch drift in either implementation

Modules:
  tax         — federal bracket lookup, matches Excel `TaxBracket` LAMBDA
  allocation  — glide-path stock/bond/crypto % by age (future)
  returns     — per-bucket returns and blended portfolio return (future)
  withdrawal  — grossed-up withdrawal + waterfall (future)
  income      — SS + disability timing (future)
  property    — purchase, appreciation, mortgage amortization (future)
  projection  — year-by-year loop (future)
  outputs     — retirement age, max spend, NW@end (future)
  integrity   — the 12 integrity checks (future)

Scope: **Moderate tax**. Matches Track B v1.6 workbook.
"""

__version__ = "0.1.0"  # M1: tax module only
