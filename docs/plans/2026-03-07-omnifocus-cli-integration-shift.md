# OmniFocus CLI Integration Shift — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the MCP server + 70 auto-registered tools + 10 wrapper Letta tools with a single `run_omnifocus` Letta tool backed by the `omnifocus-cli` Python package, following the established `run_gws` pattern.

**Architecture:** Agent calls `run_omnifocus(command, ...)` → `subprocess.run(["omnifocus-cli", ...])` → `bridge.py` detects Docker → HTTP POST to host bridge (port 8889) → osascript → OmniFocus plugin → JSON result.

**Tech Stack:** Python (Click CLI, Letta tools), Node.js (host bridge), Docker, AppleScript

**Working directories:**
- CLI source: `/Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli/`
- Main repo: `/Volumes/main-drive/ai-PA/`

---

### Task 1: Smoke Test CLI Against Live OmniFocus

Verify the existing CLI commands work against live OmniFocus before building integration.

**Files:**
- Read: `omnifocus-cli/src/omnifocus_cli/cli.py`
- Read: `omnifocus-cli/src/omnifocus_cli/bridge.py`

**Step 1: Run schema discovery commands**

```bash
cd /Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli
python -m omnifocus_cli.cli schema --list
python -m omnifocus_cli.cli schema task.create
python -m omnifocus_cli.cli schema project.list
```

Expected: Schema listing shows all 57 methods, individual schemas show params.

**Step 2: Run read-only commands against live OmniFocus**

```bash
python -m omnifocus_cli.cli task list --format json
python -m omnifocus_cli.cli project list --format json
python -m omnifocus_cli.cli folder list --format json
python -m omnifocus_cli.cli tag list --format json
python -m omnifocus_cli.cli inbox list --format json
```

Expected: JSON output with real OmniFocus data. Verify each returns valid JSON with `status` field.

**Step 3: Test dry-run for write operations**

```bash
python -m omnifocus_cli.cli task create --body '{"name":"CLI smoke test"}' --dry-run
python -m omnifocus_cli.cli task update --body '{"taskId":"fake-id","name":"test"}' --dry-run
```

Expected: Dry-run output showing what would be sent, no actual changes.

**Step 4: Test field filtering**

```bash
python -m omnifocus_cli.cli task list --fields "id,name,flagged" --format json
```

Expected: Output with only specified fields.

**Step 5: Commit smoke test results (note-only)**

No code changes — just verify. If anything fails, fix before proceeding.

---

### Task 2: Make bridge.py Docker-Aware

Add HTTP fallback transport to `bridge.py` so CLI works inside Docker containers where osascript isn't available.

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/bridge.py`
- Create: `omnifocus-cli/tests/test_bridge_docker.py`

**Step 1: Write the failing test**

```python
# tests/test_bridge_docker.py
import json
from unittest.mock import patch, MagicMock
from omnifocus_cli.bridge import call_omnifocus


def test_bridge_uses_http_when_osascript_unavailable():
    """When osascript is not available, bridge should HTTP POST to OMNIFOCUS_BRIDGE_URL."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "success": True,
        "result": json.dumps({"result": {"id": "t-123", "name": "Test"}})
    }).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("shutil.which", return_value=None), \
         patch.dict("os.environ", {"OMNIFOCUS_BRIDGE_URL": "http://localhost:8889"}), \
         patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        result = call_omnifocus("getTask", {"taskId": "t-123"})

    # Verify HTTP was used
    mock_urlopen.assert_called_once()
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    body = json.loads(req.data.decode("utf-8"))
    assert body["command"] == "getTask"
    assert body["args"]["taskId"] == "t-123"
    assert result == {"id": "t-123", "name": "Test"}


def test_bridge_uses_osascript_when_available():
    """When osascript is available, bridge should use it directly."""
    with patch("shutil.which", return_value="/usr/bin/osascript"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"result": {"id": "t-123"}}),
            stderr="",
        )
        result = call_omnifocus("getTask", {"taskId": "t-123"})

    mock_run.assert_called_once()
    assert result == {"id": "t-123"}
```

**Step 2: Run test to verify it fails**

```bash
cd /Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli
python -m pytest tests/test_bridge_docker.py -v
```

Expected: FAIL — `call_omnifocus` doesn't check for osascript availability.

**Step 3: Implement Docker-aware transport in bridge.py**

Modify `call_omnifocus()` in `omnifocus-cli/src/omnifocus_cli/bridge.py`:

```python
import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path


def build_payload(method: str, params: dict | None = None) -> str:
    """Build the JSON payload for the OmniFocus plugin."""
    return json.dumps({"method": method, "params": params or {}})


def build_applescript(method: str, params: dict | None = None) -> str:
    """Build the AppleScript that calls the OmniFocus plugin via base64-encoded JSON."""
    payload = build_payload(method, params)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"""tell application "OmniFocus"
  set _res to evaluate javascript "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='{b64}',r='';for(var i=0;i<s.length;){{var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}}var p=PlugIn.find('omnifocus-mcp');if(!p)throw new Error('Plugin not found');var lib=p.library('omnifocus-mcp');JSON.stringify(lib.request(r))"
