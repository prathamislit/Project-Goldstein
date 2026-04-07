# Project Goldstein
### Quantitative Geopolitical Volatility Signal Engine

A quantamental signal engine that converts real-time geopolitical event streams into a structured, market-calibrated risk score — the **Geopolitical Risk Premium Score (GRPS)** — validated against equity and commodity volatility across 12 global hotspots.

---

## What it is

Most geopolitical risk tools give you qualitative assessments: red/amber/green country ratings, analyst commentary, index scores with no market linkage. Project Goldstein is different. It quantifies instability into a single 0–100 score that has been validated to predict **variance increases** in sector ETFs — not just correlate with mean returns after the fact.

The core insight: geopolitical risk doesn't move prices on average. It moves **volatility**. Modelling it as a variance input rather than a return predictor is what makes this signal actionable for risk desks, not just researchers.

---

## Validated Results

ARCH-family volatility model with geopolitical exogenous inputs, fitted on 2022–2026 data.
All coefficients significant at p < 0.001 (out-of-sample).

| Region         | ETF Proxy | Exogenous Coefficient | p-value |
|--------------- |-----------|----------------------|---------|
| Middle East    | XLE       | **0.934**            | <0.001  |
| Eastern Europe | XME       | **0.918**            | <0.001  |
| Taiwan Strait  | SOXX      | **0.897**            | <0.001  |

New regions (Hormuz, South China Sea, Korea, Panama, Red Sea, India-Pakistan, Sahel, Venezuela, Arctic) are live — coefficients will be published after 90-day validation window.

---

## Active Regions (12)

| Region               | ETF Proxy | Tier   |
|----------------------|-----------|--------|
| Middle East          | XLE       | Live   |
| Eastern Europe       | XME       | Live   |
| Taiwan Strait        | SOXX      | Live   |
| Strait of Hormuz     | XLE       | Live   |
| South China Sea      | SOXX      | Live   |
| Korean Peninsula     | EWJ       | Live   |
| Panama Canal         | IYT       | Live   |
| Red Sea / Suez       | IYT       | Live   |
| India-Pakistan       | INDA      | Live   |
| Sahel / West Africa  | GDX       | Live   |
| Venezuela / Carib.   | XLE       | Live   |
| Russia / Arctic      | XOP       | Live   |

---

## Architecture

```
gdelt_fetcher.py      → pulls NLP-derived stability index from public event database via BigQuery
market_data.py        → fetches sector ETF + benchmark prices (yfinance)
preprocessor.py       → aligns, cleans, merges signals into master dataset
garch_model.py        → [NOT IN PUBLIC RELEASE] ARCH-family vol model w/ geo exogenous input
scorer.py             → [NOT IN PUBLIC RELEASE] GRPS scoring engine (0–100)
dashboard.py          → Plotly Dash multi-region dashboard
analyze.py            → CLI analysis tool: regime, momentum, anomaly detection
config.py             → single source of truth for all region/parameter config
Run_All_regions.sh    → runs full pipeline for all 12 regions sequentially
```

The model engine (`garch_model.py`, `scorer.py`) is not included in this public release. These files contain the proprietary scoring formula and volatility model.

---

## Installation

```bash
git clone https://github.com/prathamislit/Project-Goldstein
cd project-goldstein
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GCP_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS
```

**Requirements:** Python 3.11+, Google Cloud account with BigQuery API enabled, GCP service account key.

---

## Running the pipeline

```bash
# Single region
REGION=middle_east bash run_pipeline.sh

# All regions
bash Run_All_regions.sh

# Launch dashboard only
python3 dashboard.py
# → http://localhost:8050
```

---

## Signal Output

Daily `daily_scores.csv` per region:

```
date,grps,regime,goldstein_wavg,vix_zscore,...
2026-04-07,74.3,CRITICAL,-1.842,1.87,...
```

**Signal available via API — contact for access.**

---

## Access & Pricing

| Tier            | Access                          | Regions    | Price        |
|-----------------|---------------------------------|------------|--------------|
| Signal Feed     | Daily CSV delivery              | 1 region   | $299/mo      |
| Dashboard       | Hosted dashboard URL            | 3 regions  | $799/mo      |
| Full Suite      | Dashboard + raw data + CLI tool | All 12     | $1,999/mo    |
| Enterprise      | Source license + support        | Unlimited  | Contact      |

→ **pns5158@psu.edu**

---

## What this is not

This is not a geopolitical news aggregator. It is not a qualitative risk rating. It does not predict specific events. It quantifies the **current variance regime** of a hotspot and its market premium — updated daily.

---

*Project Goldstein — Quantamental Geopolitical Volatility Signal. Internal model engine not included in public release.*
