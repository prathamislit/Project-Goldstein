"""
acled_fetcher.py — ACLED Ground-Truth Anchor for GRPS geo_gate
──────────────────────────────────────────────────────────────
ACLED (Armed Conflict Location & Event Data) provides verified,
researcher-coded conflict event data — actual fatalities, battles,
explosions, civilian targeting — as opposed to GDELT which measures
media coverage volume.

Role in the GRPS pipeline:
  GDELT  → what journalists are writing about  (media proxy, noisy)
  ACLED  → what is actually happening on the ground  (ground truth)

Integration point — compute_geo_gate() in garch_model.py:
  geo_gate  =  base_geo_gate  ×  acled_modifier

  Hard gate: if ACLED shows near-zero activity in the last 30 days,
  geo_gate is capped at ACLED_HARD_FLOOR (0.25) regardless of GDELT signal.
  This prevents media noise spikes from driving false GRPS positives.

  Soft gate: confirmed ACLED activity scales geo_gate up to 1.5×.
  ACLED confirmation of GDELT signal strengthens score credibility.

  If the ACLED API is unavailable (no key, network error, rate limit),
  the modifier returns 1.0 (no change) — GDELT-only mode is preserved.
  ACLED enhancement is additive to credibility, never a single point of failure.

Setup:
  1. Register at https://acleddata.com/register/ (free for research)
  2. Add to .env:
       ACLED_API_KEY=your_key_here
       ACLED_EMAIL=your_email@domain.com
  3. The pipeline will automatically use ACLED data when keys are present.
     Without keys, falls back silently to GDELT-only mode (modifier = 1.0).

Usage:
  from acled_fetcher import get_acled_modifier, get_acled_summary

  modifier = get_acled_modifier("middle_east", lookback_days=30)
  # Returns float in [ACLED_HARD_FLOOR, ACLED_AMPLIFY_CAP]
  # or 1.0 if API unavailable

  summary = get_acled_summary("strait_of_hormuz", lookback_days=30)
  # Returns dict with events, fatalities, dominant_type, activity_ratio
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

ACLED_ENDPOINT       = "https://api.acleddata.com/acled/read"
ACLED_HARD_FLOOR     = 0.25   # geo_gate floor when ACLED confirms no activity
ACLED_AMPLIFY_CAP    = 1.50   # geo_gate ceiling when ACLED confirms high activity
ACLED_NEUTRAL        = 1.00   # returned when API unavailable — no change to geo_gate
ACLED_BASELINE_DAYS  = 90     # window for computing long-run activity baseline
ACLED_SIGNAL_DAYS    = 30     # window for computing current activity signal

# Thresholds for hard gate application
HARD_GATE_FATALITY_FLOOR = 0    # fatalities in last 30 days below which hard gate fires
HARD_GATE_EVENT_FLOOR    = 3    # events in last 30 days below which hard gate fires

# Cache file to avoid hammering the API on every pipeline run
CACHE_DIR  = Path("data/acled_cache")
CACHE_TTL_HOURS = 23  # refresh once per day

# ── Region → ACLED country/ISO mapping ──────────────────────────────────────
# ACLED uses ISO 3166-1 alpha-2 codes and country names.
# Mapping covers the primary conflict actors per region, not the full GDELT set.
# We use countries where ACLED data is most complete and event quality is highest.

REGION_ACLED_MAP = {
    "middle_east": {
        "countries": ["Israel", "Palestine", "Lebanon", "Syria", "Iraq", "Yemen", "Iran"],
        "iso_codes":  ["IL", "PS", "LB", "SY", "IQ", "YE", "IR"],
        "description": "Levant + Gulf conflict belt",
    },
    "eastern_europe": {
        "countries": ["Ukraine", "Russia", "Belarus", "Moldova"],
        "iso_codes":  ["UA", "RU", "BY", "MD"],
        "description": "Ukraine war zone + Russian border states",
    },
    "taiwan_strait": {
        "countries": ["China", "Taiwan"],
        "iso_codes":  ["CN", "TW"],
        "description": "Cross-strait tension zone",
        "note": "ACLED Taiwan data limited; treat as lower-bound estimate",
    },
    "strait_of_hormuz": {
        "countries": ["Iran", "Oman", "United Arab Emirates"],
        "iso_codes":  ["IR", "OM", "AE"],
        "description": "Hormuz chokepoint — Iran maritime + Houthi spillover",
    },
    "south_china_sea": {
        "countries": ["China", "Philippines", "Vietnam", "Malaysia"],
        "iso_codes":  ["CN", "PH", "VN", "MY"],
        "description": "SCS territorial dispute zone",
    },
    "korean_peninsula": {
        "countries": ["South Korea", "North Korea", "Japan"],
        "iso_codes":  ["KR", "KP", "JP"],
        "description": "Peninsula + Japan Sea provocation zone",
        "note": "North Korea ACLED coverage sparse; Japan incidents only",
    },
    "panama_canal": {
        "countries": ["Panama", "Colombia", "Cuba"],
        "iso_codes":  ["PA", "CO", "CU"],
        "description": "Canal zone + Caribbean basin instability",
    },
    "red_sea": {
        "countries": ["Yemen", "Djibouti", "Somalia", "Egypt"],
        "iso_codes":  ["YE", "DJ", "SO", "EG"],
        "description": "Red Sea / Bab-el-Mandeb chokepoint — Houthi attack zone",
    },
    "india_pakistan": {
        "countries": ["India", "Pakistan", "Afghanistan"],
        "iso_codes":  ["IN", "PK", "AF"],
        "description": "LoC skirmish zone + Af-Pak spillover",
    },
    "sahel": {
        "countries": ["Mali", "Niger", "Burkina Faso", "Chad"],
        "iso_codes":  ["ML", "NE", "BF", "TD"],
        "description": "Sahel coup belt — jihadist + Wagner/Africa Corps activity",
    },
    "venezuela": {
        "countries": ["Venezuela", "Colombia", "Guyana"],
        "iso_codes":  ["VE", "CO", "GY"],
        "description": "Venezuela + Essequibo dispute zone",
    },
    "russia_arctic": {
        "countries": ["Russia", "Norway", "Ukraine"],
        "iso_codes":  ["RU", "NO", "UA"],
        "description": "Arctic + European NATO border activity",
    },
}

# ACLED event types and their severity weights for modifier calculation
EVENT_TYPE_WEIGHTS = {
    "Battles":                          3.0,  # direct armed engagement
    "Explosions/Remote violence":       3.0,  # bombings, missile strikes
    "Violence against civilians":       2.5,  # targeted atrocities
    "Riots":                            1.5,  # civil unrest
    "Protests":                         0.8,  # non-violent but signalling
    "Strategic developments":           1.2,  # military positioning, arrests
}


# ── Core API Functions ────────────────────────────────────────────────────────

def _load_cache(region: str) -> Optional[dict]:
    """Load cached ACLED response if within TTL."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{region}.json"
    if not cache_file.exists():
        return None
    data = json.loads(cache_file.read_text())
    cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
    if datetime.utcnow() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
        logger.debug(f"ACLED cache hit for {region}")
        return data
    return None


