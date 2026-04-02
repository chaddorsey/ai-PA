# GWS CLI Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `gws` CLI from v0.7.0 to v0.22.5, add auto-update, fix `run_gws` docstring, retire `compose_gmail`.

**Architecture:** Single update script serves both host and container. `run_gws` docstring becomes hybrid: stable structural info + self-discovery pointers. `compose_gmail` removed since v0.18+ covers all its functionality natively.

**Tech Stack:** Bash (update script), Python (Letta tool), GitHub API (version checking)

**Spec:** `docs/plans/2026-04-01-gws-cli-upgrade-design.md`

---

### Task 1: Create the auto-update script

**Files:**
- Create: `scripts/update-gws.sh`

- [ ] **Step 1: Write the update script**

```bash
#!/bin/bash
# Update gws CLI to latest release from GitHub.
# Works on both macOS (host) and Linux (Letta container).
# Keeps previous binary as gws.bak for rollback.

set -euo pipefail

INSTALL_DIR="${GWS_INSTALL_DIR:-/usr/local/bin}"
REPO="googleworkspace/cli"
BINARY_NAME="gws"

# Detect platform
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "${OS}" in
    darwin) PLATFORM_OS="apple-darwin" ;;
    linux)  PLATFORM_OS="unknown-linux-gnu" ;;
    *)      echo "[update-gws] Unsupported OS: ${OS}"; exit 1 ;;
esac

case "${ARCH}" in
    arm64|aarch64) PLATFORM_ARCH="aarch64" ;;
    x86_64)        PLATFORM_ARCH="x86_64" ;;
    *)             echo "[update-gws] Unsupported arch: ${ARCH}"; exit 1 ;;
esac

TARGET="${PLATFORM_ARCH}-${PLATFORM_OS}"

# Get latest version from GitHub API
LATEST=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')

if [ -z "${LATEST}" ]; then
    echo "[update-gws] ERROR: Could not fetch latest version"
    exit 1
fi

# Get current version (if installed)
CURRENT="none"
if command -v "${BINARY_NAME}" &>/dev/null; then
    CURRENT=$("${BINARY_NAME}" --version 2>/dev/null | awk '{print $2}' || echo "none")
fi

if [ "${CURRENT}" = "${LATEST}" ]; then
    echo "[update-gws] Already at v${LATEST}"
    exit 0
fi

echo "[update-gws] Upgrading from v${CURRENT} to v${LATEST}..."

# Download
ASSET="google-workspace-cli-${TARGET}.tar.gz"
URL="https://github.com/${REPO}/releases/download/v${LATEST}/${ASSET}"
TMPDIR=$(mktemp -d)
trap 'rm -rf "${TMPDIR}"' EXIT

curl -fsSL "${URL}" -o "${TMPDIR}/${ASSET}"
tar -xzf "${TMPDIR}/${ASSET}" -C "${TMPDIR}"

# Find the binary in the extracted contents (may be in a subdirectory)
# -perm +111 is macOS syntax, -perm /111 is Linux; try both
EXTRACTED_BIN=$(find "${TMPDIR}" -name "gws" -type f \( -perm +111 -o -perm /111 \) 2>/dev/null | head -1)

if [ -z "${EXTRACTED_BIN}" ]; then
    # Try the tarball's strip-components pattern (binary at root of tar)
    EXTRACTED_BIN="${TMPDIR}/gws"
fi

if [ ! -f "${EXTRACTED_BIN}" ]; then
    echo "[update-gws] ERROR: Could not find gws binary in downloaded archive"
    ls -la "${TMPDIR}"
    exit 1
fi

# Backup current binary
if [ -f "${INSTALL_DIR}/${BINARY_NAME}" ]; then
    cp "${INSTALL_DIR}/${BINARY_NAME}" "${INSTALL_DIR}/${BINARY_NAME}.bak"
fi

# Install
cp "${EXTRACTED_BIN}" "${INSTALL_DIR}/${BINARY_NAME}"
chmod +x "${INSTALL_DIR}/${BINARY_NAME}"

echo "[update-gws] Updated gws: v${CURRENT} -> v${LATEST}"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/update-gws.sh`

