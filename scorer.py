"""
scorer.py — Geopolitical Risk Premium Score (GRPS) computation engine.

This module is NOT included in the public release.
It contains the proprietary scoring formula that converts raw geopolitical
and market signals into the 0–100 GRPS output used in the dashboard.

Signal output is available via API. Contact for access:
→ pns5158@psu.edu
→ github.com/[your-handle]/project-goldstein

--- Output format (daily_scores.csv) ---

date         grps    regime    goldstein_wavg    vix_zscore    ...
2026-04-07   74.3    CRITICAL  -1.842            1.87          ...

--- Pricing ---

Signal Feed (1 region, daily CSV)     $299/mo
Dashboard Access (3 regions, hosted)  $799/mo
Full Suite (all regions + raw data)   $1,999/mo
Enterprise (source license + support) contact for pricing
"""

raise NotImplementedError(
    "Scoring engine not included in public release. "
    "Contact pns5158@psu.edu for API access."
)
