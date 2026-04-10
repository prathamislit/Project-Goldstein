"""
scorer.py — Geopolitical Risk Premium Score (GRPS) computation engine.

GRPS (0-100) = 40% Instability Index + 40% GARCH-X Vol Premium + 20% VIX Z-Score component

Components:
    component_instability  : rolling percentile rank of (-goldstein_wavg), scaled 0-100
    component_vol_premium  : GARCH-X gamma contribution, scaled 0-100
    component_vix          : min(max(VIX_zscore / 3.0 * 100, 0), 100)

Regime thresholds:
    STABLE    GRPS < 33
    ELEVATED  33 <= GRPS < 66
    CRITICAL  GRPS >= 66
"""

import os
import pandas as pd
import numpy as np
import config
from garch_model import fit_garch_x


def compute_instability_component(goldstein: pd.Series,
                                  window: int = 252) -> pd.Series:
    """
    Rolling percentile rank of (-goldstein_wavg) over trailing window.
    More negative Goldstein = higher instability rank = higher component.
    min_periods=30 so scoring starts after 30 days of data.
    """
    neg_g = -goldstein
    pct   = neg_g.rolling(window=window, min_periods=30).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    ) * 100
    return pct.clip(0, 100)


def compute_vix_component(vix_zscore: pd.Series) -> pd.Series:
    """
    Linear scale from VIX z-score.
    z=0 → 0,  z=1.5 → 50,  z=3.0 → 100. Clamped at 0 (no credit for low VIX).
    """
    return (vix_zscore / 3.0 * 100).clip(lower=0, upper=100).fillna(0.0)


def compute_grps(instability, vol_premium, vix_component) -> pd.Series:
    """Weighted sum. Weights must sum to 1."""
    grps = (0.40 * instability
          + 0.40 * vol_premium
          + 0.20 * vix_component)
    return grps.clip(0, 100).round(1)


def assign_regime(grps: pd.Series) -> pd.Series:
    thresholds = config.GRPS_THRESHOLDS
    def _label(v):
        if pd.isna(v):
            return None
        if v < thresholds["elevated"][0]:    # < 33
            return "STABLE"
        elif v < thresholds["critical"][0]:  # < 66
            return "ELEVATED"
        else:
            return "CRITICAL"
    return grps.map(_label)


def run_scorer(save: bool = True) -> pd.DataFrame:
    region_cfg = config.get_region_config()
    sector_etf = region_cfg["sector_etf"]

    # Prefer the region-specific master file — the shared master_dataset_clean.csv
    # is overwritten by each region sequentially, so its columns reflect whichever
    # region ran LAST, not the current region.  This was causing vol_premium = 0
    # on all runs after the first region (e.g. XLE columns missing when russia_arctic
    # ran last and left XOP columns in the shared file).
    region_master = f"{config.DATA_DIR}/master_dataset_clean_{config.ACTIVE_REGION}.csv"
    if os.path.exists(region_master):
        master_file = region_master
    else:
        master_file = config.MASTER_FILE

    if not os.path.exists(master_file):
        raise FileNotFoundError(
            f"[scorer] Master dataset not found: {master_file}\n"
            "Run preprocessor.py first."
        )

    df = pd.read_csv(master_file, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    print(f"[scorer] Region: {config.ACTIVE_REGION} | File: {master_file} | Rows: {len(df)}")
    print(f"[scorer] Date range: {df['date'].min().date()} → {df['date'].max().date()}")

    # ── Component 1: Instability ──────────────────────────────────────────────
    df["component_instability"] = compute_instability_component(df["goldstein_wavg"])

    # ── Component 2: Vol Premium (realised-vol geopolitical premium) ──────────
    ret_col = f"{sector_etf}_log_return"
    if ret_col in df.columns and "goldstein_wavg" in df.columns:
        garch_out = fit_garch_x(
            returns=df.set_index("date")[ret_col],
            goldstein=df.set_index("date")["goldstein_wavg"],
        )
        df["component_vol_premium"] = garch_out["vol_premium"].values[:len(df)]
        df["cond_vol"]              = garch_out["cond_vol"].values[:len(df)]
        vp_latest = df["component_vol_premium"].iloc[-1]
        print(f"[scorer] Vol premium (realised-vol pct rank, geo-weighted): {vp_latest:.1f}/100")
    else:
        df["component_vol_premium"] = 0.0
        df["cond_vol"]              = 0.0
        print(f"[scorer] WARNING: {ret_col} not found. Vol premium set to 0.")

    # ── Component 3: VIX ─────────────────────────────────────────────────────
    vix_col = "VIX_zscore" if "VIX_zscore" in df.columns else None
    if vix_col:
        df["component_vix"] = compute_vix_component(df[vix_col])
    else:
        df["component_vix"] = 0.0

    # ── GRPS ─────────────────────────────────────────────────────────────────
    df["GRPS"] = compute_grps(
        df["component_instability"].fillna(0),
        df["component_vol_premium"].fillna(0),
        df["component_vix"].fillna(0),
    )
    df["GRPS_label"]    = assign_regime(df["GRPS"])
    df["decoupled_flag"] = df.get("decoupled_flag", False)

    # ── Select output columns ─────────────────────────────────────────────────
    keep = [
        "date", "goldstein_wavg", "VIX", "VIX_zscore", "VIX_elevated",
        "component_instability", "component_vol_premium", "component_vix",
        "GRPS", "GRPS_label", "decoupled_flag",
    ]
    out = df[[c for c in keep if c in df.columns]].copy()

    print(f"[scorer] Latest GRPS: {out['GRPS'].iloc[-1]} ({out['GRPS_label'].iloc[-1]})")

    if save:
        os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
        out.to_csv(config.SCORES_FILE, index=False)
        print(f"[scorer] Saved → {config.SCORES_FILE}")

    return out


if __name__ == "__main__":
    df = run_scorer()
    print("\n--- Last 5 rows ---")
    print(df[["date", "GRPS", "GRPS_label", "component_instability",
               "component_vol_premium", "component_vix"]].tail(5).to_string(index=False))
