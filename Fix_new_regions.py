#!/usr/bin/env python3
"""
fix_new_regions.py — Removes incorrectly formatted region entries and re-adds
them with the exact key names the pipeline expects.
Run from ~/Desktop/goldstein/: python3 fix_new_regions.py
"""
import re
from pathlib import Path

cfg = Path("config.py")
txt = cfg.read_text()

# ── Remove the bad block added by add_regions.py ─────────────────────────────
# It starts with the comment "# ── Strait of Hormuz" and ends before the closing
# brace of the REGIONS dict. We'll strip everything between those markers.

bad_start = '\n    # ── Strait of Hormuz'
bad_end   = '\n    # ── Panama Canal'

# Find and remove the entire injected block
if '    "strait_of_hormuz"' in txt:
    # Remove from the start of the bad block to just after the panama_canal closing brace
    pattern = r'\n    # ── Strait of Hormuz.*?},\n'   # greedy up to last },
    # Use a more targeted removal: find the block between bad_start marker and end of panama entry
    start_idx = txt.find('\n    # ── Strait of Hormuz')
    if start_idx != -1:
        # Find the closing brace of panama_canal entry (4 closing braces after "panama_canal")
        search_from = txt.find('"panama_canal"', start_idx)
        # Find the }, that closes the panama_canal dict
        end_idx = txt.find('\n    },\n', search_from)
        if end_idx != -1:
            end_idx += len('\n    },\n')
            txt = txt[:start_idx] + txt[end_idx:]
            print("✓ Removed old (incorrectly formatted) region entries")
        else:
            print("! Could not find end of panama_canal — removing manually may be needed")
    else:
        print("! Could not find start marker — entries may already be clean")
else:
    print("✓ No old entries found — config is clean")

# ── Correct entries using exact key names the pipeline expects ────────────────
CORRECT_BLOCK = '''
    # ── Strait of Hormuz ──────────────────────────────────────────────────────
    # Iran + Oman + Saudi Arabia — controls ~20% of global oil transit
    "strait_of_hormuz": {
        "label":            "Strait of Hormuz",
        "sector_etf":       "XLE",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["IR", "MU", "SA"],
        "gdelt_adm1_prefix": None,
    },

    # ── South China Sea ────────────────────────────────────────────────────────
    # China + Philippines + Vietnam + Malaysia — $3.4T annual trade
    "south_china_sea": {
        "label":            "South China Sea",
        "sector_etf":       "SOXX",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["CH", "RP", "VM", "MY"],
        "gdelt_adm1_prefix": None,
    },

    # ── Korean Peninsula ──────────────────────────────────────────────────────
    # South Korea + North Korea + Japan — nuclear escalation proxy
    "korean_peninsula": {
        "label":            "Korean Peninsula",
        "sector_etf":       "EWJ",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["KS", "KN", "JA"],
        "gdelt_adm1_prefix": None,
    },

    # ── Panama Canal ──────────────────────────────────────────────────────────
    # Panama + Colombia + Cuba — shipping chokepoint, China port influence
    "panama_canal": {
        "label":            "Panama Canal",
        "sector_etf":       "IYT",
        "benchmarks":       ["SPY", "GLD"],
        "gdelt_countries":  ["PM", "CO", "CU"],
        "gdelt_adm1_prefix": None,
    },
'''

# Find the closing brace of the REGIONS dict and inject before it
lines       = txt.splitlines()
regions_start = None
brace_depth   = 0
insert_at     = None

for i, line in enumerate(lines):
    if re.match(r'\s*REGIONS\s*=\s*\{', line):
        regions_start = i
        brace_depth   = 1
        continue
    if regions_start is not None:
        brace_depth += line.count("{") - line.count("}")
        if brace_depth == 0:
            insert_at = i
            break

if insert_at is None:
    print("ERROR: Could not find closing brace of REGIONS dict.")
    exit(1)

lines.insert(insert_at, CORRECT_BLOCK)
cfg.write_text("\n".join(lines))

print("✓ config.py updated with correct region entries:")
print("    strait_of_hormuz  → XLE  (IR, MU, SA)")
print("    south_china_sea   → SOXX (CH, RP, VM, MY)")
print("    korean_peninsula  → EWJ  (KS, KN, JA)")
print("    panama_canal      → IYT  (PM, CO, CU)")
print("")
print("Next: bash run_all_regions.sh")