#!/usr/bin/env python3
"""
generate_insights.py — Project Goldstein Intelligence Brief
─────────────────────────────────────────────────────────────
Reads all 12 region score CSVs, applies the analyze.py narrative engine,
layers in ACLED ground-truth (if API key configured), and generates a
self-contained HTML intelligence brief that opens in the browser.

Output: outputs/goldstein_insights.html

Usage:
    python3 generate_insights.py
    python3 generate_insights.py --no-browser   # generate but don't auto-open
    python3 generate_insights.py --days 90      # limit lookback window
"""

import argparse
import os
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import config as _cfg

# ── Region metadata — derived from config.py (single source of truth) ─────────
REGIONS_META = {
    k: {
        "label": v["label"],
        "etf":   v["sector_etf"],
        "color": v.get("color", "#888"),
    }
    for k, v in _cfg.REGIONS.items()
}

OUTPUTS_DIR = Path("outputs")
SCORES_PREFIX = "daily_scores_"

# Region-specific "possible effects" by regime — market pathway knowledge
REGION_EFFECTS = {
    "strait_of_hormuz": {
        "STABLE":   "Tanker insurance spreads near historical mean. No material WTI risk premium. USO tracking macro oil supply/demand without geopolitical overlay.",
        "ELEVATED": "Brent/WTI risk premium typically $3–8/bbl in comparable episodes. USO implied vol expansion of 8–15%. Long-haul tanker re-routing begins. Refinery margin volatility elevates.",
        "CRITICAL": "Potential closure scenario priced. Historical analogues (1987 Tanker War, 2019 Abqaiq attack) suggest $12–25/bbl risk premium. USO vol can double. GLD safe-haven bid activates. Consider IEA strategic reserve drawdown probability.",
    },
    "middle_east": {
        "STABLE":   "XLE tracking US energy fundamentals without significant geopolitical overlay. Defense sector (ITA/XAR) at baseline.",
        "ELEVATED": "XLE vol spread widening vs SPY. GLD typically adds 1–3% in sustained ELEVATED episodes. Defense contractors (RTX, LMT) outperform. Shipping route alternatives priced.",
        "CRITICAL": "Full risk-off rotation likely: GLD +5–12%, XLE vol expansion, SPY beta compression. Regional equity markets (EWJ, EWH) re-price on escalation spillover risk.",
    },
    "eastern_europe": {
        "STABLE":   "Ukraine war in lower-intensity phase. European gas/wheat futures at structural discount vs war-onset. XME tracking metals fundamentals.",
        "ELEVATED": "XME vol expansion (nickel, palladium, steel). European energy security premium re-activates. TLT (Treasuries) safe-haven demand. EUR/USD typically weakens.",
        "CRITICAL": "NATO Article 5 scenario risk priced. European equity markets (EZU) under heavy pressure. Natural gas futures spike. GLD, CHF, JPY safe-haven flows.",
    },
    "taiwan_strait": {
        "STABLE":   "SOXX tracking semiconductor earnings cycle. No supply-chain disruption premium. TSMC ADR (TSM) at normal premium.",
        "ELEVATED": "SOXX vol widening — semiconductor supply chain uncertainty priced. TSM ADR discount expands. EWH re-prices. US-China trade tension premium re-activates.",
        "CRITICAL": "TSMC represents ~92% of sub-7nm chip production. CRITICAL implies global tech supply chain disruption scenario. SOXX can decline 15–30%. AI/datacenter capex forecasts revised down. QQQ correlation elevates.",
    },
    "south_china_sea": {
        "STABLE":   "EWH at normal valuation premium. SCS trade routes clear. Philippine peso and Vietnamese dong stable.",
        "ELEVATED": "EWH vol expansion. Regional shipping insurance surcharges begin. ASEAN equity markets re-price. Container freight rates (FBX) elevate.",
        "CRITICAL": "Regional trade route disruption scenario. $3.4T annual trade through SCS. EWH under significant pressure. Energy import dependencies of Japan/South Korea become visible.",
    },
    "korean_peninsula": {
        "STABLE":   "EWJ tracking Japan macro (BOJ policy, yen). No North Korea provocation premium. KOSPI at normal range.",
        "ELEVATED": "EWJ vol expansion on yen safe-haven demand. KOSPI typically sells off 3–8%. JPY strengthens as regional flight-to-safety. Samsung/SK Hynix premium expands.",
        "CRITICAL": "Full peninsula escalation priced. EWJ/KOSPI under heavy pressure. JPY and gold safe-haven spike. US defense readiness premium activates. Semiconductor supply chain (SOXX) correlation elevates.",
    },
    "panama_canal": {
        "STABLE":   "IYT (transport) tracking domestic shipping fundamentals. Canal at normal throughput. No re-routing premium.",
        "ELEVATED": "IYT vol expansion. Canal draft restrictions or access uncertainty → Cape Horn re-routing premium on container rates. Agricultural commodity transit costs elevate.",
        "CRITICAL": "Full canal disruption scenario. Cape Horn re-routing adds 14–21 days transit per voyage. Global shipping cost spike (similar to Suez 2021 blockage). Agricultural commodity price spike — canal carries 40% of US grain exports.",
    },
    "red_sea": {
        "STABLE":   "IYT at baseline. Red Sea/Suez route normalizing. Container rates and tanker insurance at historical mean.",
        "ELEVATED": "IYT vol expansion. Houthi attack frequency elevated — re-routing via Cape of Good Hope adding $1–3M/voyage. Container rates (FBX) 15–40% above baseline. Eurozone inflation channel activates (delayed 6–8 weeks).",
        "CRITICAL": "Full Red Sea closure scenario. 30% of global container traffic rerouted. Cape route premium maximizes. European energy and consumer goods inflation shock. ECB rate path repriced.",
    },
    "india_pakistan": {
        "STABLE":   "INDA tracking India growth premium. Pakistan macro stress contained. No LoC escalation premium.",
        "ELEVATED": "INDA vol expansion. Rupee risk premium activates. India defense spend acceleration priced. Pakistan sovereign spreads widen. Regional safe-haven demand for GLD in South Asian markets.",
        "CRITICAL": "Nuclear-armed states in escalation — historically rare but INDA can decline 10–20%. Foreign capital flight from India accelerates. GLD regional demand spike. Global risk-off cascade if escalation broadens.",
    },
    "sahel": {
        "STABLE":   "GDX tracking gold price fundamentals. Wagner/Africa Corps activity at baseline. French/EU security presence stable.",
        "ELEVATED": "GDX vol expansion — Sahel instability threatens mine operations (Mali: 4th-largest gold producer). Uranium supply risk (Niger: 5% of global uranium). French energy policy exposure via ORANO.",
        "CRITICAL": "Mine closure risk for Barrick, AngloGold Sahel operations. Niger uranium supply disruption → European nuclear energy cost increase. Coup contagion risk to Côte d'Ivoire (largest regional economy) activates.",
    },
    "venezuela": {
        "STABLE":   "ILF tracking Brazil/Mexico macro. Venezuela sanctions regime stable. Guyana oil production ramp continuing.",
        "ELEVATED": "ILF vol expansion. Venezuela-Guyana Essequibo border tension priced. Colombia border instability activates. Guyana offshore oil project risk premium (Exxon/Hess operations).",
        "CRITICAL": "Essequibo annexation scenario — Guyana oil block (Exxon-operated, 11B barrel resource) under threat. ILF under pressure. Colombian peso risk. US response timeline uncertainty. Brazil mediation premium.",
    },
    "russia_arctic": {
        "STABLE":   "XOP tracking US oil production fundamentals. Arctic shipping route (NSR) at normal commercial activity. NATO-Russia posture stable.",
        "ELEVATED": "XOP vol expansion on Arctic energy access uncertainty. Svalbard/Barents Sea tension activates. NATO Nordic posture upgrade priced (Finland/Sweden accession impact). Norwegian energy infrastructure risk.",
        "CRITICAL": "Arctic resource contestation scenario. NSR transit rights disputed. Norwegian Barents Sea energy assets under pressure. XOP + GLD safe-haven correlation. NATO Article 5 Arctic provisions tested.",
    },
}

