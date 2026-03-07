# Phase 3 — Complete gws CLI Migration

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all direct Google OAuth/API Python dependencies from the Letta ecosystem by migrating remaining tools to gws CLI subprocess calls, and install gws in the scheduling orchestrator container.

**Architecture:** Each API-calling function replaces its OAuth boilerplate + `googleapiclient` calls with `subprocess.run(["gws", ...])`. The gws CLI handles auth, token refresh, and retries internally. Non-API functions (memory-block readers) and business logic are untouched. The scheduling orchestrator container gets gws installed via Dockerfile, and its `GoogleCalendarClient` class is rewritten to use subprocess calls while keeping the same async interface.

**Tech Stack:** gws CLI v0.7.0, Python subprocess, JSON parsing. No new dependencies.

**Prior art:** Phase 1 (`gmail_tools.py` → `run_gws`/`compose_gmail`) and Phase 2 (4 specialized tools migrated) established the inline subprocess pattern. All Phase 2 tools are smoke-tested and committed as `d71e80b`.

---

## Reference: Inline gws Subprocess Pattern

All migrated functions use this pattern (NO nested `def`, NO module-level helpers):

```python
import json
import subprocess

GWS_TIMEOUT = 30

# Build command
_cmd = ["gws"] + "admin-reports activities list".split()
_cmd.extend(["--params", json.dumps({"userKey": "all", "applicationName": "drive", "startTime": start_time, "endTime": end_time, "maxResults": 1000})])
_cmd.extend(["--format", "json"])

# Run
_r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
if _r.returncode != 0:
    raise RuntimeError(_r.stderr[:500] if _r.stderr else f"gws exit {_r.returncode}")
result = json.loads(_r.stdout) if _r.stdout.strip() else {}
```

For paginated results, use `--page-all` flag (gws handles pagination internally).

### gws Service Names

| Google API | gws service | Example command |
|-----------|-------------|-----------------|
| Admin Reports | `admin-reports` | `gws admin-reports activities list --params '{"userKey":"all","applicationName":"drive"}'` |
| Drive v3 | `drive` | `gws drive files get --params '{"fileId":"ID","fields":"id,name,webViewLink"}'` |
| Drive v3 comments | `drive` | `gws drive comments list --params '{"fileId":"ID","includeDeleted":false}'` |
| Calendar v3 | `calendar` | `gws calendar events list --params '{"calendarId":"primary","timeMin":"...","timeMax":"..."}'` |
| Gmail | `gmail` | `gws gmail users messages list --params '{"userId":"me","q":"..."}'` |

### Discovering API Parameters

When unsure about gws parameter names for a specific API method:
```bash
docker exec ai-pa-letta-1 gws schema admin-reports.activities.list
docker exec ai-pa-letta-1 gws schema drive.files.list
```

---

## Task 1: Delete Dead Files

**Files:**
- Delete: `letta/calendar_tools/tools.py` (1,482 lines)
- Delete: `letta/calendar_tools/authenticate_calendar.py` (298 lines)
- Delete: `letta/gmail_reauth.py` (162 lines)
- Delete: `letta/reauth_drive_activity.py` (97 lines)
- Delete: `letta/test_calendar_credentials_in_container.py` (165 lines)

**Context:** All 6 calendar tools were detached from calendar-agent in Phase 2. The calendar agent now uses `run_gws`. The auth/test scripts are for the old OAuth flow that gws replaces.

**Step 1: Verify no imports reference these files**

Run:
```bash
grep -rn "calendar_tools\|gmail_reauth\|reauth_drive_activity\|test_calendar_credentials" letta/*.py letta/**/*.py --include="*.py" | grep -v "^letta/calendar_tools/" | grep -v "gmail_reauth.py:" | grep -v "reauth_drive_activity.py:" | grep -v "test_calendar_credentials"
```
Expected: No output (nothing imports from these files).

**Step 2: Delete files**

```bash
rm letta/calendar_tools/tools.py
rm letta/calendar_tools/authenticate_calendar.py
rm letta/gmail_reauth.py
rm letta/reauth_drive_activity.py
rm letta/test_calendar_credentials_in_container.py
```

