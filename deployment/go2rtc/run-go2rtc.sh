#!/bin/bash
# Launcher for go2rtc that loads camera credentials from .env before exec.
# Invoked by launchd: com.ai-pa.go2rtc.plist

set -euo pipefail

REPO_DIR="/Volumes/main-drive/ai-PA"
GO2RTC_DIR="$REPO_DIR/deployment/go2rtc"
ENV_FILE="$REPO_DIR/.env"

# Copy the config to a boot-volume path that launchd-spawned agents
# can read without TCC prompts. macOS Sequoia restricts user-agent
# file access to /Volumes/* — calling open() on such paths in agent
# context hangs waiting for a permission prompt that never displays.
LIVE_CONFIG_DIR="/Users/dorseyhomeserver/.local/etc/go2rtc"
LIVE_CONFIG="$LIVE_CONFIG_DIR/go2rtc.yaml"
mkdir -p "$LIVE_CONFIG_DIR"
rm -f "$LIVE_CONFIG"  # remove any prior symlink/copy from a previous run
cp "$GO2RTC_DIR/go2rtc.yaml" "$LIVE_CONFIG"

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

# Binary lives on the boot volume at a no-spaces path. Earlier attempt
# at "/Users/.../Library/Application Support/ai-pa/go2rtc/go2rtc" hung
# under launchd, possibly due to space-handling in the launchd path
# resolver or a Sequoia provenance/xprotect check that timed out.
# A locally-compiled binary at ~/.local/bin/ has been observed to work
# under launchd where the GitHub-released one did not.
exec "/Users/dorseyhomeserver/.local/bin/go2rtc-fox-cam" \
    -config "$LIVE_CONFIG"
