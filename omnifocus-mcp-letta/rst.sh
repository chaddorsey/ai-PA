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

# Copy OmniFocus plugin
PLUGIN_SRC="$PROJECT_DIR/extra-files/omnifocus-mcp.omnijs"
PLUGIN_DEST="$HOME/Library/Application Support/OmniFocus/Plug-Ins/omnifocus-mcp.omnijs"

if [[ -f "$PLUGIN_SRC" ]]; then
  echo "📦 Installing OmniFocus plugin to $PLUGIN_DEST..."
  mkdir -p "$(dirname "$PLUGIN_DEST")"
  cp "$PLUGIN_SRC" "$PLUGIN_DEST" || { echo "❌ Failed to copy plugin"; exit 1; }
else
  echo "⚠️  Plugin source not found at $PLUGIN_SRC; skipping copy."
fi

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

# Restart simplified MCP server (ensure fresh process after plugin rebuild)
echo "🛑 Killing any running simplified server..."
pkill -f "server-mcp-simplified" >/dev/null 2>&1 || true

echo "🚀 Relaunching simplified server..."
cd "$PROJECT_DIR" || { echo "❌ Cannot find project directory for server start"; exit 1; }
nohup npm run start:simplified > "$PROJECT_DIR/server.log" 2>&1 &
echo "ℹ️  Simplified server restarting in background (log: $PROJECT_DIR/server.log)"

echo "✅ Build complete and apps restarted."