end tell
return _res
"""


def _call_via_http(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via HTTP bridge (Docker transport)."""
    bridge_url = os.environ.get("OMNIFOCUS_BRIDGE_URL", "http://host.docker.internal:8889")
    payload = json.dumps({
        "command": method,
        "args": params or {},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{bridge_url}/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if not result.get("success"):
        raise RuntimeError(f"Bridge error: {result.get('error', 'unknown')}")

    raw = result.get("result", {})
    if isinstance(raw, str):
        parsed = json.loads(raw)
        return parsed.get("result", parsed)
    if isinstance(raw, dict):
        return raw.get("result", raw)
    return raw


def _call_via_osascript(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via osascript (native macOS transport)."""
    script = build_applescript(method, params)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False) as f:
        f.write(script)
        script_path = Path(f.name)
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", str(script_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"osascript failed (exit {result.returncode}): {result.stderr.strip()}")
        raw = result.stdout.strip()
        parsed = json.loads(raw)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, dict) and "error" in parsed:
            raise RuntimeError(f"OmniFocus plugin error: {parsed['error']}")
        if isinstance(parsed, dict):
            return parsed.get("result", parsed)
        return parsed
    finally:
        script_path.unlink(missing_ok=True)


def call_omnifocus(method: str, params: dict | None = None) -> dict:
    """Call OmniFocus via osascript (native) or HTTP bridge (Docker)."""
    if shutil.which("osascript"):
        return _call_via_osascript(method, params)
    return _call_via_http(method, params)
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_bridge_docker.py -v
python -m pytest tests/ -v  # Run all existing tests too
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/omnifocus_cli/bridge.py tests/test_bridge_docker.py
git commit -m "feat: add Docker-aware HTTP transport to bridge.py"
```

---

### Task 3: Add `task batch-status` CLI Command

Add a batch status check command used by the sync tool.

**Files:**
- Modify: `omnifocus-cli/src/omnifocus_cli/schema.py` (add schema entry)
- Modify: `omnifocus-cli/src/omnifocus_cli/cli.py` (add command)
- Create: `omnifocus-cli/tests/test_batch_status.py`

**Step 1: Write the failing test**

```python
# tests/test_batch_status.py
from click.testing import CliRunner
from omnifocus_cli.cli import cli
from omnifocus_cli.schema import get_schema


def test_batch_status_schema_exists():
    """Schema registry should have task.batch-status entry."""
    schema = get_schema("task.batch-status")
    assert schema is not None
    assert schema["method"] == "checkTaskCompletionStatus"
    assert "taskIds" in schema["params"]


def test_batch_status_dry_run():
    """Dry run should show the bridge payload without executing."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "batch-status",
        "--body", '{"taskIds": ["t-1", "t-2"]}',
        "--dry-run",
    ])
    assert result.exit_code == 0
    assert "checkTaskCompletionStatus" in result.output
    assert "t-1" in result.output
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_batch_status.py -v
```

Expected: FAIL — schema and command don't exist yet.

**Step 3: Add schema entry**

Add to `SCHEMAS` dict in `schema.py`:

```python
"task.batch-status": {
    "method": "checkTaskCompletionStatus",
    "description": "Batch check completion/dropped status of multiple tasks",
    "params": {
        "taskIds": {"type": "array[string]", "required": True, "description": "List of OmniFocus task IDs to check"},
    },
},
```

**Step 4: Add CLI command**

The existing `_run()` helper in `cli.py` handles routing for all commands. Add `batch-status` as a subcommand under the `task` group, following the same pattern as other task subcommands. The `_run("task", "batch-status", ...)` call maps to schema key `task.batch-status`.

```python
@task.command("batch-status")
@click.pass_context
def task_batch_status(ctx):
    """Batch check completion status of multiple tasks."""
    _run(ctx, "task", "batch-status")
```

**Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_batch_status.py -v
python -m pytest tests/ -v
```

Expected: All pass.

**Step 6: Commit**

```bash
git add src/omnifocus_cli/schema.py src/omnifocus_cli/cli.py tests/test_batch_status.py
git commit -m "feat: add task batch-status CLI command"
```

---

### Task 4: Create `run_omnifocus` Letta Tool

Single Letta tool mirroring `run_gws` pattern. This goes in the **main repo**, not the CLI worktree.

**Files:**
- Create: `letta/omnifocus_tools.py`

**Step 1: Write the Letta tool**

Reference: `letta/gmail_tools.py:21-104` (`run_gws` pattern)

```python
# letta/omnifocus_tools.py
from typing import Dict, Any, Optional


def run_omnifocus(command: str, params: Optional[str] = None, fields: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any OmniFocus CLI command. Provides full task, project, folder,
    tag, inbox, perspective, review, search, analytics, and transaction management.

    Commands follow the pattern: <group> <action>
    Use "schema --list" to see all available commands.
    Use "schema <group.action>" to see parameters for a specific command.

    Task examples:
      command="task list"
      command="task create", params='{"name":"Buy groceries","flagged":true}'
      command="task get", params='{"taskId":"TASK_ID"}'
      command="task update", params='{"taskId":"TASK_ID","flagged":false}'
      command="task complete", params='{"taskId":"TASK_ID"}'
      command="task batch-status", params='{"taskIds":["t-1","t-2"]}'

    Project examples:
      command="project list"
      command="project create", params='{"name":"Q2 Planning","folderId":"FOLDER_ID"}'
      command="project get", params='{"projectId":"PROJECT_ID"}'

    Search examples:
      command="search query", params='{"text":"meeting notes","limit":10}'
      command="search flagged"
      command="search due-soon", params='{"days":3}'

    Other groups: folder, tag, inbox, perspective, review, analytics, transaction

    Schema discovery:
      command="schema --list"
      command="schema task.create"
      command="schema project.list"

    Args:
        command: The omnifocus-cli subcommand (e.g. "task list" or "schema task.create")
        params: JSON string of parameters (optional). Passed as --body to omnifocus-cli.
        fields: Comma-separated output fields to return (optional). Limits token usage.
        timeout: Command timeout in seconds (default 30)

    Returns:
        Dictionary with status and the parsed JSON response.
    """
    import json
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        cmd_parts = ["omnifocus-cli"] + command.strip().split()

        if params:
            cmd_parts.extend(["--body", params])
        if fields:
            cmd_parts.extend(["--fields", fields])

        # Add --format json unless this is a schema command
        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word != "schema":
            cmd_parts.extend(["--format", "json"])

        r = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            return {"status": "error", "error_message": r.stderr[:1000] if r.stderr else f"Exit code {r.returncode}"}

        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 2: Verify Letta tool compliance**

Check against Letta tool requirements:
- [x] All imports inside function body
- [x] No nested `def` statements
- [x] Parameters use basic JSON types (`str`, `int`, `Optional[str]`)
- [x] All parameters documented in `Args:` section
- [x] Entire body wrapped in try-except
- [x] Returns `Dict[str, Any]`

**Step 3: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/omnifocus_tools.py
git commit -m "feat: add run_omnifocus Letta tool (mirrors run_gws pattern)"
```

---

### Task 5: Create Registration Script

Registration script following `register_gmail_tools.py` pattern.

**Files:**
- Create: `letta/register_omnifocus_tools.py`

**Step 1: Write registration script**

Reference: `letta/register_gmail_tools.py`

```python
#!/usr/bin/env python3
"""Register OmniFocus CLI tool with Letta.

Registers a single general-purpose tool that provides full OmniFocus access:
  - run_omnifocus: CLI-backed tool for all OmniFocus operations

Usage:
    LETTA_BASE_URL=http://localhost:8283 python register_omnifocus_tools.py

Requirements:
    - Letta server running at http://localhost:8283
    - omnifocus-cli installed in Letta container (via entrypoint-wrapper.sh)
"""

import os
import sys
from letta_client import Letta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from omnifocus_tools import run_omnifocus

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register_tools():
    """Register OmniFocus tool with Letta."""
    client = Letta(base_url=LETTA_BASE_URL)

    tools = [
        (run_omnifocus, ["omnifocus", "tasks", "projects", "productivity"]),
    ]

    registered = []
    for func, tags in tools:
        try:
            tool = client.tools.create_from_function(
                func=func,
                tags=tags,
            )
            registered.append(tool.name)
            print(f"Registered: {tool.name}")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"Already exists: {func.__name__}")
                registered.append(func.__name__)
            else:
                print(f"Failed to register {func.__name__}: {e}")

    print(f"\nRegistered {len(registered)} tools")
    return registered


if __name__ == "__main__":
    register_tools()
```

**Step 2: Commit**

```bash
git add letta/register_omnifocus_tools.py
git commit -m "feat: add OmniFocus tool registration script"
```

---

### Task 6: Container Setup — Mount CLI + Install + Env Var

Configure Docker to make omnifocus-cli available inside the Letta container.

**Files:**
- Modify: `docker-compose.yml` (letta service volumes + environment)
- Modify: `letta/entrypoint-wrapper.sh` (pip install)

**Step 1: Add volume mount to docker-compose.yml**

In the `letta` service `volumes:` section (around line 604-608), add:

```yaml
      - ./omnifocus-cli:/app/tools/omnifocus-cli:ro  # OmniFocus CLI source for pip install
```

Note: The `omnifocus-cli/` directory will need to exist in the main repo root. Currently it's in a worktree — the branch merge will bring it in, or we symlink/copy.

**Step 2: Add environment variable**

In the `letta` service `environment:` section, add:

```yaml
      OMNIFOCUS_BRIDGE_URL: "http://host.docker.internal:8889"
```

**Step 3: Add pip install to entrypoint-wrapper.sh**

After the pytz install line (line 12), add:

```bash
# Install omnifocus-cli for OmniFocus task management
if [ -d "/app/tools/omnifocus-cli" ]; then
    echo "[entrypoint-wrapper] Installing omnifocus-cli..."
    python3 -m pip install --quiet --no-warn-script-location \
        /app/tools/omnifocus-cli/ \
        2>&1 | tail -3
fi
```

**Step 4: Commit**

```bash
git add docker-compose.yml letta/entrypoint-wrapper.sh
git commit -m "feat: mount omnifocus-cli in Letta container with pip install"
```

---

### Task 7: Refactor sync_omnifocus_completions to Use CLI

Replace direct bridge HTTP calls with CLI subprocess in the sync tool.

**Files:**
- Modify: `letta/sync_omnifocus_completions_tool.py` (lines 114-144)

**Step 1: Identify the change**

Current code (lines 114-144) does a direct HTTP POST to `BRIDGE_URL/execute` with `checkTaskCompletionStatus`. Replace with:

```python
        # ── Step 3: Batch-check OmniFocus completion status ──
        batch_body = json.dumps({"taskIds": list(task_map.keys())})
        cli_result = subprocess.run(
            ["omnifocus-cli", "task", "batch-status", "--body", batch_body, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if cli_result.returncode != 0:
            return {
                "status": "error",
                "checked": len(task_map), "completed": 0, "dropped": 0, "not_found": 0,
                "details": [],
                "error_message": f"CLI batch-status failed: {cli_result.stderr.strip() or cli_result.stdout.strip()}",
            }
        completion_statuses = json.loads(cli_result.stdout)
```

**Step 2: Add subprocess import**

Add `import subprocess` to the imports section inside the function (line 39 area). It's not currently imported.

**Step 3: Remove unused bridge imports/variables**

Remove `BRIDGE_URL` variable (line 49) and `urllib.request`/`urllib.error` imports (lines 43-44) — but only if no other code in the function uses them. Check: lines 58-60 use `urllib.request` for Letta API calls, so keep those imports. Only remove `BRIDGE_URL`.

**Step 4: Run existing tests**

```bash
cd /Volumes/main-drive/ai-PA
python -m pytest letta/ -v -k sync 2>/dev/null || echo "No existing sync tests"
```

**Step 5: Commit**

```bash
git add letta/sync_omnifocus_completions_tool.py
git commit -m "refactor: sync tool uses omnifocus-cli instead of direct bridge HTTP"
```

---

### Task 8: End-to-End Integration Test

Test the full chain: register tool → CLI → bridge → OmniFocus.

**Step 1: Rebuild Letta container with new mounts**

```bash
cd /Volumes/main-drive/ai-PA
docker-compose up -d --build letta
docker-compose logs -f letta 2>&1 | head -30
```

Expected: Logs show omnifocus-cli being installed.

**Step 2: Verify CLI is available inside container**

```bash
docker exec ai-pa-letta-1 omnifocus-cli schema --list
```

Expected: Schema listing output.

**Step 3: Register the tool**

```bash
LETTA_BASE_URL=http://localhost:8283 python letta/register_omnifocus_tools.py
```

Expected: `Registered: run_omnifocus`

**Step 4: Test tool via Letta agent**

Attach tool to agent and send a test message:

```bash
# List agent's tools to verify attachment
curl -s http://localhost:8283/v1/tools?limit=50 | python3 -c "import sys,json; [print(t['name']) for t in json.load(sys.stdin) if 'omnifocus' in t.get('name','').lower()]"
```

**Step 5: Test schema discovery through agent**

Send agent message: "Run omnifocus-cli schema --list to see what OmniFocus commands are available"

Expected: Agent calls `run_omnifocus(command="schema --list")` and gets back the full method listing.

**Step 6: Test a read operation**

Send agent message: "List my OmniFocus tasks"

Expected: Agent calls `run_omnifocus(command="task list")` and returns task data.

---

### Task 9: Decommission MCP Server — Remove Config

Remove the OmniFocus MCP server from Letta's MCP config.

**Files:**
- Modify: `letta/letta_mcp_config.json` (remove `omnifocus-tools` entry)

**Step 1: Remove MCP config entry**

Remove the `"omnifocus-tools"` block from `letta/letta_mcp_config.json` (around lines 49-57).

**Step 2: Commit**

```bash
git add letta/letta_mcp_config.json
git commit -m "chore: remove omnifocus-tools MCP config (replaced by CLI tool)"
```

---

### Task 10: Decommission MCP Server — Remove Docker Service

Remove the `omnifocus-mcp-server` service from Docker Compose.

**Files:**
- Modify: `docker-compose.yml` (remove `omnifocus-mcp-server` service, lines 941-980)

**Step 1: Remove the service block**

Delete the entire `omnifocus-mcp-server:` block (lines 941-980) from `docker-compose.yml`.

**Step 2: Remove extra_hosts reference**

In the `letta` service, remove line 645:
```yaml
      - "omnifocus-mcp-server:192.168.65.254"
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: remove omnifocus-mcp-server Docker service"
```

---

### Task 11: Decommission MCP Registration Script

Remove the old MCP tool registration script.

**Files:**
- Delete: `letta/register_omnifocus_mcp_tools.py`

**Step 1: Delete the file**

```bash
git rm letta/register_omnifocus_mcp_tools.py
```

**Step 2: Check for references**

```bash
grep -r "register_omnifocus_mcp" /Volumes/main-drive/ai-PA/ --include="*.py" --include="*.sh" --include="*.md" -l
```

Update any documentation or scripts that reference it.

**Step 3: Commit**

```bash
git commit -m "chore: remove old MCP tool registration script"
```

---

### Task 12: Decommission Old Wrapper Letta Tools

Remove the 10 wrapper tools from the CLI package (they're replaced by `run_omnifocus`).

**Files:**
- Delete: `omnifocus-cli/letta_tools/omnifocus_task.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_search.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_project.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_folder.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_inbox.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_tags.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_perspective.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_review.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_analytics.py`
- Delete: `omnifocus-cli/letta_tools/omnifocus_transaction.py`
- Delete: `omnifocus-cli/letta_tools/__init__.py` (if exists)

**Step 1: Delete all wrapper tools**

```bash
cd /Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli
git rm -r letta_tools/
```

**Step 2: Check for references**

```bash
grep -r "letta_tools" . --include="*.py" --include="*.toml" -l
```

Remove any `pyproject.toml` references or imports.

**Step 3: Commit**

```bash
git commit -m "chore: remove wrapper Letta tools (replaced by single run_omnifocus)"
```

---

### Task 13: Clean Up MCP Server Source (Optional)

The MCP server TypeScript source can be archived or deleted. The host bridge service stays.

**Files:**
- Consider: `omnifocus-mcp-letta/server-mcp-simplified.ts` and related TS files
- Consider: `omnifocus-mcp-letta/bridge.ts`
- Keep: `omnifocus-mcp-letta/host-bridge-service.js` (still needed)

**Step 1: Assess what to remove**

The `omnifocus-mcp-letta/` directory contains:
- `host-bridge-service.js` — KEEP (port 8889, osascript executor)
- `server-mcp-simplified.ts` — DELETE (MCP server, replaced)
- `bridge.ts` — DELETE (TS bridge layer, replaced)
- `Dockerfile` — DELETE (MCP server container, replaced)
- Other TS/build files — DELETE

**Step 2: Remove MCP server files, keep host bridge**

```bash
cd /Volumes/main-drive/ai-PA/omnifocus-mcp-letta
# Keep only host-bridge-service.js and its dependencies
git rm server-mcp-simplified.ts bridge.ts Dockerfile tsconfig.json
# Keep package.json if host-bridge-service.js needs it, otherwise slim it down
```

**Step 3: Commit**

```bash
git commit -m "chore: remove MCP server TS files (host bridge service stays)"
```

---

### Task 14: Detach Old MCP Tools from Agent

Remove the ~70 auto-registered MCP tools from the agent's tool list.

**Step 1: List current MCP tools on agent**

```bash
curl -s "http://localhost:8283/v1/tools?limit=100" | python3 -c "
import sys, json
tools = json.load(sys.stdin)
mcp_tools = [t for t in tools if t.get('metadata_', {}).get('mcp', {}).get('server_name') == 'omnifocus-tools']
print(f'{len(mcp_tools)} omnifocus MCP tools found')
for t in mcp_tools:
    print(f\"  {t['id']}: {t['name']}\")
"
```

**Step 2: Detach MCP tools from agent**

For each agent that has these tools attached, remove them via the API. The exact agent IDs will be determined at runtime.

**Step 3: Delete orphaned MCP tool objects**

```bash
# Delete each MCP tool object from Letta
# (specific IDs from Step 1)
```

**Step 4: Verify only run_omnifocus remains**

```bash
curl -s "http://localhost:8283/v1/tools?limit=100" | python3 -c "
import sys, json
tools = json.load(sys.stdin)
of_tools = [t for t in tools if 'omnifocus' in t.get('name', '').lower()]
for t in of_tools:
    print(f\"{t['name']}: {t['id']}\")
"
```

Expected: Only `run_omnifocus` appears.

---

### Task 15: Final Verification

End-to-end verification that the new system works and the old system is fully removed.

**Step 1: Verify no MCP server running**

```bash
docker ps | grep omnifocus-mcp
curl http://localhost:8888/health 2>/dev/null && echo "FAIL: MCP server still running" || echo "OK: MCP server stopped"
```

**Step 2: Verify host bridge still running**

```bash
curl http://localhost:8889/health 2>/dev/null || echo "Host bridge health check (may not have /health endpoint)"
# Test with a simple command
curl -X POST http://localhost:8889/execute -H 'Content-Type: application/json' -d '{"command":"listTasks","args":{}}' | head -c 200
```

**Step 3: Verify CLI works inside container**

```bash
docker exec ai-pa-letta-1 omnifocus-cli task list --format json | head -c 500
```

**Step 4: Verify agent can use run_omnifocus**

Send test messages through the agent:
1. "What OmniFocus commands are available?" (tests schema discovery)
2. "List my flagged OmniFocus tasks" (tests search flagged)
3. "Create an OmniFocus task called 'Integration test' with dry-run" (tests dry-run)

**Step 5: Verify sync tool works**

```bash
# Trigger sync manually via scheduler or direct tool call
curl -X POST http://localhost:8283/v1/agents/agent-62edcfac-2cc7-41a5-a3c2-d417da393397/messages \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Run sync_omnifocus_completions"}]}'
```

**Step 6: Document completion**

Update design doc with final status. No new features — just verification.
