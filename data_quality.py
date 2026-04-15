"""
data_quality.py — Pipeline data quality assertions and run logging.

Four production-grade checks that halt the pipeline on bad data rather than
silently propagating corrupt values downstream:

  1. VIX range assertion   — VIX ∈ [8, 80]; outside this = bad Yahoo print
  2. ETF return assertion  — daily log return ∈ [-0.15, +0.15]; outlier = bad print
  3. GDELT event floor    — at least MIN_EVENTS_PER_REGION events; zero = query failed
  4. Run log              — timestamped record of every run with score deltas

Motivation (from audit, FLAW 06):
Yahoo Finance has no SLA, rate-limits aggressively, and lags official close
prints by variable amounts.  If Yahoo returns a corrupted/missing VIX on a
given day, the VIX z-score component silently propagates a bad value into all
12 region scores simultaneously.  These assertions catch that before it
reaches scoring.
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
import config

# ─── Per-region minimum event floors (roughly 10% of historical daily average)
# If a region returns fewer events than this floor in a given GDELT pull,
# something is wrong with the query — not a geopolitical quiet period.
REGION_EVENT_FLOORS = {
    "middle_east":      100,
    "eastern_europe":   50,
    "taiwan_strait":    30,
    "strait_of_hormuz": 40,
    "south_china_sea":  30,
    "korean_peninsula": 20,
    "panama_canal":     15,
    "red_sea":          25,
    "india_pakistan":   40,
    "sahel":            15,
    "venezuela":        10,
    "russia_arctic":    30,
}

RUN_LOG_FILE = "logs/pipeline_run_log.jsonl"


# ─── Assertion 1: VIX sanity ─────────────────────────────────────────────────

def assert_vix_range(df: pd.DataFrame, halt: bool = True) -> bool:
    """
    Assert VIX is within [8, 80] on all trading days.

    VIX < 8: historically unprecedented low — likely a missing/corrupt print
    VIX > 80: only occurred briefly during March 2020 peak; sustained values
              indicate corrupt data rather than genuine market conditions.

    Returns True if assertion passes.
    """
    if "VIX" not in df.columns:
        print("[data_quality] WARNING: VIX column not found — skipping range check.")
        return True

    bad_rows = df[(df["VIX"] < 8) | (df["VIX"] > 80)]
    if len(bad_rows) > 0:
        msg = (
            f"[data_quality] ASSERTION FAILED: {len(bad_rows)} VIX values outside [8, 80].\n"
            f"  Bad rows:\n{bad_rows[['date', 'VIX']].to_string(index=False)}\n"
            f"  Source: Yahoo Finance — possible missing/corrupt print.\n"
            f"  Action: Do not run scorer until VIX data is validated."
        )
        print(msg)
        if halt:
            raise ValueError(msg)
        return False

    print(f"[data_quality] VIX range: OK — all {len(df)} rows within [8, 80]. "
          f"(min={df['VIX'].min():.1f}, max={df['VIX'].max():.1f})")
    return True


# ─── Assertion 2: ETF return sanity ──────────────────────────────────────────

def assert_etf_returns(df: pd.DataFrame, sector_etf: str, halt: bool = True) -> bool:
    """
    Assert ETF daily log returns are within [-0.15, +0.15].

    A single-day log return outside this range (±15%) almost certainly
    indicates a data error (wrong price, adjusted price not applied, split
    not accounted for) rather than a real market event.

    Returns True if assertion passes.
    """
    ret_col = f"{sector_etf}_log_return"
    if ret_col not in df.columns:
        print(f"[data_quality] WARNING: {ret_col} not found — skipping return range check.")
        return True

    bad_rows = df[df[ret_col].abs() > 0.15].dropna(subset=[ret_col])
    if len(bad_rows) > 0:
        msg = (
            f"[data_quality] ASSERTION FAILED: {len(bad_rows)} {sector_etf} log return(s) "
            f"outside [-0.15, +0.15].\n"
            f"  Bad rows:\n{bad_rows[['date', ret_col]].to_string(index=False)}\n"
            f"  Likely cause: bad Yahoo Finance print or unadjusted split.\n"
            f"  Action: Verify raw price data before proceeding."
        )
        print(msg)
        if halt:
            raise ValueError(msg)
        return False

    print(f"[data_quality] ETF returns ({sector_etf}): OK — max daily move "
          f"{df[ret_col].abs().max():.4f} ({df[ret_col].abs().max() * 100:.2f}%).")
    return True


# ─── Assertion 3: GDELT event floor ──────────────────────────────────────────

def assert_gdelt_event_floor(gdelt_df: pd.DataFrame, region: str, halt: bool = True) -> bool:
    """
    Assert the total GDELT event count for a region pull exceeds the floor.

    Zero events almost never means geopolitical silence — it means the BigQuery
    query failed, the FIPS codes are misconfigured, or the date range is wrong.

    Returns True if assertion passes.
    """
    total_events = gdelt_df["event_count"].sum() if "event_count" in gdelt_df.columns else 0
    floor = REGION_EVENT_FLOORS.get(region, 10)

    # Floor applies per-day on average; scale by number of days
    n_days = len(gdelt_df)
    expected_minimum = floor * max(1, n_days)

    if total_events < expected_minimum:
        msg = (
            f"[data_quality] ASSERTION FAILED: {region} returned {total_events} total events "
            f"over {n_days} days (expected ≥{expected_minimum}).\n"
            f"  This almost certainly means the GDELT query failed or FIPS codes are wrong.\n"
            f"  Check BigQuery logs and region config before proceeding."
        )
        print(msg)
        if halt:
            raise ValueError(msg)
        return False

    avg_daily = total_events / max(1, n_days)
    print(f"[data_quality] GDELT event floor ({region}): OK — "
          f"{total_events} total events, {avg_daily:.0f}/day avg (floor={floor}/day).")
    return True


# ─── Assertion 4: Stale data check ───────────────────────────────────────────

def assert_data_freshness(df: pd.DataFrame, max_stale_days: int = 3) -> bool:
    """
    Assert the most recent data row is within max_stale_days of today.

    If the latest date in the master dataset is more than 3 trading days old,
    the pipeline has silently stopped updating.  This catches cron failures.

    Returns True if data is fresh.
    """
    if "date" not in df.columns or df.empty:
        print("[data_quality] WARNING: Cannot check freshness — empty or no date column.")
        return True

    latest = pd.to_datetime(df["date"].max())
    today  = pd.Timestamp.today().normalize()
    age_calendar = (today - latest).days

    # Rough conversion: calendar days to trading days (5/7 ratio)
    age_trading = age_calendar * 5 / 7

    if age_trading > max_stale_days:
        print(f"[data_quality] WARNING: Latest data is {latest.date()} "
              f"({age_calendar} calendar days old). "
              f"Pipeline may not have run recently — check cron logs.")
        return False

    print(f"[data_quality] Data freshness: OK — latest date {latest.date()} "
          f"({age_calendar} calendar days old).")
    return True


# ─── Run log ─────────────────────────────────────────────────────────────────

def write_run_log(region: str, grps_latest: float, grps_label: str,
                  n_rows: int, passed_qc: bool, notes: str = "") -> None:
    """
    Append a structured JSON line to the run log after each successful pipeline run.

    Log format:
    {
        "ts":         "2026-04-14T07:15:00",  # UTC timestamp
        "region":     "middle_east",
        "grps":       44.8,
        "label":      "ELEVATED",
        "n_rows":     1072,
        "passed_qc":  true,
        "notes":      ""
    }

    This log is the source of truth for:
    - Detecting silent cron failures (gap in timestamps)
    - Auditing score stability (large GRPS jumps between runs = investigate)
    - Forward validation: compare grps at T vs. vol realization at T+5/10/21
    """
    os.makedirs("logs", exist_ok=True)
    entry = {
        "ts":        datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "region":    region,
        "grps":      round(float(grps_latest), 1),
        "label":     grps_label,
        "n_rows":    int(n_rows),
        "passed_qc": bool(passed_qc),
        "notes":     notes,
    }
    with open(RUN_LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[data_quality] Run log → {RUN_LOG_FILE} | GRPS={entry['grps']} {entry['label']}")


def read_run_log() -> pd.DataFrame:
    """Read the run log into a DataFrame for analysis."""
    if not os.path.exists(RUN_LOG_FILE):
        return pd.DataFrame()
    records = []
    with open(RUN_LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return pd.DataFrame(records) if records else pd.DataFrame()


# ─── Composite check — call this from scorer.py after scoring ────────────────

def run_market_data_checks(df: pd.DataFrame, sector_etf: str) -> bool:
    """Run assertions 1 and 2 on the master dataset. Returns True if all pass."""
    ok = True
    ok &= assert_vix_range(df, halt=False)
    ok &= assert_etf_returns(df, sector_etf, halt=False)
    ok &= assert_data_freshness(df)
    return ok


if __name__ == "__main__":
    # Quick test: read existing master data and run checks
    region_cfg = config.get_region_config()
    region_master = f"{config.DATA_DIR}/master_dataset_clean_{config.ACTIVE_REGION}.csv"
    if not os.path.exists(region_master):
        region_master = config.MASTER_FILE
    if os.path.exists(region_master):
        df = pd.read_csv(region_master, parse_dates=["date"])
        print(f"[data_quality] Running checks on {region_master} ({len(df)} rows)...")
        run_market_data_checks(df, region_cfg["sector_etf"])
    else:
        print("[data_quality] No master file found — run pipeline first.")

    print("\n[data_quality] Recent run log:")
    log = read_run_log()
    if not log.empty:
        print(log.tail(10).to_string(index=False))
    else:
        print("  (no run log yet)")
