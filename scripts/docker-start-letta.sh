#!/bin/bash
# Start Letta container with macOS metadata cleanup
# This ensures metadata files are cleaned before starting

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Starting Letta container with metadata cleanup..."
echo ""

# Clean metadata files first
if [ -f "$SCRIPT_DIR/clean-macos-metadata.sh" ]; then
    echo "Cleaning macOS metadata files..."
    bash "$SCRIPT_DIR/clean-macos-metadata.sh"
    echo ""
fi

# Start the container
cd "$PROJECT_ROOT"
echo "Starting Letta container..."
docker-compose up -d letta

echo ""
echo "✓ Letta container started"
echo "Monitor logs with: docker logs -f ai-pa-letta-1"
