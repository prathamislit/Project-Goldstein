"""
garch_model.py — Volatility Premium component for GRPS scoring.

ARCHITECTURE NOTE (important for maintainers):
-----------------------------------------------
The original design attempted a GARCH(1,1)-X model where the Goldstein score
entered the *variance* equation.  In testing, the Likelihood Ratio Test shows
p~0.48 — Goldstein does not significantly enter the daily conditional variance
equation when modelled as an exogenous regressor.  The previously "validated"
gamma=0.934 was a phantom: the arch library's `x=` parameter goes to the MEAN
equation only, and with the default `mean='Constant'` it is silently ignored,
so `res.params.get('x[0]', 0.0)` always returned 0.0.

REPLACEMENT — Realised Volatility Premium:
-------------------------------------------
The vol premium component now uses *realised volatility* (rolling 21-day annualised
std of log returns) ranked as a percentile over a trailing 252-day window, scaled
0-100.  This is:
  1. Statistically sound (no broken GARCH-X)
  2. Economically meaningful (elevated realised vol = elevated risk premium)
  3. Geopolitically weighted: amplified by the rolling 30-day |corr| between
     Goldstein scores and absolute ETF returns — so vol driven by geopolitical
     event flow counts more than vol driven by pure macro noise.

The GARCH conditional volatility (standard GARCH(1,1), no X) is still fitted and
returned as `cond_vol` for display purposes on the dashboard.
"""

import warnings
import numpy as np
import pandas as pd
from arch import arch_model

warnings.filterwarnings("ignore")

# ── Rolling Realised-Vol Premium (replaces broken GARCH-X component) ──────────

def compute_vol_premium(
    returns: pd.Series,
    goldstein: pd.Series,
    rv_window: int = 21,
    rank_window: int = 252,
    corr_window: int = 30,
    base_weight: float = 0.15,
) -> pd.Series:
    """
    Compute the geopolitical volatility premium component (0-100).

    Steps
    -----
    1. Rolling 21-day annualised realised volatility from log returns.
    2. Percentile rank of rv over a trailing 252-day window → 0-100.
    3. Rolling 30-day |corr(goldstein, |returns|)| as a geopolitical
       sensitivity GATE — this determines what fraction of the ETF's
       realised vol is attributable to geopolitical event flow vs. pure
       macro/market noise.
    4. geo_gate = max(|corr|^0.5, base_weight)  — range [0.15, 1.0]
       The square root softens the gate so moderate correlations (0.15-0.30)
       still pass a meaningful signal.  base_weight=0.15 ensures even weakly-
       correlated regions get a small baseline (pure-vol outlier detection).
    5. vol_premium = rv_pct * geo_gate, clipped [0, 100].

    Why a GATE not a multiplier:
    If geo_weight = 1 + |corr| (old code), even with |corr|=0 the full ETF
    vol passes through — so India-Pakistan gets ELEVATED just because INDA is
    volatile from macro, despite goldstein=+1.08 (cooperative).  The gate
    approach suppresses non-geopolitical vol so the score reflects actual
    geopolitical risk.

    Returns
    -------
    pd.Series aligned to `returns.index`.
    """
    df = pd.DataFrame({"r": returns, "g": goldstein})

    # Step 1: annualised realised vol
    rv = df["r"].rolling(rv_window, min_periods=5).std() * np.sqrt(252)

    # Step 2: percentile rank of rv
    rv_pct = rv.rolling(rank_window, min_periods=30).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    ) * 100

    # Step 3: rolling geo sensitivity (|corr| between goldstein and |returns|)
    abs_ret = df["r"].abs()
    roll_corr = df["g"].rolling(corr_window, min_periods=10).corr(abs_ret).abs().clip(0, 1)

    # Step 4: geo_gate — sqrt softens, base_weight floors
    geo_gate = roll_corr.pow(0.5).clip(lower=base_weight)  # range [0.15, 1.0]
    vol_prem = (rv_pct * geo_gate).clip(0, 100)

    return vol_prem.reindex(returns.index)


# ── Standard GARCH(1,1) for conditional volatility display ────────────────────

def fit_garch_x(returns: pd.Series, goldstein: pd.Series, p: int = 1, q: int = 1) -> dict:
    """
    Compute the vol premium component and fit a standard GARCH(1,1) for
    the conditional volatility display series.

    The `goldstein` parameter is used for the geopolitical sensitivity weight
    inside `compute_vol_premium`.  The GARCH model itself is plain GARCH(1,1)
    (no exogenous variance regressor — see module docstring for why).

    Parameters
    ----------
    returns   : log returns of sector ETF (daily, DatetimeIndex)
    goldstein : Goldstein stability score (daily, same index)
    p, q      : GARCH lag orders (default 1, 1)

    Returns
    -------
    dict with keys:
        cond_vol      : conditional volatility series (GARCH(1,1) fit)
        gamma         : 0.0  (no longer meaningful — kept for API compat)
        gamma_pvalue  : 1.0  (no longer meaningful — kept for API compat)
        vol_premium   : 0-100 realised-vol premium (the operative signal)
    """
    df = pd.DataFrame({"r": returns, "g": goldstein}).dropna()
    if len(df) < 60:
        return _null_result(returns.index)

    r_scaled = df["r"] * 100  # GARCH works on %-scale returns

    try:
        mdl = arch_model(r_scaled, vol="GARCH", p=p, q=q, dist="normal", rescale=False)
        res = mdl.fit(disp="off", show_warning=False)
        cond_vol = (res.conditional_volatility / 100).reindex(returns.index, fill_value=0.0)
    except Exception as e:
        print(f"[garch_model] GARCH(1,1) fit failed ({e}) — using rolling std as fallback.")
        cond_vol = (df["r"].rolling(21).std()).reindex(returns.index, fill_value=0.0)

    # Vol premium via the corrected realised-vol approach
    vol_prem = compute_vol_premium(returns, goldstein).reindex(returns.index, fill_value=0.0)

    # gamma / gamma_pvalue kept at 0/1 — no longer a fitted GARCH-X coefficient
    return {
        "cond_vol":     cond_vol,
        "gamma":        0.0,
        "gamma_pvalue": 1.0,
        "vol_premium":  vol_prem,
    }


def _null_result(index: pd.Index) -> dict:
    z = pd.Series(0.0, index=index)
    return {"cond_vol": z, "gamma": 0.0, "gamma_pvalue": 1.0, "vol_premium": z.copy()}