Check if `letta/calendar_tools/` directory has any remaining files. If only `__init__.py` or empty, delete the directory:
```bash
ls letta/calendar_tools/
# If empty or only __init__.py:
rm -rf letta/calendar_tools/
```

**Step 3: Commit**

```bash
git add -A letta/calendar_tools/ letta/gmail_reauth.py letta/reauth_drive_activity.py letta/test_calendar_credentials_in_container.py
git commit -m "chore: delete legacy OAuth auth scripts and detached calendar tools"
```

---

## Task 2: Delete Old Letta Tool Registrations

**Context:** Old calendar and drive comment tools are detached from agents but still registered in Letta. Clean them up.

**Step 1: Check which old tools still exist**

```bash
# Calendar tools (should have been detached in Phase 2, now delete the registrations)
for tool_id in tool-15d921fa-8a91-4e29-b954-a0f1929f9793 tool-153f96aa-7ec8-42d2-a561-7850e90e0713 tool-0ea99c36-8447-44c4-a293-1a3b7b98d436 tool-693fa9f0-f744-408d-a4e2-96dbb4120849 tool-b9f34d1f-6690-49d5-8ba9-764195821827 tool-ebab5a0b-82b8-4f98-aaab-15e2d6e4d2a7; do
  echo -n "Checking $tool_id... "
  curl -sL "http://localhost:8283/v1/tools/$tool_id/" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','NOT FOUND'))" 2>/dev/null || echo "NOT FOUND"
done

# Drive comment tools (deleted from source in Phase 2)
for tool_id in tool-91581498-99f2-48ec-87bb-1d5dcc5c81e0 tool-c6246593-39ed-48eb-9d37-0e0637589ac4 tool-2bee44d7-9c67-457f-95a8-20d599030dbc; do
  echo -n "Checking $tool_id... "
  curl -sL "http://localhost:8283/v1/tools/$tool_id/" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','NOT FOUND'))" 2>/dev/null || echo "NOT FOUND"
done
```

**Step 2: Delete tool registrations that still exist**

```bash
# For each tool that exists, delete it
for tool_id in <IDs from step 1 that still exist>; do
  echo -n "Deleting $tool_id... "
  curl -sL -X DELETE "http://localhost:8283/v1/tools/$tool_id/" -o /dev/null -w "%{http_code}\n"
done
```

**Step 3: Verify**

```bash
curl -sL "http://localhost:8283/v1/tools/?limit=200" | python3 -c "
import sys,json
tools=json.load(sys.stdin)
old = {'get_calendar_events','delete_calendar_event','update_calendar_event','get_calendar_event','create_calendar_event','list_calendars','get_document_comments','reply_to_document_comment','resolve_document_comment'}
found = [t['name'] for t in tools if t['name'] in old]
print(f'Old tools remaining: {found if found else \"none\"}')"
```

Expected: "Old tools remaining: none"

No commit needed (Letta API state, not code).

---

## Task 3: Migrate `email_analytics_tools.py`

**Files:**
- Modify: `letta/email_analytics_tools.py` (445 lines, 1 function)
- Test: Invoke via Letta agent message

**Context:** Single function `get_email_analytics()` uses Admin Reports API (`admin`, `reports_v1`) to query Gmail activity. Replace OAuth credential loading + `build("admin", "reports_v1")` with `gws admin-reports activities list` subprocess call.

**Step 1: Rewrite `get_email_analytics`**

Replace the OAuth credential loading block (lines 158-178) and Admin Reports API call (lines 180-199) with:

```python
# Replace these imports (lines 60-64):
#   from google.oauth2.credentials import Credentials
#   from google.auth.transport.requests import Request
#   from googleapiclient.discovery import build
#   from googleapiclient.errors import HttpError
# With:
import subprocess
```

Replace credential loading + API query (lines 158-220) with:

```python
GWS_TIMEOUT = 60  # Admin Reports can be slow

# Query Admin Reports API via gws
activities = []
next_page_token = None
MAX_PAGES = 50
pages_fetched = 0

while pages_fetched < MAX_PAGES:
    _params = {
        "userKey": "all",
        "applicationName": "gmail",
        "startTime": start_time,
        "endTime": end_time,
        "maxResults": 1000,
    }
    if next_page_token:
        _params["pageToken"] = next_page_token

    _cmd = ["gws"] + "admin-reports activities list".split()
    _cmd.extend(["--params", json.dumps(_params)])
    _cmd.extend(["--format", "json"])
    _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
    if _r.returncode != 0:
        return {
            "status": "error",
            "data": {},
            "error_message": f"Admin Reports API error: {_r.stderr[:500] if _r.stderr else f'gws exit {_r.returncode}'}"
        }

    _data = json.loads(_r.stdout) if _r.stdout.strip() else {}
    activities.extend(_data.get("items", []))
    next_page_token = _data.get("nextPageToken")
    pages_fetched += 1
    if not next_page_token:
        break
```

Keep ALL business logic below the API call unchanged (hashing, quartile analysis, etc.).

**Step 2: Re-register the tool**

```bash
cd /Volumes/main-drive/ai-PA
LETTA_BASE_URL=http://localhost:8283 python3 letta/register_email_analytics_tools.py
```

If no registration script exists, register manually:
```bash
LETTA_BASE_URL=http://localhost:8283 python3 -c "
from letta_client import Letta
from letta.email_analytics_tools import get_email_analytics
client = Letta(base_url='http://localhost:8283')
tool = client.tools.upsert_from_function(func=get_email_analytics)
print(f'Registered: {tool.id}  {tool.name}')
"
```

**Step 3: Smoke test**

```bash
curl -sL -X POST "http://localhost:8283/v1/agents/agent-6eb765bf-7268-4f6d-a380-c527c9c53000/messages/" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Run get_email_analytics for yesterday in org mode. Report the total sent/received counts."}]}' | python3 -c "
import sys,json
data=json.load(sys.stdin)
for msg in data.get('messages',[]):
    role = msg.get('message_type','')
    if role == 'tool_call_message':
        print(f'TOOL_CALL: {msg.get(\"tool_call\",{}).get(\"name\",\"\")}')
    elif role == 'tool_return_message':
        ret = msg.get('tool_return','')[:300]
        print(f'TOOL_RETURN: {ret}')
    elif role == 'assistant_message':
        print(f'ASSISTANT: {msg.get(\"content\",\"\")[:300]}')
"
```

Expected: Tool returns status "ok" with email analytics data.

**Step 4: Commit**

```bash
git add letta/email_analytics_tools.py
git commit -m "feat: migrate email_analytics to gws CLI subprocess"
```

---

## Task 4: Migrate `drive_analytics_tools.py` — Module-Level Changes

**Files:**
- Modify: `letta/drive_analytics_tools.py`

**Context:** This file has module-level imports and 5 private helper functions that use Google OAuth. The public functions that call APIs are Letta tools (imports inlined inside function body), but some still call the module-level helpers. This task restructures the file to remove all module-level Google dependencies.

**Step 1: Remove module-level Google imports (lines 9-19)**

Replace:
```python
import os
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
```

With:
```python
import os
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
```

**Step 2: Delete module-level helpers (lines 22-244)**

Delete these sections entirely:
- `OAUTH_KEY_FILE`, `TOKEN_PATH`, `MY_EMAIL` constants (lines 22-30)
- `SCOPES` list (lines 32-37)
- `MAX_RESULTS_PER_PAGE` and other constants (lines 39-43) — move these into functions that use them
- `_load_credentials()` function (lines 46-82)
- `_is_workday()` function (lines 84-87) — inline into callers
- `_get_last_workday()` function (lines 89-100) — inline into callers
- `_query_admin_reports_api()` function (lines 102-141) — each caller will use gws subprocess directly
- `_query_drive_api()` function (lines 143-177) — each caller will use gws subprocess directly
- `_query_drive_activity_api()` function (lines 179-212) — only used by optimized path in `search_drive_activity`, which we'll remove
- `_get_file_comments()` function (lines 214-244) — each caller will use gws subprocess directly

Also delete the `if __name__ == "__main__"` test block at the end (lines 2410-2415).