# ── Data loading ──────────────────────────────────────────────────────────────

def load_region_data(region: str, days: int = 365) -> pd.DataFrame | None:
    f = OUTPUTS_DIR / f"{SCORES_PREFIX}{region}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    # Exclude warmup
    if "is_warmup" in df.columns:
        df = df[~df["is_warmup"].fillna(False)]
    cutoff = df["date"].max() - timedelta(days=days)
    df = df[df["date"] >= cutoff].copy()
    return df if not df.empty else None

# ── Narrative engine (upgraded from analyze.py) ───────────────────────────────

def get_score_col(df):
    return "GRPS" if "GRPS" in df.columns else "grps"

def get_label_col(df):
    for c in ["GRPS_label", "regime", "label"]:
        if c in df.columns:
            return c
    return None

def build_region_insight(region: str, df: pd.DataFrame) -> dict:
    """
    Full insight dict for one region. Powers the HTML template below.
    """
    sc   = get_score_col(df)
    lc   = get_label_col(df)
    last = df.iloc[-1]

    grps_now   = float(last[sc])
    label_now  = str(last[lc]) if lc else ("CRITICAL" if grps_now > 66 else ("ELEVATED" if grps_now > 33 else "STABLE"))
    as_of      = last["date"].strftime("%d %b %Y")

    def n_days_ago(n):
        target = last["date"] - timedelta(days=n)
        prior  = df[df["date"] <= target]
        return float(prior.iloc[-1][sc]) if not prior.empty else np.nan

    g7d_ago  = n_days_ago(7)
    g30d_ago = n_days_ago(30)
    g7d      = grps_now - g7d_ago  if not np.isnan(g7d_ago)  else np.nan
    g30d     = grps_now - g30d_ago if not np.isnan(g30d_ago) else np.nan

    # Component values
    instab_col   = next((c for c in df.columns if "instab" in c.lower()), None)
    vp_col       = next((c for c in df.columns if "vol_premium" in c.lower()), None)
    vix_comp_col = next((c for c in df.columns if "vix" in c.lower() and "comp" in c.lower()), None)
    vix_z_col    = next((c for c in df.columns if "vix" in c.lower() and "z" in c.lower() and "comp" not in c.lower()), None)
    gold_col     = next((c for c in df.columns if "goldstein" in c.lower()), None)
    decoupled_col= "decoupled_flag" if "decoupled_flag" in df.columns else None

    instab_val   = float(last[instab_col])   if instab_col   else None
    vp_val       = float(last[vp_col])       if vp_col       else None
    vix_comp_val = float(last[vix_comp_col]) if vix_comp_col else None
    vix_z        = float(last[vix_z_col])    if vix_z_col    else None
    goldstein    = float(last[gold_col])     if gold_col     else None
    decoupled    = bool(last[decoupled_col]) if decoupled_col else False

    # Dominant driver
    components = {"Instability": instab_val, "Vol Premium": vp_val, "VIX": vix_comp_val}
    valid_comps = {k: v for k, v in components.items() if v is not None}
    dominant_driver = max(valid_comps, key=valid_comps.get) if valid_comps else "Instability"

    # Anomaly detection
    series = df.set_index("date")[sc]
    rolling_mean = series.rolling(60, min_periods=10).mean()
    rolling_std  = series.rolling(60, min_periods=10).std()
    z_series     = (series - rolling_mean) / rolling_std.replace(0, np.nan)
    recent_anomalies = z_series[
        (z_series > 2.0) & (z_series.index >= last["date"] - timedelta(days=30))
    ].dropna()

    # Recent 14-day history
    hist14 = df.tail(14)[["date", sc, lc] if lc else ["date", sc]].copy()
    hist14["date_str"] = hist14["date"].dt.strftime("%b %d")
    hist14_list = hist14.to_dict("records")

    # 90-day GRPS range
    df90  = df[df["date"] >= last["date"] - timedelta(days=90)]
    grps90_min = float(df90[sc].min()) if not df90.empty else grps_now
    grps90_max = float(df90[sc].max()) if not df90.empty else grps_now

    # ── WHY narrative ──────────────────────────────────────────────────────────
    why_parts = []

    if grps_now > 66:
        why_parts.append(f"Score of {grps_now:.1f} is in <strong>CRITICAL</strong> territory — all three components are simultaneously elevated.")
    elif grps_now > 33:
        why_parts.append(f"Score of {grps_now:.1f} sits in the <strong>ELEVATED</strong> band (33–66). Risk is measurable but not at crisis level.")
    else:
        why_parts.append(f"Score of {grps_now:.1f} is <strong>STABLE</strong> — event flow is cooperative or low-volume, minimal variance pressure.")

    # Driver explanation
    if dominant_driver == "Instability" and instab_val is not None:
        if instab_val > 70:
            why_parts.append(f"Primary driver is the <strong>Instability Index at {instab_val:.1f}</strong> — Goldstein event flow is sitting at the {instab_val:.0f}th percentile of its 252-day window, meaning the region is more conflictual now than it has been for most of the past year.")
        elif instab_val > 40:
            why_parts.append(f"The <strong>Instability Index ({instab_val:.1f})</strong> shows moderately elevated event hostility relative to the past year.")
        else:
            why_parts.append(f"The Instability Index ({instab_val:.1f}) is subdued — Goldstein event flow is near the cooperative end of its historical range.")

    if dominant_driver == "Vol Premium" and vp_val is not None:
        if vp_val > 60:
            why_parts.append(f"The <strong>Vol Premium component ({vp_val:.1f})</strong> is the dominant driver — realised volatility in the sector ETF proxy is unusually elevated relative to its historical norm, and the geo_gate is amplifying this signal.")
        else:
            why_parts.append(f"Vol Premium ({vp_val:.1f}) is contributing meaningfully — the ETF proxy is showing above-average variance attributed to the geopolitical channel.")

    if goldstein is not None:
        if goldstein < -1.5:
            why_parts.append(f"GDELT Goldstein WAVG is <strong>{goldstein:.2f}</strong> — event flow is net-conflictual (hostile and coercive events outnumber cooperative ones).")
        elif goldstein > 1.5:
            why_parts.append(f"GDELT Goldstein WAVG is <strong>+{goldstein:.2f}</strong> — event flow is net-cooperative despite the score level; the GRPS elevation is coming primarily from the volatility channel, not Goldstein instability.")
        else:
            why_parts.append(f"GDELT Goldstein WAVG is {goldstein:.2f} — mixed event balance with no strongly dominant direction.")

    if vix_z is not None:
        if vix_z > 1.5:
            why_parts.append(f"VIX z-score is {vix_z:.2f} — market fear is independently elevated, confirming the geopolitical signal through the macro channel simultaneously.")
        elif decoupled:
            why_parts.append(f"VIX is elevated (z={vix_z:.2f}) but flagged as <strong>decoupled</strong> from Goldstein — macro fear is not confirmed by regional event flow. VIX component is suppressed 70% to prevent double-counting.")
        elif vix_z < 0.3:
            why_parts.append(f"VIX z-score is subdued at {vix_z:.2f} — market is not pricing fear through the macro channel. If GRPS is elevated while VIX is low, the geopolitical signal may be forward-leading relative to market pricing.")

    # Momentum read
    if not np.isnan(g7d) and not np.isnan(g30d):
        if g7d > 3 and g30d > 3:
            why_parts.append(f"Momentum is <strong>consistently deteriorating</strong>: +{g7d:.1f} pts over 7 days, +{g30d:.1f} pts over 30 days. This is a building trend, not a spike.")
        elif g7d < -3 and g30d < -3:
            why_parts.append(f"Momentum is <strong>improving</strong>: {g7d:.1f} pts over 7 days, {g30d:.1f} pts over 30 days. Conditions are actively decompressing.")
        elif g7d > 3 and g30d < -3:
            why_parts.append(f"Short-term deterioration (+{g7d:.1f}/7d) against an improving 30-day trend ({g30d:.1f}/30d). Watch whether this is a reversal or a temporary flare.")

    if recent_anomalies is not None and len(recent_anomalies) > 0:
        why_parts.append(f"⚠ <strong>{len(recent_anomalies)} anomalous spike(s)</strong> detected in the last 30 days (2σ above 60-day rolling mean), on: {', '.join(d.strftime('%b %d') for d in recent_anomalies.index)}.")

    # ── EFFECTS narrative ──────────────────────────────────────────────────────
    effects_map = REGION_EFFECTS.get(region, {})
    effects_text = effects_map.get(label_now, "Monitor ETF proxy vol and regional equity markets for pricing signals.")

    # Add decoupling note to effects if relevant
    if decoupled and label_now != "STABLE":
        effects_text += " Note: VIX component is suppressed today due to macro-geopolitical decoupling — the score is driven by the geopolitical channel only, which may indicate an early-stage signal not yet confirmed by broad market fear."

    return {
        "region":         region,
        "label_display":  REGIONS_META[region]["label"],
        "etf":            REGIONS_META[region]["etf"],
        "color":          REGIONS_META[region]["color"],
        "grps":           grps_now,
        "label":          label_now,
        "as_of":          as_of,
        "g7d":            g7d,
        "g30d":           g30d,
        "instab":         instab_val,
        "vol_premium":    vp_val,
        "vix_comp":       vix_comp_val,
        "vix_z":          vix_z,
        "goldstein":      goldstein,
        "dominant_driver":dominant_driver,
        "why_parts":      why_parts,
        "effects_text":   effects_text,
        "hist14":         hist14_list,
        "grps90_min":     grps90_min,
        "grps90_max":     grps90_max,
        "n_anomalies_30d":len(recent_anomalies) if recent_anomalies is not None else 0,
        "sc_col":         sc,
        "lc_col":         lc,
    }


