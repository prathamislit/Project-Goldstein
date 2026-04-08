#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Project Goldstein — All-Regions Pipeline Runner
# Runs every configured region sequentially, saves per-region CSVs
# Usage: bash run_all_regions.sh
# ─────────────────────────────────────────────────────────────────────────────

cd ~/Desktop/goldstein
source venv/bin/activate
mkdir -p logs outputs data

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

    STAGE_FAILED=0

    echo "  [1/4] GDELT..." | tee -a logs/pipeline.log
    python3 gdelt_fetcher.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }

    if [ $STAGE_FAILED -eq 0 ]; then
        echo "  [2/4] Market data..." | tee -a logs/pipeline.log
        python3 market_data.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }
    fi

    if [ $STAGE_FAILED -eq 0 ]; then
        echo "  [3/4] Preprocessing..." | tee -a logs/pipeline.log
        python3 preprocessor.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }
    fi

    if [ $STAGE_FAILED -eq 0 ]; then
        echo "  [4/4] Scoring..." | tee -a logs/pipeline.log
        python3 scorer.py >> logs/pipeline.log 2>&1 || { STAGE_FAILED=1; }
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

echo "" | tee -a logs/pipeline.log
echo "═══════════════════════════════════════════════════" | tee -a logs/pipeline.log
echo "Completed: $(date)"                                  | tee -a logs/pipeline.log
echo "  Success: ${SUCCESS[*]}"                            | tee -a logs/pipeline.log
echo "  Failed:  ${#FAILED[@]} region(s)"                  | tee -a logs/pipeline.log
echo "═══════════════════════════════════════════════════" | tee -a logs/pipeline.log

# Restore .env to middle_east as default
sed -i '' "s/^REGION=.*/REGION=middle_east/" .env

# Kill existing dashboard
lsof -ti :8050 | xargs kill -9 2>/dev/null
sleep 1

echo ""
echo "Launching dashboard at http://localhost:8050 ..."
nohup python3 dashboard.py >> logs/pipeline.log 2>&1 &
DASH_PID=$!
sleep 3
open http://localhost:8050

echo ""
echo "✓ Done. ${#SUCCESS[@]}/${#REGIONS[@]} regions loaded."
echo "  Dashboard PID: $DASH_PID"
echo "  Stop: kill $DASH_PID"