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
#      shot and nothing fires. Likely a Metal/MPS model state bug we
#      can only see from the outside. Hit three times in 36 hours.
#
# Strategy: poll Frigate's /api/stats once a minute (called by
# launchd). Track two counters with separate hysteresis:
#
#   wedge_hard:    ALL cams det_fps=0 AND any cam_fps>0.5  (≥3 in a row)
#   wedge_silent:  zero events in EVENT_WINDOW_SEC AND a recording file
#                  was written in the last RECORDING_WINDOW_SEC AND all
#                  cams det+cam alive (≥3 in a row).
#
# The recording-activity check is what lets us tighten the silent-wedge
# window aggressively without false-positiving on legit quiet periods:
# Frigate writes 10s motion-triggered segments under
# /media/frigate/recordings/<date>/<hour>/<cam>/. If recordings are
# being written but zero events fire, that's *motion without
# detections* — the high-confidence silent-wedge signature. If no
# recordings have been written either, the scene is genuinely quiet
# and we DON'T restart.
#
# Either tier-1 or tier-2 trips a docker-compose restart frigate.
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
# Tightened from 2700s (45 min) to 600s (10 min) on 2026-05-08 after
# the third silent-wedge in 36h. The motion-gated check below prevents
# false positives during legit quiet periods, so a tight window is
# safe.
EVENT_WINDOW_SEC=600

# Recording-file mtime threshold. If any recording is newer than this,
# Frigate is seeing motion. Frigate writes 10s segments, so 5 min
# easily covers normal pacing while staying short enough to be a
# meaningful "recent activity" signal.
RECORDING_WINDOW_SEC=300

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

# Recording-activity check: any motion segment file written in the
# last RECORDING_WINDOW_SEC seconds. We use `find -mmin` (rounded to
# minutes); convert seconds to minutes with a ceil. Output is "yes"
# (some file matched) or "no" (none matched). Failure modes (find
# errors, container down) → "unknown" — don't escalate either way.
rec_mins=$(( (RECORDING_WINDOW_SEC + 59) / 60 ))
rec_active=$(docker exec frigate sh -c "find /media/frigate/recordings -type f -mmin -${rec_mins} -name '*.mp4' 2>/dev/null | head -1" 2>/dev/null || true)
if [[ -z "$rec_active" ]]; then
    # Either no recent recordings OR find failed. Distinguish by
    # checking whether the recordings dir is reachable at all.
    rec_dir_ok=$(docker exec frigate sh -c "test -d /media/frigate/recordings && echo ok" 2>/dev/null || true)
    if [[ "$rec_dir_ok" == "ok" ]]; then
        rec_signal="quiet"     # dir reachable, no recent files → genuinely quiet
    else
        rec_signal="unknown"   # can't read dir → treat as unknown
    fi
else
    rec_signal="motion"        # at least one fresh recording → motion is happening
fi

# Classify the stats payload into hard / silent / healthy. Pure verdict
# string output makes the bash case-statement below easy to read.
verdict=$(echo "$stats" | EVENTS="$events_count" REC_SIGNAL="$rec_signal" /usr/bin/env python3 -c "
import sys, json, os
events = int(os.environ.get('EVENTS', '-1'))
rec_signal = os.environ.get('REC_SIGNAL', 'unknown')
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
elif (events == 0 and all_det_alive and all_cam_active
      and rec_signal == 'motion'):
    # Detector running fine, every cam streaming, motion segments
    # being written to disk → motion exists but no events. The
    # high-confidence silent-wedge signature. Tight window OK
    # because rec_signal=='motion' rules out legitimate quiet.
    print('wedged_silent')
elif events == 0 and rec_signal == 'quiet' and all_cam_active:
    # No events AND no recordings AND cams streaming → scene is
    # genuinely quiet. Don't restart, but it IS healthy.
    print('healthy_quiet')
elif events < 0 or rec_signal == 'unknown':
    # Couldn't read events or recordings dir — don't escalate,
    # don't reset either.
    print('signals_unknown')
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
        echo "$(ts) verdict=wedged_silent consecutive=$n events_in_${EVENT_WINDOW_SEC}s=0 rec_signal=motion" >> "$LOG"
        if [[ $n -ge 3 ]]; then
            restart_frigate "silent wedge — 0 events in ${EVENT_WINDOW_SEC}s but motion recording active, $n checks"
        fi
        ;;
    healthy|healthy_quiet)
        if [[ "$prev_hard" != "0" || "$prev_silent" != "0" ]]; then
            echo "$(ts) verdict=$verdict (was hard=$prev_hard silent=$prev_silent)" >> "$LOG"
        fi
        echo 0 > "$STATE_HARD"
        echo 0 > "$STATE_SILENT"
        ;;
    signals_unknown)
        # Stats good, events API or recordings dir blip. Don't change
        # either counter.
        echo "$(ts) verdict=signals_unknown — events_count=$events_count rec_signal=$rec_signal" >> "$LOG"
        ;;
    *)
        echo "$(ts) verdict=$verdict — no action" >> "$LOG"
        ;;
esac