def _save_cache(region: str, payload: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload["cached_at"] = datetime.utcnow().isoformat()
    (CACHE_DIR / f"{region}.json").write_text(json.dumps(payload))


def fetch_acled_events(region: str, lookback_days: int = 90) -> Optional[pd.DataFrame]:
    """
    Fetch ACLED events for a region via the REST API.

    Returns a DataFrame with columns:
        event_date, event_type, sub_event_type, country, fatalities, notes

    Returns None if API is unavailable, unconfigured, or rate-limited.
    GDELT-only operation is preserved when None is returned.
    """
    api_key = os.getenv("ACLED_API_KEY")
    email   = os.getenv("ACLED_EMAIL")

    if not api_key or not email:
        logger.debug("ACLED_API_KEY or ACLED_EMAIL not set — running in GDELT-only mode")
        return None

    if region not in REGION_ACLED_MAP:
        logger.warning(f"Region '{region}' has no ACLED mapping — skipping")
        return None

    # Check cache first
    cached = _load_cache(region)
    if cached and "events" in cached:
        try:
            return pd.DataFrame(cached["events"])
        except Exception:
            pass

    region_cfg  = REGION_ACLED_MAP[region]
    iso_filter  = "|".join(region_cfg["iso_codes"])
    start_date  = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date    = datetime.utcnow().strftime("%Y-%m-%d")

    params = {
        "key":        api_key,
        "email":      email,
        "iso":        iso_filter,
        "event_date": f"{start_date}|{end_date}",
        "event_date_where": "BETWEEN",
        "fields":     "event_date|event_type|sub_event_type|country|fatalities|notes",
        "limit":      5000,
        "export_type": "json",
    }

    try:
        resp = requests.get(ACLED_ENDPOINT, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("status") != 200:
            logger.warning(f"ACLED API returned status {payload.get('status')} for {region}")
            return None

        rows = payload.get("data", [])
        if not rows:
            # No events returned — legitimate zero-activity result
            df = pd.DataFrame(columns=["event_date", "event_type", "sub_event_type",
                                       "country", "fatalities", "notes"])
        else:
            df = pd.DataFrame(rows)
            df["event_date"] = pd.to_datetime(df["event_date"])
            df["fatalities"] = pd.to_numeric(df.get("fatalities", 0), errors="coerce").fillna(0)

        _save_cache(region, {"events": df.to_dict("records")})
        logger.info(f"ACLED: fetched {len(df)} events for {region} ({start_date} → {end_date})")
        return df

    except requests.exceptions.RequestException as e:
        logger.warning(f"ACLED API request failed for {region}: {e} — falling back to GDELT-only")
        return None
    except Exception as e:
        logger.warning(f"ACLED parsing error for {region}: {e} — falling back to GDELT-only")
        return None


# ── Modifier Computation ──────────────────────────────────────────────────────

def _compute_weighted_activity(df: pd.DataFrame, days: int) -> float:
    """
    Compute severity-weighted event count for the most recent `days` window.
    Weights are defined in EVENT_TYPE_WEIGHTS — battles and explosions count more
    than protests. Fatalities add a linear fatality premium on top.
    """
    if df.empty:
        return 0.0

    cutoff = pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=days)
    window = df[df["event_date"] >= cutoff].copy()

    if window.empty:
        return 0.0

    window["weight"] = window["event_type"].map(EVENT_TYPE_WEIGHTS).fillna(1.0)
    weighted_events  = window["weight"].sum()

    # Fatality premium: each fatality adds 0.1 to the weighted count
    # This prevents low-fatality but high-frequency protests from dominating
    fatality_premium = float(window["fatalities"].sum()) * 0.1

    return weighted_events + fatality_premium


def get_acled_modifier(region: str, lookback_days: int = ACLED_SIGNAL_DAYS) -> float:
    """
    Compute the ACLED geo_gate modifier for a region.

    Returns a float multiplier for geo_gate:
        ACLED_HARD_FLOOR  (0.25)  — ACLED confirms near-zero activity → dampen GDELT noise
        ~1.0              (1.00)  — ACLED activity at historical baseline → neutral
        ACLED_AMPLIFY_CAP (1.50)  — ACLED confirms elevated activity → amplify GDELT signal

    Returns ACLED_NEUTRAL (1.0) if API is unavailable, preserving GDELT-only operation.

    Design principle:
      - The modifier only NARROWS the range of geo_gate, it never dominates it.
      - ACLED at 1.5× still requires GDELT to be elevated for GRPS to be ELEVATED.
      - ACLED at 0.25× prevents a GDELT media spike from producing a false positive
        when ground truth shows nothing is happening.
    """
    df = fetch_acled_events(region, lookback_days=max(lookback_days, ACLED_BASELINE_DAYS))

    if df is None:
        # API unavailable — return neutral, preserve GDELT signal unchanged
        return ACLED_NEUTRAL

    # Current window activity
    signal_activity   = _compute_weighted_activity(df, days=lookback_days)
    # Long-run baseline activity
    baseline_activity = _compute_weighted_activity(df, days=ACLED_BASELINE_DAYS)

    # ── Hard gate ────────────────────────────────────────────────────────────
    # If signal window shows near-zero activity, GDELT spike is likely media noise.
    # Apply hard floor regardless of GDELT signal.
    if df.empty:
        return ACLED_HARD_FLOOR

    signal_window = df[df["event_date"] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=lookback_days))]
    n_events    = len(signal_window)
    n_fatalities= int(signal_window["fatalities"].sum()) if not signal_window.empty else 0

    if n_events <= HARD_GATE_EVENT_FLOOR and n_fatalities <= HARD_GATE_FATALITY_FLOOR:
        logger.info(
            f"ACLED hard gate fired for {region}: {n_events} events, {n_fatalities} fatalities "
            f"in last {lookback_days}d → geo_gate capped at {ACLED_HARD_FLOOR}"
        )
        return ACLED_HARD_FLOOR

    # ── Soft calibration ──────────────────────────────────────────────────────
    # activity_ratio = current 30d / long-run 90d baseline (annualised to same period)
    # Baseline is scaled to the same window length for a fair comparison.
    daily_baseline = baseline_activity / ACLED_BASELINE_DAYS if ACLED_BASELINE_DAYS > 0 else 1.0
    daily_signal   = signal_activity   / lookback_days        if lookback_days > 0        else 1.0

    if daily_baseline < 1e-6:
        # No baseline — neutral (region has no historical ACLED record)
        return ACLED_NEUTRAL

    activity_ratio = daily_signal / daily_baseline

    # Map ratio to modifier: ratio=1.0 → 1.0 modifier, ratio>1.5 → 1.5 modifier
    # Using a dampened log-linear mapping to avoid extreme amplification
    # modifier = clip(0.5 + 0.5 × activity_ratio, FLOOR, CAP)
    raw_modifier = 0.5 + 0.5 * activity_ratio
    modifier     = float(np.clip(raw_modifier, ACLED_HARD_FLOOR, ACLED_AMPLIFY_CAP))

    logger.info(
        f"ACLED modifier for {region}: {modifier:.3f}  "
        f"(signal={daily_signal:.2f}/day, baseline={daily_baseline:.2f}/day, "
        f"ratio={activity_ratio:.2f})"
    )
    return modifier


