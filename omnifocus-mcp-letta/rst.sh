#!/bin/bash

# Resolve project directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}" && pwd)"
REPO_ROOT="$(cd "${PROJECT_DIR}/.." && pwd)"

# Source and destination for Claude desktop config (optional)
SRC2="${REPO_ROOT}/extra-files/claude_desktop_config.json"
DEST2="${HOME}/Library/Application Support/Claude/claude_desktop_config.json"

# Copy Claude config if available
if [[ -f "$SRC2" ]]; then
  echo "Copying Claude config to $DEST2..."
  mkdir -p "$(dirname "$DEST2")"
  cp "$SRC2" "$DEST2" || { echo "File copy failed"; exit 1; }
else
  echo "⚠️  Claude config not found at $SRC2; skipping copy."
fi

# Build TypeScript output
echo "🔧 Running npm build..."
cd "$PROJECT_DIR" || { echo "❌ Cannot find project directory"; exit 1; }
npm run build || { echo "❌ Build failed"; exit 1; }

# Restart OmniFocus
echo "🔄 Restarting OmniFocus..."
osascript -e 'tell application "OmniFocus" to quit'
sleep 2
open -a "OmniFocus"

# Restart Claude desktop (optional helper for local setup)
echo "🔄 Restarting Claude desktop..."
osascript -e 'quit app "Claude"' >/dev/null 2>&1 || true
sleep 2
open -a "Claude" >/dev/null 2>&1 || true

echo "✅ Build complete and apps restarted."

