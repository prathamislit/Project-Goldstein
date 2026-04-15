#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Project Goldstein — All-Regions Pipeline Runner
# Runs every configured region sequentially, saves per-region CSVs
# Usage: bash run_all_regions.sh [--incremental]
#
# Health check (FLAW 13 fix):
#   After every run, writes timestamp + result to logs/health_status.txt.
#   If the cron job silently drops, the absence of a fresh timestamp is the
#   detection mechanism.  Check: cat ~/Desktop/goldstein/logs/health_status.txt
# ─────────────────────────────────────────────────────────────────────────────

cd ~/Desktop/goldstein
source venv/bin/activate
mkdir -p logs outputs data

RUN_START=$(date +%s)
RUN_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Kill existing dashboard (prevents hot-reload collisions during the run)
lsof -ti :8050 | xargs kill -9 2>/dev/null
sleep 1

# Incremental mode: pass --incremental to only fetch last 14 days
# Full history (default): fetches from START_DATE in config.py (2022-01-01)
INCREMENTAL=0
for arg in "$@"; do
    if [ "$arg" = "--incremental" ]; then
        INCREMENTAL=1
    fi
done

if [ $INCREMENTAL -eq 1 ]; then
    INCREMENTAL_START=$(date -v-14d +%Y-%m-%d 2>/dev/null || date -d "14 days ago" +%Y-%m-%d)
    export START_DATE=$INCREMENTAL_START
    echo "INCREMENTAL mode: fetching $START_DATE to today (~$0.12 BigQuery cost)" | tee -a logs/pipeline.log
else
    echo "FULL mode: fetching from 2022-01-01 (~$6 BigQuery cost)" | tee -a logs/pipeline.log
fi

echo "═══════════════════════════════════════════════════" | tee -a logs/pipeline.log
echo "ALL-REGIONS run started: $(date)"                    | tee -a logs/pipeline.log
echo "═══════════════════════════════════════════════════" | tee -a logs/pipeline.log

REGIONS=(
    "middle_east"
    "eastern_europe"
    "taiwan_strait"
    "strait_of_hormuz"
    "south_china_sea"
    "korean_peninsula"
    "panama_canal"
    "red_sea"
    "india_pakistan"
    "sahel"
    "venezuela"
    "russia_arctic"
)

SUCCESS=()
FAILED=()

for REGION in "${REGIONS[@]}"; do
    echo "" | tee -a logs/pipeline.log
    echo "───────────────────────────────────────────────────" | tee -a logs/pipeline.log
    echo "  Region: $REGION  ($(date +%H:%M:%S))"             | tee -a logs/pipeline.log
    echo "───────────────────────────────────────────────────" | tee -a logs/pipeline.log

    # Switch region
    sed -i '' "s/^REGION=.*/REGION=$REGION/" .env

    # ── Auto-healing incremental failsafe ─────────────────────────────────────
    if [ $INCREMENTAL -eq 1 ]; then
        if [ ! -f "data/master_dataset_clean_${REGION}.csv" ]; then
            echo "  [0/4] OVERRIDE: cache missing. Forcing 4-year full backfill." | tee -a logs/pipeline.log
            export START_DATE="2022-01-01"
        else
            export START_DATE=$INCREMENTAL_START
        fi
    fi

    STAGE_FAILED=0

    echo "  [1/4] GDELT..." | tee -a logs/pipeline.log
    python3 -u gdelt_fetcher.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }

    if [ $STAGE_FAILED -eq 0 ]; then
        echo "  [2/4] Market data..." | tee -a logs/pipeline.log
        python3 -u market_data.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }
    fi

    if [ $STAGE_FAILED -eq 0 ]; then
        echo "  [3/4] Preprocessing..." | tee -a logs/pipeline.log
        python3 -u preprocessor.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }
    fi

    if [ $STAGE_FAILED -eq 0 ]; then
        echo "  [4/4] Scoring..." | tee -a logs/pipeline.log
        python3 -u scorer.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }
    fi

    if [ $STAGE_FAILED -eq 0 ]; then
        cp outputs/daily_scores.csv      outputs/daily_scores_${REGION}.csv
        cp data/master_dataset_clean.csv data/master_dataset_clean_${REGION}.csv
        echo "  ✓ Saved: outputs/daily_scores_${REGION}.csv" | tee -a logs/pipeline.log
        SUCCESS+=("$REGION")
    else
        echo "  ✗ FAILED: $REGION — check logs/pipeline.log" | tee -a logs/pipeline.log
        FAILED+=("$REGION")
    fi

done

RUN_END=$(date +%s)
RUN_DURATION=$(( RUN_END - RUN_START ))

echo "" | tee -a logs/pipeline.log
echo "═══════════════════════════════════════════════════" | tee -a logs/pipeline.log
echo "Completed: $(date)"                                  | tee -a logs/pipeline.log
echo "  Success: ${#SUCCESS[@]}/${#REGIONS[@]} regions"    | tee -a logs/pipeline.log
echo "  Failed:  ${#FAILED[@]} region(s): ${FAILED[*]}"    | tee -a logs/pipeline.log
echo "  Duration: ${RUN_DURATION}s"                        | tee -a logs/pipeline.log
echo "═══════════════════════════════════════════════════" | tee -a logs/pipeline.log

# ── Health check write (FLAW 13 fix) ──────────────────────────────────────────
# This file is the dead-man's switch: if its timestamp is >3 days old, the
# cron job has silently failed.  Check: cat logs/health_status.txt
if [ ${#FAILED[@]} -eq 0 ]; then
    HEALTH_STATUS="OK"
else
    HEALTH_STATUS="PARTIAL_FAILURE"
fi

cat > logs/health_status.txt << EOF
last_run_utc:    $RUN_TS
status:          $HEALTH_STATUS
regions_success: ${#SUCCESS[@]}
regions_failed:  ${#FAILED[@]}
failed_list:     ${FAILED[*]:-none}
duration_sec:    $RUN_DURATION
incremental:     $INCREMENTAL
EOF

echo "[health] Status written → logs/health_status.txt ($HEALTH_STATUS)"

# Restore .env to middle_east as default
sed -i '' "s/^REGION=.*/REGION=middle_east/" .env

echo ""
echo "Running daily backtest validation..."
python3 -u backtest.py --html >> logs/pipeline.log 2>&1

echo "Generating intelligence brief..."
python3 -u generate_insights.py --no-browser >> logs/pipeline.log 2>&1

echo "Merging combined dashboard..."
python3 -u merge_reports.py --no-browser >> logs/pipeline.log 2>&1
open outputs/goldstein_combined.html



echo ""
echo "Launching dashboard at http://localhost:8050 ..."
nohup python3 Dashboard.py >> logs/pipeline.log 2>&1 &
DASH_PID=$!
sleep 10
open http://localhost:8050

echo ""
echo "✓ Done. ${#SUCCESS[@]}/${#REGIONS[@]} regions loaded."
echo "  Dashboard PID: $DASH_PID"
echo "  Stop: kill $DASH_PID"
echo "  Health: cat ~/Desktop/goldstein/logs/health_status.txt"