#!/bin/bash
# Simple snapshot status - no Docker dependency
cd "$(dirname "$0")"

show_status() {
    clear
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           SNAPSHOT STATUS (Simple)                       ║"
    echo "╠══════════════════════════════════════════════════════════╣"
    printf "║  Updated: %-42s  ║\n" "$(date '+%Y-%m-%d %H:%M:%S')"
    echo "╠══════════════════════════════════════════════════════════╣"

    # Check process
    if pgrep -f "populate_snapshots" > /dev/null 2>&1; then
        echo "║  Process: RUNNING                                        ║"
    else
        echo "║  Process: STOPPED                                        ║"
    fi

    echo "╠══════════════════════════════════════════════════════════╣"

    # Count files on filesystem (fast)
    SNAP_COUNT=$(find /Volumes/main-filestore/ai-PA-data/drive-rag-snapshots -name "*.json.gz" 2>/dev/null | wc -l | tr -d ' ')
    TOTAL=44353
    REMAINING=$((TOTAL - SNAP_COUNT))
    PCT=$((SNAP_COUNT * 100 / TOTAL))

    printf "║  Snapshots:  %6d / %d  (%2d%%)                   ║\n" "$SNAP_COUNT" "$TOTAL" "$PCT"
    printf "║  Remaining:  %6d                                    ║\n" "$REMAINING"

    echo "╠══════════════════════════════════════════════════════════╣"

    # Disk usage
    DISK=$(du -sh /Volumes/main-filestore/ai-PA-data/drive-rag-snapshots 2>/dev/null | cut -f1)
    printf "║  Disk:       %-43s  ║\n" "$DISK"

    echo "╠══════════════════════════════════════════════════════════╣"

    # Recent activity from log
    if [ -f "snapshot_population.log" ]; then
        LAST=$(tail -1 snapshot_population.log 2>/dev/null | grep -oE "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")
        SUCCESSES=$(grep -c "saved_snapshot" snapshot_population.log 2>/dev/null || echo 0)
        ERRORS=$(grep -c "ERROR:" snapshot_population.log 2>/dev/null || echo 0)
        printf "║  Log Success: %6d    Errors: %6d                 ║\n" "$SUCCESSES" "$ERRORS"
        printf "║  Last Log:    %-42s  ║\n" "$LAST"
    fi

    echo "╚══════════════════════════════════════════════════════════╝"
}

if [ "$1" = "watch" ]; then
    while true; do
        show_status
        echo ""
        echo "  Refreshing every 10 seconds... (Ctrl+C to exit)"
        sleep 10
    done
else
    show_status
fi
