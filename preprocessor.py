"""
preprocessor.py — Merges GDELT + market data, computes log returns and VIX z-score.

Steps:
1. Load gdelt_raw.csv and market_data.csv
2. Merge on date (left join on market dates — market is the anchor)
3. Forward-fill Goldstein scores across weekends/holidays
   (geopolitical state doesn't reset; it persists until new event data arrives)
4. Compute daily log returns for ETF and benchmarks
5. Compute rolling VIX z-score (replaces arbitrary VIX > 25 threshold)
6. Flag "Decoupled" days where VIX z-score is anomalous
7. Output: data/master_dataset_clean.csv
"""

import os
import pandas as pd
import numpy as np
import config


def load_raw_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load raw CSVs from disk."""
    if not os.path.exists(config.GDELT_RAW_FILE):
        raise FileNotFoundError(
            f"[preprocessor] GDELT file not found: {config.GDELT_RAW_FILE}\n"
            "Run: python gdelt_fetcher.py"
        )
    if not os.path.exists(config.MARKET_RAW_FILE):
        raise FileNotFoundError(
            f"[preprocessor] Market data file not found: {config.MARKET_RAW_FILE}\n"
            "Run: python market_data.py"
        )

    gdelt  = pd.read_csv(config.GDELT_RAW_FILE,  parse_dates=["date"])
    market = pd.read_csv(config.MARKET_RAW_FILE, parse_dates=["date"])
    return gdelt, market


def compute_log_returns(df: pd.DataFrame, price_cols: list[str]) -> pd.DataFrame:
    """
    Compute daily log returns: ln(P_t / P_{t-1})

    Log returns are used instead of raw prices because:
    - Raw prices are non-stationary (they trend), which invalidates Granger/VAR models
    - Log returns are approximately stationary and normally distributed
    - They're additive across time (useful for multi-period aggregation)
    """
    for col in price_cols:
        if col in df.columns:
            df[f"{col}_log_return"] = np.log(df[col] / df[col].shift(1))
    return df


def compute_vix_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rolling z-score of VIX over a 252-day (1 trading year) window.

    z = (VIX_t - rolling_mean) / rolling_std

    A z-score > VIX_ZSCORE_THRESHOLD signals anomalously elevated VIX
    relative to its own recent history — this is the "Decoupled" flag.

    Why this beats VIX > 25:
    - Self-calibrating: adapts to the current volatility regime
    - Statistically grounded: based on the distribution of recent VIX, not a fixed number
    - Works in both high-vol regimes (2022) and low-vol regimes (2024)
    """
    if "VIX" not in df.columns:
        print("[preprocessor] WARNING: VIX column not found. Skipping z-score computation.")
        return df

    rolling_mean = df["VIX"].rolling(window=config.VIX_ROLLING_WINDOW, min_periods=30).mean()
    rolling_std  = df["VIX"].rolling(window=config.VIX_ROLLING_WINDOW, min_periods=30).std()

    df["VIX_zscore"]   = (df["VIX"] - rolling_mean) / rolling_std
    df["VIX_elevated"] = df["VIX_zscore"] > config.VIX_ZSCORE_THRESHOLD

    return df


def flag_decoupled(df: pd.DataFrame, sector_etf: str) -> pd.DataFrame:
    """
    Flag days where geopolitical signal is weak but VIX is anomalously high.
    This means the sector is being driven by something other than the
    specific geopolitical event we're measuring — label it 'Decoupled'.

    Correlation check uses a 30-day rolling window between Goldstein
    score and ETF log return.
    """
    ret_col = f"{sector_etf}_log_return"
    if ret_col not in df.columns or "goldstein_wavg" not in df.columns:
        return df

    # Rolling 30-day correlation between Goldstein score and ETF return
    df["rolling_corr_30d"] = (
        df["goldstein_wavg"]
        .rolling(30)
        .corr(df[ret_col])
    )

    # Decoupled: correlation is weak AND VIX is anomalously elevated
    df["decoupled_flag"] = (
        df["rolling_corr_30d"].abs() < 0.3
    ) & (
        df.get("VIX_elevated", False)
    )

    return df


def build_master_dataset(save: bool = True) -> pd.DataFrame:
    """Main pipeline function."""
    region_cfg = config.get_region_config()
    sector_etf = region_cfg["sector_etf"]
    benchmarks = region_cfg["benchmarks"]

    gdelt, market = load_raw_data()
    print(f"[preprocessor] GDELT rows: {len(gdelt)} | Market rows: {len(market)}")

    # Merge: market dates as anchor (trading days only)
    df = pd.merge(market, gdelt[["date", "goldstein_wavg", "total_articles", "event_count"]],
                  on="date", how="left")

    # Forward-fill Goldstein scores across weekends/market holidays
    # Geopolitical state persists — it doesn't reset to zero on days with no new GDELT events
    pre_ffill_nulls = df["goldstein_wavg"].isnull().sum()
    df["goldstein_wavg"] = df["goldstein_wavg"].ffill()
    df["total_articles"] = df["total_articles"].fillna(0)
    df["event_count"]    = df["event_count"].fillna(0)
    post_ffill_nulls = df["goldstein_wavg"].isnull().sum()
    print(f"[preprocessor] Forward-filled {pre_ffill_nulls - post_ffill_nulls} missing Goldstein scores.")

    # Drop leading rows where Goldstein is still NaN (no prior data to forward-fill from)
    df = df.dropna(subset=["goldstein_wavg"]).reset_index(drop=True)

    # Compute log returns
    price_cols = [sector_etf] + benchmarks
    df = compute_log_returns(df, price_cols)

    # Drop the first row (NaN log return from shift)
    df = df.dropna(subset=[f"{sector_etf}_log_return"]).reset_index(drop=True)

    # VIX z-score regime detection
    df = compute_vix_zscore(df)

    # Decoupled flag
    df = flag_decoupled(df, sector_etf)

    print(f"[preprocessor] Master dataset shape: {df.shape}")
    print(f"[preprocessor] Date range: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"[preprocessor] Decoupled days: {df['decoupled_flag'].sum() if 'decoupled_flag' in df.columns else 'N/A'}")

    # ── Merge with existing master history (incremental mode preservation) ──────
    # If a master file already exists, concat and deduplicate so that
    # full history is always preserved. New rows overwrite old rows for
    # the same date (keeps the freshest data).
    if os.path.exists(config.MASTER_FILE):
        try:
            existing = pd.read_csv(config.MASTER_FILE, parse_dates=["date"])
            # Only keep existing rows that are OLDER than what we just fetched
            # (new data wins for overlapping dates)
            new_min_date = df["date"].min()
            existing_prior = existing[existing["date"] < new_min_date]
            if len(existing_prior) > 0:
                # Align columns: use union, fill missing with NaN
                df = pd.concat([existing_prior, df], ignore_index=True)
                df = df.sort_values("date").reset_index(drop=True)
                print(f"[preprocessor] Merged with existing history: "
                      f"{len(existing_prior)} prior rows + {len(df) - len(existing_prior)} new rows "
                      f"= {len(df)} total rows")
        except Exception as e:
            print(f"[preprocessor] WARNING: Could not merge with existing master: {e}")

    if save:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        df.to_csv(config.MASTER_FILE, index=False)
        print(f"[preprocessor] Saved → {config.MASTER_FILE}")

    return df


if __name__ == "__main__":
    df = build_master_dataset()
    print("\n--- Sample ---")
    print(df[["date", "goldstein_wavg", "VIX", "VIX_zscore", "VIX_elevated"]].tail(10))
    print(f"\nColumn list:\n{list(df.columns)}")
