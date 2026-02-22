#!/bin/bash
# Wrapper for OmniFocus host bridge that waits for external drive mount.
# Used by launchd (com.omnifocus.bridge) to survive reboots gracefully.

EXTERNAL_DRIVE="/Volumes/main-drive"
BRIDGE_DIR="${EXTERNAL_DRIVE}/ai-PA/omnifocus-mcp-letta"
MAX_WAIT=120  # seconds to wait for drive
POLL_INTERVAL=5

# Wait for external drive
elapsed=0
while [ ! -f "${BRIDGE_DIR}/host-bridge-service.js" ]; do
    if [ $elapsed -ge $MAX_WAIT ]; then
        echo "$(date): Drive not mounted after ${MAX_WAIT}s, exiting" >&2
        exit 1
    fi
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo "$(date): Drive mounted, starting bridge (waited ${elapsed}s)"
cd "${BRIDGE_DIR}" || exit 1
exec /opt/homebrew/bin/node host-bridge-service.js 8889