def get_acled_summary(region: str, lookback_days: int = ACLED_SIGNAL_DAYS) -> dict:
    """
    Return a structured summary of ACLED activity for a region.
    Used by generate_insights.py to add ground-truth context to the narrative.

    Returns dict with:
        available        : bool  — True if ACLED data was retrieved
        n_events         : int   — total events in window
        n_fatalities     : int   — total fatalities in window
        dominant_type    : str   — most frequent event type
        activity_ratio   : float — current vs baseline activity level
        modifier         : float — computed geo_gate modifier
        hard_gate_fired  : bool  — True if hard gate was applied
        countries        : list  — countries with events in window
        coverage_note    : str   — any known data quality caveats for this region
    """
    result = {
        "available":       False,
        "n_events":        0,
        "n_fatalities":    0,
        "dominant_type":   "unknown",
        "activity_ratio":  1.0,
        "modifier":        ACLED_NEUTRAL,
        "hard_gate_fired": False,
        "countries":       [],
        "coverage_note":   REGION_ACLED_MAP.get(region, {}).get("note", ""),
    }

    df = fetch_acled_events(region, lookback_days=max(lookback_days, ACLED_BASELINE_DAYS))

    if df is None:
        result["available"] = False
        result["modifier"]  = ACLED_NEUTRAL
        return result

    result["available"] = True
    result["modifier"]  = get_acled_modifier(region, lookback_days)

    signal_window = df[df["event_date"] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=lookback_days))]

    if signal_window.empty:
        result["hard_gate_fired"] = True
        return result

    result["n_events"]     = len(signal_window)
    result["n_fatalities"] = int(signal_window["fatalities"].sum())
    result["hard_gate_fired"] = (
        result["n_events"] <= HARD_GATE_EVENT_FLOOR and
        result["n_fatalities"] <= HARD_GATE_FATALITY_FLOOR
    )

    if "event_type" in signal_window.columns and not signal_window.empty:
        result["dominant_type"] = signal_window["event_type"].value_counts().index[0]

    if "country" in signal_window.columns:
        result["countries"] = signal_window["country"].unique().tolist()

    # Activity ratio for summary
    baseline_activity = _compute_weighted_activity(df, days=ACLED_BASELINE_DAYS)
    signal_activity   = _compute_weighted_activity(df, days=lookback_days)
    daily_baseline = baseline_activity / ACLED_BASELINE_DAYS if ACLED_BASELINE_DAYS > 0 else 1.0
    daily_signal   = signal_activity   / lookback_days        if lookback_days > 0        else 1.0
    result["activity_ratio"] = round(daily_signal / daily_baseline, 2) if daily_baseline > 1e-6 else 1.0

    return result


