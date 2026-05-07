#!/usr/bin/env bash
# Frigate detect-pipeline watchdog.
#
# Two distinct failure modes seen in the wild on Frigate 0.17.1 with
# the apple-silicon (Metal/MPS) detector:
#
#   1. HARD WEDGE — the detect queue between capture workers and the
#      detector locks up after a transient go2rtc / RTSP blip. Symptom:
#      every cam's `detection_fps` sits at 0.0 forever even though
#      `camera_fps` stays healthy.
#
#   2. SILENT WEDGE — the detector keeps reporting healthy inference
#      latency (130-150ms) and a non-zero `detection_fps`, but its
#      output is empty for every frame. Foxes + people walk through
#      shot and nothing fires. We only know it's broken because zero
#      events are created over an unusually long window. Restart fixes
#      it cleanly. Likely a Metal/MPS model state bug we can only see
#      from the outside.
#
# We've hit case (1) twice in one day and case (2) once on the same
# day; both restart cleanly. The poll cadence (launchd, 60s) is fast
# enough that hysteresis-padded recovery is well under 5 minutes for
# (1) and under ~50 minutes for (2).
#
# Strategy: poll Frigate's /api/stats once a minute (called by
# launchd). Track two counters with separate hysteresis:
#
#   wedge_hard:  ALL cams det_fps=0 AND any cam_fps>0.5  (≥3 in a row)
#   wedge_silent: events count over the last EVENT_WINDOW_SEC seconds
#                 is zero AND all cams det_fps>0.5 AND cam_fps>0.5
#                 (≥3 in a row)
#
# Either trips a docker-compose restart frigate. EVENT_WINDOW_SEC is
# set to 45 minutes — long enough to ride out genuinely quiet periods
# (foxes can be absent for an hour easily, but leaves/shadows almost
# always produce *some* false-positive event in a working pipeline),
# short enough that a real silent-wedge gets caught within ~50 min of
# detection.
#
# Run via ~/Library/LaunchAgents/com.ai-pa.frigate-watchdog.plist
# (StartInterval=60). Logs to ~/Library/Logs/frigate-watchdog/.
set -euo pipefail

STATE_DIR=/tmp/frigate-watchdog
mkdir -p "$STATE_DIR"
STATE_HARD="$STATE_DIR/hard"
STATE_SILENT="$STATE_DIR/silent"
LOG_DIR="$HOME/Library/Logs/frigate-watchdog"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/watchdog.log"

# How far back to look for SOME event before declaring silent-wedge.
# 45 min: long enough to absorb normal quiet stretches; short enough
# to catch real wedges within an hour.
EVENT_WINDOW_SEC=2700

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Fetch stats from inside the container (auth bypass on the internal
# port). Empty response = container down or stats endpoint hung; treat
# as "unknown" and DON'T increment the wedge counters — we don't want
# to restart while Frigate is already shutting down for some other
# reason.
stats=$(docker exec frigate sh -c 'wget -qO- --timeout=5 http://127.0.0.1:5000/api/stats' 2>/dev/null || true)
if [[ -z "$stats" ]]; then
    echo "$(ts) stats unavailable — skipping" >> "$LOG"
    echo 0 > "$STATE_HARD"
    echo 0 > "$STATE_SILENT"
    exit 0
fi

# Pull the events count over the recent window. If the events query
# fails we treat it as "unknown" rather than zero — never want to
# restart on a transient API hiccup.
since=$(($(date +%s) - EVENT_WINDOW_SEC))
events_json=$(docker exec frigate sh -c "wget -qO- --timeout=5 'http://127.0.0.1:5000/api/events?after=$since&limit=5&include_thumbnails=0'" 2>/dev/null || true)
events_count=$(echo "$events_json" | /usr/bin/env python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(len(data) if isinstance(data, list) else -1)
except Exception:
    print(-1)
" 2>/dev/null || echo -1)

# Classify the stats payload into hard / silent / healthy. Pure verdict
# string output makes the bash case-statement below easy to read.
verdict=$(echo "$stats" | EVENTS="$events_count" /usr/bin/env python3 -c "
import sys, json, os
events = int(os.environ.get('EVENTS', '-1'))
try:
    s = json.loads(sys.stdin.read())
except Exception:
    print('bad_json')
    sys.exit()
cams = s.get('cameras', {})
if not cams:
    print('no_cams')
    sys.exit()
all_det_zero = all((c.get('detection_fps') or 0) == 0 for c in cams.values())
all_det_alive = all((c.get('detection_fps') or 0) > 0.5 for c in cams.values())
any_cam_active = any((c.get('camera_fps') or 0) > 0.5 for c in cams.values())
all_cam_active = all((c.get('camera_fps') or 0) > 0.5 for c in cams.values())
if all_det_zero and any_cam_active:
    print('wedged_hard')
elif events == 0 and all_det_alive and all_cam_active:
    # Detector running fine, every cam streaming, yet not a single
    # event in the long window. Real silent-wedge signature.
    print('wedged_silent')
elif events < 0:
    # Couldn't read events — don't escalate, but don't reset either.
    print('events_unknown')
else:
    print('healthy')
" 2>/dev/null || echo bad_parse)

prev_hard=$(cat "$STATE_HARD" 2>/dev/null || echo 0)
prev_silent=$(cat "$STATE_SILENT" 2>/dev/null || echo 0)

restart_frigate() {
    local reason="$1"
    echo "$(ts) → restarting frigate ($reason)" >> "$LOG"
    cd /Volumes/main-drive/ai-PA && \
        /usr/local/bin/docker-compose restart frigate >> "$LOG" 2>&1 || \
        /opt/homebrew/bin/docker-compose restart frigate >> "$LOG" 2>&1
    echo 0 > "$STATE_HARD"
    echo 0 > "$STATE_SILENT"
    echo "$(ts) restart issued" >> "$LOG"
}

case "$verdict" in
    wedged_hard)
        n=$((prev_hard + 1))
        echo "$n" > "$STATE_HARD"
        echo "$(ts) verdict=wedged_hard consecutive=$n" >> "$LOG"
        if [[ $n -ge 3 ]]; then
            restart_frigate "hard wedge — det_fps=0 across all cams for $n checks"
        fi
        ;;
    wedged_silent)
        n=$((prev_silent + 1))
        echo "$n" > "$STATE_SILENT"
        echo "$(ts) verdict=wedged_silent consecutive=$n events_in_${EVENT_WINDOW_SEC}s=0" >> "$LOG"
        if [[ $n -ge 3 ]]; then
            restart_frigate "silent wedge — 0 events in ${EVENT_WINDOW_SEC}s while det+cam alive, $n checks"
        fi
        ;;
    healthy)
        if [[ "$prev_hard" != "0" || "$prev_silent" != "0" ]]; then
            echo "$(ts) verdict=healthy (was hard=$prev_hard silent=$prev_silent)" >> "$LOG"
        fi
        echo 0 > "$STATE_HARD"
        echo 0 > "$STATE_SILENT"
        ;;
    events_unknown)
        # Stats good, events API blip. Don't change either counter.
        echo "$(ts) verdict=events_unknown — stats ok but events API didn't respond" >> "$LOG"
        ;;
    *)
        echo "$(ts) verdict=$verdict — no action" >> "$LOG"
        ;;
esac