**Step 3: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "refactor: remove module-level Google OAuth from drive_analytics_tools"
```

---

## Task 5: Migrate `collect_daily_workspace_activity`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 246)

**Context:** Uses `_query_admin_reports_api()` for workspace activity and `build("drive", "v3")` + `files().get()` for link/accessibility checking on top 25 docs. Also calls `_load_credentials()`, `_is_workday()`, `_get_last_workday()`.

**Step 1: Rewrite function**

Replace all Google API calls with gws subprocess. The function already has a Letta-compatible structure (try-except wrapper, returns JSON string). Key changes:

1. Add `import subprocess` at top of function body
2. Inline `_is_workday` (single line: `target_date.weekday() < 5`)
3. Inline `_get_last_workday` (3-line while loop)
4. Replace `_query_admin_reports_api(start_time, end_time, "all")` with gws subprocess (with pagination via loop, same as Task 3 pattern but using `applicationName: "drive"`)
5. Replace `build("drive", "v3") + files().get()` loop with gws subprocess calls:
   ```python
   _cmd = ["gws"] + "drive files get".split()
   _cmd.extend(["--params", json.dumps({"fileId": doc_id, "fields": "id,name,webViewLink,shared,capabilities", "supportsAllDrives": True})])
   _cmd.extend(["--format", "json"])
   _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=15)
   ```
6. Replace `HttpError` status checks with gws stderr parsing (check for "404", "403" in stderr)
7. Remove the nested `def get_top_five()` — use a lambda or inline the logic (Letta extracts nested defs as tools)

**IMPORTANT:** The existing function has a nested `def get_top_five()` at line 417. This MUST be inlined (Letta constraint). Replace with direct list comprehension or inline loop.

**Step 2: Re-register the tool**

```bash
LETTA_BASE_URL=http://localhost:8283 python3 letta/register_drive_analytics_tools_api.py
```

Or register individually if the script doesn't handle it:
```bash
LETTA_BASE_URL=http://localhost:8283 python3 -c "
import sys; sys.path.insert(0, 'letta')
from letta_client import Letta
from drive_analytics_tools import collect_daily_workspace_activity
client = Letta(base_url='http://localhost:8283')
tool = client.tools.upsert_from_function(func=collect_daily_workspace_activity)
print(f'Registered: {tool.id}  {tool.name}')
"
```

**Step 3: Smoke test**

```bash
curl -sL -X POST "http://localhost:8283/v1/agents/agent-6eb765bf-7268-4f6d-a380-c527c9c53000/messages/" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Run collect_daily_workspace_activity for yesterday. Just tell me the total activities count and number of unique users."}]}' | python3 -c "
import sys,json
data=json.load(sys.stdin)
for msg in data.get('messages',[]):
    role = msg.get('message_type','')
    if role == 'tool_call_message':
        print(f'TOOL_CALL: {msg.get(\"tool_call\",{}).get(\"name\",\"\")}({msg.get(\"tool_call\",{}).get(\"arguments\",\"\")[:200]})')
    elif role == 'tool_return_message':
        print(f'TOOL_RETURN: {msg.get(\"tool_return\",\"\")[:400]}')
    elif role == 'assistant_message':
        print(f'ASSISTANT: {msg.get(\"content\",\"\")[:300]}')
"
```

Expected: Returns JSON with `type: "drive_analytics_daily"`, summary with total_activities > 0.

**Step 4: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate collect_daily_workspace_activity to gws CLI"
```

---

## Task 6: Migrate `collect_daily_personal_activity`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 492)

**Context:** Uses `_query_admin_reports_api(start_time, end_time, MY_EMAIL)` for personal activity and `build("drive", "v3") + files().get()` for link fetching. Same pattern as Task 5 but filtered to user's own activity.

**Step 1: Rewrite function**

Same pattern as Task 5:
1. Add `import subprocess`
2. Inline `_is_workday` and `_get_last_workday`
3. Replace Admin Reports call with gws subprocess (use `"userKey": "cdorsey@concord.org"`)
4. Replace Drive `files().get()` loop with gws subprocess calls
5. Replace `HttpError` checks with stderr parsing

**Step 2: Re-register and smoke test**

Same pattern as Task 5. Test with pulse-monitor-agent.