# ── HTML generation ───────────────────────────────────────────────────────────

LABEL_COLORS = {"STABLE": "#2A6E2A", "ELEVATED": "#B8922A", "CRITICAL": "#8B2020"}
LABEL_BG     = {"STABLE": "rgba(42,110,42,0.10)", "ELEVATED": "rgba(184,146,42,0.10)", "CRITICAL": "rgba(139,32,32,0.10)"}

def pct_bar(value, max_val=100, color="#B8922A"):
    if value is None:
        return '<div style="font-family:\'JetBrains Mono\',monospace;color:#7A766E;font-size:11px;">N/A</div>'
    pct = min(100, max(0, (value / max_val) * 100))
    return f'''
    <div style="display:flex;align-items:center;gap:8px;">
      <div style="flex:1;background:#E0D8C3;border-radius:2px;height:6px;">
        <div style="width:{pct:.0f}%;background:{color};height:6px;border-radius:2px;transition:width 0.3s;"></div>
      </div>
      <span style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#55504A;min-width:36px;text-align:right;">{value:.1f}</span>
    </div>'''

def trend_badge(delta):
    if np.isnan(delta):
        return '<span style="color:#7A766E;">—</span>'
    if delta > 2:
        return f'<span style="color:#8B2020;">▲ +{delta:.1f}</span>'
    elif delta < -2:
        return f'<span style="color:#2A6E2A;">▼ {delta:.1f}</span>'
    else:
        return f'<span style="color:#55504A;">→ {delta:+.1f}</span>'

