"""
market_data.py — Pulls ETF, benchmark, and VIX data via yfinance.

Pulls for the active region's sector ETF + benchmarks + VIX.
Outputs: data/market_data.csv
"""

import os
import pandas as pd
import numpy as np
import yfinance as yf
import config


def fetch_market_data(save: bool = True) -> pd.DataFrame:
    """
    Downloads daily adjusted close prices for:
    - Sector ETF (e.g. XLE for Middle East energy exposure)
    - Benchmarks (SPY, GLD)
    - VIX (^VIX) for regime detection

    Returns a clean daily DataFrame with one column per ticker.
    """
    region_cfg = config.get_region_config()
    sector_etf = region_cfg["sector_etf"]
    benchmarks = region_cfg["benchmarks"]

    tickers = [sector_etf] + benchmarks + [config.VIX_TICKER]
    tickers_deduped = list(dict.fromkeys(tickers))  # preserve order, remove dupes

    print(f"[market_data] Pulling tickers: {tickers_deduped}")
    print(f"[market_data] Date range: {config.START_DATE} → {config.END_DATE}")

    raw = yf.download(
        tickers_deduped,
        start=config.START_DATE,
        end=config.END_DATE,
        auto_adjust=True,
        progress=False,
    )

    # yfinance returns MultiIndex columns when multiple tickers are passed
    # Extract just the "Close" level
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw["Close"].copy()
    else:
        df = raw[["Close"]].copy()
        df.columns = tickers_deduped

    df.index.name = "date"
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["date"])

    # Rename VIX column to something readable
    vix_col = config.VIX_TICKER
    if vix_col in df.columns:
        df = df.rename(columns={vix_col: "VIX"})

    # Drop rows where the sector ETF has no data (primary signal)
    sector_col = sector_etf
    initial_len = len(df)
    df = df.dropna(subset=[sector_col])
    dropped = initial_len - len(df)
    if dropped > 0:
        print(f"[market_data] Dropped {dropped} rows with missing {sector_col} data.")

    df = df.sort_values("date").reset_index(drop=True)

    print(f"[market_data] Final shape: {df.shape}")
    print(f"[market_data] Date range in data: {df['date'].min().date()} → {df['date'].max().date()}")

    if save:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        df.to_csv(config.MARKET_RAW_FILE, index=False)
        print(f"[market_data] Saved → {config.MARKET_RAW_FILE}")

    return df


if __name__ == "__main__":
    df = fetch_market_data()
    print(df.head(10))
    print(f"\nColumns: {list(df.columns)}")
    print(f"Nulls:\n{df.isnull().sum()}")
