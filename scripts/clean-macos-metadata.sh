#!/bin/bash
# Clean macOS metadata files from mounted directories
# These files can cause issues with Docker containers, especially during cleanup operations
#
# Why these files appear:
# - macOS creates ._* files (resource forks) to store extended attributes
# - This happens especially on external drives (like /Volumes/main-drive)
# - They're created when files are copied, moved, or accessed
# - They can interfere with Docker, Python, and other tools
#
# Prevention:
# - Run scripts/prevent-macos-metadata.sh to configure system-wide prevention
# - Set COPYFILE_DISABLE=1 environment variable
# - Use dot_clean on volumes to remove and prevent creation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Cleaning macOS metadata files from project directories..."
echo "Project root: $PROJECT_ROOT"
echo ""

# Directories that are mounted into Docker containers
MOUNTED_DIRS=(
    "$PROJECT_ROOT/letta"
    "$PROJECT_ROOT/letta/calendar_tools"
    "$PROJECT_ROOT/letta/env"  # Virtual environment (if it exists)
)

# Count files before cleanup
TOTAL_REMOVED=0

for dir in "${MOUNTED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "Cleaning: $dir"
        
        # Remove macOS metadata files
        # ._* files (resource forks)
        METADATA_COUNT=$(find "$dir" -name "._*" -type f | wc -l | tr -d ' ')
        if [ "$METADATA_COUNT" -gt 0 ]; then
            find "$dir" -name "._*" -type f -delete
            echo "  Removed $METADATA_COUNT ._* files"
            TOTAL_REMOVED=$((TOTAL_REMOVED + METADATA_COUNT))
        fi
        
        # .DS_Store files
        DS_COUNT=$(find "$dir" -name ".DS_Store" -type f | wc -l | tr -d ' ')
        if [ "$DS_COUNT" -gt 0 ]; then
            find "$dir" -name ".DS_Store" -type f -delete
            echo "  Removed $DS_COUNT .DS_Store files"
            TOTAL_REMOVED=$((TOTAL_REMOVED + DS_COUNT))
        fi
    else
        echo "Skipping (not found): $dir"
    fi
done

echo ""
echo "✓ Cleanup complete. Removed $TOTAL_REMOVED metadata files total."

# Also clean the .gmail-mcp directory if it exists
GMAIL_DIR="$HOME/.gmail-mcp"
if [ -d "$GMAIL_DIR" ]; then
    echo ""
    echo "Cleaning: $GMAIL_DIR"
    GMAIL_METADATA=$(find "$GMAIL_DIR" -name "._*" -o -name ".DS_Store" | wc -l | tr -d ' ')
    if [ "$GMAIL_METADATA" -gt 0 ]; then
        find "$GMAIL_DIR" \( -name "._*" -o -name ".DS_Store" \) -type f -delete
        echo "  Removed $GMAIL_METADATA metadata files from .gmail-mcp"
        TOTAL_REMOVED=$((TOTAL_REMOVED + GMAIL_METADATA))
    fi
fi

echo ""
echo "Total files removed: $TOTAL_REMOVED"
