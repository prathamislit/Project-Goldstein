#!/usr/bin/env python3
"""
merge_reports.py — Combine Intelligence Brief + Backtest Report into one file.

Three-page unified dashboard:
  1. Intelligence Brief  (from goldstein_insights.html)
  2. System Overview     (from backtest_report.html)
  3. Backtest Results    (from backtest_report.html)

Output: outputs/goldstein_combined.html
Called automatically by Run_All_regions.sh after every run.
"""

import re
import sys
import webbrowser
import argparse
from pathlib import Path
from datetime import datetime

INSIGHTS_FILE = Path("outputs/goldstein_insights.html")
BACKTEST_FILE = Path("outputs/backtest_report.html")
OUTPUT_FILE   = Path("outputs/goldstein_combined.html")


def extract_insights_body(html: str) -> str:
    """Pull the main content block out of goldstein_insights.html.
    Strips the sticky-nav bar and the outer shell, then uses
    bracket-counting to extract the full max-width wrapper div
    including all deeply-nested region cards."""
    # Remove the sticky nav bar
    html = re.sub(r'<!-- Sticky region nav -->.*?</div>\s*\n', '', html, flags=re.DOTALL)

    # Find the outer max-width content wrapper
    marker = 'max-width:1100px'
    start_attr = html.find(marker)
    if start_attr == -1:
        # Fallback: everything inside <body>
        m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
        return m.group(1).strip() if m else html

    # Walk back to the opening < of this div
    start = html.rfind('<', 0, start_attr)

    # Void elements that must not increment depth
    VOID = {'<br', '<img', '<input', '<hr', '<meta', '<link', '<col',
            '<area', '<base', '<embed', '<param', '<source', '<track', '<wbr'}

    # Bracket-count to find the matching </div>
    depth = 0
    i = start
    length = len(html)
    while i < length:
        if html[i] == '<':
            if html[i:i+4] == '<!--':
                end_comment = html.find('-->', i)
                i = end_comment + 3 if end_comment != -1 else length
                continue
            elif html[i:i+2] == '</':
                depth -= 1
                if depth == 0:
                    end = html.index('>', i) + 1
                    content = html[start:end]
                    # Strip any stray shell tags that leaked past the outer div
                    for tag in ('</html>', '</body>', '</head>'):
                        content = content.replace(tag, '')
                    return content.rstrip()
            else:
                # Only increment for non-void opening tags
                tag_start = html[i:i+10].split()[0].rstrip('>')
                if tag_start.lower() not in VOID:
                    depth += 1
        i += 1
    # Fallback: grab everything and strip shell tags
    content = html[start:]
    for tag in ('</html>', '</body>', '</head>'):
        content = content.replace(tag, '')
    return content.rstrip()


def extract_backtest_css(html: str) -> str:
    m = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
    return m.group(1) if m else ""


def extract_page_div(html: str, page_id: str) -> str:
    """
    Extract a full <div class="page" id="page-X"> ... </div> block.
    Uses bracket-counting to find the correct matching closing tag
    so nested divs don't truncate the result.
    """
    start_tag = f'id="{page_id}"'
    start = html.find(start_tag)
    if start == -1:
        return ""
    # Walk back to the opening < of this div
    start = html.rfind('<', 0, start)

    depth = 0
    i = start
    length = len(html)
    while i < length:
        if html[i] == '<':
            if html[i:i+2] == '</':
                depth -= 1
                if depth == 0:
                    end = html.index('>', i) + 1
                    return html[start:end]
            elif not html[i:i+2] == '<!':
                depth += 1
        i += 1
    return html[start:]


def extract_bt_script(html: str) -> str:
    m = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
    return m.group(1) if m else ""


def extract_insights_styles(html: str) -> str:
    m = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
    return m.group(1) if m else ""


def build_combined(insights_html: str, backtest_html: str) -> str:
    bt_css       = extract_backtest_css(backtest_html)
    insights_css = extract_insights_styles(insights_html)
    overview_div = extract_page_div(backtest_html, "page-overview")
    backtest_div = extract_page_div(backtest_html, "page-backtest")
    bt_script    = extract_bt_script(backtest_html)
    insights_body= extract_insights_body(insights_html)

    # Make overview/backtest divs non-active by default (insights is page 1)
    overview_div = overview_div.replace('class="page active"', 'class="page"')
    backtest_div = backtest_div.replace('class="page active"', 'class="page"')

    generated = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Project Goldstein — Live Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
/* ── Backtest shell styles ── */
{bt_css}

/* ── Insights page overrides ── */
#page-insights {{
  background: #080c14;
  min-height: 100%;
  padding: 0;
  margin: -36px -40px;
  padding: 28px 32px;
}}
#page-insights h2 {{
  color: #e8e8e8;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 2px;
  border-bottom: 1px solid #1a2030;
  padding-bottom: 10px;
  margin-top: 0;
}}
/* Override body bg for insights page consistency */
body {{ background: #0d1117; }}
main {{ background: #0d1117; }}

/* Scrollable main */
main {{ overflow-y: auto; height: 100vh; }}

/* Nav section label */
.nav-section-label {{
  padding: 16px 12px 4px;
  font-size: 10px;
  font-weight: 500;
  color: var(--nav-muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}}

/* Insights region cards keep their inline styles — no conflicts */
.region-card a {{ color: inherit; }}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">
    <div class="nav-brand-title">◆ Project Goldstein</div>
    <div class="nav-brand-sub">Live Intelligence Dashboard</div>
  </div>

  <div class="nav-section-label">Signal</div>
  <div class="nav-item active" onclick="show('insights',this)">
    <span class="nav-dot" style="background:#7B9FFF;"></span>Intelligence Brief
  </div>

  <div class="nav-section-label">Validation</div>
  <div class="nav-item" onclick="show('overview',this)">
    <span class="nav-dot"></span>System Overview
  </div>
  <div class="nav-item" onclick="show('backtest',this)">
    <span class="nav-dot"></span>Backtest Results
  </div>

  <div class="nav-footer">Updated: {generated}</div>
</nav>

<main>

<!-- INTELLIGENCE BRIEF -->
<div class="page active" id="page-insights">
{insights_body}
</div>

<!-- SYSTEM OVERVIEW -->
{overview_div}

<!-- BACKTEST RESULTS -->
{backtest_div}

</main>

<script>
function show(id, el) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  el.classList.add('active');
  // scroll main back to top on tab switch
  document.querySelector('main').scrollTop = 0;
}}

{bt_script}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import os
    os.chdir(Path(__file__).parent)

    if not INSIGHTS_FILE.exists():
        print(f"ERROR: {INSIGHTS_FILE} not found — run generate_insights.py first")
        sys.exit(1)
    if not BACKTEST_FILE.exists():
        print(f"ERROR: {BACKTEST_FILE} not found — run backtest.py --html first")
        sys.exit(1)

    insights_html = INSIGHTS_FILE.read_text(encoding="utf-8")
    backtest_html = BACKTEST_FILE.read_text(encoding="utf-8")

    combined = build_combined(insights_html, backtest_html)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(combined, encoding="utf-8")
    print(f"Combined dashboard → {OUTPUT_FILE}  ({len(combined)//1024}KB)")

    if not args.no_browser:
        webbrowser.open(f"file://{OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
