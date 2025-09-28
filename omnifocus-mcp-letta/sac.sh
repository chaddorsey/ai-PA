#!/bin/bash

# Ensure a commit message is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <commit-message>"
    exit 1
fi

# Commit message
COMMIT_MSG="$1"

# Hardcoded file paths (with correct escaping for spaces)
SRC1="/Users/chaddorsey/Library/Containers/com.omnigroup.OmniFocus4/Data/Library/Application Support/Plug-Ins/omnifocus-mcp.omnijs"
SRC2="/Users/chaddorsey/Library/Application Support/Claude/claude_desktop_config.json"
DEST1="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge/extra-files/omnifocus-mcp.omnijs"
DEST2="/Users/chaddorsey/Dropbox/dev/MCP/omnifocus-mcp-bridge/extra-files/claude_desktop_config.json"

# Copy files
echo "Copying operational files to commit folder $DEST..."
cp "$SRC1" "$DEST1" || { echo "File copy failed"; exit 1; }
cp "$SRC2" "$DEST2" || { echo "File copy failed"; exit 1; }

# Change to repo root (assumes script is somewhere within the repo)
cd "$(git rev-parse --show-toplevel)" || { echo "Not inside a git repository"; exit 1; }

# Git add all
echo "Adding files to Git..."
git add . || { echo "Git add failed"; exit 1; }

# Git commit
echo "Committing changes..."
git commit -m "$COMMIT_MSG" || { echo "Git commit failed"; exit 1; }

echo "✅ Sync and commit complete."