# ── Integration helper for garch_model.py ───────────────────────────────────

def apply_acled_to_geo_gate(geo_gate_series: "pd.Series", region: str) -> "pd.Series":
    """
    Apply ACLED modifier to an existing geo_gate pandas Series.

    Called from garch_model.compute_geo_gate() after the base geo_gate
    is computed from GDELT correlation. This is the integration point.

    Example in garch_model.py:
        from acled_fetcher import apply_acled_to_geo_gate
        roll_corr = ...  # existing geo_gate computation
        roll_corr = apply_acled_to_geo_gate(roll_corr, region=region)

    The modifier is a scalar applied uniformly to the entire series.
    A future enhancement could fetch monthly ACLED snapshots and apply
    a time-varying modifier — but the current approach is conservative
    and avoids look-ahead bias.
    """
    modifier = get_acled_modifier(region)

    if modifier == ACLED_NEUTRAL:
        # API unavailable or neutral — return unchanged
        return geo_gate_series

    adjusted = (geo_gate_series * modifier).clip(ACLED_HARD_FLOOR, ACLED_AMPLIFY_CAP)
    logger.info(
        f"ACLED geo_gate adjustment for {region}: modifier={modifier:.3f}  "
        f"geo_gate mean {geo_gate_series.mean():.3f} → {adjusted.mean():.3f}"
    )
    return adjusted


