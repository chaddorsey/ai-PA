#!/bin/bash

# Set working directory to project folder (adjust if needed)
PROJECT_DIR="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge"

# Hardcoded file paths (with correct escaping for spaces)
# Note: Plugin file is now a symbolic link, so no copy needed
DEST2="/Users/chaddorsey/Library/Application Support/Claude/claude_desktop_config.json"
SRC2="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge/extra-files/claude_desktop_config.json"

# Copy Claude config (plugin file is now a symbolic link, so no copy needed)
echo "Copying Claude config to $DEST2..."
echo "ℹ️  Plugin file is now a symbolic link - no copy needed"
cp "$SRC2" "$DEST2" || { echo "File copy failed"; exit 1; }

echo "🔧 Running npm build..."
cd "$PROJECT_DIR" || { echo "❌ Cannot find project directory"; exit 1; }
npm run build || { echo "❌ Build failed"; exit 1; }

# Restart OmniFocus
echo "🔄 Restarting OmniFocus..."
osascript -e 'tell application "OmniFocus" to quit'
sleep 2
open -a "OmniFocus"

# Restart Claude desktop
echo "🔄 Restarting Claude desktop..."
osascript -e 'quit app "Claude"'
sleep 2
open -a "Claude"

echo "✅ Build complete and apps restarted."

