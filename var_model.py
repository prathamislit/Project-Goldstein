"""
var_model.py — VAR model + Granger precedence tests + Impulse Response Functions.

Why VAR instead of standalone Granger:
- Standalone Granger tests one direction in isolation
- VAR models the joint dynamics of Goldstein scores AND ETF returns simultaneously
- Granger tests emerge from the VAR as a byproduct — but now in a richer, bidirectional framework
- Impulse Response Functions (IRFs) show HOW a geopolitical shock propagates through
  returns over time — this is what makes the output interpretable to a buyer

Language discipline:
  Say: "Goldstein scores Granger-precede XLE returns"
  Never say: "Goldstein scores cause XLE returns"
  Granger precedence = past scores improve the forecast of future returns.
  That's a predictive relationship, not a causal mechanism.
"""

import pandas as pd
import numpy as np
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests
import config


def run_var_model(df: pd.DataFrame) -> dict:
    """
    Fits a VAR model on Goldstein scores + ETF log returns.
    Selects optimal lag order via AIC.
    Returns model results + Granger test results + IRF data.
    """
    region_cfg = config.get_region_config()
    sector_etf = region_cfg["sector_etf"]
    ret_col    = f"{sector_etf}_log_return"

    required = ["goldstein_wavg", ret_col]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"[var_model] Missing column: {col}. Run preprocessor.py first.")

    # Use only the two core series, drop NaN
    model_df = df[required].dropna().copy()
    print(f"[var_model] Modeling {len(model_df)} observations.")
    print(f"[var_model] Series: Goldstein Score + {sector_etf} Log Return")

    # Fit VAR — AIC selects optimal lag count up to VAR_MAX_LAGS
    model = VAR(model_df)
    lag_order_results = model.select_order(maxlags=config.VAR_MAX_LAGS)
    optimal_lags = lag_order_results.aic
    optimal_lags = max(optimal_lags, 1)  # ensure at least 1 lag

    print(f"[var_model] Optimal lag order (AIC): {optimal_lags}")

    fitted = model.fit(optimal_lags)

    # Granger Precedence Tests
    # Tests whether past Goldstein scores improve prediction of ETF returns
    # beyond what past returns alone provide.
    print(f"\n[var_model] Granger Precedence: Goldstein → {sector_etf} returns")
    granger_results = {}
    for lag in config.GRANGER_LAGS:
        test_result = grangercausalitytests(
            model_df[[ret_col, "goldstein_wavg"]],
            maxlag=lag,
            verbose=False,
        )
        # Extract F-test p-value at the target lag
        p_val = test_result[lag][0]["ssr_ftest"][1]
        significant = p_val < config.GRANGER_SIGNIFICANCE
        granger_results[lag] = {
            "lag_days":    lag,
            "p_value":     round(p_val, 6),
            "significant": significant,
            "verdict": (
                f"✅ Goldstein Granger-precedes {sector_etf} at {lag}d lag"
                if significant else
                f"❌ No significant precedence at {lag}d lag (p={p_val:.4f})"
            ),
        }
        print(f"  Lag {lag}d: p={p_val:.4f} → {granger_results[lag]['verdict']}")

    # Impulse Response Functions
    # Shows how a 1-unit shock to Goldstein score propagates through ETF returns
    # over the next N periods. This is the key output for a buyer:
    # "if geopolitical stability drops by 1 unit today, what happens to XLE over the next week?"
    irf = fitted.irf(periods=14)

    irf_data = pd.DataFrame(
        irf.irfs[:, 1, 0],   # Response of ETF return (col 1) to Goldstein shock (col 0)
        columns=["irf_etf_response"],
    )
    irf_data["day"] = range(len(irf_data))

    # Summary of best predictive lag
    significant_lags = [l for l, r in granger_results.items() if r["significant"]]
    best_lag = min(significant_lags) if significant_lags else None

    print(f"\n[var_model] Best predictive lag: {best_lag}d" if best_lag else
          "\n[var_model] No significant Granger precedence found at tested lags.")

    return {
        "fitted_model":    fitted,
        "optimal_lags":    optimal_lags,
        "granger_results": granger_results,
        "irf_data":        irf_data,
        "best_lag":        best_lag,
        "summary":         fitted.summary(),
    }


if __name__ == "__main__":
    import os
    if not os.path.exists(config.MASTER_FILE):
        print("Master dataset not found. Run preprocessor.py first.")
    else:
        df = pd.read_csv(config.MASTER_FILE, parse_dates=["date"])
        results = run_var_model(df)
        print("\n--- IRF: ETF Response to Goldstein Shock (14-day window) ---")
        print(results["irf_data"].to_string(index=False))
