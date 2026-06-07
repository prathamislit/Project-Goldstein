# Project Goldstein — Architecture & Onboarding Guide

> **Purpose**: Quantify the Geopolitical Risk Premium (GRPS) across 12 strategic chokepoints.  
> **Output**: A 0–100 score per region per day, reflecting how much excess volatility in a region's linked financial instrument is attributable to geopolitical event flow.

---

## Quick Start

```bash
# 1. Activate the virtual environment
cd ~/Desktop/P.N.S/goldstein
source venv/bin/activate

# 2. Run the preflight check (catches broken deps before hitting APIs)
python3 preflight.py

# 3. Run all 12 regions (incremental = last 14 days only, ~$0.12 BigQuery)
bash Run_All_regions.sh --incremental

# 4. Full backfill from 2022 (~$6 BigQuery cost)
bash Run_All_regions.sh
```

---

## Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐     ┌───────────┐
│ GDELT       │     │ Yahoo        │     │                │     │           │
│ BigQuery    │────▶│ Finance      │────▶│ preprocessor   │────▶│ scorer    │
│             │     │ (yfinance)   │     │                │     │           │
│ gdelt_      │     │ market_      │     │ Merge, ffill,  │     │ GRPS =    │
│ fetcher.py  │     │ data.py      │     │ log returns,   │     │ 40% inst  │
│             │     │              │     │ VIX z-score    │     │ 40% vol   │
│ → gdelt_    │     │ → market_    │     │                │     │ 20% vix   │
│   raw.csv   │     │   data.csv   │     │ → master_      │     │           │
│             │     │              │     │   dataset_     │     │ → daily_  │
│             │     │              │     │   clean.csv    │     │   scores_ │
│             │     │              │     │   + per-region │     │   {r}.csv │
└─────────────┘     └──────────────┘     └────────────────┘     └───────────┘
                                                                     │
                    ┌──────────────┐     ┌────────────────┐          │
                    │ generate_    │     │ backtest.py    │◀─────────┘
                    │ insights.py  │     │ (validation)   │
                    │ (HTML brief) │     │ → backtest_    │
                    │ → goldstein_ │     │   report.html  │
                    │   insights   │     └────────────────┘
                    │   .html      │              │
                    └──────┬───────┘              │
                           │     ┌────────────────┘
                           ▼     ▼
                    ┌──────────────┐     ┌────────────────┐
                    │ merge_       │     │ Dashboard.py   │
                    │ reports.py   │     │ (Dash app)     │
                    │ → combined   │     │ localhost:8050 │
                    │   .html      │     └────────────────┘
                    └──────────────┘
```

---

## File Inventory

### Core Pipeline (run in order by Run_All_regions.sh)

| # | File | Purpose |
|---|------|---------|
| 0 | `preflight.py` | Pre-run diagnostics — checks Python, venv, packages, credentials |
| 1 | `gdelt_fetcher.py` | Pulls Goldstein Scale events from GDELT BigQuery |
| 2 | `market_data.py` | Pulls ETF/benchmark/VIX prices via yfinance |
| 3 | `preprocessor.py` | Merges GDELT + market data, computes log returns, VIX z-score |
| 4 | `scorer.py` | Computes GRPS (0–100) from 3 components |

### Supporting Modules

| File | Purpose |
|------|---------|
| `config.py` | **Single source of truth** — all region defs, parameters, thresholds, paths |
| `garch_model.py` | Volatility premium component (realised-vol + geo_gate, NOT GARCH-X) |
| `data_quality.py` | VIX range, ETF return, and staleness assertions |
| `acled_fetcher.py` | ACLED ground-truth anchor (optional, requires API key) |

### Reports & Visualization

| File | Purpose |
|------|---------|
| `backtest.py` | Threshold-crossing event study — validates GRPS predictive power |
| `generate_insights.py` | HTML intelligence brief with per-region narratives |
| `merge_reports.py` | Combines insights + backtest into single dashboard HTML |
| `Dashboard.py` | Interactive Dash app (localhost:8050) |

### CLI Tools

| File | Purpose |
|------|---------|
| `analyze.py` | Terminal-only analysis (legacy — `generate_insights.py` is preferred) |
| `stationarity.py` | ADF stationarity tests |
| `var_model.py` | VAR model + Granger precedence tests |

### Infrastructure

| File | Purpose |
|------|---------|
| `Run_All_regions.sh` | Master pipeline runner (12 regions, sequential) |
| `auth.py` | Login gate for production dashboard deployment |
| `deploy.sh` | Docker deployment script |

---

## Key Design Decisions

### 1. Why GRPS uses realised-vol, not GARCH-X
The original GARCH(1,1)-X model was broken — the `arch` library's `x=` parameter goes to the mean equation only, and with `mean='Constant'` it's silently ignored. The "validated gamma=0.934" was a phantom. See `garch_model.py` docstring for full post-mortem.

### 2. Why geo_gate uses a 21-day lag
Without the lag, when a geopolitical shock hits, Goldstein and vol spike simultaneously, the correlation rises mechanically, and vol_premium inflates via procyclical bias. The lag ensures the correlation estimate uses only pre-shock data.

### 3. Why VIX is suppressed on "decoupled" days
VIX is globally identical across all 12 regions. During a pure macro shock (Fed policy, banking crisis), all 12 scores shift equally from the VIX term, generating false positives. Suppression logic reduces VIX contribution by 70% when VIX is elevated but regional Goldstein is calm.

### 4. Why incremental runs merge with existing data
Rolling statistics (VIX z-score, percentile rank) need full history. A 14-day incremental window only has 14 rows — `rolling(252)` would produce all NaN. The preprocessor merges new data with the previous region-specific cache file, then recomputes rolling stats on the full merged dataset.

---

## Adding a New Region

1. Add to `config.py → REGIONS` dict (label, sector_etf, benchmarks, gdelt_countries, color)
2. Add to `data_quality.py → REGION_EVENT_FLOORS` dict
3. Add to `acled_fetcher.py → REGION_ACLED_MAP` dict (if ACLED integration is desired)
4. Add market effects narratives to `generate_insights.py → REGION_EFFECTS` dict
5. Run: `bash Run_All_regions.sh` (the region will be picked up automatically)

**Do NOT add region metadata to Dashboard.py or generate_insights.py** — they derive from config.py automatically.

---

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| All 12 regions fail at GDELT | Wrong Python / packages not installed | `python3 preflight.py` to diagnose |
| Schema mutation error | ETF was changed in config but old cache exists | Delete `data/master_dataset_clean_{region}.csv`, run full backfill |
| VIX assertion failure | Yahoo Finance returned corrupt print | Check `logs/pipeline.log` for the bad date, manually verify |
| Dashboard won't start | Port 8050 in use | `lsof -ti :8050 \| xargs kill -9` |
| Scores all STABLE | Missing region-specific score file | Run full pipeline, not just single region |