**Step 3: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate collect_daily_personal_activity to gws CLI"
```

---

## Task 7: Migrate `collect_daily_mentions`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 685)

**Context:** This function already has inline imports (Letta compliant). Uses Drive v3 for `files().list()` (with pagination) and `comments().list()` (with pagination) to find @mentions. This is the most complex migration because of double pagination (files then comments per file).

**Step 1: Rewrite function**

1. Replace Google OAuth imports with `import subprocess`
2. Replace credential loading block with nothing (gws handles auth)
3. Replace `build("drive", "v3") + files().list()` pagination with:
   ```python
   _cmd = ["gws"] + "drive files list".split()
   _cmd.extend(["--params", json.dumps({
       "q": all_files_query,
       "pageSize": 100,
       "fields": "nextPageToken,files(id,name,webViewLink)",
       "supportsAllDrives": True,
       "includeItemsFromAllDrives": True,
       "corpora": "allDrives",
   })])
   _cmd.extend(["--format", "json"])
   ```
   Use a manual pagination loop (check for `nextPageToken` in response, pass it in next call).

   **Alternative:** Use `--page-all` flag if gws supports it for `drive files list`. Test first:
   ```bash
   docker exec ai-pa-letta-1 gws drive files list --params '{"q":"modifiedTime > \"2026-03-01T00:00:00Z\"","pageSize":10,"fields":"nextPageToken,files(id,name)"}' --format json --page-all 2>&1 | head -5
   ```

4. Replace `comments().list()` per-file loop with gws subprocess:
   ```python
   _cmd = ["gws"] + "drive comments list".split()
   _cmd.extend(["--params", json.dumps({
       "fileId": file_id,
       "pageSize": 100,
       "fields": "nextPageToken,comments(id,content,author,createdTime,modifiedTime,resolved,mentionedEmailAddresses)",
   })])
   _cmd.extend(["--format", "json"])
   ```

5. Replace `HttpError` catch blocks with gws stderr checks

**Step 2: Re-register and smoke test**

Test with pulse-monitor-agent asking for recent mentions.

**Step 3: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate collect_daily_mentions to gws CLI"
```

---

## Task 8: Migrate `get_document_events`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 1138)

**Context:** Already has inline imports (Letta compliant). Uses Admin Reports API only. Straightforward — replace OAuth + `build("admin", "reports_v1")` with gws subprocess.

**Step 1: Rewrite function**

1. Replace Google imports with `import subprocess`
2. Remove credential loading block
3. Replace Admin Reports query loop with gws subprocess (same pagination pattern as Tasks 3/5)
4. Keep all business logic (doc_id filtering, event aggregation, sorting) unchanged

**Step 2: Re-register and smoke test**

**Step 3: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate get_document_events to gws CLI"
```

---

## Task 9: Migrate `get_drive_file_info`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 1409)

**Context:** Uses `_load_credentials()` + `build("drive", "v3") + files().get()` for a single file lookup. Simple migration.

**Step 1: Rewrite function**

1. Add `import subprocess` (already has `import re`)
2. Remove `_load_credentials()` call and `build()` call
3. Replace `service.files().get(...)` with:
   ```python
   _cmd = ["gws"] + "drive files get".split()
   _cmd.extend(["--params", json.dumps({
       "fileId": file_id,
       "fields": "id,name,mimeType,createdTime,modifiedTime,owners,shared,webViewLink,webContentLink,size,permissions,capabilities,description,starred,trashed",
       "supportsAllDrives": True,
   })])
   _cmd.extend(["--format", "json"])
   _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=15)
   ```
4. Replace `HttpError` status checks with stderr parsing:
   ```python
   if _r.returncode != 0:
       _err = _r.stderr or ""
       if "404" in _err or "notFound" in _err:
           return json.dumps({"error": "File not found", ...})
       elif "403" in _err or "forbidden" in _err.lower():
           return json.dumps({"error": "Access denied", ...})
       ...
   ```

**Step 2: Re-register and smoke test**

**Step 3: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate get_drive_file_info to gws CLI"
```

---

## Task 10: Migrate `search_drive_activity`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 1610)

**Context:** This is the most complex function (~550 lines). It has two code paths:
- **Optimized path** (lines 1753-1920): Uses Drive v3 + Drive Activity v2. Since Drive Activity v2 is NOT supported by gws, **remove this path entirely**. The standard path already handles the same queries via Admin Reports.
- **Standard path** (lines 1923-2151): Uses Admin Reports + Drive v3 for link fetching.

**Step 1: Remove the optimized path**

Delete lines 1753-1921 (the entire `if owner_list and not user_list and not needs_view_data:` block). This eliminates the only Drive Activity v2 dependency in the entire codebase.

