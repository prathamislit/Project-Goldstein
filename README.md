# Project Goldstein

### Quantamental Geopolitical Volatility Signal Engine

Project Goldstein converts geopolitical event flow into a daily market-calibrated risk score: the **Geopolitical Risk Premium Score (GRPS)**.

GRPS is a 0–100 score across 12 strategic regions. It measures geopolitical volatility pressure, not market direction.

---

## What it does

Most geopolitical risk tools produce qualitative assessments: country ratings, analyst commentary, or narrative indexes.

Project Goldstein takes a different approach.

It combines geopolitical event data, market proxy behavior, realized volatility, and VIX regime context into one daily score per region.

The core idea is simple:

Geopolitical risk usually does not predict price direction. It affects uncertainty, hedging demand, and volatility.

GRPS is built to measure that variance pressure.

---

## How GRPS works

The score has three components:

* **Instability Index — 40%**
  Percentile rank of regional Goldstein hostility over a 252-trading-day rolling window.

* **Volatility Premium — 40%**
  Realized volatility of the linked ETF proxy, scaled by a lagged geopolitical-market gate.

* **VIX Component — 20%**
  VIX z-score adjustment, suppressed when broad macro fear is disconnected from regional event flow.

GRPS outputs three regimes:

| Regime   | Score Range |
| -------- | ----------: |
| STABLE   |        0–33 |
| ELEVATED |       33–66 |
| CRITICAL |      66–100 |

This is a risk-management signal.

It quantifies volatility pressure.
It does not predict direction.

---

## Validation Status

Earlier GARCH-X coefficient claims have been removed.

The prior gamma estimates were based on an invalid model specification and should not be treated as validated results.

Current validation focuses on:

* threshold-crossing event studies
* forward realized-volatility response
* Spearman information coefficient
* region-level significance testing
* warm-up exclusion
* QC-gated backfills

The full 12-region framework is live.

Validation remains ongoing across regions and horizons.

---

## Active Regions

| Region                | ETF Proxy | Rationale                        |
| --------------------- | --------: | -------------------------------- |
| Middle East           |       XLE | Energy-sector exposure           |
| Eastern Europe        |       XME | Metals and mining shock channel  |
| Taiwan Strait         |      SOXX | Semiconductor supply-chain risk  |
| Strait of Hormuz      |       USO | Oil chokepoint exposure          |
| South China Sea       |       EWH | Hong Kong equity-market proxy    |
| Korean Peninsula      |       EWJ | Japan-market escalation proxy    |
| Panama Canal          |       IYT | Transport and shipping exposure  |
| Red Sea / Suez        |       IYT | Logistics and rerouting exposure |
| India-Pakistan        |      INDA | India equity-market risk proxy   |
| Sahel / West Africa   |       GDX | Gold and resource exposure       |
| Venezuela / Caribbean |       ILF | Latin America risk proxy         |
| Russia / Arctic       |       XOP | Oil and gas exposure             |

---

## Architecture

```text
preflight.py            → environment and dependency checks
gdelt_fetcher.py        → GDELT BigQuery event extraction
market_data.py          → ETF, benchmark, and VIX prices
preprocessor.py         → merged datasets and rolling features
scorer.py               → GRPS score computation
garch_model.py          → realized-volatility premium component
acled_fetcher.py        → optional ACLED ground-truth anchor
data_quality.py         → QC checks and data assertions
backtest.py             → threshold-crossing validation
generate_insights.py    → HTML intelligence brief
merge_reports.py        → combined report dashboard
Dashboard.py            → local Plotly Dash dashboard
config.py               → region definitions and parameters
Run_All_regions.sh      → full 12-region pipeline runner
```

---

## Setup

```bash
git clone https://github.com/prathamislit/Project-Goldstein
cd Project-Goldstein

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Fill in:

```bash
GCP_PROJECT_ID=
GOOGLE_APPLICATION_CREDENTIALS=
```

Requirements:

* Python 3.11+
* Google Cloud project
* BigQuery API enabled
* service-account JSON key

Optional ACLED integration:

```bash
ACLED_API_KEY=
ACLED_EMAIL=
```

---

## Running

Run preflight:

```bash
python3 preflight.py
```

Run full backfill:

```bash
bash Run_All_regions.sh
```

Run incremental update:

```bash
bash Run_All_regions.sh --incremental
```

Run dashboard:

```bash
python3 Dashboard.py
```

Open:

```text
http://localhost:8050
```

Generate combined report:

```bash
python3 generate_insights.py
python3 backtest.py --html
python3 merge_reports.py
```

Output:

```text
outputs/goldstein_combined.html
```

---

## Output

Daily regional score files:

```text
outputs/daily_scores_{region}.csv
```

Example schema:

```text
date, GRPS, GRPS_label, goldstein_wavg, VIX_zscore,
component_instability, component_vol_premium, component_vix, is_warmup
```

Run health:

```text
logs/health_status.txt
logs/pipeline_run_log.jsonl
```

---

## What this is not

Project Goldstein is not a news aggregator.

It is not a qualitative country-risk score.

It does not predict wars, crises, or market direction.

It measures whether geopolitical event flow is translating into abnormal volatility pressure in linked financial instruments.

---

## Disclaimer

GRPS is informational research data only.

It is not investment advice, a trading recommendation, or a solicitation to buy or sell securities.
