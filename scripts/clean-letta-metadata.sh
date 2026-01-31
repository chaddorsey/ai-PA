#!/bin/bash
# Clean macOS metadata files from Letta directory to prevent startup issues
# These files (._* and .DS_Store) are created by macOS but can corrupt Letta's sandbox venv

LETTA_DIR="/Volumes/main-drive/ai-PA/letta"

# Only run if directory exists
if [ -d "$LETTA_DIR" ]; then
    # Remove AppleDouble files (._*)
    find "$LETTA_DIR" -name "._*" -type f -delete 2>/dev/null

    # Remove .DS_Store files
    find "$LETTA_DIR" -name ".DS_Store" -type f -delete 2>/dev/null

    echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleaned macOS metadata from $LETTA_DIR"
fi
