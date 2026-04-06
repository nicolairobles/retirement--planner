# Retirement Planner — Streamlit App

Interactive web UI for the retirement model built in `retirement-sim/`.
Wraps the Python model with a sidebar-driven input form, projection charts,
historical Monte Carlo, and sensitivity analysis.

**All defaults are hypothetical personas.** No real financial data is
embedded in this app.

## What makes this different

Most online retirement calculators show you one number (you need $1.8M!)
and one smooth compounding curve. This tool is built differently:

- **Dollar-exact parity with a spreadsheet it replicates.** The underlying
  Python model matches an Excel workbook down to the cent across 14 baseline
  scenarios and 23 regression seeds. Every cell is traceable.
- **Tax, Roth, RMDs, healthcare, property — all modeled.** Federal brackets
  (indexed forward), Traditional/Roth 401(k) split, required minimum
  distributions at age 73+, Medicare transition, mortgage amortization,
  property appreciation into net worth.
- **Glide-path allocation.** Bond share auto-rises 2%/yr starting at age 20,
  capped at your max. Toggle to a fixed mix if you prefer.
- **Historical backtest, not just deterministic.** The Monte Carlo page
  replays your plan through every start year 1928 to 2024 using actual
  S&P 500, Treasury, and CPI data (Damodaran + BLS). You see how the plan
  performs through the Great Depression, 1970s stagflation, 2008, COVID,
  etc., not just one averaged path.
- **Sensitivity tornado.** Ranks every input by how much it moves a chosen
  outcome, so you know where to spend your estimation effort.
- **Top levers recommendations.** The Planner auto-surfaces the 3 most
  impactful realistic changes you could make, ranked by retirement-age
  improvement.
- **Auto-saved locally.** All inputs persist in browser localStorage.
  Nothing transmitted anywhere. Reload the tab and your scenario comes back.
- **Open model.** 79 unit tests, 23 scenario regressions, public methodology.
  You can read the code and verify every formula.

What it is NOT: financial advice, a robo-advisor, or a tax-optimization
service. It's a planning/exploration tool that shows you the mechanics
of your own assumptions.

## Quick start

```bash
# From repo root
pip install -r app/requirements.txt --break-system-packages
streamlit run app/Planner.py
```

The app opens at `http://localhost:8501`.

## Pages

- **Planner** (main): inputs sidebar, year-by-year projection, key outputs, top levers
- **Monte Carlo**: historical backtest across 1928-2024 sequences
- **Sensitivity**: tornado diagram ranking inputs by impact
- **Glossary**: plain-language definitions (Traditional vs Roth, RMD, glide path, etc.)
- **Methodology**: full methodology and disclaimer

## Personas (hypothetical)

| Persona | Age | Starting balance | Salary | Target |
|---|---|---|---|---|
| **Alex — Mid-Career Saver** | 35 | $150K | $95K | $1.5M |
| **Jordan — Late Starter** | 45 | $50K | $140K | $1.8M |
| **Sam — Early Career** | 28 | $25K | $68K | $1.8M |

These are **illustrative only** — not modeling any real person. Users are
expected to edit the inputs in the sidebar to reflect their own situation
while running the app locally.

## Architecture

```
app/
├── Planner.py                    # entry point (Planner page)
├── pages/
│   ├── 1_Monte_Carlo.py
│   ├── 2_Sensitivity.py
│   └── 3_Methodology.py
├── helpers/
│   ├── demo_cases.json           # hypothetical personas (no real data)
│   ├── seeds.py                   # SeedCase builders
│   └── charts.py                  # Altair chart factories
└── requirements.txt
```

Imports the Python model from `retirement-sim/model/` via `sys.path`. Does
not modify the model or the eval suite.

## Session state

- `st.session_state.inputs` — current input dict (mutated by sidebar controls)
- `st.session_state.current_age` — persona's starting age
- `st.session_state.last_persona` — tracks persona switches to reset state

## Deployment

### Local only (recommended for private use)

```bash
streamlit run app/Planner.py
```

Runs at `localhost:8501`. No data leaves your machine.

### Streamlit Community Cloud (public deploy)

1. Push this repo to GitHub (if desired — consider privacy first)
2. Sign in at https://streamlit.io/cloud
3. Point to `app/streamlit_app.py`
4. Set `requirements.txt` path to `app/requirements.txt`
5. Free tier supports 1 public app + unlimited private apps

**Before public deploy, verify:**
- [ ] No real financial data in `app/helpers/demo_cases.json`
- [ ] No real data in session state defaults
- [ ] Disclaimer is visible on every page
- [ ] Git history does not contain personal financial data
  (the real `base-current` case lives in `retirement-sim/evals/seed-cases.json`
  and is NEVER imported by the app)

### Privacy architecture

The app is designed so that users can:
- Run it locally with no data leaving their machine
- Fork the repo, edit the personas, deploy their own private instance
- Share a public instance that's populated only with hypothetical defaults

User inputs entered in the sidebar **live only in the Streamlit session** —
they are not logged, persisted, or transmitted anywhere.

## Not yet implemented

- Side-by-side scenario comparison
- User accounts / cross-device persistence
- PDF export
- Mobile-optimized layout
- State income tax (federal only today)
- Spouse/couple modeling (single-filer only today)
- HSA as a distinct bucket (model as Custom Asset for now)
- Guyton-Klinger / variable withdrawal strategies

## Disclaimer

This is a planning/exploration tool, not financial advice. See the
**Methodology** page inside the app for full disclaimer text.
