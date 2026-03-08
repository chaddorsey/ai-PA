# OmniFocus CLI Integration Shift — Rollback Procedure

> If the CLI integration doesn't work as expected, this document covers how to
> fully revert to the MCP-based OmniFocus integration.

## Pre-Rollback: What Changed

| Component | Before (MCP) | After (CLI) |
|---|---|---|
| OmniFocus access | 23 MCP tools auto-registered via `omnifocus-tools` MCP server | 1 Letta tool (`run_omnifocus`) calling `omnifocus-cli` subprocess |
| Agent tool source | MCP server config in `letta_mcp_config.json` | Direct Letta tool registration |
| Docker services | `omnifocus-mcp-server` container (port 8888) + `host-bridge-service.js` (port 8889) | `host-bridge-service.js` (port 8889) only |
| Sync tool | Direct HTTP to bridge (port 8889) | `omnifocus-cli task batch-status` subprocess |
| Container deps | None | `omnifocus-cli` pip-installed in Letta container |

## Branch Info

- **Integration branch:** `feature/omnifocus-cli-integration`
- **Pre-merge commit (main):** `7398db1`
- **To revert everything:** `git checkout main` — the branch was never merged

## Step-by-Step Rollback

### 1. Git Revert

If the branch was **not yet merged** to main:
```bash
# Nothing to do — main is untouched
git checkout main
```

If the branch **was merged** to main:
```bash
# Find the merge commit
git log --oneline --merges -5

# Revert the merge commit (keep main's side)
git revert -m 1 <merge-commit-sha>
```

Or hard reset to pre-merge state:
```bash
git reset --hard 7398db1  # Pre-merge commit on main
```

### 2. Restore MCP Config

If git revert handled it, skip this. Otherwise, ensure `letta/letta_mcp_config.json` contains:

```json
"omnifocus-tools": {
  "command": "http",
  "args": ["http://host.docker.internal:8888/mcp"],
  "env": {
    "MCP_SERVER_NAME": "omnifocus-tools",
    "MCP_SERVER_VERSION": "1.0.0",
    "MCP_TRANSPORT": "streamable-http"
  },
  "disabled": false
}
```

### 3. Restore Docker Service

Ensure `docker-compose.yml` contains the `omnifocus-mcp-server` service:

```yaml
  omnifocus-mcp-server:
    build:
      context: ./omnifocus-mcp-letta
      dockerfile: Dockerfile
    container_name: omnifocus-mcp-server
    restart: unless-stopped
    networks: [pa-internal]
    ports:
      - "8888:8888"
    volumes:
      - ./omnifocus-mcp-letta/extra-files:/app/extra-files:ro
    environment:
      - MCP_SERVER_NAME=omnifocus-tools
      - MCP_SERVER_VERSION=1.0.0
      - MCP_SERVER_DESCRIPTION=OmniFocus integration tools via AppleScript
      - MCP_SERVER_HOST=0.0.0.0
      - MCP_SERVER_PORT=8888
      - NODE_ENV=production
      - PORT=8888
      - HOST_BRIDGE_URL=http://host.docker.internal:8889
    healthcheck:
      test: ["CMD", "node", "-e", "require('http').get('http://localhost:8888/health', (res) => process.exit(res.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
        labels: "service,component,network"
    labels:
      - "service=omnifocus-mcp-server"
      - "component=mcp-server"
      - "network=pa-internal"
      - "mcp-transport=http"
      - "mcp-version=1.0.0"
```

Also restore in `letta` service `extra_hosts:`:
```yaml
      - "omnifocus-mcp-server:192.168.65.254"
```

### 4. Restore MCP Server Source Files

The MCP server TypeScript files were removed from `omnifocus-mcp-letta/`. To restore:

```bash
# Restore from the commit before cleanup
git checkout 34e89c9 -- omnifocus-mcp-letta/
```

Or from main (if never merged):
```bash
git checkout main -- omnifocus-mcp-letta/
```

### 5. Remove CLI Integration Artifacts

```bash
# Remove new Letta tool and registration script
rm -f letta/omnifocus_tools.py
rm -f letta/register_omnifocus_tools.py

# Remove CLI volume mount from docker-compose.yml letta service
# (remove the line: - ./omnifocus-cli:/app/tools/omnifocus-cli:ro)

# Remove OMNIFOCUS_BRIDGE_URL env var from docker-compose.yml letta service

# Remove pip install from letta/entrypoint-wrapper.sh
# (remove the omnifocus-cli install block)
```

