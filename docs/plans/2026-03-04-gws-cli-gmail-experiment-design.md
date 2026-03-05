# Design: Replace Gmail API Tools with Google Workspace CLI (`gws`)

**Date:** 2026-03-04
**Status:** Experiment active — powering Gmail drafts sidebar in pa-web-ui via x86_64 sidecar (full tool replacement still awaits linux/arm64)
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

### MCP Server Mode — Evaluated and Rejected

`gws mcp -s gmail` exposes all Gmail Discovery API methods as MCP tools (10-80 tools). Problems:
- **Tool explosion** — Letta sees dozens of tools it will never use, degrading tool selection accuracy
- **No per-method filtering** — you get all of a service's methods or none
- **Requires supergateway proxy** — `gws mcp` is stdio-only, so Letta needs a proxy (same pattern as Granola MCP)
- **Another process to manage** — launchd plist, health monitoring, restart logic

The CLI approach avoids all of this: each Letta tool wraps exactly one `gws` command, giving the agent a curated tool set instead of a raw API dump.

---

## Constraints Discovered

### Platform: `gws` does NOT run in the Letta Docker container

The Letta container runs **Debian 12 on linux/arm64** (Apple Silicon via Docker). The `gws` npm package (v0.3.4) only ships native binaries for:
- `aarch64-apple-darwin` (macOS ARM)
- `x86_64-apple-darwin` (macOS Intel)
- `x86_64-unknown-linux-gnu` (Linux x86_64)
- Windows variants

**linux/arm64 is not supported.** `npm install -g @googleworkspace/cli` fails inside the container with: `Platform with type "Linux" and architecture "arm64" is not supported`.

**Verified:** Node 22 and npm 10 are already installed in the Letta container. The binary platform support is the only blocker.

**This is not a Letta-specific constraint** — it's the combination of:
1. Apple Silicon host → Docker runs arm64 containers by default
2. `gws` not shipping a linux/arm64 binary (yet)

### Workaround Options Evaluated

**Option A — x86_64 sidecar container in Docker Compose:**
Run a small `node:20-slim` container with `platform: linux/amd64` (via Rosetta 2 emulation). Install `gws` there, expose an HTTP bridge on `pa-internal`. This solves all operational concerns (managed by Compose, restartable, health-checkable, service DNS). Emulation overhead is negligible for network-bound CLI calls.

```yaml
gws-bridge:
  image: node:20-slim
  platform: linux/amd64
  volumes:
    - ./gws-bridge:/app
    - ~/.gmail-mcp:/root/.gmail-mcp:ro
  ports:
    - "8098:8098"
  networks:
    - pa-internal
```

**Option B — Host-based bridge with launchd:**
Run `gws` on macOS host, expose via FastAPI on port 8098. Letta calls `http://host.docker.internal:8098`. Breaks the Docker Compose model — not managed, no restart policy, silent failures, separate process management.

**Option C — Force Letta container to x86_64:**
Set `platform: linux/amd64` on the Letta service. Imposes emulation penalty on ALL Letta operations (inference, memory, tool execution) — far too costly just for one CLI binary.

**Option D — Wait for linux/arm64 support (selected):**
`gws` is pre-1.0 (v0.3.4). linux/arm64 is a natural addition as the tool matures — ARM servers (AWS Graviton, etc.) are increasingly common. When this ships, tools call `gws` via subprocess directly inside the Letta container with zero infrastructure changes.

### Why We're Waiting (Not Building the Bridge)

While Option A (x86_64 sidecar) is technically viable, **the bridge negates most of the simplification benefit**:

| What we wanted | What the bridge gives us |
|---|---|
| `subprocess.run(["gws", ...])` in tool | `urllib.request.urlopen("http://gws-bridge:8098/...")` in tool |
| No extra services | A new container + bridge code to maintain |
| Fewer moving parts | One more moving part |
| Eliminated OAuth boilerplate | Traded for HTTP client boilerplate |

The current `gmail_tools.py` works. The OAuth boilerplate is repetitive but stable. Adding a bridge introduces a network hop, a new service, and a new failure domain — to solve a problem that's already solved. The real win comes when `gws` runs directly in the container.

---

## Ideal End State (When linux/arm64 Ships)

### Architecture

```
┌──────────────────────────────────┐
│  Letta container (arm64)         │
│                                  │
│  search_emails() ──► subprocess  │──► Google Gmail API v1
│  draft_email()   ──► gws CLI    │    (auth via gws credentials)
│  send_email()    ──► ...        │
│                                  │
│  /root/.config/gws/credentials  │
└──────────────────────────────────┘
```

