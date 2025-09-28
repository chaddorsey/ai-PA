#!/bin/bash

# Set working directory to project folder (adjust if needed)
PROJECT_DIR="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge"

# Hardcoded file paths (with correct escaping for spaces)
DEST1="/Users/chaddorsey/Library/Containers/com.omnigroup.OmniFocus4/Data/Library/Application Support/Plug-Ins/omnifocus-mcp.omnijs"
DEST2="/Users/chaddorsey/Library/Application Support/Claude/claude_desktop_config.json"
SRC1="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge/extra-files/omnifocus-mcp.omnijs"
SRC2="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge/extra-files/claude_desktop_config.json"

# Copy files
echo "Copying files to $DEST1 and $DEST2..."
cp "$SRC1" "$DEST1" || { echo "File copy failed"; exit 1; }
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

