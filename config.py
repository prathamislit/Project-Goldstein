"""
config.py — Single source of truth for all project parameters.
All hardcoded values live here. Nothing is scattered across modules.
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ─── GCP ────────────────────────────────────────────────────────────────────
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if not GCP_PROJECT_ID:
    raise EnvironmentError(
        "GCP_PROJECT_ID not set. Copy .env.example to .env and fill in your project ID."
    )

# ─── Date Range ──────────────────────────────────────────────────────────────
# 2022-present: covers Ukraine invasion, Gaza escalation cycle, post-COVID regime
START_DATE = os.getenv("START_DATE", "2022-01-01")
END_DATE   = os.getenv("END_DATE", (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d"))

# ─── Region & Sector Mapping ─────────────────────────────────────────────────
# Add new regions here — the rest of the pipeline reads from this dict.
REGIONS = {
    "middle_east": {
        "label":       "Middle East",
        "sector_etf":  "XLE",               # Energy — most direct exposure
        "benchmarks":  ["SPY", "GLD"],       # Broad market + gold as safe haven
        "gdelt_countries": [                 # CAMEO CountryCode values for region
            "IR", "IZ", "IS", "SA", "SY", "YM", "LE", "JO", "KU", "TC", "GZ", "WE"
        ],
        "gdelt_adm1_prefix": None,           # None = use country-level filter only
    },
    "eastern_europe": {
        "label":       "Eastern Europe",
        "sector_etf":  "XME",               # Metals & Mining — commodity shock exposure
        "benchmarks":  ["SPY", "GLD"],
        "gdelt_countries": ["UP", "RS", "PL", "BO", "MD"],
        "gdelt_adm1_prefix": None,
    },
    "taiwan_strait": {
        "label":       "Taiwan Strait",
        "sector_etf":  "SOXX",              # Semiconductors — direct supply chain risk
        "benchmarks":  ["SPY", "QQQ"],
        "gdelt_countries": ["TW", "CH"],
        "gdelt_adm1_prefix": None,
    },



    # ── Strait of Hormuz ──────────────────────────────────────────────────────
    # Iran + Oman + Saudi Arabia — controls ~20% of global oil transit
    # ETF: USO (United States Oil Fund) — tracks WTI crude directly.
    # Preferred over XLE (which also covers Permian Basin / Canadian oil sands,
    # diluting Hormuz-specific geopolitical signal with unrelated US production).
    # USO is directly priced off Brent/WTI, where Hormuz disruption is
    # immediately reflected. Previously duplicated XLE with Middle East region.
    "strait_of_hormuz": {
        "label":            "Strait of Hormuz",
        "sector_etf":       "USO",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["IR", "MU", "SA"],
        "gdelt_adm1_prefix": None,
    },

    # ── South China Sea ────────────────────────────────────────────────────────
    # China + Philippines + Vietnam + Malaysia — $3.4T annual trade
    # ETF: EWH (iShares MSCI Hong Kong) — Hong Kong financial markets are the
    # most direct liquid proxy for SCS geopolitical risk; HK equities re-price
    # immediately on Taiwan/SCS escalation. Previously duplicated SOXX with
    # Taiwan Strait, collapsing them into mathematically identical vol signals.
    "south_china_sea": {
        "label":            "South China Sea",
        "sector_etf":       "EWH",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["CH", "RP", "VM", "MY"],
        "gdelt_adm1_prefix": None,
    },

    # ── Korean Peninsula ──────────────────────────────────────────────────────
    # South Korea + North Korea + Japan — nuclear escalation proxy
    "korean_peninsula": {
        "label":            "Korean Peninsula",
        "sector_etf":       "EWJ",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["KS", "KN", "JA"],
        "gdelt_adm1_prefix": None,
    },

    # ── Panama Canal ──────────────────────────────────────────────────────────
    # Panama + Colombia + Cuba — shipping chokepoint, China port influence
    "panama_canal": {
        "label":            "Panama Canal",
        "sector_etf":       "IYT",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["PM", "CO", "CU"],
        "gdelt_adm1_prefix": None,
    },

    # ── Red Sea / Suez Canal ──────────────────────────────────────────────────
    # Yemen Houthis + Djibouti + Egypt + Saudi Arabia
    # 30% of global container traffic rerouted since late 2023
    "red_sea": {
        "label":            "Red Sea / Suez",
        "sector_etf":       "IYT",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["YM", "DJ", "EG", "SA"],
        "gdelt_adm1_prefix": None,
    },

    # ── India-Pakistan ────────────────────────────────────────────────────────
    # Two nuclear states, active LoC skirmishes, India = world's fastest growing major economy
    "india_pakistan": {
        "label":            "India-Pakistan",
        "sector_etf":       "INDA",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["IN", "PK", "AF"],
        "gdelt_adm1_prefix": None,
    },

    # ── Sahel / West Africa ───────────────────────────────────────────────────
    # Mali + Niger + Burkina Faso + Chad — 3 coups in 4 years, Wagner/Africa Corps present
    # Sits on major gold and uranium deposits — GDX is the cleanest proxy
    "sahel": {
        "label":            "Sahel / West Africa",
        "sector_etf":       "GDX",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["ML", "NG", "UV", "CD"],
        "gdelt_adm1_prefix": None,
    },

    # ── Venezuela / Caribbean ─────────────────────────────────────────────────
    # Venezuela + Guyana + Colombia — US sanctions cycles, Guyana Exxon discovery
    # ETF: ILF (iShares Latin America 40) — most liquid LatAm ETF; incorporates
    # Venezuela sanctions regime impact through Brazil/Colombia equity exposure
    # and captures Guyana oil discovery premium. Previously used XLE (third
    # duplicate of US energy ETF), which has minimal direct Venezuela exposure.
    "venezuela": {
        "label":            "Venezuela / Caribbean",
        "sector_etf":       "ILF",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["VE", "GY", "CO"],
        "gdelt_adm1_prefix": None,
    },

    # ── Russia-Arctic ─────────────────────────────────────────────────────────
    # Russia + Norway + Canada — NATO expansion, Svalbard, Northern Sea Route
    "russia_arctic": {
        "label":            "Russia / Arctic",
        "sector_etf":       "XOP",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["RS", "NO", "CA"],
        "gdelt_adm1_prefix": None,
    },

}

# Active region for current run — change this to pivot the entire pipeline
ACTIVE_REGION = os.getenv("REGION", "middle_east")

def get_region_config():
    if ACTIVE_REGION not in REGIONS:
        raise ValueError(f"Region '{ACTIVE_REGION}' not defined in REGIONS config.")
    return REGIONS[ACTIVE_REGION]

# ─── GDELT ───────────────────────────────────────────────────────────────────
GDELT_TABLE      = "gdelt-bq.gdeltv2.events"
GDELT_DATE_COL   = "SQLDATE"
GDELT_SCORE_COL  = "GoldsteinScale"
GDELT_COUNTRY_COL = "ActionGeo_CountryCode"

# ─── Statistical Model Parameters ────────────────────────────────────────────
GRANGER_LAGS     = [1, 3, 7]          # Lag windows to test (days)
ADF_SIGNIFICANCE = 0.05               # p-value threshold for stationarity
GRANGER_SIGNIFICANCE = 0.05           # p-value threshold for Granger precedence
VAR_MAX_LAGS     = 10                 # Max lags for VAR model selection (AIC)
PERCENTILE_WINDOW = 1008              # Trailing window for instability percentiles

# ─── VIX Regime Detection ────────────────────────────────────────────────────
VIX_TICKER          = "^VIX"
VIX_ROLLING_WINDOW  = 252             # 1 trading year
VIX_ZSCORE_THRESHOLD = 1.5           # z-score above this = anomalously elevated VIX
                                      # Replaces the arbitrary >25 hard threshold

# ─── GARCH-X ─────────────────────────────────────────────────────────────────
GARCH_P = 1                           # GARCH lag order
GARCH_Q = 1                           # ARCH lag order
GARCH_DIST = "normal"                 # Error distribution (swap to 't' for fat tails)

# ─── Scoring Thresholds ──────────────────────────────────────────────────────
# Geopolitical Risk Premium Score (GRPS) — output of scorer.py
GRPS_THRESHOLDS = {
    "stable":   (None, 33),           # GRPS < 33
    "elevated": (33,   66),           # 33 <= GRPS < 66
    "critical": (66,   None),         # GRPS >= 66
}

# ─── File Paths ──────────────────────────────────────────────────────────────
DATA_DIR    = "data"
OUTPUTS_DIR = "outputs"

GDELT_RAW_FILE   = f"{DATA_DIR}/gdelt_raw.csv"
MARKET_RAW_FILE  = f"{DATA_DIR}/market_data.csv"
MASTER_FILE      = f"{DATA_DIR}/master_dataset_clean.csv"
SCORES_FILE      = f"{OUTPUTS_DIR}/daily_scores.csv"