def sparkline_html(hist14, sc_col, lc_col, color):
    if not hist14:
        return ""
    vals     = [r.get(sc_col, r.get("grps", r.get("GRPS", 0))) for r in hist14]
    labels   = [r.get(lc_col, r.get("GRPS_label", r.get("label", r.get("regime", "")))) for r in hist14]
    dates    = [r.get("date_str", "") for r in hist14]
    rows = ""
    for i, (v, l, d) in enumerate(zip(vals, labels, dates)):
        bg   = "rgba(17,16,8,0.03)" if i % 2 == 0 else "transparent"
        lc_  = LABEL_COLORS.get(str(l).upper(), "#55504A")
        bar  = "█" * max(1, int(float(v) / 10)) if v else ""
        rows += f'<tr style="background:{bg}"><td style="padding:2px 8px;font-family:\'JetBrains Mono\',monospace;color:#7A766E;font-size:10px;">{d}</td><td style="padding:2px 8px;font-family:\'JetBrains Mono\',monospace;color:{color};font-size:11px;">{float(v):.1f}</td><td style="padding:2px 8px;"><span style="font-family:\'JetBrains Mono\',monospace;color:{lc_};font-size:9px;font-weight:600;letter-spacing:0.05em;">{l}</span></td><td style="padding:2px 8px;color:{color};font-size:9px;opacity:0.4;letter-spacing:-1px;">{bar}</td></tr>'
    return f'<table style="width:100%;border-collapse:collapse;">{rows}</table>'

