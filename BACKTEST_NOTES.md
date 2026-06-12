# Backtest Notes — Hit-Rate / False-Positive-Rate Baseline Fix (June 2026)

## The bug

Until this fix, `compute_stats()` in `backtest.py` computed the 75th and 50th
percentile volatility thresholds **from the crossing-event sample itself**:

```python
p75 = vol_series.quantile(0.75)        # vol_series = event forward vols
hit_rate = (vol_series > p75).mean()   # ≈ 25% by construction
fp_rate  = (vol_series < p50).mean()   # ≈ 50% by construction
```

Asking "what fraction of events exceed the 75th percentile of the events"
always returns ~25%, regardless of whether the signal has any predictive
power. The old `backtest_summary.csv` confirmed this: every region showed
hit_rate ≈ 0.24–0.27 and fp_rate ≈ 0.47–0.50. Both metrics were tautological.

## The fix

The threshold is now a **region-level baseline**: for each region and forward
window, forward realized vol is computed for *every* post-warmup score date
(not just crossing dates). The baseline sample is the **non-crossing days**
(GRPS < 33 — days when the system was not signalling), which are cleanly
identifiable and plentiful (376–641 days per region/window, well above the
60-day minimum). The fallback to all post-warmup days was never needed.

- `baseline_p75_vol` — 75th percentile of forward vol over non-crossing days
- `event_hit_rate` — fraction of crossing events whose forward vol exceeds
  `baseline_p75_vol`
- `false_positive_rate` — fraction of non-crossing days whose forward vol
  exceeds `baseline_p75_vol`. Because the threshold is the 75th percentile of
  that same sample, this is ≈ 25% by construction; it is reported as the
  **base rate** the hit rate must beat, not as an independent finding.
- `baseline_sample_n`, `false_positive_sample_n` — sample sizes

Spearman IC and its p-value are computed exactly as before (verified
identical to the pre-fix run).

## Results from the regenerated run (June 11, 2026)

| Window | Pooled hits | Pooled hit rate | Base rate | One-sided binomial p |
|---|---|---|---|---|
| 5d  | 86/332 | 25.9% | 25.0% | 0.372 |
| 10d | 87/332 | 26.2% | 25.0% | 0.326 |
| 21d | 94/331 | 28.4% | 25.0% | 0.088 |

Per-region 21-day hit rates range from 18.5% (Middle East) to 36.8%
(Strait of Hormuz). 9 of 12 regions beat the base rate at 21d, but the
pooled lift (+3.4pp) is not statistically significant — and the binomial
test above is *generous*, since overlapping forward windows make the
effective sample smaller than the nominal event count.

## Why README.md and index.html were NOT updated

The new hit-rate numbers are honest but **not meaningful as evidence of
predictive power**: at every horizon the pooled hit rate is statistically
indistinguishable from the 25% chance-level base rate (best p = 0.088,
pre-correction). Publishing "28.4% hit rate vs 25% base rate" as a headline
stat would invite the same credibility criticism the June 2026 cleanup was
meant to fix. The public docs continue to cite only the Spearman IC results
(unchanged by this fix). If a future model revision lifts the hit rate
meaningfully above the base rate (with the autocorrelation caveat addressed),
the docs can pick the numbers up from `outputs/backtest_summary.csv`.

Note: `outputs/` is gitignored (data artifacts are not committed), so the
regenerated `backtest_summary.csv` lives only in the local working tree.
