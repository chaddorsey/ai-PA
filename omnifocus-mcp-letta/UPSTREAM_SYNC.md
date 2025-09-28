# Upstream Sync Workflow for OmniFocus MCP Server

This document explains how to sync updates from the original omnifocus-mcp-bridge repository into this integrated version.

## Overview

This repository uses git subtree to maintain a connection to the upstream omnifocus-mcp-bridge repository while allowing for Docker/Letta-specific customizations.

## Sync Process

### 1. Fetch Upstream Changes

```bash
cd /Users/dorseyhomeserver/ai-PA
git subtree pull --prefix=omnifocus-mcp-letta https://github.com/chaddorsey/omnifocus-mcp-letta.git master --squash
```

### 2. Handle Conflicts (if any)

If there are conflicts during the sync:
1. Git will pause and show conflict markers
2. Resolve conflicts manually
3. Continue with: `git add . && git commit`

### 3. Test the Integration

After syncing, always test the Docker build:

```bash
cd /Users/dorseyhomeserver/ai-PA
docker-compose build omnifocus-mcp-server
docker-compose up omnifocus-mcp-server
```

### 4. Commit Changes

```bash
git add .
git commit -m "Sync omnifocus-mcp-letta upstream changes"
```

## Customizations Made for ai-PA Integration

The following files have been customized for Docker integration:

- `Dockerfile` - Added for Docker containerization
- `docker-compose.yml` - Standalone compose file for testing
- `package.json` - Added Express dependencies for HTTP server files
- `/ai-PA/docker-compose.yml` - Integrated into main stack

## Upstream Repository

- **Original**: https://github.com/omnifocus-mcp-bridge/omnifocus-mcp-bridge.git
- **Fork**: https://github.com/chaddorsey/omnifocus-mcp-letta.git

## Notes

- The subtree approach preserves the ability to sync upstream changes while maintaining Docker customizations
- All Docker-specific changes are tracked in the ai-PA repository
- The HTTP bridge server runs on port 8888 by default
- Health checks are configured for the Docker integration