def region_card(ins: dict) -> str:
    lbl     = ins["label"]
    lc      = LABEL_COLORS.get(lbl, "#888")
    lbg     = LABEL_BG.get(lbl, "rgba(136,136,136,0.12)")
    clr     = ins["color"]
    g7d     = ins["g7d"] if not np.isnan(ins.get("g7d", float("nan"))) else float("nan")
    g30d    = ins["g30d"] if not np.isnan(ins.get("g30d", float("nan"))) else float("nan")

    why_html = "".join(f'<p style="margin:0 0 8px;color:#55504A;font-size:14px;line-height:1.65;font-family:\'EB Garamond\',Georgia,serif;">{p}</p>' for p in ins["why_parts"])

    # Component bars
    comp_html = ""
    if ins.get("instab") is not None:
        comp_html += f'<div style="margin-bottom:8px;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;letter-spacing:0.12em;color:#7A766E;text-transform:uppercase;margin-bottom:4px;">Instability Index (40%)</div>{pct_bar(ins["instab"], 100, "#8B2020")}</div>'
    if ins.get("vol_premium") is not None:
        comp_html += f'<div style="margin-bottom:8px;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;letter-spacing:0.12em;color:#7A766E;text-transform:uppercase;margin-bottom:4px;">Vol Premium (40%)</div>{pct_bar(ins["vol_premium"], 100, "#B8922A")}</div>'
    if ins.get("vix_comp") is not None:
        comp_html += f'<div style="margin-bottom:8px;"><div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;letter-spacing:0.12em;color:#7A766E;text-transform:uppercase;margin-bottom:4px;">VIX Component (20%)</div>{pct_bar(ins["vix_comp"], 100, "#55504A")}</div>'

    anom_badge = ""
    if ins.get("n_anomalies_30d", 0) > 0:
        anom_badge = f'<span style="background:rgba(139,32,32,0.08);border:1px solid rgba(139,32,32,0.25);color:#8B2020;padding:2px 8px;border-radius:4px;font-family:\'JetBrains Mono\',monospace;font-size:9px;letter-spacing:0.05em;margin-left:8px;">⚠ {ins["n_anomalies_30d"]} anomaly</span>'

    sparkline = sparkline_html(ins["hist14"], ins["sc_col"], ins["lc_col"] or "GRPS_label", clr)

    return f'''
<div class="region-card" id="card-{ins["region"]}" style="background:#faf9f5;border:1px solid rgba(17,16,8,.10);border-radius:8px;padding:24px;margin-bottom:20px;border-left:3px solid {clr};">
  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
    <div>
      <h2 style="margin:0;font-family:\'EB Garamond\',Georgia,serif;font-size:20px;color:#111008;font-weight:500;letter-spacing:0.01em;">{ins["label_display"]}</h2>
      <span style="font-family:\'JetBrains Mono\',monospace;font-size:10px;color:#7A766E;letter-spacing:0.08em;">ETF proxy: <span style="color:#55504A;font-weight:600;">{ins["etf"]}</span> &nbsp;·&nbsp; as of {ins["as_of"]}</span>
    </div>
    <div style="text-align:right;">
      <div style="font-family:\'EB Garamond\',Georgia,serif;font-size:36px;font-weight:500;color:{clr};line-height:1;">{ins["grps"]:.1f}</div>
      <div style="background:{lbg};border:1px solid {lc}55;color:{lc};padding:3px 10px;border-radius:4px;font-family:\'JetBrains Mono\',monospace;font-size:9px;font-weight:600;letter-spacing:0.08em;margin-top:4px;display:inline-block;">{lbl}</div>
      {anom_badge}
    </div>
  </div>

  <!-- Trend + Range -->
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px;">
    <div style="background:#EDE5D0;border:1px solid rgba(17,16,8,.08);border-radius:6px;padding:10px;text-align:center;">
      <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.12em;">7-Day Δ</div>
      <div style="font-size:15px;">{trend_badge(g7d)}</div>
    </div>
    <div style="background:#EDE5D0;border:1px solid rgba(17,16,8,.08);border-radius:6px;padding:10px;text-align:center;">
      <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.12em;">30-Day Δ</div>
      <div style="font-size:15px;">{trend_badge(g30d)}</div>
    </div>
    <div style="background:#EDE5D0;border:1px solid rgba(17,16,8,.08);border-radius:6px;padding:10px;text-align:center;">
      <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;margin-bottom:5px;text-transform:uppercase;letter-spacing:0.12em;">90-Day Range</div>
      <div style="font-family:\'JetBrains Mono\',monospace;font-size:12px;color:#55504A;">{ins["grps90_min"]:.0f} – {ins["grps90_max"]:.0f}</div>
    </div>
  </div>

  <!-- Two-column layout: components + history -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
    <div>
      <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:10px;">Score Components</div>
      {comp_html if comp_html else '<div style="font-family:\'JetBrains Mono\',monospace;color:#7A766E;font-size:11px;">Component data not available</div>'}
    </div>
    <div>
      <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:10px;">14-Day History</div>
      {sparkline}
    </div>
  </div>

  <!-- Why section -->
  <div style="background:#EDE5D0;border-radius:6px;padding:16px;margin-bottom:12px;border-left:2px solid {clr}88;">
    <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:10px;">Why is the score at this level?</div>
    {why_html}
  </div>

  <!-- Effects section -->
  <div style="background:#EDE5D0;border-radius:6px;padding:16px;border-left:2px solid {lc}88;">
    <div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.15em;margin-bottom:8px;">Possible Market Effects · {lbl}</div>
    <p style="margin:0;font-family:\'EB Garamond\',Georgia,serif;color:#55504A;font-size:15px;line-height:1.65;">{ins["effects_text"]}</p>
  </div>
</div>'''


