#!/bin/bash
# Launcher for go2rtc that loads camera credentials from .env before exec.
# Invoked by launchd: com.ai-pa.go2rtc.plist

set -euo pipefail

REPO_DIR="/Volumes/main-drive/ai-PA"
GO2RTC_DIR="$REPO_DIR/deployment/go2rtc"
ENV_FILE="$REPO_DIR/.env"

# Source credentials. Only export the FOX_CAM_* keys to keep the rest
# of the .env (e.g. ANTHROPIC_API_KEY, etc.) out of go2rtc's env.
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key val; do
        case "$key" in
            FOX_CAM_USER|FOX_CAM_PASS)
                export "$key=$val"
                ;;
        esac
    done < <(grep -E '^(FOX_CAM_USER|FOX_CAM_PASS)=' "$ENV_FILE")
fi

if [ -z "${FOX_CAM_USER:-}" ] || [ -z "${FOX_CAM_PASS:-}" ]; then
    echo "ERROR: FOX_CAM_USER or FOX_CAM_PASS missing from $ENV_FILE"
    exit 1
fi

# Binary lives on the boot volume (not /Volumes/) to avoid macOS App
# Translocation, which hangs unsigned binaries when launched by launchd
# from non-boot mounts. Config can stay in the repo.
exec "/Users/dorseyhomeserver/Library/Application Support/ai-pa/go2rtc/go2rtc" \
    -config "$GO2RTC_DIR/go2rtc.yaml"
