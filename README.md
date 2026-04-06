# Retirement Planner

Interactive retirement planning tool built with Streamlit and a pure-Python
financial projection model. Edit inputs in the sidebar, see your plan update
instantly.

## What it does

Shows, year by year, whether your savings reach retirement and then survive it.
Models taxes, Social Security, Roth vs Traditional 401(k), required minimum
distributions, healthcare inflation, property with mortgage amortization, and
a shifting stock/bond allocation as you age.

Includes a **historical backtest** (Monte Carlo) that replays your plan through
every start year from 1928 to 2024 using actual U.S. stock, bond, and inflation
data. You see how the plan performs through the Great Depression, 1970s
stagflation, 2008, and COVID, not just one smooth averaged path.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app/Planner.py
```

Opens at `http://localhost:8501`.

## Pages

- **Planner** -- inputs sidebar, projection chart, top levers, rent-vs-buy comparison
- **Monte Carlo** -- historical backtest across 1928-2024 sequences
- **Sensitivity** -- which inputs move the needle most
- **Glossary** -- plain-language definitions (Traditional vs Roth, 4% rule, glide path, etc.)
- **Methodology** -- full methodology and disclaimer

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub
2. Sign in at [streamlit.io/cloud](https://streamlit.io/cloud)
3. Create a new app pointing to `app/Planner.py`
4. Set the requirements path to `requirements.txt`
5. Deploy

No secrets, no database, no API keys required. Everything runs in the browser
session. User inputs are saved to browser localStorage only.

## Architecture

```
app/                      Streamlit UI
  Planner.py              Main page (entry point)
  pages/                  Sub-pages (Monte Carlo, Sensitivity, Glossary, Methodology)
  helpers/                Charts, widgets, recommendations, housing comparison
  .streamlit/config.toml  Theme and server config

retirement-sim/           Pure-Python projection engine
  model/                  Dataclasses + year-by-year projection logic
  model/tests/            79 unit tests
  evals/external-benchmarks/
    historical-returns-annual.csv   1928-2024 S&P 500, Treasury, CPI data
```

## Defaults

All defaults are **hypothetical personas** (Alex, Jordan, Sam). No real
financial data is embedded. Users edit the sidebar to model their own situation.

## Not financial advice

This is a planning and exploration tool. See the Methodology page inside the
app for the full disclaimer.