# ── CLI diagnostic ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import config

    parser = argparse.ArgumentParser(description="ACLED ground-truth check for a region")
    parser.add_argument("--region", default="middle_east",
                        choices=list(REGION_ACLED_MAP.keys()))
    parser.add_argument("--days",   type=int, default=30)
    args = parser.parse_args()

    summary = get_acled_summary(args.region, lookback_days=args.days)

    print(f"\n{'═'*60}")
    print(f"  ACLED Summary — {args.region}  ({args.days}-day window)")
    print(f"{'═'*60}")
    print(f"  API available       : {summary['available']}")
    if summary["available"]:
        print(f"  Events in window    : {summary['n_events']}")
        print(f"  Fatalities          : {summary['n_fatalities']}")
        print(f"  Dominant type       : {summary['dominant_type']}")
        print(f"  Activity ratio      : {summary['activity_ratio']:.2f}× baseline")
        print(f"  geo_gate modifier   : {summary['modifier']:.3f}")
        print(f"  Hard gate fired     : {summary['hard_gate_fired']}")
        print(f"  Active countries    : {', '.join(summary['countries'])}")
        if summary["coverage_note"]:
            print(f"  Coverage note       : {summary['coverage_note']}")
    else:
        print("  Set ACLED_API_KEY and ACLED_EMAIL in .env to enable.")
        print(f"  geo_gate modifier   : {summary['modifier']:.3f}  (neutral / GDELT-only mode)")
    print(f"{'═'*60}\n")
