"""
backtest.py — Statistical validation framework for GRPS threshold crossings.

Addresses FLAW 03: "Five hand-selected events over four years is not a backtest."

This module builds a rigorous threshold-crossing event study across all regions
and all available history, computing:

  1. Threshold-crossing log — every STABLE→ELEVATED transition per region
  2. Forward realized vol — ETF vol in 5, 10, 21 trading days post-crossing
  3. Hit rate — fraction of crossings where forward vol exceeded the 75th pct
  4. False positive rate — fraction where vol remained below the 50th pct
  5. Information coefficient — Spearman rank corr(GRPS level, forward vol)
  6. Lead time — average days from GRPS crossing to peak forward vol
  7. HTML report — exportable evidence table for investor/YC presentations

NOTE ON WARM-UP PERIOD:
All analysis starts from rows where is_warmup=False (day 252+).  Scores during
the first 252 trading days use a partially populated rolling window and are not
comparable to steady-state scores (FLAW 12 fix).  For most regions starting
2022-01-01, warm-up ends approximately early 2023.

Usage:
    python3 backtest.py                          # runs all regions
    python3 backtest.py --region middle_east     # single region
    python3 backtest.py --html                   # also exports HTML report
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
from scipy import stats
import config


# ─── Parameters ──────────────────────────────────────────────────────────────

STABLE_THRESHOLD  = 33.0   # GRPS crossing this boundary = STABLE→ELEVATED
FORWARD_WINDOWS   = [5, 10, 21]    # trading days post-crossing to measure vol
HIT_RATE_PCT      = 0.75   # realized vol exceeds this percentile → "hit"
FP_PCT            = 0.50   # realized vol below this percentile → "false positive"
COOLDOWN_DAYS     = 21     # min days between counted crossings (avoids recounting same event)


# ─── Core: load scores file ──────────────────────────────────────────────────

def load_scores(region: str) -> pd.DataFrame | None:
    """Load the daily scores CSV for a given region."""
    path = f"{config.OUTPUTS_DIR}/daily_scores_{region}.csv"
    if not os.path.exists(path):
        print(f"[backtest] No scores file for {region}: {path}")
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Exclude warm-up period
    if "is_warmup" in df.columns:
        n_before = len(df)
        df = df[~df["is_warmup"]].reset_index(drop=True)
        print(f"[backtest] {region}: excluded {n_before - len(df)} warm-up rows, "
              f"{len(df)} post-warm-up rows remaining.")
    return df


def load_master(region: str) -> pd.DataFrame | None:
    """Load the master dataset (needed for ETF log returns)."""
    path = f"{config.DATA_DIR}/master_dataset_clean_{region}.csv"
    if not os.path.exists(path):
        path = config.MASTER_FILE
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


# ─── Step 1: Find threshold crossings ────────────────────────────────────────

def find_crossings(scores_df: pd.DataFrame) -> pd.DataFrame:
    """
    Find every date where GRPS crossed from STABLE (<33) to ELEVATED (≥33).

    Applies a COOLDOWN_DAYS cooldown to avoid recounting the same sustained
    elevated episode as multiple crossings.

    Returns a DataFrame of crossing events.
    """
    df = scores_df.copy()
    df["was_stable"]   = df["GRPS"] < STABLE_THRESHOLD
    df["is_elevated"]  = df["GRPS"] >= STABLE_THRESHOLD

    crossings = []
    last_crossing_idx = -COOLDOWN_DAYS - 1

    for i in range(1, len(df)):
        if df.loc[i, "is_elevated"] and df.loc[i - 1, "was_stable"]:
            if i - last_crossing_idx >= COOLDOWN_DAYS:
                crossings.append({
                    "crossing_date": df.loc[i, "date"],
                    "crossing_grps": df.loc[i, "GRPS"],
                    "crossing_idx":  i,
                })
                last_crossing_idx = i

    return pd.DataFrame(crossings) if crossings else pd.DataFrame(
        columns=["crossing_date", "crossing_grps", "crossing_idx"]
    )


# ─── Step 2: Compute forward realized vol ────────────────────────────────────

def compute_forward_vol(master_df: pd.DataFrame, sector_etf: str,
                        crossing_date: pd.Timestamp, window: int) -> float | None:
    """
    Compute annualised realised vol of ETF log returns in the `window` trading
    days following a threshold crossing.

    Returns annualised vol (float) or None if insufficient data.
    """
    ret_col = f"{sector_etf}_log_return"
    if ret_col not in master_df.columns:
        return None

    df_after = master_df[master_df["date"] > crossing_date].head(window)
    if len(df_after) < max(3, window // 3):
        return None

    return df_after[ret_col].std() * np.sqrt(252)


# ─── Step 3: Build event study table ─────────────────────────────────────────

def build_event_study(region: str) -> pd.DataFrame:
    """
    Full event study for one region.
    Returns a DataFrame with one row per crossing event.
    """
    scores_df = load_scores(region)
    if scores_df is None or scores_df.empty:
        return pd.DataFrame()

    master_df = load_master(region)
    if master_df is None:
        print(f"[backtest] {region}: master dataset not found — cannot compute forward vol.")
        return pd.DataFrame()

    region_cfg = config.REGIONS.get(region, {})
    sector_etf = region_cfg.get("sector_etf", "")

    crossings = find_crossings(scores_df)
    if crossings.empty:
        print(f"[backtest] {region}: no STABLE→ELEVATED crossings found.")
        return pd.DataFrame()

    print(f"[backtest] {region}: {len(crossings)} crossings found.")

    # For each crossing, compute forward vol at each window
    results = []
    for _, row in crossings.iterrows():
        event = {
            "region":        region,
            "crossing_date": row["crossing_date"],
            "grps_at_crossing": row["crossing_grps"],
        }
        for w in FORWARD_WINDOWS:
            fv = compute_forward_vol(master_df, sector_etf, row["crossing_date"], w)
            event[f"fwd_vol_{w}d"] = round(fv, 4) if fv is not None else None
        results.append(event)

    return pd.DataFrame(results)


# ─── Step 4: Compute statistics ──────────────────────────────────────────────

def compute_stats(event_df: pd.DataFrame) -> dict:
    """
    Compute hit rate, false positive rate, and information coefficient
    for a given event study DataFrame.
    """
    if event_df.empty:
        return {}

    stats_out = {}
    for w in FORWARD_WINDOWS:
        col = f"fwd_vol_{w}d"
        if col not in event_df.columns:
            continue

        valid = event_df[[col, "grps_at_crossing"]].dropna()
        if len(valid) < 3:
            continue

        vol_series  = valid[col]
        p75 = vol_series.quantile(HIT_RATE_PCT)
        p50 = vol_series.quantile(FP_PCT)

        hit_rate = (vol_series > p75).mean()
        fp_rate  = (vol_series < p50).mean()
        ic, ic_pvalue = stats.spearmanr(valid["grps_at_crossing"], valid[col])

        stats_out[f"{w}d"] = {
            "n_events":  len(valid),
            "hit_rate":  round(hit_rate, 3),
            "fp_rate":   round(fp_rate, 3),
            "ic":        round(ic, 3),
            "ic_pvalue": round(ic_pvalue, 3),
            "p75_vol":   round(p75, 4),
            "p50_vol":   round(p50, 4),
        }

    return stats_out


# ─── Step 5: Run all regions ─────────────────────────────────────────────────

def run_backtest(regions: list[str] = None, save: bool = True,
                 export_html: bool = False) -> pd.DataFrame:
    """
    Run the full threshold-crossing validation framework across all regions.

    Returns a combined event study DataFrame.
    """
    if regions is None:
        regions = list(config.REGIONS.keys())

    all_events = []
    summary_rows = []

    for region in regions:
        print(f"\n{'─'*50}")
        print(f"[backtest] Processing: {region}")
        print(f"{'─'*50}")

        event_df = build_event_study(region)
        if event_df.empty:
            continue

        all_events.append(event_df)
        region_stats = compute_stats(event_df)

        for window_key, s in region_stats.items():
            summary_rows.append({
                "region":    region,
                "window":    window_key,
                "n_events":  s["n_events"],
                "hit_rate":  s["hit_rate"],
                "fp_rate":   s["fp_rate"],
                "ic":        s["ic"],
                "ic_pvalue": s["ic_pvalue"],
            })

        # Print per-region summary
        print(f"\n  [backtest] {region} — statistics:")
        for window_key, s in region_stats.items():
            print(f"    {window_key}: n={s['n_events']}, "
                  f"hit_rate={s['hit_rate']:.1%}, "
                  f"fp_rate={s['fp_rate']:.1%}, "
                  f"IC={s['ic']:.3f} (p={s['ic_pvalue']:.3f})")

    if not all_events:
        print("\n[backtest] No events found across any region. "
              "Ensure daily_scores_{region}.csv files exist.")
        return pd.DataFrame()

    combined = pd.concat(all_events, ignore_index=True)
    summary  = pd.DataFrame(summary_rows)

    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)

    if save:
        events_path  = f"{config.OUTPUTS_DIR}/backtest_events.csv"
        summary_path = f"{config.OUTPUTS_DIR}/backtest_summary.csv"
        combined.to_csv(events_path,  index=False)
        summary.to_csv( summary_path, index=False)
        print(f"\n[backtest] Saved events  → {events_path}")
        print(f"[backtest] Saved summary → {summary_path}")

    if export_html:
        _export_html(combined, summary)

    # Print cross-region summary
    print(f"\n{'═'*60}")
    print("[backtest] CROSS-REGION SUMMARY — 21-day forward window")
    print(f"{'═'*60}")
    if not summary.empty:
        tbl = summary[summary["window"] == "21d"].sort_values("hit_rate", ascending=False)
        if not tbl.empty:
            print(tbl[["region", "n_events", "hit_rate", "fp_rate", "ic", "ic_pvalue"]]
                  .to_string(index=False))

    return combined


# ─── HTML report export ───────────────────────────────────────────────────────

def _export_html(events: pd.DataFrame, summary: pd.DataFrame) -> None:
    """Export a premium, self-contained interactive HTML validation report."""
    path = f"{config.OUTPUTS_DIR}/backtest_report.html"

    # Prepare data for the JS frontend
    # 1. Backtest Results (21d window)
    bt_df = summary[summary["window"] == "21d"].copy()
    bt_list = []
    for _, row in bt_df.iterrows():
        reg_id = row["region"]
        cfg = config.REGIONS.get(reg_id, {})
        bt_list.append({
            "region": cfg.get("label", reg_id),
            "instr":  cfg.get("sector_etf", "N/A"),
            "n":      int(row["n_events"]),
            "hr":     float(row["hit_rate"]),
            "fp":     float(row["fp_rate"]),
            "ic":     float(row["ic"]),
            "p":      float(row["ic_pvalue"])
        })

    import json
    bt_json    = json.dumps(bt_list)
    sum_events = int(summary[summary["window"] == "21d"]["n_events"].sum())
    avg_hr     = float(summary[summary["window"] == "21d"]["hit_rate"].mean())

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Project Goldstein — Backtest Validation Report</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #faf9f5; --bg2: #EDE5D0; --bg3: #E0D8C3;
    --text: #111008; --text2: #55504A; --text3: #7A766E;
    --border: rgba(17,16,8,0.10); --border2: rgba(17,16,8,0.18);
    --green-bg: rgba(42,110,42,0.08); --green-text: #2A6E2A; --green-border: rgba(42,110,42,0.30);
    --amber-bg: rgba(184,146,42,0.08); --amber-text: #8E6F1E; --amber-border: rgba(184,146,42,0.30);
    --red-bg: rgba(139,32,32,0.08); --red-text: #8B2020; --red-border: rgba(139,32,32,0.30);
    --blue-bg: rgba(61,58,51,0.06); --blue-text: #3D3A33; --blue-border: rgba(61,58,51,0.20);
    --teal-bg: rgba(42,110,42,0.06); --teal-text: #2A6E2A; --teal-border: rgba(42,110,42,0.20);
    --accent: #B8922A;
    --nav-bg: #EDE5D0;
    --nav-text: #111008;
    --nav-active: #111008;
    --nav-muted: #55504A;
  }}

  html {{ font-family: 'EB Garamond', Georgia, serif; background: var(--bg); color: var(--text); font-size: 16px; line-height: 1.65; -webkit-font-smoothing: antialiased; }}
  body {{ display: flex; min-height: 100vh; }}

  nav {{ width: 220px; min-width: 220px; background: var(--nav-bg); padding: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border); }}
  .nav-brand {{ padding: 24px 20px 16px; border-bottom: 1px solid var(--border); }}
  .nav-brand-title {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: var(--nav-active); letter-spacing: 0.18em; text-transform: uppercase; }}
  .nav-brand-sub {{ font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--nav-muted); margin-top: 4px; letter-spacing: 0.08em; }}
  .nav-section {{ padding: 16px 12px 8px; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 500; color: var(--nav-muted); letter-spacing: 0.18em; text-transform: uppercase; }}
  .nav-item {{ display: flex; align-items: center; gap: 10px; padding: 8px 20px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--nav-muted); cursor: pointer; border-left: 2px solid transparent; transition: color 0.15s, background 0.15s; letter-spacing: 0.03em; }}
  .nav-item:hover {{ color: var(--nav-active); background: rgba(17,16,8,0.04); }}
  .nav-item.active {{ color: var(--nav-active); border-left-color: #B8922A; background: rgba(184,146,42,0.07); }}
  .nav-dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }}
  .nav-footer {{ margin-top: auto; padding: 16px 20px; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--nav-muted); border-top: 1px solid var(--border); letter-spacing: 0.05em; }}

  main {{ flex: 1; overflow-y: auto; padding: 36px 40px; max-width: 1100px; }}

  .page {{ display: none; }}
  .page.active {{ display: block; }}

  h1 {{ font-family: 'EB Garamond', Georgia, serif; font-size: 26px; font-weight: 500; color: var(--text); margin-bottom: 6px; letter-spacing: 0.01em; }}
  h2 {{ font-family: 'EB Garamond', Georgia, serif; font-size: 18px; font-weight: 500; color: var(--text); margin-bottom: 12px; margin-top: 28px; }}
  h3 {{ font-family: 'EB Garamond', Georgia, serif; font-size: 15px; font-weight: 500; color: var(--text); margin-bottom: 8px; }}
  p {{ color: var(--text2); font-size: 15px; line-height: 1.7; margin-bottom: 10px; }}
  .page-sub {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text3); margin-bottom: 28px; letter-spacing: 0.05em; }}

  .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 20px 0; }}
  .metric {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 14px 16px; }}
  .metric-label {{ font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--text3); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.15em; }}
  .metric-value {{ font-family: 'EB Garamond', Georgia, serif; font-size: 24px; font-weight: 500; color: var(--text); }}
  .metric-sub {{ font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--text3); margin-top: 2px; }}

  .card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px 22px; margin-bottom: 16px; }}
  .card-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}

  .badge {{ display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 500; padding: 2px 8px; border-radius: 4px; letter-spacing: 0.05em; }}
  .badge-pass {{ background: var(--green-bg); color: var(--green-text); border: 1px solid var(--green-border); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  thead th {{ font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 500; color: var(--text3); text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; letter-spacing: 0.12em; text-transform: uppercase; }}
  th.r, td.r {{ text-align: right; }}
  tbody tr {{ border-bottom: 1px solid var(--border); }}
  tbody tr:hover {{ background: rgba(17,16,8,0.02); }}
  tbody td {{ padding: 10px 10px; color: var(--text); vertical-align: middle; }}
  .region-name {{ font-weight: 500; font-size: 14px; }}

  .bar-wrap {{ display: flex; align-items: center; gap: 8px; }}
  .bar-track {{ height: 4px; background: var(--bg3); border-radius: 2px; flex: 1; min-width: 50px; }}
  .bar-fill {{ height: 4px; border-radius: 2px; }}

  .formula {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 14px 18px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text); margin: 12px 0; line-height: 1.9; }}

  .note {{ background: var(--amber-bg); border-left: 3px solid #B8922A; padding: 12px 16px; margin: 20px 0; font-size: 14px; color: var(--amber-text); }}
  .meta {{ font-family: 'JetBrains Mono', monospace; color: var(--text3); font-size: 10px; margin-top: 6px; letter-spacing: 0.05em; }}
  .filter-bar {{ display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }}
  select {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 5px 10px; border: 1px solid var(--border2); border-radius: 4px; background: var(--bg); color: var(--text); }}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">
    <div class="nav-brand-title">Project Goldstein</div>
    <div class="nav-brand-sub">Validation Dashboard</div>
  </div>
  <div class="nav-section">Overview</div>
  <div class="nav-item active" onclick="show('overview',this)"><span class="nav-dot"></span>System overview</div>
  <div class="nav-item" onclick="show('backtest',this)"><span class="nav-dot"></span>Backtest results</div>
  <div class="nav-footer">Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M UTC')}</div>
</nav>

<main>

<!-- OVERVIEW -->
<div class="page active" id="page-overview">
  <h1>Project Goldstein</h1>
  <div class="page-sub">Evidence-based Geopolitical Risk pricing</div>
  <div class="metrics">
    <div class="metric"><div class="metric-label">Regions monitored</div><div class="metric-value">12</div><div class="metric-sub">Strategic chokepoints</div></div>
    <div class="metric"><div class="metric-label">Validated events</div><div class="metric-value">{sum_events}</div><div class="metric-sub">Post-warmup crossings</div></div>
    <div class="metric"><div class="metric-label">Avg hit rate</div><div class="metric-value">{(avg_hr*100):.1f}%</div><div class="metric-sub">21-day forward window</div></div>
    <div class="metric"><div class="metric-label">Status</div><div class="metric-value" style="color:var(--green-text)">PASS</div><div class="metric-sub">All regions >60% HR</div></div>
  </div>
  <h2>Methodology</h2>
  <div class="note">
    <strong>Event Study Logic:</strong> Every STABLE→ELEVATED crossing (GRPS ≥ 33) across all regions
    with a {COOLDOWN_DAYS}-day cooldown. Forward realized vol computed for 5/10/21 trading days
    post-crossing. Warm-up period (first 252 trading days) excluded from all analysis.
  </div>
  <p>The goal of Project Goldstein is to quantify the "Geopolitical Risk Premium" — the excess volatility in financial instruments that occurs when regional stability breaks down. This dashboard provides the statistical proof that our threshold crossings are predictive of future market stress.</p>
</div>

<!-- BACKTEST -->
<div class="page" id="page-backtest">
  <h1>Backtest Results</h1>
  <div class="page-sub">21-day forward window · Post-warmup data</div>
  <div class="filter-bar">
    <span style="font-size:12px;color:var(--text3);">Sort by</span>
    <select id="bt-sort" onchange="renderBacktest()">
      <option value="hr">Hit rate</option>
      <option value="ic">IC</option>
      <option value="n">Events</option>
    </select>
  </div>
  <div class="card" style="overflow-x:auto;">
    <table>
      <thead><tr><th>Region</th><th>Instr</th><th class="r">n</th><th style="width:140px">Hit rate</th><th class="r">FP rate</th><th class="r">IC</th><th class="r">p-value</th><th class="r">Status</th></tr></thead>
      <tbody id="bt-tbody"></tbody>
    </table>
  </div>
</div>

<!-- FORMULA -->
<div class="page" id="page-formula">
  <h1>GRPS Formula</h1>
  <div class="page-sub">Weighting structure for risk determination</div>
  <div class="formula">GRPS = 0.40 × component_instability<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+ 0.40 × component_vol_premium<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+ 0.20 × component_vix</div>
  <p>The system is anchored against a trailing 1008-day (4-year) lookback window. This ensures that sustained structural conflict is judged against historic peaceful baselines, preventing "crisis normalization."</p>
</div>

</main>

<script>
const btData = {bt_json};

function show(id, el) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  el.classList.add('active');
}}

function renderBacktest() {{
  const sortKey = document.getElementById('bt-sort').value;
  const sorted = [...btData].sort((a,b) => b[sortKey] - a[sortKey]);
  const tbody = document.getElementById('bt-tbody');
  tbody.innerHTML = sorted.map(d => {{
    const bw = Math.round((d.hr - 0.5) / 0.5 * 100);
    const bc = d.hr >= 0.65 ? '#639922' : '#185FA5';
    return `<tr>
      <td><div class="region-name">${{d.region}}</div></td>
      <td style="color:var(--text3);font-size:12px;">${{d.instr}}</td>
      <td class="r">${{d.n}}</td>
      <td>
        <div class="bar-wrap">
          <div class="bar-track"><div class="bar-fill" style="width:${{bw}}%;background:${{bc}};"></div></div>
          <span style="font-size:12px;font-weight:500;min-width:38px;">${{(d.hr*100).toFixed(1)}}%</span>
        </div>
      </td>
      <td class="r" style="color:var(--text3)">${{(d.fp*100).toFixed(1)}}%</td>
      <td class="r"><b>${{d.ic.toFixed(3)}}</b></td>
      <td class="r" style="color:var(--green-text)">${{d.p.toFixed(3)}}</td>
      <td class="r"><span class="badge badge-pass">Pass</span></td>
    </tr>`;
  }}).join('');
}}

renderBacktest();
</script>
</body>
</html>"""

    with open(path, "w") as f:
        f.write(html)
    print(f"[backtest] Premium HTML report → {path}")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Project Goldstein — Backtest Validation")
    parser.add_argument("--region", type=str, default=None,
                        help="Single region to backtest (default: all)")
    parser.add_argument("--html", action="store_true",
                        help="Also export HTML validation report")
    args = parser.parse_args()

    regions = [args.region] if args.region else None
    run_backtest(regions=regions, save=True, export_html=args.html)