- [ ] **Step 3: Test on server host**

Run: `GWS_INSTALL_DIR=~/bin ./scripts/update-gws.sh`
Expected: Downloads v0.22.5, backs up old binary, prints "Updated gws: v0.7.0 -> v0.22.5"

- [ ] **Step 4: Verify the upgrade**

Run: `~/bin/gws --version`
Expected: `gws 0.22.5`

Run: `~/bin/gws gmail +send --help`
Expected: Shows `--draft`, `-a`/`--attach` flags

Run: `~/bin/gws gmail +reply --help`
Expected: Shows reply helper (didn't exist in v0.7.0)

- [ ] **Step 5: Verify rollback backup exists**

Run: `~/bin/gws.bak --version`
Expected: `gws 0.7.0`

- [ ] **Step 6: Commit**

```bash
git add scripts/update-gws.sh
git commit -m "feat: add gws CLI auto-update script

Supports macOS and Linux, backs up previous binary as gws.bak.
Detects platform automatically, queries GitHub API for latest release."
```

---

### Task 2: Upgrade gws in Letta container

**Files:**
- Modify: `letta/entrypoint-wrapper.sh` (lines 38-57)

- [ ] **Step 1: Replace the gws install block in entrypoint-wrapper.sh**

Replace lines 38-57 (the entire `# Install gws CLI` block) with:

```bash
# Install/update gws CLI (Google Workspace) for Gmail/Calendar/Drive API access
if [ -f "/app/tools/scripts/update-gws.sh" ]; then
    GWS_INSTALL_DIR=/usr/local/bin bash /app/tools/scripts/update-gws.sh || \
        echo "[entrypoint-wrapper] WARNING: gws update failed, continuing with existing version"
elif ! command -v gws &>/dev/null; then
    echo "[entrypoint-wrapper] WARNING: update-gws.sh not found and gws not installed"
fi
```

- [ ] **Step 2: Add volume mount for scripts in docker-compose.yml**

Check if `./scripts` is already mounted into the Letta container.

Run: `grep -A5 'scripts' docker-compose.yml | head -20`

If not mounted, add to the letta service volumes section:
```yaml
      - ./scripts:/app/tools/scripts:ro
```

- [ ] **Step 3: Test by running the update inside the container**

Run: `docker exec ai-pa-letta-1 bash /app/tools/scripts/update-gws.sh`
Expected: Downloads v0.22.5, prints upgrade message

Run: `docker exec ai-pa-letta-1 gws --version`
Expected: `gws 0.22.5`

Run: `docker exec ai-pa-letta-1 gws gmail +reply --help`
Expected: Shows reply helper with `--draft`, `-a` flags

- [ ] **Step 4: Commit**

```bash
git add letta/entrypoint-wrapper.sh
git commit -m "feat: use shared update-gws.sh in Letta entrypoint

Replaces hardcoded v0.7.0 download with shared auto-update script.
Falls back gracefully if script not mounted."
```

---

### Task 3: Add scheduled auto-update

**Files:**
- Create: cron entry on host

- [ ] **Step 1: Add weekly cron job for host gws update**

Run:
```bash
(crontab -l 2>/dev/null; echo "0 3 * * 1 GWS_INSTALL_DIR=$HOME/bin $HOME/ai-PA/scripts/update-gws.sh >> /tmp/gws-update.log 2>&1") | crontab -
```

This runs every Monday at 3am.

- [ ] **Step 2: Add weekly cron job for Letta container gws update**

Run:
```bash
(crontab -l 2>/dev/null; echo "5 3 * * 1 docker exec ai-pa-letta-1 bash /app/tools/scripts/update-gws.sh >> /tmp/gws-update-container.log 2>&1") | crontab -
```

Runs 5 minutes after the host update.

- [ ] **Step 3: Verify cron entries**

Run: `crontab -l | grep gws`
Expected: Two entries — host at 3:00, container at 3:05, both Monday

- [ ] **Step 4: Test the container cron command manually**

Run: `docker exec ai-pa-letta-1 bash /app/tools/scripts/update-gws.sh`
Expected: "Already at v0.22.5" (since Task 2 already upgraded it)

---

### Task 4: Refactor run_gws docstring

**Files:**
- Modify: `letta/gmail_tools.py` (lines 1-17 module docstring, lines 25-133 run_gws docstring)

- [ ] **Step 1: Update module docstring**

Replace lines 1-17 with:

```python
"""
Google Workspace CLI Tools for Letta Agents

Two tools that provide full access to all Google Workspace APIs:

1. run_gws — General-purpose tool for ANY gws CLI command (read, write, schema discovery)
2. fetch_gmail_messages — Batch-fetch Gmail messages with configurable fields in a single call

The gws CLI was designed for native LLM use: structured JSON output, self-documenting
schema commands, and consistent `gws <service> <resource> <method>` syntax.

Authentication:
- gws CLI reads credentials from GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE env var
- Credential file: /root/.gws/credentials.json (OAuth client + refresh token)
- Auto-refreshes tokens internally
"""
```

- [ ] **Step 2: Replace the run_gws docstring (lines 25-153)**

Replace the entire docstring with the hybrid version. Keep stable structural info, replace
flag-level detail with `--help` pointers:

```python
    """
    Run any Google Workspace CLI command. Provides access to ALL Google APIs.

    The gws CLI follows a consistent pattern: gws <service> <resource> <method>
    Use "schema <dotted.path>" to discover any API's parameters and response shapes.

    IMPORTANT: All params values must be strings or numbers, NOT arrays. For multi-value
    fields like labelIds, use a comma-separated string: "INBOX,UNREAD" not ["INBOX","UNREAD"].

    Available services: gmail, calendar, drive, docs, sheets, slides, tasks, people,
      chat, classroom, forms, keep, meet, events, admin-reports, workflow

    === SELF-DISCOVERY ===
    The gws CLI is self-documenting. Use these to discover current capabilities:
      command="gmail --help"                    — list Gmail helpers and subcommands
      command="gmail +send --help"              — see flags for +send (--draft, -a, --html, etc.)
      command="schema gmail.users.drafts.create" — see API parameters for any method
      command="calendar --help"                 — list Calendar helpers and subcommands

    === SCHEMA DISCOVERY ===
    Discover API parameters before calling any method:
      command="schema docs.documents.get"
      command="schema drive.files.export"
      command="schema gmail.users.messages.list"
      command="schema calendar.events.list"

    === GMAIL ===
    Helpers handle MIME, threading, attachments, and drafts automatically:
      +send       — compose and send (supports --draft, -a/--attach, --html, --cc, --bcc)
      +reply      — reply with threading (supports --draft, -a)
      +reply-all  — reply-all (supports --draft, -a)
      +forward    — forward to new recipients (supports --draft, -a)
      +read       — extract message body and headers
      +triage     — unread inbox summary
      +watch      — stream new emails as NDJSON
    Use command="gmail +send --help" (etc.) to see current flags for each helper.
    Raw API for operations not covered by helpers:
      command="gmail users messages list", params='{"userId":"me","q":"is:unread","maxResults":5}'
      command="gmail users messages get", params='{"userId":"me","id":"MSG_ID","format":"full"}'
    Get inbox counts (use labels get, NOT messages list):
      command="gmail users labels get", params='{"userId":"me","id":"INBOX"}'
      Returns messagesTotal and messagesUnread — these are exact counts.
      WARNING: Gmail's "resultSizeEstimate" from messages.list is inaccurate. Use labels.get.
    Modify labels:
      command="gmail users messages modify", params='{"userId":"me","id":"MSG_ID"}', body='{"addLabelIds":["STARRED"]}'

    === DOCS ===
    Read a document (first tab only):
      command="docs documents get", params='{"documentId":"DOC_ID"}'
    Read a document (ALL tabs — use this for multi-tab docs):
      command="docs documents get", params='{"documentId":"DOC_ID","includeTabsContent":true}'
      With tabs: content is in result.tabs[].documentTab.body (not result.body)
    Append text:
      command="docs +write --document DOC_ID --text 'Text to append'"

    === DRIVE ===
    Export Google Docs/Sheets/Slides:
      command="drive files export", params='{"fileId":"DOC_ID","mimeType":"text/plain"}', output_file="/dev/stdout"
      Supported mimeTypes: text/plain, text/markdown, application/pdf
      IMPORTANT: Use output_file="/dev/stdout" to get exported content returned directly.
    Upload a file:
      command="drive +upload --help"    — see current flags
    List/search files:
      command="drive files list", params='{"q":"name contains \\'report\\'","pageSize":10}'

    === CALENDAR ===
    Helpers:
      command="calendar +agenda"
      command="calendar +insert --help"    — see current flags
    Raw API:
      command="calendar events list", params='{"calendarId":"primary","timeMin":"2026-04-01T00:00:00Z","maxResults":10}'

    === SHEETS ===
    Helpers:
      command="sheets +read --spreadsheet SHEET_ID --range Sheet1!A1:D10"
      command="sheets +append --spreadsheet SHEET_ID --range Sheet1 --values 'val1,val2,val3'"

    === OTHER SERVICES ===
    slides, tasks, people, chat, keep, meet, events — use command="<service> --help"

    === WORKFLOW HELPERS ===
    Cross-service productivity helpers:
      command="workflow +standup-report"
      command="workflow +meeting-prep"
      command="workflow +email-to-task"
      command="workflow +weekly-digest"
      command="workflow +file-announce"

    === FLAGS ===
    format: Override output format — "json" (default), "table", "yaml", "csv"
    output_file: Write binary/text output to this path (use "/dev/stdout" to capture export content)
    page_all: Auto-paginate through all results (for list operations with many pages)
    timeout: Command timeout in seconds (default 30, increase for large docs/exports)

    Args:
        command: The gws subcommand (e.g. "docs documents get" or "schema docs.documents.get")
        params: JSON string of query/path parameters (optional)
        body: JSON string of request body (optional). Used for create, update, modify operations.
        output_file: File path for binary/export output (optional). Use "/dev/stdout" to return
            content directly (essential for drive files export).
        format: Output format override (optional). One of: json, table, yaml, csv.
            Default is json. Use "table" or "yaml" for more readable output on complex responses.
        page_all: Auto-paginate through all results (default False). Useful for list operations.
        timeout: Command timeout in seconds (default 30, increase for large operations)

    Returns:
        Dictionary with status and the parsed JSON response, or result_text for non-JSON output.
    """
```

- [ ] **Step 3: Commit**

```bash
git add letta/gmail_tools.py
git commit -m "refactor: update run_gws docstring for hybrid self-discovery

Replace flag-level docs that went stale with --help pointers.
Keep stable structural info (service list, schema discovery, key tips).
Agents discover current flags via gws --help at runtime."
```

---

### Task 5: Retire compose_gmail

**Files:**
- Modify: `letta/gmail_tools.py` (remove compose_gmail function, lines 344-537)
- Modify: `letta/register_gmail_tools.py` (remove compose_gmail references)

- [ ] **Step 1: Check which agents have compose_gmail attached**

Already verified: `email-agent` and `main-assistant-agent-kinara` have it.
MC does not. Neither of the other active agents do.

Note: `email-agent` and `main-assistant-agent-kinara` may be legacy agents — verify
before detaching. If active, they need `run_gws` attached as replacement.

Run:
```bash
curl -sL "http://localhost:8283/v1/agents/?limit=50" | python3 -c "
import sys,json
agents=json.load(sys.stdin)
for a in agents:
    if a['id'] in ['agent-b4928949-8012-4436-a3c7-a9e510785147', 'agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a']:
        print(f'{a[\"name\"]}  {a[\"id\"]}')
"
```

- [ ] **Step 2: Remove compose_gmail from gmail_tools.py**

Delete the entire `compose_gmail` function (lines 344-537) and its import reference
in the module docstring (already handled in Task 4 Step 1).

- [ ] **Step 3: Update register_gmail_tools.py**

Remove the `compose_gmail` import and registration entry:

Replace:
```python
from gmail_tools import (
    run_gws,
    fetch_gmail_messages,
    compose_gmail,
)
```

With:
```python
from gmail_tools import (
    run_gws,
    fetch_gmail_messages,
)
```

Remove from the tools list:
```python
        (compose_gmail, ["gws", "gmail", "email", "send", "draft"]),
```

- [ ] **Step 4: Delete compose_gmail tool from Letta**

Run:
```bash
curl -sL -X DELETE "http://localhost:8283/v1/tools/tool-014136c1-4877-44b0-97f5-eaab09fe9aa1/"
```

Note: Deleting a tool auto-detaches it from all agents.

- [ ] **Step 5: Re-register run_gws with updated docstring**

Run:
```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python letta/register_gmail_tools.py
```

Expected: "Registered: run_gws" and "Registered: fetch_gmail_messages" (2 tools, not 3)

- [ ] **Step 6: Commit**

```bash
git add letta/gmail_tools.py letta/register_gmail_tools.py
git commit -m "refactor: retire compose_gmail, gws v0.18+ covers all its features

Remove compose_gmail function and registration. Gmail helpers now
natively support --draft, -a/--attach, +reply, +reply-all, +forward."
```

---

### Task 6: Update version lock file

**Files:**
- Modify: `config/versions/versions.lock.yml`

- [ ] **Step 1: Add cli_tools section to versions.lock.yml**

Add after the `infrastructure` section (before `supabase_services`):

```yaml
# CLI Tools
cli_tools:
  gws:
    source: "github.com/googleworkspace/cli"
    version: "0.22.5"
    locked: false
    locations:
      - "~/bin/gws (server host)"
      - "/usr/local/bin/gws (letta container)"
      - "@googleworkspace/cli (gws-bridge, npm)"
    upgrade_path: "auto"
    notes: "Auto-updated weekly via scripts/update-gws.sh (cron Monday 3am)"
```

- [ ] **Step 2: Update metadata counts**

Update:
```yaml
  total_services: 16
```

- [ ] **Step 3: Commit**

```bash
git add config/versions/versions.lock.yml
git commit -m "chore: add gws CLI to version lock file

Track gws across host, container, and gws-bridge locations.
Auto-updated weekly via cron."
```

---

### Task 7: Verify end-to-end

- [ ] **Step 1: Verify gws on host**

Run: `~/bin/gws --version`
Expected: `gws 0.22.5`

Run: `~/bin/gws gmail +send --help | grep -E 'draft|attach'`
Expected: Shows both `--draft` and `-a`/`--attach` flags

- [ ] **Step 2: Verify gws in Letta container**

Run: `docker exec ai-pa-letta-1 gws --version`
Expected: `gws 0.22.5`

Run: `docker exec ai-pa-letta-1 gws gmail +reply --help`
Expected: Shows reply helper with full flags

- [ ] **Step 3: Verify run_gws tool works with new features**

Run:
```bash
curl -sL -X POST "http://localhost:8283/v1/agents/agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef/messages/" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Use run_gws to check what flags gmail +send supports. Run: command=\"gmail +send --help\""}]}'
```

Expected: Agent response includes `--draft`, `-a`/`--attach` in the output.

- [ ] **Step 4: Verify compose_gmail is gone**

Run:
```bash
curl -sL "http://localhost:8283/v1/tools/" | python3 -c "
import sys,json
tools=json.load(sys.stdin)
matches = [t['name'] for t in tools if 'compose_gmail' in t['name']]
print('compose_gmail found:', matches if matches else 'NONE (correct)')
"
```

Expected: "compose_gmail found: NONE (correct)"

- [ ] **Step 5: Verify auto-update script is idempotent**

Run: `GWS_INSTALL_DIR=~/bin ./scripts/update-gws.sh`
Expected: "Already at v0.22.5"
