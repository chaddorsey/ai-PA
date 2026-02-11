#!/bin/bash
# Clean macOS metadata files from entire ai-PA project tree
# These files (._* and .DS_Store) cause backup tar failures and corrupt Letta's sandbox venv
# Runs hourly via launchd agent com.ai-pa.letta-cleanup

PROJECT_DIR="/Volumes/main-drive/ai-PA"

# Only run if directory exists (volume may not be mounted)
if [ -d "$PROJECT_DIR" ]; then
    # Remove AppleDouble files (._*) and .DS_Store from entire project
    count=$(find "$PROJECT_DIR" -name "._*" -type f -delete -print 2>/dev/null | wc -l | tr -d ' ')
    count_ds=$(find "$PROJECT_DIR" -name ".DS_Store" -type f -delete -print 2>/dev/null | wc -l | tr -d ' ')

    echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleaned ${count} ._* and ${count_ds} .DS_Store files from $PROJECT_DIR"
fi
