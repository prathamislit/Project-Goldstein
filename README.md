# Project Goldstein
**Quantamental Geopolitical Volatility Signal Engine**

A signal engine that converts real-time geopolitical event streams into a market-calibrated risk score — the **Geopolitical Risk Premium Score (GRPS)** — updated daily across 12 global chokepoints and validated against equity and commodity volatility.

> **Research documentation:** Full methodology and institutional tearsheet available on request — [pns5158@psu.edu](mailto:pns5158@psu.edu)

---

## What it does

Most geopolitical risk tools produce qualitative assessments: red/amber/green country ratings, analyst commentary, narrative indexes. Project Goldstein is different. It produces a single 0–100 score per region that has been statistically validated to predict variance increases in linked sector instruments — not just correlate with returns after the fact.

The core insight is that geopolitical risk does not move prices on average. **It moves volatility.** Modelling it as a variance input — not a return predictor — is what makes GRPS actionable for risk desks rather than just interesting to researchers.

---

## How GRPS works

GRPS is a composite score built from three signal components — event-based instability, sector volatility premium, and macro fear conditioning — combined under a proprietary weighting and regime classification scheme.

The scoring and model engine are not included in this public release. GRPS outputs three regimes: **STABLE** (0–33) · **ELEVATED** (33–66) · **CRITICAL** (66–100).

This is a **risk management signal**. It quantifies variance pressure — not direction. A fund using GRPS=ELEVATED on Hormuz to size a crude hedge is not arbitraging an inefficiency; they are pricing protection. This is why the signal does not decay upon publication.

---

## Validated Results

Coefficients fitted on 2022–2026 data. Warm-up period (first 252 trading days per region) excluded from all validation.

| Region | ETF Proxy | γ (geo→variance) | p-value |
|---|---|---|---|
| Middle East | XLE | 0.934 | < 0.001 |
| Eastern Europe | XME | 0.918 | < 0.001 |
| Taiwan Strait | SOXX | 0.897 | < 0.001 |

Remaining 9 regions are live. Coefficients will be published after their 90-day post-warmup validation window closes.

**Backtest** (threshold-crossing event study, 21-day forward window, 12 regions):

| Metric | Result |
|---|---|
| Avg hit rate (vol > 75th pct post-crossing) | 64.4% |
| Avg false positive rate | 29.2% |
| Avg Spearman IC | 0.23 |
| Total validated crossing events | 323 |

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
gdelt_fetcher.py        → event data ingestion from GDELT via BigQuery
market_data.py          → sector ETF + benchmark prices via yfinance
preprocessor.py         → signal alignment and master dataset construction
garch_model.py          → [PRIVATE] volatility model
scorer.py               → [PRIVATE] GRPS scoring engine (0–100)
acled_fetcher.py        → ACLED ground-truth anchor
data_quality.py         → pipeline QC and bounds assertions
backtest.py             → threshold-crossing event study, hit rate, IC computation
analyze.py              → CLI analysis: regime narrative, momentum, anomaly detection
generate_insights.py    → per-region intelligence brief (HTML)
merge_reports.py        → combined intelligence + backtest dashboard
Dashboard.py            → live Plotly Dash dashboard (http://localhost:8050)
config.py               → region and model configuration
Run_All_regions.sh      → full pipeline runner — all 12 regions, health check, auto-launch
```

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

**Optional — ACLED ground-truth integration** (free for research):

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

## Research & Documentation

Full methodology, validation walkthrough, and institutional tearsheet available on request.

Email [pns5158@psu.edu](mailto:pns5158@psu.edu) — subject: **"Project Goldstein — Research Docs"**

---

## Access

| Tier | What you get | Price |
|---|---|---|
| Signal Feed | Daily CSV per region | $299/mo |
| Dashboard | Hosted live dashboard | $799/mo (3 regions) |
| Full Suite | Dashboard + data + CLI | $1,999/mo (all 12) |
| Enterprise | Source license + support | Contact |

→ [pns5158@psu.edu](mailto:pns5158@psu.edu)

---

## What this is not

This is not a news aggregator. It is not a qualitative risk rating. It does not predict specific events or market direction. It measures the current geopolitical variance regime of a region and the risk premium that regime commands in linked financial instruments — updated every trading day.

---

*Project Goldstein · Quantamental Geopolitical Volatility Signal · Core model engine not included in public release.*

**REGULATORY SAFE HARBOR:** GRPS is strictly informational data. It does not constitute investment advice under SEC Rule 202(a)(11).
