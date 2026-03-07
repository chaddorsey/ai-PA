# OmniFocus CLI Integration Shift — Design

## Goal

Replace the MCP server + 70 auto-registered tools with a single `run_omnifocus` Letta tool backed by the `omnifocus-cli` Python package, following the established `run_gws` pattern.

## Architecture

```
Agent (Letta, Docker)
  → run_omnifocus(command, params, fields, dry_run, timeout)
    → subprocess.run(["omnifocus-cli", ...])
      → bridge.py detects Docker → HTTP POST to host bridge
        → host-bridge-service.js (Node.js, port 8889, existing)
          → osascript → OmniFocus plugin (omnifocus-mcp.omnijs)
        → returns JSON
      → CLI applies validation, field masking, formatting
    → returns {"status": "ok", "result": {...}}
```

## Components

### 1. CLI bridge.py — Docker-aware transport

`call_omnifocus()` currently runs `/usr/bin/osascript` directly. Add detection: if `osascript` isn't available (Docker), HTTP POST to `OMNIFOCUS_BRIDGE_URL` (default `http://host.docker.internal:8889`). Payload is `{"command": "<method>", "args": {"method": "...", "params": {...}}}` — what the host bridge already expects. All CLI logic (schema validation, dry-run, field masking) stays above the transport layer.

### 2. New CLI command: task batch-status

Schema entry `task.batch-status`, method `checkTaskCompletionStatus`. Takes `{"taskIds": ["t-1", "t-2", ...]}`, returns completion/dropped/not-found per task. Used by sync tool and available to agents.

### 3. Letta tool: run_omnifocus

Single tool, ~40 lines, mirrors `run_gws`:

```python
def run_omnifocus(command: str, params: Optional[str] = None,
                  fields: Optional[str] = None, dry_run: bool = False,
                  timeout: int = 30) -> Dict[str, Any]:
```

Docstring includes examples and schema discovery instructions. Registered with tags `["omnifocus", "tasks", "projects"]`.

### 4. Container setup

- Mount `omnifocus-cli/` source into Letta Docker container
- `pip install /app/tools/omnifocus-cli/` in `entrypoint-wrapper.sh`
- Env var: `OMNIFOCUS_BRIDGE_URL=http://host.docker.internal:8889`

### 5. Sync tool refactor

`sync_omnifocus_completions_tool.py` switches from direct bridge HTTP calls to `subprocess.run(["omnifocus-cli", "task", "batch-status", "--body", ...])`.

### 6. Decommission

Remove after migration verified:
- MCP server (`omnifocus-mcp-letta/server-mcp-simplified.ts`)
- MCP config entry in `letta_mcp_config.json`
- MCP registration script (`register_omnifocus_mcp_tools.py`)
- 10 wrapper Letta tools (replaced by single `run_omnifocus`)
- Bridge TypeScript layer (`bridge.ts`)

### What stays unchanged

- `omnifocus-mcp.omnijs` plugin (foundation)
- `host-bridge-service.js` (existing osascript executor, port 8889)
- `retrieve_task_info_tool.py`, `task_lifecycle_tools.py`, `prepare_completion_feedback_tool.py` (Letta-only, no OF dependency)
- `omnifocus_sync_service.py` (inherits sync tool changes)

## Testing strategy

1. Smoke test new CLI commands against live OmniFocus (integration tests)
2. Verify bridge.py Docker transport against host bridge
3. Register `run_omnifocus`, attach to agent, test schema discovery + task creation
4. Run sync tool end-to-end
5. Verify all existing functionality before decommissioning MCP
