# Project Goldstein
### Quantamental Geopolitical Volatility Signal Engine

A signal engine that converts real-time geopolitical event streams into a market-calibrated risk score — the **Geopolitical Risk Premium Score (GRPS)** — updated daily across 12 global chokepoints and validated against equity and commodity volatility.

---

## What it does

Most geopolitical risk tools produce qualitative assessments: red/amber/green country ratings, analyst commentary, narrative indexes. Project Goldstein is different. It produces a single 0–100 score per region that has been statistically validated to predict **variance increases** in linked sector instruments — not just correlate with returns after the fact.

The core insight is that geopolitical risk does not move prices on average. It moves **volatility**. Modelling it as a variance input — not a return predictor — is what makes GRPS actionable for risk desks rather than just interesting to researchers.

---

## How GRPS works

The score has three components:

- **Instability Index (40%)** — Percentile rank of Goldstein event hostility over a 252-day rolling window. Measures where the current event balance sits relative to the past year of activity in that region.
- **Vol Premium (40%)** — Realized volatility of the sector ETF proxy, scaled by a geopolitical gate derived from the rolling correlation between Goldstein scores and ETF returns. Captures how much the market is actually pricing the geopolitical channel.
- **VIX Component (20%)** — Z-score of VIX relative to its 252-day rolling distribution, with conditional suppression when macro fear is decoupled from regional event flow.

GRPS outputs three regimes: **STABLE** (0–33), **ELEVATED** (33–66), **CRITICAL** (66–100).

This is a risk management signal. It quantifies variance pressure — not direction. A fund using GRPS=ELEVATED on Hormuz to size a crude hedge is not arbitraging an inefficiency; they are pricing protection. This is why the signal does not decay upon publication.

---

## Validated Results

All coefficients fitted on 2022–2026 data. p < 0.001 across validated regions.

| Region | ETF Proxy | γ (geo→variance) | p-value |
|---|---|---|---|
| Middle East | XLE | **0.934** | < 0.001 |
| Eastern Europe | XME | **0.918** | < 0.001 |
| Taiwan Strait | SOXX | **0.897** | < 0.001 |

Remaining 9 regions are live. Coefficients will be published after their 90-day post-warmup validation window closes.

**Backtest (threshold-crossing event study, 21-day forward window, 12 regions):**

| Metric | Result |
|---|---|
| Avg hit rate (vol > 75th pct post-crossing) | 64.4% |
| Avg false positive rate | 29.2% |
| Avg Spearman IC | 0.23 |
| Total validated crossing events | 323 |

Warm-up period (first 252 trading days per region) excluded from all validation.

---

## Active Regions

| Region | ETF Proxy | Rationale |
|---|---|---|
| Middle East | XLE | Energy sector — direct oil supply exposure |
| Eastern Europe | XME | Metals & mining — commodity shock channel |
| Taiwan Strait | SOXX | Semiconductors — TSMC supply chain risk |
| Strait of Hormuz | USO | WTI/Brent direct — 20% of global oil transit |
| South China Sea | EWH | HK equities — most liquid SCS tension proxy |
| Korean Peninsula | EWJ | Japan markets — peninsula escalation repricing |
| Panama Canal | IYT | Transport — shipping chokepoint exposure |
| Red Sea / Suez | IYT | Transport — 30% of global container rerouting |
| India-Pakistan | INDA | India equities — nuclear escalation premium |
| Sahel / West Africa | GDX | Gold miners — Sahel gold and uranium exposure |
| Venezuela / Caribbean | ILF | LatAm 40 — Essequibo + sanctions cycle |
| Russia / Arctic | XOP | Oil & gas — Arctic resource contestation |

---

## Architecture

```
gdelt_fetcher.py        → sqrt-weighted Goldstein scores from GDELT via BigQuery
market_data.py          → sector ETF + benchmark prices via yfinance
preprocessor.py         → aligns and merges signals into master dataset
garch_model.py          → [PRIVATE] volatility model with geopolitical exogenous input
scorer.py               → [PRIVATE] GRPS scoring engine (0–100)
acled_fetcher.py        → ACLED ground-truth anchor — hard gate on geo_gate
data_quality.py         → QC assertions: VIX bounds, ETF return bounds, GDELT event floors
backtest.py             → threshold-crossing event study, hit rate, IC computation
analyze.py              → CLI analysis: regime narrative, momentum, anomaly detection
generate_insights.py    → builds per-region intelligence brief (HTML)
merge_reports.py        → merges intelligence brief + backtest report into one dashboard
Dashboard.py            → live Plotly Dash dashboard (http://localhost:8050)
config.py               → single source of truth for all region and model parameters
Run_All_regions.sh      → full pipeline runner — all 12 regions, health check, auto-launch
```

The model engine (`garch_model.py`, `scorer.py`) is not in this public release. They contain the proprietary scoring formula and volatility model architecture.

---

## Setup

```bash
git clone https://github.com/prathamislit/Project-Goldstein
cd Project-Goldstein
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in: GCP_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS
```

**Requirements:** Python 3.11+, Google Cloud account with BigQuery API enabled, GCP service account JSON key.

Optional — ACLED ground-truth integration (free for research):
```bash
# Add to .env:
ACLED_API_KEY=your_key
ACLED_EMAIL=your_email
# Register at acleddata.com
```

---

## Running

```bash
# Full run — all 12 regions
bash Run_All_regions.sh

# Incremental — last 14 days only (~$0.12 BigQuery cost)
bash Run_All_regions.sh --incremental

# Dashboard only
python3 Dashboard.py
# → http://localhost:8050

# Intelligence brief + backtest report (combined dashboard)
python3 generate_insights.py && python3 backtest.py --html && python3 merge_reports.py
# → outputs/goldstein_combined.html
```

---

## Output

Daily `outputs/daily_scores_{region}.csv` per region:

```
date, GRPS, GRPS_label, goldstein_wavg, VIX_zscore, component_instability, component_vol_premium, component_vix, is_warmup
2026-04-10, 49.2, ELEVATED, -1.24, 0.83, 64.3, 47.1, 10.7, False
```

Pipeline health written to `logs/health_status.txt` after every run. Run log in `logs/pipeline_run_log.jsonl`.

---

## Access

| Tier | What you get | Price |
|---|---|---|
| Signal Feed | Daily CSV per region | $299/mo |
| Dashboard | Hosted live dashboard | $799/mo (3 regions) |
| Full Suite | Dashboard + data + CLI | $1,999/mo (all 12) |
| Enterprise | Source license + support | Contact |

→ **pns5158@psu.edu**

---

## What this is not

This is not a news aggregator. It is not a qualitative risk rating. It does not predict specific events or market direction. It measures the **current geopolitical variance regime** of a region and the risk premium that regime commands in linked financial instruments — updated every trading day.

---

*Project Goldstein · Quantamental Geopolitical Volatility Signal · Core model engine not included in public release.*
*REGULATORY SAFE HARBOR: GRPS is strictly informational data. It does not constitute investment advice under SEC Rule 202(a)(11).*