### 6. Restore sync_omnifocus_completions_tool.py

```bash
git checkout main -- letta/sync_omnifocus_completions_tool.py
```

Or from the pre-integration commit:
```bash
git checkout 7398db1 -- letta/sync_omnifocus_completions_tool.py
```

### 7. Remove run_omnifocus Tool from Letta

```bash
# Find and delete the run_omnifocus tool
curl -s "http://localhost:8283/v1/tools/?limit=200" | python3 -c "
import sys, json
tools = json.load(sys.stdin)
for t in tools:
    if t['name'] == 'run_omnifocus':
        print(f\"Deleting {t['id']}\")
        import urllib.request
        req = urllib.request.Request(f\"http://localhost:8283/v1/tools/{t['id']}\", method='DELETE')
        urllib.request.urlopen(req)
        print('Deleted')
"
```

### 8. Rebuild and Restart Services

```bash
# Rebuild MCP server
docker-compose up -d --build omnifocus-mcp-server

# Restart Letta (picks up restored MCP config)
docker-compose restart letta

# Verify MCP server health
curl http://localhost:8888/health

# Verify MCP tools re-registered
curl -s "http://localhost:8283/v1/tools/?limit=200" | python3 -c "
import sys, json
tools = json.load(sys.stdin)
mcp = [t for t in tools if t.get('metadata_',{}).get('mcp',{}).get('server_name') == 'omnifocus-tools']
print(f'{len(mcp)} omnifocus MCP tools restored')
"
```

### 9. Verify Agent Access

MCP tools are attached to agents automatically via the MCP server config in `letta_mcp_config.json` — no per-agent re-attachment needed. Letta discovers tools from registered MCP servers on startup.

The 23 MCP tools that should be restored:

| Tool ID | Name |
|---|---|
| tool-0fa5df4a-... | systemOperations |
| tool-f86e2777-... | analyticsInsights |
| tool-b3775181-... | automationSupport |
| tool-555e163d-... | reviewOperations |
| tool-4776029a-... | taskGroupOperations |
| tool-69685b20-... | transactionOperations |
| tool-39a91a53-... | validationOperations |
| tool-2474c0da-... | tagOperations |
| tool-c3ef8b6e-... | perspectiveOperations |
| tool-c0df50fe-... | bulkInboxProcessing |
| tool-65aedc80-... | inboxOperations |
| tool-aa4a7eac-... | folderNavigation |
| tool-19ebf172-... | folderOperations |
| tool-e151d744-... | projectSettings |
| tool-abcc2537-... | projectOperations |
| tool-806e1926-... | taskHierarchy |
| tool-d62820e6-... | taskQuery |
| tool-7b011577-... | taskOperations |
| tool-6bfa9f39-... | moveTaskToProject |
| tool-ca3812f9-... | tasksHelp |
| tool-2e15d62e-... | listProjects |
| tool-6650c2d0-... | listUncompletedTasks |
| tool-66bce88f-... | markCompleted |

Note: Tool IDs may change if re-registered — the names will match but IDs are generated fresh.

### 10. Test

1. Ask agent: "List my OmniFocus tasks" — should work via MCP tools
2. Check sync tool: trigger `sync_omnifocus_completions` — should use bridge HTTP directly
3. Verify host bridge still running: `curl http://localhost:8889/execute -X POST -H 'Content-Type: application/json' -d '{"command":"listTasks","args":{}}'`

## Quick Rollback (if branch never merged)

If you never merged `feature/omnifocus-cli-integration` to main, rollback is trivial:

```bash
# You're already on main — nothing changed
# Just clean up the worktree
git worktree remove .worktrees/omnifocus-cli-integration

# Optionally delete the branch
git branch -D feature/omnifocus-cli-integration
```

## Partial Rollback: Keep CLI, Restore MCP

If you want to keep the CLI available but also restore MCP tools:

1. Keep `omnifocus-cli/` directory and volume mount
2. Restore MCP config and Docker service (steps 2-4 above)
3. Keep `run_omnifocus` tool registered alongside MCP tools
4. Agents will have both access paths — MCP tools (auto-registered) + CLI tool (manual)