No bridge, no MCP, no proxy. Each Letta tool is a thin subprocess wrapper:

```python
def search_emails(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Search Gmail messages using Gmail search syntax.

    Args:
        query: Gmail search query string
        max_results: Maximum number of results to return (1-50, default 10)

    Returns:
        Dictionary with status, emails list, and count.
    """
    import json
    import subprocess
    import traceback

    try:
        if max_results is None or max_results < 1:
            max_results = 10
        if max_results > 50:
            max_results = 50

        cmd = [
            "gws", "gmail", "users", "messages", "list",
            "--params", json.dumps({"userId": "me", "q": query, "maxResults": max_results}),
            "--format", "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {"status": "error", "error_message": f"gws error: {result.stderr}"}

        data = json.loads(result.stdout)
        messages = data.get("messages", [])

        if not messages:
            return {"status": "ok", "emails": [], "count": 0, "query": query}

        # Fetch metadata for each message
        emails = []
        for msg in messages:
            cmd_get = [
                "gws", "gmail", "users", "messages", "get",
                "--params", json.dumps({
                    "userId": "me",
                    "id": msg["id"],
                    "format": "metadata",
                    "metadataHeaders": ["Subject", "From", "To", "Date"],
                }),
                "--format", "json",
            ]
            msg_result = subprocess.run(cmd_get, capture_output=True, text=True, timeout=15)
            if msg_result.returncode != 0:
                continue

            msg_data = json.loads(msg_result.stdout)
            headers = msg_data.get("payload", {}).get("headers", [])
            header_map = {h["name"].lower(): h["value"] for h in headers}

            emails.append({
                "id": msg_data["id"],
                "threadId": msg_data.get("threadId", ""),
                "subject": header_map.get("subject", ""),
                "from": header_map.get("from", ""),
                "to": header_map.get("to", ""),
                "date": header_map.get("date", ""),
                "snippet": msg_data.get("snippet", ""),
                "labelIds": msg_data.get("labelIds", []),
            })

        return {"status": "ok", "emails": emails, "count": len(emails), "query": query}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

Compare to current: **no OAuth imports, no credential loading, no token refresh, no service building.** The ~30 lines of auth boilerplate per tool become zero.

### Migration Steps (When Ready)

1. Install `gws` in Letta container: `npm install -g @googleworkspace/cli` (add to Dockerfile or startup script)
2. Auth setup: `gws auth login` on host, then `gws auth export > credentials.json` and mount into container at `/root/.config/gws/credentials.json` via `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env var
3. Write new `search_emails` with subprocess pattern (as above)
4. Comparison test: run old and new tool with identical queries, verify same message IDs
5. If successful, convert remaining 8 core tools one at a time
6. Update specialized tools (meeting followup, email task queue, draft reply) to use subprocess pattern
7. Remove `google-auth-library`, `google-api-python-client` from Letta sandbox pip requirements
8. Retire `gmail_tools.py` OAuth boilerplate

### Migration Effort Estimate

The bridge-to-direct migration (if we had built the bridge) would be a one-line-per-tool change — swap HTTP call for subprocess call. The JSON output is identical either way.

The full migration from current `gmail_tools.py` → `gws` subprocess is also straightforward: each tool keeps its parameter signature and return format, only the middle section (auth + API call) changes.

---

## Broader Opportunity: Beyond Gmail

Once `gws` runs in-container, the same subprocess pattern works for **all Google Workspace APIs**:

| API | Current State | With `gws` |
|-----|--------------|------------|
| Gmail | 9 custom tools + 3 specialized | Subprocess wrappers, no OAuth |
| Google Calendar | No direct tools (uses Calendly MCP) | `gws calendar` — native access |
| Google Drive | `drive-rag-service` has its own OAuth | Could share `gws` auth |
| Google Sheets | No integration | `gws sheets` — available immediately |
| Google Docs | Comment tools use Drive API directly | `gws docs` — unified access |

This is the real long-term value: **one auth mechanism and one CLI for all Google Workspace APIs**, instead of building separate OAuth integrations per service.

---

## Monitoring: When to Revisit

- **Watch:** [github.com/googleworkspace/cli/issues](https://github.com/googleworkspace/cli) for linux/arm64 support
- **Trigger:** When `gws` ships a `aarch64-unknown-linux-gnu` binary (or equivalent), proceed with the migration steps above
- **Alternative trigger:** If a new Google Workspace API integration is needed (Calendar, Sheets, etc.) and the bridge cost is justified by multi-service use, reconsider Option A (x86_64 sidecar)

---

## Port Allocation (Reserved)

| Service | Port | Status |
|---------|------|--------|
| gws-bridge | 8098 | Reserved for future use |
