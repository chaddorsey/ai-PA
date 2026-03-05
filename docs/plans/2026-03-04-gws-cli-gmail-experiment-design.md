# Design: Replace Gmail API Tools with Google Workspace CLI (`gws`)

**Date:** 2026-03-04
**Status:** Experiment — proof-of-concept for `search_emails` only
**Scope:** Validate `gws` CLI as Gmail backend; no disruption to existing tools

---

## Context

### Current State

Gmail access in the PA ecosystem uses **direct Google API calls** from Python Letta tools (`letta/gmail_tools.py`). The old `gmail-mcp-server` (Node.js) was decommissioned Feb 2026.

**Current Gmail touchpoints:**

| Layer | Component | Gmail Methods | Files |
|-------|-----------|---------------|-------|
| Core tools | 9 Letta tools | list, get, send, draft, modify, labels, attachments | `letta/gmail_tools.py` |
| Meeting followup | `prepare_meeting_followup` | drafts.create, messages.modify | `letta/meeting_followup_tool.py` |
| Email task queue | `process_email_task_queue` | messages.list, get, modify | `letta/email_task_queue_tool.py` |
| Draft reply | `draft_reply_to_email` | messages.get, drafts.create | `letta/draft_reply_to_email_tool.py` |
| Watch service | gmail-watch-service | users.watch, getHistory, labels | `gmail-watch-service/` |
| Watch tools | 4 Letta tools | HTTP calls to watch service | `letta/gmail_watch_tools.py` |

**Pain points with current approach:**
- Every tool duplicates ~30 lines of OAuth boilerplate (load keys, load tokens, build Credentials, refresh, persist, build service)
- Token refresh logic duplicated across 5+ files
- `googleapiclient` pagination handled manually per tool
- No built-in retry, rate-limit handling, or auto-pagination

### Proposed Change

