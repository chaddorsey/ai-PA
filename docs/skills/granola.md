---
description: Granola meeting-notes CLI. Wraps the 6 MCP tools exposed by the local supergateway bridge (mcp-remote → https://mcp.granola.ai/mcp). Replaces the run_granola family of Letta tools with a single Bash-callable surface.
applies-to: any local-mode agent that needs to query, list, fetch, or transcribe Granola meeting notes. Primary user: Docs-and-Transcripts agent. Also useful for MC (meeting prep, follow-up extraction) and Tasks (action-item mining).
replaces:
  - query_granola_meetings (Letta tool / Granola MCP)
  - list_meetings (Letta tool / Granola MCP)
  - list_meeting_folders (Letta tool / Granola MCP)
  - get_meetings (Letta tool / Granola MCP)
  - get_meeting_transcript (Letta tool / Granola MCP)
  - get_account_info (Letta tool / Granola MCP)
cli: scripts/granola
---

# Granola CLI Skill

## When to use

- **Open-ended question about meeting content**: `granola query "what
  did Kate say about the budget?"`. The Granola server uses RAG to
  return a Markdown answer with inline citation links like
  `[[0]](https://app.granola.ai/...)`. The agent MUST preserve these
  citations when relaying to the user — they're how the user verifies
  and clicks through.
- **Enumerate meetings in a date range**: `granola list --range
  this_week | last_week | last_30_days | custom`. Returns an XML
  payload (Granola's chosen format for token efficiency) with title,
  id, date, participants per meeting.
- **Find specific folders** before scoping a list: `granola folders`.
  Returns IDs, titles, descriptions, note_counts.
- **Fetch one or more meeting records by UUID**: `granola get
  <meeting_id> [<meeting_id>...]`. Returns full metadata JSON.
- **Read a transcript verbatim**: `granola transcript <meeting_id>`.
- **Confirm auth + active workspace**: `granola account`.

This skill replaces the six `run_granola`-related Letta tools 1:1.
Behavior is identical because both routes go through the same MCP
server; the CLI is the shape Letta-code subprocesses can call via
Bash without the Letta-server-side tool runtime.

## When NOT to use

- **Live calendar queries (upcoming events, scheduling)**: use the
  calendar agent / orchestrate_scheduling instead. Granola is for
  meeting *notes*, not the calendar itself.
- **Creating or editing meetings or transcripts**: Granola exposes
  read-only tools. Write operations don't exist via this surface.
- **Searching Drive documents** that aren't Granola transcripts: use
  `drive-rag-curl` or `gws docs`. Granola only sees meetings it
  recorded.

## Prerequisites

- **Supergateway bridge must be running**. Verify:

  ```bash
  curl -sS http://localhost:8089/mcp \
       -H 'Content-Type: application/json' \
       -H 'Accept: application/json,text/event-stream' \
       -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 200
  ```

  The supergateway runs as `npm exec mcp-remote
  https://mcp.granola.ai/mcp` under the user's launchctl. If it's
  down, restart the launchd plist:

  ```bash
  launchctl kickstart -k gui/$UID/com.ai-pa.supergateway-granola
  ```

- **OAuth tokens at `.granola-tokens.json`** must be valid (6h
  expiry; refresh via `scripts/granola-oauth.py --refresh`). The
  supergateway uses these transparently.

- `jq` must be installed.

## Subcommands

### Query (open-ended Q&A)

```bash
# Natural-language query over all meetings in scope
granola query "what was decided about the FY26 budget?"

# Scope to specific meetings by UUID
granola query "what action items did I commit to?" \
        --document-ids a1b2c3d4-...,e5f6g7h8-...
```

The response is Markdown with inline citations `[[N]](url)`. Preserve
the citation syntax verbatim when surfacing the answer to the user —
the user clicks through to verify.

`query` is a real LLM call; expect 5-30s. Override timeout via
`GRANOLA_TIMEOUT=300 granola query ...` if you have a complex query.

### List meetings

```bash
# Predefined ranges
granola list --range this_week
granola list --range last_week
granola list --range last_30_days

# Custom date range
granola list --range custom --start 2026-04-01 --end 2026-04-30

# Scope to a folder
granola list --range last_30_days --folder 5cc4b5d1-df20-4d26-bc3e-...
```

Returns an XML-style payload:

```xml
<meetings_data from="May 24, 2026" to="May 28, 2026" count="14">
  <meeting id="..." title="..." date="...">
    <known_participants>...</known_participants>
  </meeting>
  ...
</meetings_data>
```

If you need to extract meeting IDs for follow-up calls, grep them:

```bash
granola list --range last_week | grep -oE 'id="[^"]+"' | sed 's/id="//; s/"$//'
```

### Folders

```bash
granola folders | jq '.folders[] | {id, title, note_count}'
```

Returns 8 standard folders + any user-created. Use the `id` field as
input to `list --folder`.

### Get meetings (by ID)

```bash
granola get a1b2c3d4-... b5c6d7e8-... | jq '.[] | {id, title, date}'
```

Batch fetch of meeting metadata (multiple IDs accepted as separate
positional args).

### Transcript

```bash
granola transcript a1b2c3d4-... | jq -r '.transcript'
```

Returns full transcript JSON. Pipe through `jq -r` for plain text.

### Account info

```bash
granola account
```

Returns email and active workspace ID/name. Useful for confirming
which Granola account the supergateway is authenticated as.

### Health

```bash
granola health
```

Probes the supergateway by issuing a `tools/list` JSON-RPC. Returns
`{"status":"healthy", ...}` or exits non-zero on failure.

## Pattern: meeting prep workflow

When the user asks *"prepare me for my meeting with X tomorrow"*:

```bash
# 1. Find their recent meetings with X
granola query "recent meetings with X" --document-ids "$(granola list --range last_30_days | grep -B2 -A2 'X' | grep -oE 'id=\"[^\"]+\"' | sed 's/id=\"//; s/\"$//' | tr '\n' ',' | sed 's/,$//')"

# 2. For the most relevant one, pull the transcript
granola transcript <meeting_id>

# 3. Ask the model for highlights (back in MC's reasoning):
#    "Given the transcript above, what should Chad re-read before
#     tomorrow's meeting?"
```

## Pattern: extract action items across a date range

```bash
granola query "what action items did I commit to in the last two weeks?" \
        | tee /tmp/granola-actions.md

# Pipe into tasks-agent for processing (when tasks-agent migrates):
# tasks-extract --from-markdown /tmp/granola-actions.md
```

## Failure modes + remediation

- **`supergateway unreachable at http://localhost:8089`**: bridge not
  running. Check launchctl: `launchctl list | grep supergateway`. If
  loaded but not responding, kick it: `launchctl kickstart -k
  gui/$UID/com.ai-pa.supergateway-granola`.

- **Timeout on `query`**: the LLM call exceeded `GRANOLA_TIMEOUT`
  (default 180s). Either narrow the query (`--document-ids` to scope),
  or bump: `GRANOLA_TIMEOUT=300 granola query ...`.

- **MCP error in response**: usually OAuth expired. Refresh tokens:
  `scripts/granola-oauth.py --refresh`. Then retry.

- **Empty `folders` or `list` result**: account auth might be wrong
  workspace. Confirm with `granola account` — should show
  `cdorsey@concord.org` + Concord Consortium workspace.

## Migration history

- **Before 2026-05-30**: agents accessed Granola via the
  `query_granola_meetings` Letta tool plus 5 siblings, each
  registered separately. The Letta server held the tool runtime;
  agents called via the standard tool-call → server-side execution
  path.
- **2026-05-30**: this CLI shipped. The Letta tools still exist
  during the migration window; once Docs-and-Transcripts agent
  flips to local mode, the tools can be detached and the CLI is
  the canonical surface. Other agents (MC, Tasks) will follow.

## Validation history

- **2026-05-30** — Shipped + smoke-tested all 6 subcommands + health:
  - `health` returns `healthy` JSON
  - `account` returns Chad's email + Concord Consortium workspace
  - `folders` returns 8 folders, jq-pipeable
  - `list --range this_week` returns 14 meetings in XML format
  - `query "what was discussed about the Spark Glasses project this
    week?"` returns a properly-formatted Markdown answer with the
    real meeting context (9 seconds for the LLM round-trip)
  - `--help` renders cleanly
  - Unknown subcommand → error + exit 2
  - Missing required args → clear error + exit 2
