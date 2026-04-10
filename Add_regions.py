#!/usr/bin/env python3
"""
add_regions.py — Adds 4 new geopolitical regions to config.py
Run from ~/Desktop/goldstein/: python3 add_regions.py
"""
from pathlib import Path

cfg = Path("config.py")
if not cfg.exists():
    print("ERROR: config.py not found. Run from ~/Desktop/goldstein/")
    exit(1)

txt = cfg.read_text()

# ── New regions block to inject ───────────────────────────────────────────────
NEW_REGIONS = '''
    # ── Strait of Hormuz ──────────────────────────────────────────────────────
    # Iran + Oman + Saudi Arabia — controls ~20% of global oil transit
    # ETF: XLE (Energy) — most direct oil-price sensitivity
    "strait_of_hormuz": {
        "countries": ["IR", "MU", "SA"],
        "etf":       "XLE",
        "name":      "Strait of Hormuz",
    },

    # ── South China Sea ────────────────────────────────────────────────────────
    # China + Philippines + Vietnam + Malaysia — $3.4T trade annually
    # ETF: SOXX (Semiconductors) — supply chain + Taiwan Strait overlap
    "south_china_sea": {
        "countries": ["CH", "RP", "VM", "MY"],
        "etf":       "SOXX",
        "name":      "South China Sea",
    },

    # ── Korean Peninsula ──────────────────────────────────────────────────────
    # South Korea + North Korea + Japan — nuclear escalation proxy
    # ETF: EWJ (Japan ETF) — most liquid regional risk proxy
    "korean_peninsula": {
        "countries": ["KS", "KN", "JA"],
        "etf":       "EWJ",
        "name":      "Korean Peninsula",
    },

    # ── Panama Canal ──────────────────────────────────────────────────────────
    # Panama + Colombia + Cuba — shipping chokepoint, China port influence
    # ETF: IYT (iShares Transportation) — direct shipping/logistics exposure
    "panama_canal": {
        "countries": ["PM", "CO", "CU"],
        "etf":       "IYT",
        "name":      "Panama Canal",
    },
'''

# Find the closing brace of the REGIONS dict and inject before it
# We look for the last closing brace of the REGIONS = { ... } block
import re

# Strategy: find REGIONS = { ... } and append new entries before closing }
# Detect end of REGIONS dict by finding a line that is just "}" after the dict starts
if "strait_of_hormuz" in txt:
    print("✓ New regions already present in config.py — nothing to add.")
    exit(0)

# Find the REGIONS dict and inject new entries before its closing brace
# We'll look for the pattern: the last entry in the dict followed by closing }
# Insert before the line that closes the top-level REGIONS dict

lines = txt.splitlines()
regions_start = None
brace_depth   = 0
insert_at     = None

for i, line in enumerate(lines):
    if re.match(r'\s*REGIONS\s*=\s*\{', line):
        regions_start = i
        brace_depth = 1
        continue
    if regions_start is not None:
        brace_depth += line.count("{") - line.count("}")
        if brace_depth == 0:
            insert_at = i
            break

if insert_at is None:
    print("ERROR: Could not locate REGIONS dict closing brace.")
    print("Add the new regions manually to config.py REGIONS dict.")
    exit(1)

lines.insert(insert_at, NEW_REGIONS)
cfg.write_text("\n".join(lines))

print("✓ config.py updated with 4 new regions:")
print("    strait_of_hormuz  → XLE  (IR, MU, SA)")
print("    south_china_sea   → SOXX (CH, RP, VM, MY)")
print("    korean_peninsula  → EWJ  (KS, KN, JA)")
print("    panama_canal      → IYT  (PM, CO, CU)")
print("")
print("Next: bash run_all_regions.sh")