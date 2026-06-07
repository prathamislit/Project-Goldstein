"""
dashboard.py - Project Goldstein: Multi-Region Dashboard (v4)
Dynamic region loading, date filter, geopolitical event annotations
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output

import config

# Build REGION_META from the single source of truth (config.py)
# This replaces the old hardcoded dict that had drifted out of sync
# (e.g., strait_of_hormuz→XLE instead of USO, south_china_sea→SOXX instead of EWH)
REGION_META = {
    k: {
        "label": v["label"],
        "etf":   v["sector_etf"],
        "color": v.get("color", "#888"),
    }
    for k, v in config.REGIONS.items()
}

SCORES_PATH = lambda r: f"outputs/daily_scores_{r}.csv"
MASTER_PATH = lambda r: f"data/master_dataset_clean_{r}.csv"

REGIME_META = {
    "STABLE":   {"color": "#2A6E2A", "bg": "rgba(42,110,42,0.08)",   "border": "rgba(42,110,42,0.22)"},
    "ELEVATED": {"color": "#8E6F1E", "bg": "rgba(184,146,42,0.08)",  "border": "rgba(184,146,42,0.22)"},
    "CRITICAL": {"color": "#8B2020", "bg": "rgba(139,32,32,0.08)",   "border": "rgba(139,32,32,0.22)"},
    "N/A":      {"color": "#7A766E", "bg": "rgba(17,16,8,0.05)",     "border": "rgba(17,16,8,0.12)"},
}

BG       = "#faf9f5"
CARD_BG  = "#EDE5D0"
CARD_BG2 = "#E0D8C3"
BORDER   = "rgba(17,16,8,0.12)"
TEXT_PRI = "#111008"
TEXT_SEC = "#55504A"
GRID_CLR = "rgba(17,16,8,0.07)"

DATE_PRESETS = [
    ("1M",  30),
    ("3M",  90),
    ("6M",  180),
    ("1Y",  365),
    ("2Y",  730),
    ("ALL", 0),
]

# Major geopolitical events to annotate on the comparison chart
# (date, short label, y position for label, color)
GEO_EVENTS = [
    ("2022-02-24", "Russia invades Ukraine",        90, "#4FC3F7"),
    ("2022-10-08", "Nord Stream sabotage",           78, "#4FC3F7"),
    ("2023-10-07", "Hamas attacks Israel",           90, "#F5A623"),
    ("2023-12-15", "Houthi Red Sea attacks",         78, "#AB47BC"),
    ("2024-04-13", "Iran strikes Israel",            90, "#F5A623"),
    ("2024-07-31", "Haniyeh assassination",          70, "#F5A623"),
    ("2025-01-15", "Gaza ceasefire / Trump 2.0",     90, "#8BC34A"),
    ("2025-03-15", "US strikes Yemen",               78, "#AB47BC"),
    ("2025-04-02", "Trump Liberation Day tariffs",   85, "#D29922"),
    ("2025-06-12", "Iran nuclear talks collapse",    78, "#F5A623"),
    ("2025-08-01", "Taiwan drills escalation",       80, "#EF5350"),
    ("2026-01-20", "Trump 2nd term escalations",     85, "#D29922"),
]

# ── Data helpers ──────────────────────────────────────────────────────────────

def load_region(rkey):
    p = SCORES_PATH(rkey)
    if not Path(p).exists():
        return None
    try:
        df = pd.read_csv(p, parse_dates=["date"])
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None

def load_master(rkey):
    p = MASTER_PATH(rkey)
    if not Path(p).exists():
        return None
    try:
        df = pd.read_csv(p, parse_dates=["date"])
        return df.sort_values("date").reset_index(drop=True)
    except Exception:
        return None

def available_regions():
    return [r for r in REGION_META if Path(SCORES_PATH(r)).exists()]

def find_col(df, keywords):
    if df is None:
        return None
    for kw in keywords:
        for c in df.columns:
            if kw.lower() in c.lower():
                return c
    return None

def latest_val(df, keywords):
    col = find_col(df, keywords)
    if col is None or df is None:
        return None
    s = df[col].dropna()
    return float(s.iloc[-1]) if not s.empty else None

def get_regime(df):
    col = find_col(df, ["regime", "label", "status"])
    if col is None or df is None:
        return "N/A"
    s = df[col].dropna()
    return str(s.iloc[-1]) if not s.empty else "N/A"

def filter_by_days(df, days):
    if df is None or days == 0:
        return df
    cutoff = df["date"].max() - timedelta(days=days)
    return df[df["date"] >= cutoff].copy()

def last_date(df):
    if df is None:
        return "--"
    return df["date"].max().strftime("%d %b %Y")

# ── Chart builders ────────────────────────────────────────────────────────────

def make_gauge(grps, regime, color):
    val = grps if grps is not None else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        number={"font": {"size": 40, "color": TEXT_PRI, "family": "EB Garamond, Georgia, serif"}},
        gauge={
            "axis": {
                "range": [0, 100],
                "tickvals": [0, 25, 50, 75, 100],
                "tickfont": {"color": TEXT_SEC, "size": 9, "family": "JetBrains Mono, monospace"},
                "tickcolor": BORDER, "ticklen": 4,
            },
            "bar": {"color": color, "thickness": 0.18},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0,  33], "color": "rgba(42,110,42,0.06)"},
                {"range": [33, 66], "color": "rgba(184,146,42,0.06)"},
                {"range": [66, 100], "color": "rgba(139,32,32,0.06)"},
            ],
            "threshold": {"line": {"color": color, "width": 4}, "thickness": 0.85, "value": val},
        },
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=8, b=0, l=28, r=28),
        height=170,
        font={"color": TEXT_PRI, "family": "EB Garamond, Georgia, serif"},
    )
    return fig


def make_comparison_chart(days_filter, show_events=True):
    fig = go.Figure()
    regions = available_regions()

    # compute visible window so we only draw events inside it
    all_dates = []
    for rkey in regions:
        df = filter_by_days(load_region(rkey), days_filter)
        if df is not None:
            all_dates.extend(df["date"].tolist())
    chart_min = min(all_dates) if all_dates else pd.Timestamp("2020-01-01")
    chart_max = max(all_dates) if all_dates else pd.Timestamp.today()

    for rkey in regions:
        meta = REGION_META[rkey]
        df   = filter_by_days(load_region(rkey), days_filter)
        if df is None:
            continue
        col = find_col(df, ["grps", "GRPS"])
        if col is None:
            continue
        c = meta["color"]
        # Reindex to every business day, then forward-fill missing days.
        # Rationale: GRPS measures a regime state, not a daily event count.
        # If no new pipeline data arrived, the previous day's regime assessment
        # remains valid — the geopolitical situation did not change, only the
        # data feed was thin. Forward-fill is standard practice for risk indices.
        df = df.set_index("date").reindex(
            pd.bdate_range(df["date"].min(), df["date"].max())
        )[[col]].ffill().reset_index()
        df.columns = ["date", col]
        fig.add_trace(go.Scatter(
            x=df["date"], y=df[col],
            mode="lines",
            name=meta["label"],
            line=dict(color=c, width=1.6),
            connectgaps=False,
            hovertemplate=f"<b>{meta['label']}</b><br>%{{x|%d %b %Y}}<br>GRPS: %{{y:.1f}}<extra></extra>",
        ))

    # Regime threshold lines
    fig.add_hline(y=33, line=dict(color="rgba(102,187,106,0.3)", width=1, dash="dot"))
    fig.add_hline(y=66, line=dict(color="rgba(239,83,80,0.3)",   width=1, dash="dot"))
    fig.add_annotation(x=0.005, y=16, xref="paper", text="STABLE",   showarrow=False,
                       font=dict(color="rgba(102,187,106,0.4)", size=9), xanchor="left")
    fig.add_annotation(x=0.005, y=49, xref="paper", text="ELEVATED", showarrow=False,
                       font=dict(color="rgba(255,167,38,0.4)",  size=9), xanchor="left")
    fig.add_annotation(x=0.005, y=83, xref="paper", text="CRITICAL", showarrow=False,
                       font=dict(color="rgba(239,83,80,0.4)",   size=9), xanchor="left")

    # Geopolitical event overlays — only draw events within the visible window
    if show_events:
        for date_str, label, y_pos, evt_color in GEO_EVENTS:
            evt_date = pd.Timestamp(date_str)
            if evt_date < chart_min or evt_date > chart_max:
                continue
            # convert hex to rgba for Plotly support
            r = int(evt_color[1:3], 16)
            g = int(evt_color[3:5], 16)
            b = int(evt_color[5:7], 16)
            rgba_color = f"rgba({r},{g},{b},0.31)"

            # add_vline requires ISO string for datetime axes
            fig.add_vline(
                x=date_str,
                line=dict(color=rgba_color, width=1.2, dash="dot"),
            )
            fig.add_annotation(
                x=date_str,
                y=y_pos,
                text=f"<b>{label}</b>",
                showarrow=False,
                font=dict(color=evt_color, size=7.5, family="JetBrains Mono, monospace"),
                bgcolor="rgba(237,229,208,0.95)",
                bordercolor=evt_color,
                borderwidth=1,
                borderpad=4,
                xanchor="left",
                yanchor="bottom",
                textangle=-90,
                opacity=0.92,
            )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=CARD_BG2,
        font={"color": TEXT_PRI, "family": "EB Garamond, Georgia, serif", "size": 11},
        margin=dict(t=16, b=8, l=48, r=16),
        height=290,
        legend=dict(
            orientation="h", x=1, xanchor="right", y=1.14,
            font={"size": 10, "color": TEXT_SEC, "family": "JetBrains Mono, monospace"},
            bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
        ),
        xaxis=dict(gridcolor=GRID_CLR, showgrid=True, zeroline=False,
                   tickfont={"color": TEXT_SEC, "size": 10, "family": "JetBrains Mono, monospace"},
                   tickformat="%b %Y"),
        yaxis=dict(gridcolor=GRID_CLR, showgrid=True, zeroline=False,
                   range=[0, 100],
                   tickfont={"color": TEXT_SEC, "size": 10, "family": "JetBrains Mono, monospace"},
                   title=dict(text="GRPS", font={"color": TEXT_SEC, "size": 10})),
        hovermode="x",
        hoverlabel=dict(bgcolor=CARD_BG, font_size=12, bordercolor=BORDER,
                        font_family="JetBrains Mono, monospace"),
    )
    return fig


def make_detail_chart(rkey, days_filter):
    df_s  = filter_by_days(load_region(rkey), days_filter)
    df_m  = filter_by_days(load_master(rkey), days_filter)
    color = REGION_META[rkey]["color"]
    etf   = REGION_META[rkey]["etf"]

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.38, 0.36, 0.26],
        vertical_spacing=0.05,
        subplot_titles=[
            "Goldstein Stability Score (volume-weighted)",
            f"{etf}  Log Returns  vs.  GARCH-X Conditional Volatility",
            "VIX Z-Score  (rolling 252-day)",
        ],
    )

    g_col = find_col(df_m, ["goldstein"])
    if g_col and df_m is not None:
        fig.add_trace(go.Scatter(
            x=df_m["date"], y=df_m[g_col],
            mode="lines", name="Goldstein",
            line=dict(color="#B8922A", width=1.4, shape="spline", smoothing=0.4),
            hovertemplate="%{x|%d %b %Y}  Goldstein: %{y:.3f}<extra></extra>",
        ), row=1, col=1)
        fig.add_hline(y=0, line=dict(color=BORDER, width=1, dash="dash"), row=1, col=1)

    ret_col   = find_col(df_m, ["log_return", "logreturn", "return"])
    # cond_vol / vol_premium is saved by scorer.py into the scores file, not the master file
    garch_col = find_col(df_s, ["cond_vol", "condvol", "garch", "vol_premium"])
    garch_src = df_s
    if garch_col is None:
        garch_col = find_col(df_m, ["cond_vol", "condvol", "garch", "vol_premium"])
        garch_src = df_m
    if ret_col and df_m is not None:
        vals = df_m[ret_col].fillna(0)
        r2, g2, b2 = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        fig.add_trace(go.Bar(
            x=df_m["date"], y=df_m[ret_col],
            name="Log Return",
            marker=dict(
                color=[f"rgba({r2},{g2},{b2},0.6)" if v >= 0 else "rgba(100,100,120,0.5)"
                       for v in vals],
                line=dict(width=0),
            ),
            hovertemplate="%{x|%d %b %Y}  Return: %{y:.4f}<extra></extra>",
        ), row=2, col=1)
    if garch_col and garch_src is not None:
        fig.add_trace(go.Scatter(
            x=garch_src["date"], y=garch_src[garch_col],
            mode="lines", name="GARCH-X Vol",
            line=dict(color=color, width=1.6),
            hovertemplate="%{x|%d %b %Y}  GARCH Vol: %{y:.4f}<extra></extra>",
        ), row=2, col=1)

    vix_col = find_col(df_s, ["VIX_zscore", "vix_zscore"])
    vix_src = df_s
    if vix_col is None:
        vix_col = find_col(df_m, ["VIX_zscore", "vix_zscore"])
        vix_src = df_m
    if vix_col and vix_src is not None and vix_col in vix_src.columns:
        fig.add_trace(go.Scatter(
            x=vix_src["date"], y=vix_src[vix_col],
            mode="lines", name="VIX Z-Score",
            line=dict(color="#B8922A", width=1.4),
            fill="tozeroy", fillcolor="rgba(184,146,42,0.08)",
            hovertemplate="%{x|%d %b %Y}  VIX z: %{y:.2f}<extra></extra>",
        ), row=3, col=1)
        fig.add_hline(y=1.5, line=dict(color="rgba(239,83,80,0.45)", width=1, dash="dot"), row=3, col=1)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=CARD_BG2,
        font={"color": TEXT_PRI, "family": "EB Garamond, Georgia, serif", "size": 10},
        margin=dict(t=28, b=20, l=55, r=16),
        height=480,
        showlegend=True,
        legend=dict(orientation="h", x=1, xanchor="right", y=1.04,
                    bgcolor="rgba(0,0,0,0)",
                    font={"size": 10, "color": TEXT_SEC, "family": "JetBrains Mono, monospace"}),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=CARD_BG, font_size=11, bordercolor=BORDER,
                        font_family="JetBrains Mono, monospace"),
    )
    for i in range(1, 4):
        fig.update_xaxes(gridcolor=GRID_CLR, showgrid=True, zeroline=False,
                         tickfont={"color": TEXT_SEC, "size": 9, "family": "JetBrains Mono, monospace"},
                         tickformat="%b %Y", row=i, col=1)
        fig.update_yaxes(gridcolor=GRID_CLR, showgrid=True, zeroline=False,
                         tickfont={"color": TEXT_SEC, "size": 9, "family": "JetBrains Mono, monospace"},
                         row=i, col=1)
    for ann in fig.layout.annotations:
        ann.font.color  = TEXT_SEC
        ann.font.size   = 10
        ann.font.family = "JetBrains Mono, monospace"
    return fig

# ── UI helpers ────────────────────────────────────────────────────────────────

def regime_badge(regime):
    rm = REGIME_META.get(regime, REGIME_META["N/A"])
    return html.Span(regime, style={
        "background": rm["bg"], "border": f"1px solid {rm['border']}",
        "color": rm["color"], "borderRadius": "20px",
        "padding": "3px 12px", "fontSize": "10px",
        "fontWeight": "600", "letterSpacing": "0.8px",
    })

def date_btn(label, value, active_val):
    is_active = (value == active_val)
    return html.Button(label, id={"type": "date-btn", "index": value}, n_clicks=0, style={
        "background":   "#E0D8C3" if not is_active else "#111008",
        "border":       f"1px solid {'#111008' if is_active else BORDER}",
        "color":        "#faf9f5" if is_active else TEXT_SEC,
        "borderRadius": "4px",
        "padding":      "5px 14px",
        "fontSize":     "11px",
        "fontFamily":   "JetBrains Mono, monospace",
        "fontWeight":   "600" if is_active else "400",
        "cursor":       "pointer",
        "letterSpacing":"0.5px",
        "transition":   "all 0.15s",
    })

def stat_tile(label, value, color):
    return html.Div([
        html.Div(label, style={
            "color": TEXT_SEC, "fontSize": "9px",
            "fontFamily": "JetBrains Mono, monospace",
            "letterSpacing": "1px", "marginBottom": "5px",
            "textTransform": "uppercase",
        }),
        html.Div(value, style={
            "color": color, "fontSize": "19px",
            "fontFamily": "EB Garamond, Georgia, serif",
            "fontWeight": "600", "lineHeight": "1",
        }),
    ], style={
        "background": CARD_BG, "border": f"1px solid {BORDER}",
        "borderLeft": f"3px solid {color}", "borderRadius": "6px",
        "padding": "11px 16px", "minWidth": "120px", "flex": "1",
    })

# ── Tab builder -- must be defined before app.layout ─────────────────────────

def _build_tabs():
    regions = available_regions() or list(REGION_META.keys())
    return [
        dcc.Tab(
            label=REGION_META.get(rkey, {"label": rkey})["label"],
            value=rkey,
            style={
                "backgroundColor": "transparent", "color": TEXT_SEC,
                "border": "none", "borderBottom": f"2px solid {BORDER}",
                "padding": "10px 22px", "fontSize": "11px",
                "fontFamily": "JetBrains Mono, monospace", "cursor": "pointer",
            },
            selected_style={
                "backgroundColor": "transparent",
                "color": REGION_META.get(rkey, {"color": "#888"})["color"],
                "border": "none",
                "borderBottom": f"2px solid {REGION_META.get(rkey, {'color': '#888'})['color']}",
                "padding": "10px 22px", "fontSize": "11px",
                "fontFamily": "JetBrains Mono, monospace", "fontWeight": "600",
            },
        )
        for rkey in regions
    ]

# ── App ───────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title="Project Goldstein",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
app.config.suppress_callback_exceptions = True

app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #faf9f5; }
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: #faf9f5; }
  ::-webkit-scrollbar-thumb { background: rgba(17,16,8,0.18); border-radius: 3px; }
  button:hover { opacity: 0.85; }
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""

app.layout = html.Div([
    dcc.Store(id="date-store", data=365),

    html.Div(style={
        "height": "2px",
        "background": "linear-gradient(90deg,#B8922A 0%,#8B2020 40%,#2A6E2A 70%,#B8922A 100%)",
    }),

    html.Div([
        html.Div([
            html.Div([
                html.Span("◆ ", style={"color": "#B8922A", "fontSize": "16px"}),
                html.Span("PROJECT GOLDSTEIN", style={
                    "color": TEXT_PRI, "fontSize": "17px",
                    "fontFamily": "JetBrains Mono, monospace",
                    "fontWeight": "600", "letterSpacing": "3px",
                }),
            ]),
            html.Div("Geopolitical Risk Premium Signal  ·  Global Chokepoints",
                     style={"color": TEXT_SEC, "fontSize": "10px",
                            "fontFamily": "JetBrains Mono, monospace",
                            "marginTop": "3px", "letterSpacing": "0.4px"}),
        ]),

        html.Div([
            html.Div("WINDOW", style={"color": TEXT_SEC, "fontSize": "9px",
                                      "fontFamily": "JetBrains Mono, monospace",
                                      "letterSpacing": "1.5px", "marginBottom": "6px"}),
            html.Div(id="date-btn-row",
                     children=[date_btn(label, days, 365) for label, days in DATE_PRESETS],
                     style={"display": "flex", "gap": "6px"}),
        ]),

        html.Div(id="header-status", style={"textAlign": "right"}),

    ], style={
        "display": "flex", "justifyContent": "space-between", "alignItems": "center",
        "padding": "16px 24px 14px", "borderBottom": f"1px solid {BORDER}",
    }),

    html.Div([

        html.Div(id="gauge-row", style={
            "display": "flex", "flexWrap": "wrap",
            "gap": "10px", "padding": "18px 0 14px",
        }),

        html.Div([
            html.Div([
                html.Div(style={"flex": "1", "height": "1px", "background": BORDER}),
                html.Span("GRPS COMPARISON  —  ALL REGIONS", style={
                    "color": TEXT_SEC, "fontSize": "9px",
                    "fontFamily": "JetBrains Mono, monospace",
                    "padding": "0 14px", "letterSpacing": "1.8px", "whiteSpace": "nowrap",
                }),
                html.Div(style={"flex": "1", "height": "1px", "background": BORDER}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),

            html.Div([
                html.Div([
                    html.Span("EVENTS", style={
                        "color": TEXT_SEC, "fontSize": "9px", "letterSpacing": "1.2px",
                        "marginRight": "8px", "verticalAlign": "middle",
                    }),
                    dcc.Checklist(
                        id="events-toggle",
                        options=[{"label": " show", "value": "on"}],
                        value=["on"],
                        inline=True,
                        style={"display": "inline-block", "verticalAlign": "middle"},
                        labelStyle={"color": TEXT_SEC, "fontSize": "10px", "cursor": "pointer"},
                    ),
                ], style={"textAlign": "right", "marginBottom": "6px", "paddingRight": "8px"}),
            ]),

            dcc.Graph(id="comparison-chart", config={"displayModeBar": False}),

        ], style={
            "background": CARD_BG, "border": f"1px solid {BORDER}",
            "borderRadius": "10px", "padding": "16px 8px 10px",
            "marginBottom": "18px",
        }),

        html.Div([
            html.Div([
                html.Div(style={"flex": "1", "height": "1px", "background": BORDER}),
                html.Span("REGION DRILL-DOWN", style={
                    "color": TEXT_SEC, "fontSize": "9px",
                    "fontFamily": "JetBrains Mono, monospace",
                    "padding": "0 14px", "letterSpacing": "1.8px",
                }),
                html.Div(style={"flex": "1", "height": "1px", "background": BORDER}),
            ], style={"display": "flex", "alignItems": "center"}),

            dcc.Tabs(
                id="region-tabs",
                value=available_regions()[0] if available_regions() else "middle_east",
                children=_build_tabs(),
                colors={"border": BORDER, "primary": BORDER, "background": "transparent"},
                style={"border": "none", "borderBottom": f"1px solid {BORDER}"},
            ),
            html.Div(id="tab-content", style={"paddingTop": "16px"}),
        ], style={
            "background": CARD_BG, "border": f"1px solid {BORDER}",
            "borderRadius": "10px", "padding": "16px 16px 20px",
        }),

    ], style={"padding": "0 24px 28px"}),

    html.Div([
        html.Div(
            "COMMERCIAL LICENSING & ALPHA DECAY NOTE: GRPS is natively a risk management and volatility premium identification tool, NOT a directional alpha signal. Alpha elements invariably decay upon commercial publicity; risk management factors persist as they price systemic hedge costs rather than predictive excess returns. Pricing Tiers: Quantitative API Access ($X/mo per region), Dashboard Risk Monitoring ($Y/mo), Institutional Research License ($Z/yr).",
            style={"textAlign": "center", "color": TEXT_SEC, "fontSize": "9px",
                   "letterSpacing": "0.3px", "padding": "8px 24px 4px", "maxWidth": "900px", "margin": "0 auto"}
        ),
        html.Div(
            "REGULATORY SAFE HARBOR: Project Goldstein GRPS constitutes strictly informational data output. The platform provides geopolitical analysis and mathematical volatility premiums, and does explicitly NOT constitute investment advice under SEC Rule 202(a)(11).",
            style={"textAlign": "center", "color": "#8B2020", "fontSize": "9px",
                   "fontFamily": "JetBrains Mono, monospace",
                   "letterSpacing": "0.3px", "padding": "0 24px 12px", "maxWidth": "900px", "margin": "0 auto"}
        ),
        html.Div(
            "Project Goldstein © 2026 · Quantamental Geopolitical Volatility Signal · Internal Use Only",
            style={"textAlign": "center", "color": TEXT_PRI, "fontSize": "10px",
                   "letterSpacing": "0.5px", "padding": "12px",
                   "borderTop": f"1px solid {BORDER}"}
        ),
    ]),

], style={
    "backgroundColor": BG, "minHeight": "100vh",
    "fontFamily": "EB Garamond, Georgia, serif", "color": TEXT_PRI,
})

# ── Callbacks ─────────────────────────────────────────────────────────────────

@app.callback(Output("date-store", "data"),
              [Input({"type": "date-btn", "index": d}, "n_clicks")
               for _, d in DATE_PRESETS],
              prevent_initial_call=True)
def update_date_store(*args):
    from dash import ctx
    if not ctx.triggered_id:
        return 365
    return ctx.triggered_id["index"]


@app.callback(Output("date-btn-row", "children"), Input("date-store", "data"))
def refresh_btn_styles(active_val):
    return [date_btn(label, days, active_val) for label, days in DATE_PRESETS]


@app.callback(Output("header-status", "children"), Input("date-store", "data"))
def update_header_status(_):
    regions = available_regions()
    dates   = []
    for r in regions:
        df_r = load_region(r)
        if df_r is not None:
            dates.append(df_r["date"].max())
    as_of   = max(dates).strftime("%d %b %Y") if dates else "--"
    ok      = len(regions) == len(REGION_META)
    return html.Div([
        html.Div([
            html.Span("●", style={"color": "#66BB6A" if ok else "#FFA726",
                                   "fontSize": "8px", "marginRight": "5px"}),
            html.Span(f"{len(regions)}/{len(REGION_META)} REGIONS",
                      style={"color": TEXT_SEC, "fontSize": "9px", "letterSpacing": "1px"}),
        ], style={"marginBottom": "3px"}),
        html.Div(f"as of  {as_of}", style={"color": TEXT_SEC, "fontSize": "10px"}),
    ])


@app.callback(Output("gauge-row", "children"), Input("date-store", "data"))
def update_gauges(_):
    regions = available_regions()
    n       = len(regions)
    min_w   = "calc(33% - 10px)" if n <= 3 else "calc(25% - 10px)"
    cards   = []
    for rkey in regions:
        meta   = REGION_META.get(rkey, {"label": rkey, "etf": "--", "color": "#888"})
        df     = load_region(rkey)
        grps   = latest_val(df, ["grps", "GRPS"])
        regime = get_regime(df)
        color  = meta["color"]
        cards.append(html.Div([
            html.Div([
                html.Span(meta["label"], style={"color": TEXT_PRI, "fontSize": "12px",
                                                "fontFamily": "EB Garamond, Georgia, serif",
                                                "fontWeight": "600"}),
                html.Span(f" · {meta['etf']}", style={"color": TEXT_SEC, "fontSize": "10px",
                                                       "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"textAlign": "center", "marginBottom": "6px"}),
            dcc.Graph(figure=make_gauge(grps, regime, color),
                      config={"displayModeBar": False}, style={"height": "170px"}),
            html.Div(regime_badge(regime),
                     style={"textAlign": "center", "marginTop": "4px", "marginBottom": "5px"}),
            html.Div(f"as of {last_date(df)}" if df is not None else "no data",
                     style={"textAlign": "center", "color": TEXT_SEC, "fontSize": "9px",
                            "fontFamily": "JetBrains Mono, monospace"}),
        ], style={
            "flex": f"1 1 {min_w}", "minWidth": "180px",
            "background": CARD_BG, "border": f"1px solid {BORDER}",
            "borderTop": f"3px solid {color}", "borderRadius": "10px",
            "padding": "14px 10px 12px",
        }))
    return cards


@app.callback(
    Output("comparison-chart", "figure"),
    Input("date-store", "data"),
    Input("events-toggle", "value"),
)
def update_comparison(days_filter, events_val):
    show = bool(events_val and "on" in events_val)
    return make_comparison_chart(days_filter, show_events=show)


@app.callback(
    Output("tab-content", "children"),
    Input("region-tabs", "value"),
    Input("date-store", "data"),
)
def render_tab(rkey, days_filter):
    df_s  = load_region(rkey)
    df_m  = load_master(rkey)
    meta  = REGION_META.get(rkey, {"label": rkey, "etf": "--", "color": "#888"})
    color = meta["color"]

    if df_s is None:
        return html.Div([
            html.Div("◈", style={"fontSize": "28px", "color": BORDER, "marginBottom": "10px"}),
            html.Div("No data for this region.", style={"color": TEXT_SEC, "marginBottom": "6px"}),
            html.Code("bash run_all_regions.sh", style={
                "color": TEXT_PRI, "background": CARD_BG2,
                "padding": "5px 12px", "borderRadius": "4px", "fontSize": "11px",
                "fontFamily": "JetBrains Mono, monospace",
            }),
        ], style={"textAlign": "center", "padding": "50px 20px"})

    grps   = latest_val(df_s, ["grps", "GRPS"])
    regime = get_regime(df_s)
    rm     = REGIME_META.get(regime, REGIME_META["N/A"])
    g_val  = latest_val(df_m, ["goldstein"]) if df_m is not None else None
    vix_z  = latest_val(df_s, ["VIX_zscore", "vix_zscore"]) or (latest_val(df_m, ["VIX_zscore", "vix_zscore"]) if df_m is not None else None)

    tiles = html.Div([
        stat_tile("Status",         regime,                            rm["color"]),
        stat_tile("GRPS Score",     f"{grps:.1f} / 100" if grps is not None else "--", color),
        stat_tile("Goldstein WAVG", f"{g_val:.3f}"       if g_val  is not None else "--", "#B8922A"),
        stat_tile("VIX Z-Score",    f"{vix_z:.2f}"       if vix_z  is not None else "--", "#8B2020"),
    ], style={"display": "flex", "gap": "10px", "marginBottom": "14px", "flexWrap": "wrap"})

    chart = html.Div(
        dcc.Graph(
            figure=make_detail_chart(rkey, days_filter),
            config={"displayModeBar": True, "displaylogo": False,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"]},
        ),
        style={
            "background": CARD_BG2, "border": f"1px solid {BORDER}",
            "borderTop": f"2px solid {color}", "borderRadius": "8px", "overflow": "hidden",
        },
    )
    return html.Div([tiles, chart])


@app.callback(Output("region-tabs", "children"), Input("date-store", "data"))
def refresh_tabs(_):
    return _build_tabs()


if __name__ == "__main__":
    # Wire auth if GOLDSTEIN_USERS env var is set (production)
    # Skipped in local dev unless you set the var
    if os.getenv("GOLDSTEIN_USERS"):
        from auth import register_auth
        register_auth(app.server)
        print("[auth] Login gate active.")

    print("Project Goldstein -> http://localhost:8050")
    print(f"Regions loaded: {available_regions()}")
    app.run(debug=False, host="0.0.0.0", port=8050)