Also remove `needs_view_data` calculation (line 1758) since it's only used by the optimized path guard.

**Step 2: Rewrite the standard path**

1. Replace Google imports with `import subprocess`
2. Remove credential loading block
3. Replace `build("admin", "reports_v1") + activities().list()` pagination with gws subprocess loop
4. Replace `build("drive", "v3") + files().get()` link-fetching loop with gws subprocess
5. Replace `HttpError` checks with stderr parsing

**Step 3: Re-register and smoke test**

Test queries:
- `search_drive_activity(user="cdorsey@concord.org", start_date="2026-03-06", end_date="2026-03-06")`
- `search_drive_activity(owner="cdorsey@concord.org", start_date="2026-03-01", end_date="2026-03-07")`

**Step 4: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate search_drive_activity to gws CLI, remove Drive Activity v2 path"
```

---

## Task 11: Migrate `get_drive_documents`

**Files:**
- Modify: `letta/drive_analytics_tools.py` (function at ~line 2162)

**Context:** Uses Drive v3 `files().list()` with pagination. Straightforward migration.

**Step 1: Rewrite function**

1. Replace Google imports with `import subprocess`
2. Remove credential loading block
3. Replace `build("drive", "v3") + files().list()` pagination with gws subprocess loop:
   ```python
   _cmd = ["gws"] + "drive files list".split()
   _cmd.extend(["--params", json.dumps({
       "q": query,
       "pageSize": min(100, count - len(documents)),
       "fields": "nextPageToken,files(id,name,mimeType,webViewLink,owners,modifiedTime,shared,size,createdTime)",
       "orderBy": "modifiedTime desc",
       "supportsAllDrives": True,
       "includeItemsFromAllDrives": True,
   })])
   _cmd.extend(["--format", "json"])
   ```

**Step 2: Re-register and smoke test**

**Step 3: Commit**

```bash
git add letta/drive_analytics_tools.py
git commit -m "feat: migrate get_drive_documents to gws CLI"
```

---

## Task 12: Migrate Scheduling Orchestrator `GoogleCalendarClient`

**Files:**
- Modify: `letta/scheduling_orchestrator/Dockerfile.api` (add gws install)
- Modify: `letta/scheduling_orchestrator/google_calendar_client.py` (rewrite to subprocess)
- Modify: `letta/scheduling_orchestrator/requirements-api.txt` (remove google deps)
- Modify: `docker-compose.yml` (update volume mount)

**Context:** The scheduling orchestrator runs in a separate container (`scheduling-orchestrator-api`, aarch64 Linux). The `GoogleCalendarClient` class has 2 async methods: `get_core_event_data()` and `fetch_event_by_id()`. The `_classify_event()` helper is pure logic (no API calls) and stays as-is.

**Step 1: Add gws install to Dockerfile.api**

After the `RUN apt-get update` block, add:

```dockerfile
# Install gws CLI for Google Calendar API access
ARG GWS_VERSION=0.7.0
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then TARGET="aarch64-unknown-linux-gnu"; \
    elif [ "$ARCH" = "amd64" ]; then TARGET="x86_64-unknown-linux-gnu"; fi && \
    curl -fsSL "https://github.com/googleworkspace/cli/releases/download/v${GWS_VERSION}/gws-${TARGET}.tar.gz" \
    | tar -xz --strip-components=1 -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/gws
```

**Step 2: Update docker-compose.yml volume mount**

Replace:
```yaml
volumes:
  - ${HOME}/.gmail-mcp:/root/.gmail-mcp:ro
```

With:
```yaml
volumes:
  - ./gws-bridge/credentials.json:/root/.gws/credentials.json:ro