[Google Workspace CLI (`gws`)](https://github.com/googleworkspace/cli) is an official Google tool that wraps all Workspace APIs with:
- Structured JSON output
- Built-in auth with token refresh
- Auto-pagination (`--page-all`)
- Dry-run mode
- CLI and MCP server interfaces

**Key insight:** Rather than using `gws` as an MCP server (which would dump 10-80 Gmail tools into Letta's tool list), we use the **CLI directly** via `subprocess` from Letta tools. This gives us:
- Full control over which operations are tools
- No MCP proxy overhead (no supergateway, no tool explosion)
- `gws` handles auth, pagination, retries internally
- Each tool becomes a thin subprocess wrapper instead of 30+ lines of API boilerplate

---

## Constraints Discovered

### Platform: `gws` does NOT run in the Letta Docker container

The Letta container runs **Debian 12 on linux/arm64** (Apple Silicon via Docker). The `gws` npm package only ships native binaries for:
- `aarch64-apple-darwin` (macOS ARM)
- `x86_64-apple-darwin` (macOS Intel)
- `x86_64-unknown-linux-gnu` (Linux x86_64)
- Windows variants

**linux/arm64 is not supported.** `npm install -g @googleworkspace/cli` fails inside the container.

### Solution: Host-based `gws` via HTTP bridge

Since `gws` runs on the macOS host but not inside the container, the Letta tool must reach it over the network. Two viable patterns:

**Pattern A — Thin HTTP bridge service (selected):**
A minimal FastAPI service on the host that exposes specific `gws` commands as HTTP endpoints. Letta tools call the bridge the same way they call `gmail-watch-service`.

**Pattern B — SSH/exec bridge:**
Letta tool SSHes to host or uses `docker exec` in reverse. Fragile, not recommended.

**Pattern C — Wait for linux/arm64 support:**
`gws` is pre-1.0. ARM Linux support may come. Not viable for experiment timeline.

---

## Experiment Design

### Goal

Validate that `gws` CLI produces equivalent results to the current `search_emails` Letta tool, with acceptable latency and reliability.

### Architecture

```
┌─────────────────────────┐     HTTP      ┌──────────────────────┐
│  Letta container        │ ────────────► │  gws-bridge (host)   │
│                         │               │  FastAPI :8098       │
│  search_emails_gws()    │               │                      │
│  (Letta tool)           │  ◄──────────  │  subprocess:         │
│                         │     JSON      │  gws gmail users     │
└─────────────────────────┘               │  messages list ...   │
                                          └──────────────────────┘
                                                    │
                                                    ▼
                                          Google Gmail API v1
                                          (auth via gws credentials)
```

### Components

#### 1. `gws` Auth Setup (host)

`gws` needs its own OAuth credentials. Two options:

**Option A — Reuse existing GCP OAuth client (recommended):**
```bash
# Point gws at the existing client_secret
cp ~/.gmail-mcp/gcp-oauth.keys.json ~/.config/gws/client_secret.json
# Or symlink
ln -s ~/.gmail-mcp/gcp-oauth.keys.json ~/.config/gws/client_secret.json

# Login (opens browser, one-time)
gws auth login
```

Note: The existing `gcp-oauth.keys.json` uses the `"web"` client type. `gws` may need an `"installed"` (desktop) client type for the local OAuth flow. If so, create a new OAuth client ID in the same GCP project with type "Desktop app" and download it as `client_secret.json`.

**Option B — Use env vars with existing tokens:**
```bash
export GOOGLE_WORKSPACE_CLI_CLIENT_ID=<from gcp-oauth.keys.json>
export GOOGLE_WORKSPACE_CLI_CLIENT_SECRET=<from gcp-oauth.keys.json>
export GOOGLE_WORKSPACE_CLI_TOKEN=<access_token from credentials.json>
```
Downside: access tokens expire hourly, no auto-refresh in this mode.

#### 2. `gws-bridge` Service (host, port 8098)

Minimal FastAPI service — NOT a general-purpose proxy. Exposes only the operations we're testing.

**File:** `gws-bridge/main.py`

```python
"""Thin HTTP bridge for gws CLI commands. Runs on host, not in Docker."""

from fastapi import FastAPI, HTTPException
import subprocess
import json

app = FastAPI()

GWS_BIN = "gws"  # Assumes gws is on PATH

@app.get("/health")
def health():
    result = subprocess.run([GWS_BIN, "auth", "status"], capture_output=True, text=True, timeout=10)
    status = json.loads(result.stdout) if result.returncode == 0 else {"error": result.stderr}
    return {"status": "healthy" if "credential_source" in status else "unhealthy", "gws_auth": status}

@app.post("/gmail/messages/search")
def search_messages(query: str, max_results: int = 10):
    """Search Gmail messages via gws CLI."""
    cmd = [
        GWS_BIN, "gmail", "users", "messages", "list",
        "--params", json.dumps({"userId": "me", "q": query, "maxResults": max_results}),
        "--format", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise HTTPException(status_code=502, detail=f"gws error: {result.stderr}")

    messages_response = json.loads(result.stdout)
    # gws returns raw Gmail API response — may need to fetch individual message metadata
    # just like the current tool does, OR use a second gws call per message
    return messages_response
```

**Key design decisions:**
- Runs on host (not Docker) because `gws` binary is macOS-only on ARM
- Port 8098 (unused in current port map)
- Letta reaches it via `http://host.docker.internal:8098`
- No auth on the bridge itself (internal network only, same as other MCP servers)
- Each endpoint maps to exactly one `gws` command — no generic passthrough

#### 3. `search_emails_gws` Letta Tool

**File:** `letta/gmail_gws_experiment.py`

A new Letta tool registered alongside (not replacing) the existing `search_emails`. Follows all Letta tool patterns.

```python
def search_emails_gws(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    [EXPERIMENT] Search Gmail via gws CLI bridge.

    Args:
        query: Gmail search query string
        max_results: Maximum results (1-50, default 10)

    Returns:
        Dictionary with status, emails list, and count.
    """
    import json
    import traceback
    import urllib.request
    import urllib.parse

    try:
        if max_results is None or max_results < 1:
            max_results = 10
        if max_results > 50:
            max_results = 50

        params = urllib.parse.urlencode({"query": query, "max_results": max_results})
        url = f"http://host.docker.internal:8098/gmail/messages/search?{params}"

        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        # Normalize to match existing search_emails output format
        # (transformation logic depends on what gws returns)

        return {"status": "ok", "data": data, "source": "gws-bridge"}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

#### 4. Comparison Test Script

**File:** `scripts/test-gws-experiment.py`

Calls both `search_emails` (existing) and `search_emails_gws` (experiment) with the same queries and compares:
- Result equivalence (same message IDs returned?)
- Latency (wall clock time for each)
- Error handling (what happens with bad queries, empty results, auth expiry?)

Test queries:
1. `is:unread` — basic inbox check
2. `from:specific@email.com newer_than:7d` — scoped search
3. `label:TaskQueue` — label-based (used by email_task_queue_tool)
4. `subject:"meeting notes"` — subject search (used by meeting pipeline)
5. Empty result query — edge case

---

## What This Experiment Does NOT Change

- No existing tools are modified or replaced
- No Docker Compose changes
- No Letta agent re-registration (the experiment tool is additive)
- `gmail-watch-service` is untouched
- Meeting followup, email task queue, draft reply tools are untouched
- Auth credentials for existing tools are untouched

---

## Success Criteria

1. **Functional:** `search_emails_gws` returns the same message IDs as `search_emails` for identical queries
2. **Latency:** Within 2x of current tool (acceptable given extra network hop to bridge)
3. **Auth:** `gws` handles token refresh without manual intervention for 24+ hours
4. **Reliability:** No failures across 20+ test queries

## If Successful — Migration Path

1. Add more endpoints to gws-bridge: `read_email`, `draft_email`, `send_email`, `modify_email`, `list_labels`
2. Write equivalent `_gws` Letta tools for each
3. Validate with comparison tests
4. Swap Letta agent tool attachments from old → new (one at a time)
5. Retire `gmail_tools.py` OAuth boilerplate
6. Update specialized tools (meeting followup, etc.) to call bridge instead of direct API
7. Eventually: when `gws` supports linux/arm64, move bridge logic into Letta tools directly

## If `gws` Adds linux/arm64 Support

The bridge service becomes unnecessary. Tools would call `gws` via subprocess directly from inside the container, which was the original preferred approach:

```python
cmd = ["gws", "gmail", "users", "messages", "list", "--params", json.dumps({...})]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
```

This is the ideal end state — no bridge, no MCP, just clean subprocess calls.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `gws` CLI interface changes (pre-1.0) | Medium | Pin version, bridge isolates changes |
| OAuth scope mismatch (gws requests different scopes) | Low | Use same GCP project, verify scopes |
| `gws` output format differs from raw Gmail API | Medium | Bridge normalizes output |
| Bridge service adds latency | Certain (small) | Acceptable for experiment; eliminated if arm64 support added |
| `gws` token refresh fails headless | Low | `gws auth login` with `--full` stores refresh token in keyring |

---

## Port Allocation

| Service | Port | Status |
|---------|------|--------|
| gws-bridge | 8098 | New (experiment only) |
