#!/usr/bin/env bash
# Frigate detect-pipeline watchdog.
#
# Symptom this guards against: every cam's RTSP feed reconnects after
# a transient go2rtc / network blip, ffmpeg comes back fine, but the
# detect queue between capture workers and the detector wedges —
# `camera_fps` stays normal, `detection_fps` sits at 0.0 forever, and
# every frame is dropped at the skip stage. We've hit this twice in
# one day; both times a `docker-compose restart frigate` cleanly
# unwedged everything.
#
# Strategy: poll Frigate's /api/stats once a minute (called by
# launchd). Track consecutive observations where ALL cams have
# detection_fps=0 AND at least one cam has camera_fps>0.5 (so we
# don't restart during a real outage where cameras themselves are
# offline). After 3 in a row (~3 min), restart the container and
# reset the counter.
#
# Run via ~/Library/LaunchAgents/com.ai-pa.frigate-watchdog.plist
# (StartInterval=60). Logs to ~/Library/Logs/frigate-watchdog/.
set -euo pipefail

STATE=/tmp/frigate-watchdog.state
LOG_DIR="$HOME/Library/Logs/frigate-watchdog"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/watchdog.log"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Fetch stats from inside the container (auth bypass on the internal
# port). Empty response = container down or stats endpoint hung; treat
# as "unknown" and DON'T increment the wedge counter — we don't want
# to restart while Frigate is already shutting down for some other
# reason.
stats=$(docker exec frigate sh -c 'wget -qO- --timeout=5 http://127.0.0.1:5000/api/stats' 2>/dev/null || true)
if [[ -z "$stats" ]]; then
    echo "$(ts) stats unavailable — skipping" >> "$LOG"
    echo 0 > "$STATE"
    exit 0
fi

verdict=$(echo "$stats" | /usr/bin/env python3 -c "
import sys, json
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
any_cam_active = any((c.get('camera_fps') or 0) > 0.5 for c in cams.values())
if all_det_zero and any_cam_active:
    print('wedged')
else:
    print('healthy')
" 2>/dev/null || echo bad_parse)

prev=$(cat "$STATE" 2>/dev/null || echo 0)

case "$verdict" in
    wedged)
        n=$((prev + 1))
        echo "$n" > "$STATE"
        echo "$(ts) verdict=wedged consecutive=$n" >> "$LOG"
        if [[ $n -ge 3 ]]; then
            echo "$(ts) → restarting frigate (wedged for $n checks)" >> "$LOG"
            cd /Volumes/main-drive/ai-PA && \
                /usr/local/bin/docker-compose restart frigate >> "$LOG" 2>&1 || \
                /opt/homebrew/bin/docker-compose restart frigate >> "$LOG" 2>&1
            echo 0 > "$STATE"
            echo "$(ts) restart issued" >> "$LOG"
        fi
        ;;
    healthy)
        if [[ "$prev" != "0" ]]; then
            echo "$(ts) verdict=healthy (was $prev)" >> "$LOG"
        fi
        echo 0 > "$STATE"
        ;;
    *)
        echo "$(ts) verdict=$verdict — no action" >> "$LOG"
        ;;
esac