def build_html(insights: list, generated_at: str, args_days: int) -> str:
    elevated   = sorted([i for i in insights if i["label"] in ("ELEVATED", "CRITICAL")], key=lambda x: -x["grps"])
    stable     = sorted([i for i in insights if i["label"] == "STABLE"],                 key=lambda x: -x["grps"])
    all_sorted = elevated + stable

    n_elevated = len([i for i in insights if i["label"] == "ELEVATED"])
    n_critical = len([i for i in insights if i["label"] == "CRITICAL"])
    n_stable   = len([i for i in insights if i["label"] == "STABLE"])

    # Global summary bar
    def mini_card(ins):
        lc = LABEL_COLORS.get(ins["label"], "#55504A")
        return f'''<a href="#card-{ins["region"]}" style="text-decoration:none;">
          <div style="background:#faf9f5;border:1px solid rgba(17,16,8,.10);border-left:3px solid {ins["color"]};border-radius:6px;padding:10px 14px;cursor:pointer;transition:background 0.15s;" onmouseover="this.style.background='#EDE5D0'" onmouseout="this.style.background='#faf9f5'">
            <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:{ins["color"]};font-weight:600;letter-spacing:0.08em;margin-bottom:5px;">{ins["label_display"]}</div>
            <div style="font-family:'EB Garamond',Georgia,serif;font-size:24px;font-weight:500;color:{ins["color"]};line-height:1;">{ins["grps"]:.1f}</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:{lc};font-weight:600;letter-spacing:0.06em;margin-top:5px;">{ins["label"]}</div>
          </div></a>'''

    overview_cards = "".join(mini_card(i) for i in all_sorted)

    # Nav links
    nav_links = "".join(
        f'<a href="#card-{i["region"]}" style="font-family:\'JetBrains Mono\',monospace;color:{i["color"]};font-size:9px;letter-spacing:0.08em;text-decoration:none;padding:3px 10px;border-radius:4px;border:1px solid {i["color"]}55;white-space:nowrap;" onmouseover="this.style.background=\'{i["color"]}18\'" onmouseout="this.style.background=\'transparent\'">{i["label_display"]}</a> '
        for i in all_sorted
    )

    # Deep-dive cards
    detail_cards = "".join(region_card(i) for i in all_sorted)

    interpretation_guide = '''
    <div style="background:#EDE5D0;border:1px solid rgba(17,16,8,.10);border-radius:8px;padding:24px;margin-bottom:32px;">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
        <h2 style="margin:0;font-family:'JetBrains Mono',monospace;color:#111008;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.20em;">Signal Interpretation Guide</h2>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
        <div>
          <p style="font-family:'EB Garamond',Georgia,serif;color:#55504A;font-size:15px;line-height:1.7;margin:0 0 12px;">
            <strong style="color:#111008;">GRPS is a risk management signal, not directional alpha.</strong>
            An ELEVATED score means geopolitical variance pressure is building in that region — it does not predict whether the linked ETF goes up or down. It quantifies the magnitude of risk, not its direction.
          </p>
          <p style="font-family:'EB Garamond',Georgia,serif;color:#55504A;font-size:15px;line-height:1.7;margin:0;">
            A fund using GRPS=ELEVATED for Hormuz to buy USO OTM puts is not arbitraging a pricing inefficiency — they are sizing a hedge. This is why <strong style="color:#111008;">GRPS does not decay upon commercial publication</strong>: the consuming desk is not trading against the signal.
          </p>
        </div>
        <div>
          <div style="background:#faf9f5;border:1px solid rgba(17,16,8,.08);border-radius:6px;padding:16px;">
            <div style="margin-bottom:10px;"><span style="font-family:'JetBrains Mono',monospace;color:#2A6E2A;font-size:10px;font-weight:600;letter-spacing:0.05em;">STABLE (0–33)</span> <span style="font-family:'EB Garamond',Georgia,serif;color:#55504A;font-size:13px;margin-left:8px;">Event flow cooperative, minimal variance pressure</span></div>
            <div style="margin-bottom:10px;"><span style="font-family:'JetBrains Mono',monospace;color:#B8922A;font-size:10px;font-weight:600;letter-spacing:0.05em;">ELEVATED (33–66)</span> <span style="font-family:'EB Garamond',Georgia,serif;color:#55504A;font-size:13px;margin-left:8px;">Geopolitical variance detectable, above baseline</span></div>
            <div style="margin-bottom:10px;"><span style="font-family:'JetBrains Mono',monospace;color:#8B2020;font-size:10px;font-weight:600;letter-spacing:0.05em;">CRITICAL (66–100)</span> <span style="font-family:'EB Garamond',Georgia,serif;color:#55504A;font-size:13px;margin-left:8px;">Crisis-level pressure; all components simultaneously elevated</span></div>
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(17,16,8,.08);font-family:'JetBrains Mono',monospace;font-size:9px;color:#7A766E;letter-spacing:0.05em;line-height:1.8;">
              Components: Instability Index (40%) + Vol Premium (40%) + VIX Component (20%)<br>
              Data sources: GDELT BigQuery · yfinance · CBOE VIX · [ACLED when configured]
            </div>
          </div>
        </div>
      </div>
    </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Project Goldstein — Intelligence Brief</title>
  <link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #faf9f5;
      color: #111008;
      font-family: 'EB Garamond', Georgia, serif;
      min-height: 100vh;
      padding: 0;
      -webkit-font-smoothing: antialiased;
    }}
    ::-webkit-scrollbar {{ width: 5px; }}
    ::-webkit-scrollbar-track {{ background: #faf9f5; }}
    ::-webkit-scrollbar-thumb {{ background: #E0D8C3; border-radius: 3px; }}
    .sticky-nav {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(237,229,208,0.95);
      backdrop-filter: blur(14px) saturate(1.1);
      border-bottom: 1px solid rgba(17,16,8,.10);
      padding: 10px 32px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .sticky-nav .brand {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 600;
      color: #111008;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      margin-right: 16px;
      white-space: nowrap;
    }}
    a:hover {{ opacity: 0.80; }}
    @media (max-width: 768px) {{
      .region-card div[style*="grid-template-columns: 1fr 1fr"] {{
        grid-template-columns: 1fr !important;
      }}
    }}
  </style>
</head>
<body>

<!-- Sticky region nav -->
<div class="sticky-nav">
  <span class="brand">◆ GOLDSTEIN</span>
  {nav_links}
</div>

<!-- Main content -->
<div style="max-width:1100px;margin:0 auto;padding:32px 24px;">

  <!-- Header -->
  <div style="margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid rgba(17,16,8,.10);">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px;">
      <div>
        <h1 style="font-family:'EB Garamond',Georgia,serif;font-size:30px;font-weight:500;color:#111008;letter-spacing:0.01em;margin-bottom:4px;">
          Project Goldstein
        </h1>
        <p style="font-family:'JetBrains Mono',monospace;color:#7A766E;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;">Geopolitical Intelligence Brief · {generated_at}</p>
      </div>
      <div style="display:flex;gap:20px;text-align:center;">
        <div><div style="font-family:'EB Garamond',Georgia,serif;font-size:28px;font-weight:500;color:#8B2020;">{n_critical}</div><div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.12em;">Critical</div></div>
        <div><div style="font-family:'EB Garamond',Georgia,serif;font-size:28px;font-weight:500;color:#B8922A;">{n_elevated}</div><div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.12em;">Elevated</div></div>
        <div><div style="font-family:'EB Garamond',Georgia,serif;font-size:28px;font-weight:500;color:#2A6E2A;">{n_stable}</div><div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#7A766E;text-transform:uppercase;letter-spacing:0.12em;">Stable</div></div>
      </div>
    </div>
  </div>

  <!-- Overview grid -->
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:32px;">
    {overview_cards}
  </div>

  <!-- Signal interpretation guide -->
  {interpretation_guide}

  <!-- Region deep-dives -->
  <h2 style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#7A766E;text-transform:uppercase;letter-spacing:0.18em;margin-bottom:20px;padding-bottom:10px;border-bottom:1px solid rgba(17,16,8,.10);">Regional Intelligence — Elevated &amp; Critical First</h2>

  {detail_cards}

  <!-- Footer -->
  <div style="margin-top:48px;padding-top:24px;border-top:1px solid rgba(17,16,8,.10);text-align:center;">
    <p style="font-family:'JetBrains Mono',monospace;color:#7A766E;font-size:9px;line-height:1.9;letter-spacing:0.04em;">
      GRPS is a risk management signal, not directional alpha. Alpha decays on publication; variance premia persist.
    </p>
    <p style="font-family:'JetBrains Mono',monospace;color:#8B2020;font-size:9px;margin-top:6px;letter-spacing:0.04em;">
      REGULATORY SAFE HARBOR: GRPS constitutes strictly informational data output and does NOT constitute investment advice under SEC Rule 202(a)(11).
    </p>
    <p style="font-family:'JetBrains Mono',monospace;color:#7A766E;font-size:9px;margin-top:10px;letter-spacing:0.04em;">
      Project Goldstein © {datetime.now().year} · Generated {generated_at} · {args_days}-day lookback
    </p>
  </div>

</div>
</body>
</html>'''


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Goldstein Intelligence Brief")
    parser.add_argument("--days",       type=int, default=365, help="Lookback window in days")
    parser.add_argument("--no-browser", action="store_true",   help="Do not auto-open browser")
    parser.add_argument("--output",     type=str, default="outputs/goldstein_insights.html")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent)

    insights = []
    missing  = []

    for region in REGIONS_META:
        df = load_region_data(region, days=args.days)
        if df is None:
            missing.append(region)
            continue
        try:
            ins = build_region_insight(region, df)
            insights.append(ins)
        except Exception as e:
            print(f"  WARNING: could not build insight for {region}: {e}")
            missing.append(region)

    if not insights:
        print("ERROR: No region data found. Run the pipeline first.")
        sys.exit(1)

    if missing:
        print(f"Missing regions (no score file): {', '.join(missing)}")

    generated_at = datetime.now().strftime("%d %b %Y, %H:%M UTC")
    html = build_html(insights, generated_at, args.days)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Brief generated → {out_path}  ({len(insights)} regions)")

    if not args.no_browser:
        webbrowser.open(f"file://{out_path.resolve()}")

if __name__ == "__main__":
    main()
