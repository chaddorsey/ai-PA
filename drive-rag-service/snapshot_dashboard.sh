#!/bin/bash
# Snapshot Population Dashboard
# Usage: ./snapshot_dashboard.sh        (one-time check)
#        ./snapshot_dashboard.sh watch  (auto-updating dashboard)

cd "$(dirname "$0")"

show_dashboard() {
    # Get counts from database
    TOTAL_DOCS=$(docker exec supabase-db psql -U postgres -d postgres -t -A -c "SELECT COUNT(*) FROM rag.document_state;" 2>/dev/null || echo "0")
    SNAPSHOTS_DB=$(docker exec supabase-db psql -U postgres -d postgres -t -A -c "SELECT COUNT(*) FROM rag.document_snapshots;" 2>/dev/null || echo "0")

    # Get filesystem snapshot count
    SNAPSHOTS_FS=$(find /Volumes/main-filestore/ai-PA-data/drive-rag-snapshots -name "*.json.gz" 2>/dev/null | wc -l | tr -d ' ')

    # Calculate progress
    REMAINING=$((TOTAL_DOCS - SNAPSHOTS_DB))
    if [ "$TOTAL_DOCS" -gt 0 ]; then
        PCT=$((SNAPSHOTS_DB * 100 / TOTAL_DOCS))
    else
        PCT=0
    fi

    # Get disk usage
    DISK_USAGE=$(du -sh /Volumes/main-filestore/ai-PA-data/drive-rag-snapshots 2>/dev/null | cut -f1 || echo "0")

    # Check if process is running
    RUNNING=$(pgrep -f "populate_snapshots" > /dev/null && echo "YES" || echo "NO")

    # Get recent log entries
    if [ -f "snapshot_population.log" ]; then
        LAST_LOG=$(tail -1 snapshot_population.log 2>/dev/null | head -c 80)
        ERRORS=$(grep -c "ERROR:" snapshot_population.log 2>/dev/null | tr -d '[:space:]')
        SUCCESSES=$(grep -c "saved_snapshot" snapshot_population.log 2>/dev/null | tr -d '[:space:]')
        # Ensure numeric values
        ERRORS=${ERRORS:-0}
        SUCCESSES=${SUCCESSES:-0}
    else
        LAST_LOG="No log file yet"
        ERRORS=0
        SUCCESSES=0
    fi

    # Calculate rate if log exists
    if [ -f "snapshot_population.log" ]; then
        # Get timestamps from first and last progress lines
        FIRST_TIME=$(grep "Progress:" snapshot_population.log 2>/dev/null | head -1 | grep -oE "[0-9]+,[0-9]+" | head -1 | tr -d ',')
        LAST_TIME=$(grep "Progress:" snapshot_population.log 2>/dev/null | tail -1 | grep -oE "[0-9]+,[0-9]+" | head -1 | tr -d ',')
        if [ -n "$FIRST_TIME" ] && [ -n "$LAST_TIME" ] && [ "$LAST_TIME" -gt "$FIRST_TIME" ]; then
            PROCESSED=$((LAST_TIME - FIRST_TIME))
            # Estimate rate (rough)
            RATE_INFO="~processing"
        else
            RATE_INFO="calculating..."
        fi
    else
        RATE_INFO="not started"
    fi

    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           SNAPSHOT POPULATION DASHBOARD                  ║"
    echo "╠══════════════════════════════════════════════════════════╣"
    printf "║  Updated: %-42s  ║\n" "$(date '+%Y-%m-%d %H:%M:%S')"
    echo "╠══════════════════════════════════════════════════════════╣"
    printf "║  Process Running: %-38s  ║\n" "$RUNNING"
    echo "╠══════════════════════════════════════════════════════════╣"
    printf "║  Total Documents:     %10d                         ║\n" "$TOTAL_DOCS"
    printf "║  Snapshots (DB):      %10d  (%3d%%)                 ║\n" "$SNAPSHOTS_DB" "$PCT"
    printf "║  Snapshots (Files):   %10d                         ║\n" "$SNAPSHOTS_FS"
    printf "║  Remaining:           %10d                         ║\n" "$REMAINING"
    echo "╠══════════════════════════════════════════════════════════╣"
    printf "║  Disk Usage:          %-34s  ║\n" "$DISK_USAGE"
    echo "╠══════════════════════════════════════════════════════════╣"
    printf "║  Log Successes:       %10d                         ║\n" "$SUCCESSES"
    printf "║  Log Errors:          %10d                         ║\n" "$ERRORS"
    echo "╠══════════════════════════════════════════════════════════╣"
    # Calculate rate from progress reports in log
    if [ -f "snapshot_population.log" ]; then
        # Count progress reports and calculate rate
        PROGRESS_LINES=$(grep -c "Progress:" snapshot_population.log 2>/dev/null | tr -d '[:space:]')
        PROGRESS_LINES=${PROGRESS_LINES:-0}
        if [ "$PROGRESS_LINES" -gt 1 ]; then
            # Each progress report is every 100 docs
            # Calculate elapsed time from first to last progress line
            RATE_MSG="~${PROGRESS_LINES}00 processed"
        else
            RATE_MSG="calculating..."
        fi
    else
        RATE_MSG="not started"
    fi
    # Estimate time remaining using start time from log
    if [ "$SNAPSHOTS_DB" -gt 50 ] && [ "$REMAINING" -gt 0 ]; then
        # Get start time from first log entry (format: 2026-02-03 12:33:08)
        START_TIME=$(head -5 snapshot_population.log 2>/dev/null | grep -oE "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1)
        if [ -n "$START_TIME" ]; then
            START_EPOCH=$(date -j -f "%Y-%m-%d %H:%M:%S" "$START_TIME" "+%s" 2>/dev/null)
            NOW_EPOCH=$(date "+%s")
            if [ -n "$START_EPOCH" ] && [ "$NOW_EPOCH" -gt "$START_EPOCH" ]; then
                ELAPSED_SECS=$((NOW_EPOCH - START_EPOCH))
                ELAPSED_MINS=$((ELAPSED_SECS / 60))
                if [ "$ELAPSED_MINS" -gt 0 ]; then
                    # Snapshots processed since start (assume started at ~70)
                    PROCESSED=$((SNAPSHOTS_DB - 70))
                    DOCS_PER_MIN=$((PROCESSED / ELAPSED_MINS))
                    DOCS_PER_HOUR=$((DOCS_PER_MIN * 60))
                    if [ "$DOCS_PER_HOUR" -gt 0 ]; then
                        HOURS_LEFT=$((REMAINING / DOCS_PER_HOUR))
                        MINS_LEFT=$(( (REMAINING * 60 / DOCS_PER_HOUR) % 60 ))
                        printf "║  Elapsed:             %d min                            ║\n" "$ELAPSED_MINS"
                        printf "║  Rate:                ~%d/hour                        ║\n" "$DOCS_PER_HOUR"
                        printf "║  Est. Time Left:      ~%dh %dm                         ║\n" "$HOURS_LEFT" "$MINS_LEFT"
                    fi
                fi
            fi
        fi
    fi
    echo "╠══════════════════════════════════════════════════════════╣"
    # Get cleaner last activity timestamp
    LAST_TIME=$(grep "saved_snapshot\|normalized" snapshot_population.log 2>/dev/null | tail -1 | grep -oE "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}" | head -1)
    if [ -n "$LAST_TIME" ]; then
        printf "║  Last Activity:       %-34s  ║\n" "$LAST_TIME"
    else
        echo "║  Last Activity:       (checking...)                       ║"
    fi
    echo "╚══════════════════════════════════════════════════════════╝"

    if [ "$RUNNING" = "NO" ] && [ "$REMAINING" -gt 0 ]; then
        echo ""
        echo "  ⚠️  Process not running but snapshots incomplete!"
        echo "  Restart: poetry run python scripts/populate_snapshots.py >> snapshot_population.log 2>&1 &"
    fi
}

if [ "$1" = "watch" ]; then
    echo "Starting dashboard (Ctrl+C to exit)..."
    sleep 1
    while true; do
        clear
        show_dashboard
        echo ""
        echo "  Refreshing every 15 seconds... (Ctrl+C to exit)"
        sleep 15
    done
else
    show_dashboard
fi
