#!/bin/bash
# Script to ensure OmniFocus bridge service is running
# Checks if external drive is mounted and starts the service if needed

BRIDGE_SERVICE="com.omnifocus.bridge"
EXTERNAL_DRIVE="/Volumes/main-drive"
BRIDGE_DIR="${EXTERNAL_DRIVE}/ai-PA/omnifocus-mcp-letta"
MAX_RETRIES=10
RETRY_DELAY=5

# Function to check if bridge service process is running
is_bridge_running() {
    pgrep -f "host-bridge-service.js" > /dev/null
}

# Function to check if external drive is mounted
is_drive_mounted() {
    [ -d "${EXTERNAL_DRIVE}" ] && [ -f "${BRIDGE_DIR}/host-bridge-service.js" ]
}

# Wait for external drive to be mounted
wait_for_drive() {
    local retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        if is_drive_mounted; then
            return 0
        fi
        sleep $RETRY_DELAY
        retries=$((retries + 1))
    done
    return 1
}

# Main execution
main() {
    # Wait for external drive to be mounted
    if ! wait_for_drive; then
        # If drive not mounted, try to log to a fallback location
        FALLBACK_LOG="${HOME}/Library/Logs/omnifocus-bridge-startup.log"
        echo "$(date): External drive not mounted after ${MAX_RETRIES} retries" >> "${FALLBACK_LOG}" 2>&1
        exit 1
    fi

    # Set up log file path (use fallback if drive not accessible)
    if [ -w "${BRIDGE_DIR}" ]; then
        LOG_FILE="${BRIDGE_DIR}/bridge-startup.log"
    else
        LOG_FILE="${HOME}/Library/Logs/omnifocus-bridge-startup.log"
    fi

    # Check if bridge service is already running
    if is_bridge_running; then
        echo "$(date): Bridge service already running" >> "${LOG_FILE}" 2>&1
        exit 0
    fi

    # Start the launchd service
    if launchctl start "${BRIDGE_SERVICE}" >> "${LOG_FILE}" 2>&1; then
        # Wait a moment and verify it started
        sleep 2
        if is_bridge_running; then
            echo "$(date): Successfully started bridge service" >> "${LOG_FILE}" 2>&1
            exit 0
        else
            echo "$(date): Failed to start bridge service (process not found after start)" >> "${LOG_FILE}" 2>&1
            exit 1
        fi
    else
        echo "$(date): Failed to start bridge service via launchctl" >> "${LOG_FILE}" 2>&1
        exit 1
    fi
}

main "$@"
