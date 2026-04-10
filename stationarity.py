"""
stationarity.py — ADF tests to validate series before Granger/VAR modeling.

This is the gate that must pass before any causal modeling begins.
Granger causality and VAR models assume stationarity. Running them on
non-stationary data produces spurious results that look significant but mean nothing.

ADF null hypothesis: the series HAS a unit root (non-stationary).
We want to REJECT the null → p-value < 0.05 → series is stationary → safe to model.

Tested series:
- Goldstein score (level)
- ETF log returns
- Benchmark log returns
"""

import pandas as pd
from statsmodels.tsa.stattools import adfuller
import config


def run_adf(series: pd.Series, name: str) -> dict:
    """
    Run Augmented Dickey-Fuller test on a single series.
    Returns a result dict with the key stats.
    """
    clean = series.dropna()
    if len(clean) < 30:
        return {
            "series": name,
            "adf_stat": None,
            "p_value": None,
            "lags_used": None,
            "stationary": None,
            "verdict": "INSUFFICIENT DATA",
        }

    adf_stat, p_value, lags_used, _, critical_values, _ = adfuller(clean, autolag="AIC")

    stationary = p_value < config.ADF_SIGNIFICANCE
    verdict = "PASS — stationary, safe to model" if stationary else "FAIL — non-stationary, DO NOT model"

    return {
        "series":     name,
        "adf_stat":   round(adf_stat, 4),
        "p_value":    round(p_value, 6),
        "lags_used":  lags_used,
        "crit_1pct":  round(critical_values["1%"], 4),
        "crit_5pct":  round(critical_values["5%"], 4),
        "stationary": stationary,
        "verdict":    verdict,
    }


def run_all_adf_tests(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run ADF on all relevant columns in the master dataset.
    Returns a summary DataFrame.
    """
    region_cfg = config.get_region_config()
    sector_etf = region_cfg["sector_etf"]
    benchmarks = region_cfg["benchmarks"]

    # Series to test
    series_to_test = {
        "Goldstein Score (level)": df["goldstein_wavg"],
    }

    # Log returns for ETF and benchmarks
    for ticker in [sector_etf] + benchmarks:
        col = f"{ticker}_log_return"
        if col in df.columns:
            series_to_test[f"{ticker} Log Return"] = df[col]

    results = []
    for name, series in series_to_test.items():
        result = run_adf(series, name)
        results.append(result)

        status = "✅" if result["stationary"] else "❌"
        print(f"  {status}  {name:<35} p={result['p_value']}  →  {result['verdict']}")

    results_df = pd.DataFrame(results)

    # Pipeline decision
    log_return_cols = [r for r in results if f"Log Return" in r["series"]]
    all_returns_pass = all(r["stationary"] for r in log_return_cols if r["stationary"] is not None)

    if all_returns_pass:
        print("\n[stationarity] ✅ All log returns are stationary. Cleared for Granger/VAR modeling.")
    else:
        failing = [r["series"] for r in log_return_cols if not r["stationary"]]
        print(f"\n[stationarity] ❌ Non-stationary log returns: {failing}")
        print("[stationarity] Action: First-difference these series before modeling.")

    return results_df


def load_and_test(master_file: str = None) -> pd.DataFrame:
    """Load master dataset and run full ADF suite."""
    path = master_file or config.MASTER_FILE
    df = pd.read_csv(path, parse_dates=["date"])
    print(f"\n[stationarity] Running ADF tests on {path}")
    print(f"[stationarity] Dataset: {len(df)} rows | {df['date'].min().date()} → {df['date'].max().date()}\n")
    return run_all_adf_tests(df)


if __name__ == "__main__":
    results = load_and_test()
    print("\n--- Full ADF Results Table ---")
    print(results.to_string(index=False))