```

Remove the `CALENDAR_CREDENTIALS_PATH` and `CALENDAR_OAUTH_PATH` environment variables (gws handles auth via its own credentials file).

**Step 3: Rewrite `google_calendar_client.py`**

Replace `_get_calendar_service()` and the `GoogleCalendarClient` class internals to use gws subprocess. The class interface stays identical.

```python
"""
Google Calendar client for the scheduling orchestrator.

Uses gws CLI subprocess for Calendar API access.
Interface compatible with MCPCalendarClient.
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from mcp_client import MCPError

GWS_TIMEOUT = 30


def _gws_calendar(method: str, params: dict) -> dict:
    """Run a gws calendar command and return parsed JSON."""
    _cmd = ["gws"] + f"calendar {method}".split()
    _cmd.extend(["--params", json.dumps(params)])
    _cmd.extend(["--format", "json"])
    _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
    if _r.returncode != 0:
        _err = _r.stderr or f"gws exit {_r.returncode}"
        if "404" in _err or "notFound" in _err:
            raise MCPError(code=-32603, message=f"Calendar not found: {params.get('calendarId', '?')}")
        if "403" in _err or "forbidden" in _err.lower():
            raise MCPError(code=-32603, message=f"No access to calendar: {params.get('calendarId', '?')}")
        raise MCPError(code=-32603, message=f"Calendar API error: {_err[:500]}")
    return json.loads(_r.stdout) if _r.stdout.strip() else {}


def _classify_event(event: Dict[str, Any]) -> Dict[str, bool]:
    # ... keep exactly as-is (pure logic, no API calls) ...
```

Rewrite `GoogleCalendarClient`:
- Remove `_get_service()` and `self._service`
- `initialize()`: verify gws is available (`subprocess.run(["gws", "--version"])`)
- `get_core_event_data()`: call `_gws_calendar("events list", {...})`, then process items same as before
- `fetch_event_by_id()`: call `_gws_calendar("events get", {...})`, then process same as before

**IMPORTANT:** `_gws_calendar` is a module-level helper, NOT inside the class. This is fine because this file runs in the orchestrator container (not extracted by Letta as a tool).

**Step 4: Update requirements-api.txt**

Remove:
```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.2.0
```

**Step 5: Rebuild and test**

```bash
docker-compose up -d --build scheduling-orchestrator-api
docker-compose logs -f scheduling-orchestrator-api 2>&1 | head -30
# Check health
curl -s http://localhost:8096/health
```

Smoke test via calendar agent:
```bash
curl -sL -X POST "http://localhost:8283/v1/agents/agent-892a2d58-b9f6-4baf-84f3-c431fe46487d/messages/" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Use orchestrate_scheduling to find a 30-minute slot for a meeting with me tomorrow afternoon. Just show the top 3 options."}]}' | python3 -c "
import sys,json
data=json.load(sys.stdin)
for msg in data.get('messages',[]):
    role = msg.get('message_type','')
    if role == 'tool_call_message':
        print(f'TOOL_CALL: {msg.get(\"tool_call\",{}).get(\"name\",\"\")}')
    elif role == 'tool_return_message':
        print(f'TOOL_RETURN: {msg.get(\"tool_return\",\"\")[:400]}')
    elif role == 'assistant_message':
        print(f'ASSISTANT: {msg.get(\"content\",\"\")[:300]}')
"
```

**Step 6: Commit**

```bash
git add letta/scheduling_orchestrator/Dockerfile.api letta/scheduling_orchestrator/google_calendar_client.py letta/scheduling_orchestrator/requirements-api.txt docker-compose.yml
git commit -m "feat: migrate scheduling orchestrator to gws CLI for Calendar API"
```

---

## Task 13: Final Cleanup — Remove Google OAuth Dependencies

**Files:**
- Modify: `letta/entrypoint-wrapper.sh` (remove pip installs)
- Modify: `letta/scheduling_orchestrator/requirements-api.txt` (verify clean)
- Delete: `letta/register_drive_analytics_tools_api.py` (if it only does OAuth-based registration)
- Modify: `docker-compose.yml` (remove `~/.gmail-mcp` mount from Letta container if no longer needed)

**Prerequisite:** ALL previous tasks must be complete and smoke-tested.

**Step 1: Update entrypoint-wrapper.sh**

Remove these pip install lines:
```bash
python3 -m pip install --quiet --no-warn-script-location \
    pytz \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client \
    2>&1 | tail -3
```

Replace with (pytz is still needed):
```bash
python3 -m pip install --quiet --no-warn-script-location \
    pytz \
    2>&1 | tail -3
```

**Step 2: Verify no remaining Google OAuth references in Letta tools**

```bash
grep -rn "google.oauth2\|google_auth_oauthlib\|googleapiclient\|from google.auth" letta/*.py letta/**/*.py --include="*.py"
```

Expected: No output from files that run in the Letta container. (The scheduling orchestrator files are in a separate container and should already be clean from Task 12.)

**Step 3: Check if `~/.gmail-mcp` mount is still needed**

```bash
grep -n "gmail-mcp" docker-compose.yml
```

If only the scheduling-orchestrator-api referenced it (and Task 12 changed it to `gws-bridge/credentials.json`), and no other service uses it, the mount can be removed from the Letta service too. But verify first:

```bash
grep -rn "gmail-mcp\|\.gmail-mcp" letta/*.py letta/**/*.py --include="*.py"
```

If still referenced (e.g., by files not yet migrated), keep the mount.

**Step 4: Rebuild Letta and verify**

```bash
docker-compose up -d --build letta
docker-compose logs -f letta 2>&1 | head -40
# Wait for startup, then verify tools still work
curl -sL -X POST "http://localhost:8283/v1/agents/agent-892a2d58-b9f6-4baf-84f3-c431fe46487d/messages/" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"List my calendar events for today using run_gws."}]}' | python3 -c "
import sys,json
data=json.load(sys.stdin)
for msg in data.get('messages',[]):
    if msg.get('message_type') == 'assistant_message':
        print(msg.get('content','')[:300])
"
```

**Step 5: Commit**

```bash
git add letta/entrypoint-wrapper.sh docker-compose.yml
git commit -m "chore: remove Google OAuth pip dependencies from Letta container"
```

---

## Task Dependency Graph

```
Task 1 (delete dead files) ──────────────────┐
Task 2 (delete old tool registrations) ──────┤
                                              ├─► Task 13 (final cleanup)
Task 3 (email_analytics) ───────────────────┤
Task 4 (module-level cleanup) ──┐            │
Task 5 (workspace_activity) ────┤            │
Task 6 (personal_activity) ─────┤            │
Task 7 (daily_mentions) ────────┼─► commit ──┤
Task 8 (document_events) ───────┤            │
Task 9 (drive_file_info) ───────┤            │
Task 10 (search_drive_activity) ┤            │
Task 11 (get_drive_documents) ──┘            │
Task 12 (scheduling orchestrator) ───────────┘
```

Tasks 1-3 are independent. Tasks 4-11 are sequential (all modify same file). Task 12 is independent. Task 13 depends on all others.

---

## Memory Block Readers (NO migration needed)

These 8 functions in `drive_analytics_tools.py` return JSON instructions for the agent to read from memory blocks. They call NO Google APIs and need no changes:

- `calculate_running_averages()` (line 943) — stub
- `get_drive_analytics_summary()` (line 961)
- `get_drive_trends()` (line 1014)
- `get_my_drive_activity()` (line 1038)
- `get_drive_mentions()` (line 1089)
- `get_top_documents()` (line 1294)
- `get_recent_my_activity()` (line 1355)
- `initialize_drive_analytics_memory()` (line 1570)

These functions use `json.dumps()` from the module-level import, which remains after Task 4.

---

## Risk Notes

1. **Admin Reports API via gws:** Verify `gws admin-reports activities list` returns the same JSON structure as `service.activities().list().execute()`. Key fields: `items[]`, `nextPageToken`, `items[].actor.email`, `items[].events[].name`, `items[].events[].parameters[]`. Test before migrating.

2. **Pagination:** gws may handle pagination differently than raw API. Test `--page-all` vs manual `pageToken` loop. If `--page-all` works, it simplifies code significantly. If not, use manual loop.

3. **Drive Activity v2 removal:** Dropping the optimized path in `search_drive_activity` means owner-filtered queries without view data will be slower (Admin Reports scans all activity). This is acceptable — the Admin Reports path works and has been the fallback all along.

4. **Scheduling orchestrator rebuild:** The container rebuild will briefly take the orchestrator offline. Schedule during low-usage time.

5. **gws credentials scope:** The gws credentials at `/root/.gws/credentials.json` must include `admin.reports.audit.readonly` scope (already authorized in Phase 2 Step 0). Verify:
   ```bash
   docker exec ai-pa-letta-1 gws admin-reports activities list --params '{"userKey":"all","applicationName":"drive","maxResults":1}' --format json 2>&1 | head -5
   ```
