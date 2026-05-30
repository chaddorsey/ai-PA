---
description: Atlassian Rovo CLI (Jira + Confluence). Wraps the 30+ MCP tools surfaced by the local supergateway bridge (mcp-remote → https://mcp.atlassian.com/v1/mcp). Replaces the run_atlassian Letta tool with a Bash-callable surface — and intentionally exposes a `call <tool> <args>` escape hatch for tools that don't yet have named subcommands.
applies-to: any local-mode agent that needs to query or write to Jira issues / Confluence pages. Primary users: MC (Jira triage, project status queries), Pulse Agent (issue activity monitoring).
replaces:
  - run_atlassian (Letta tool — covered ~30 underlying MCP operations)
  - getAccessibleAtlassianResources (MCP tool)
  - searchJiraIssuesUsingJql (MCP tool)
  - searchConfluenceUsingCql (MCP tool)
  - getJiraIssue (MCP tool)
  - getConfluencePage (MCP tool)
  - addCommentToJiraIssue (MCP tool)
  - …and other MCP tools accessed via `atlassian call`
cli: scripts/atlassian
---

# Atlassian CLI Skill

## When to use

- **Find Jira issues by JQL**: `atlassian jql "project = INGEST AND
  status = 'In Progress'"`. Standard JQL syntax.
- **Find Confluence pages by CQL**: `atlassian cql 'space = "DEV"
  AND title ~ "FY26"'`. Standard CQL syntax.
- **Fetch one Jira issue or Confluence page** by key/ID: `atlassian
  issue INGEST-42` or `atlassian page 12345`.
- **Add a Jira comment**: `atlassian comment-add INGEST-42 "..."`.
- **Discover accessible workspaces** (cloud_id values needed by
  multi-tenant calls): `atlassian resources`.
- **Discover the full tool surface** (the underlying MCP server
  exposes ~30 tools; the CLI surfaces the most common as named
  subcommands but new ones land all the time): `atlassian tools`.
- **Call any MCP tool not yet wrapped as a subcommand**: `atlassian
  call <tool-name> '{"arg":"value"}'`.

This skill replaces the legacy `run_atlassian` Letta tool plus the
individual `mcp__Atlassian__*` operations it dispatched. Both routes
go through the same supergateway → mcp-remote → Atlassian MCP server
path; the CLI is the shape local-mode agents call.

## When NOT to use

- **Editing/creating pages or issues that involve interactive
  approval flows** — the CLI is suitable for headless operations.
  Anything that requires the user to review before final submit
  should go through MC's normal "draft → user confirms → execute"
  pattern, not blind CLI calls.
- **Bulk Jira operations on the production project tracker** — use
  the CLI for targeted reads; coordinate with the team before
  scripted batch writes.

## Prerequisites

- **supergateway-atlassian launchd service running**:

  ```bash
  launchctl list | grep atlassian
  # Should show running with PID, exit code 0
  ```

- **Valid OAuth tokens** at `~/.atlassian-rovo-token.txt` + the
  underlying `~/.mcp-auth/mcp-remote-0.1.36/01910c24c5f2edcaf999bd1eaaeaeee8_*`
  cache. mcp-remote refreshes lazily on 401 during real traffic;
  if the refresh-token has expired, the supergateway crashes on
  startup with `"Refreshed token is still invalid"` and an
  interactive re-auth is required (see [Re-auth procedure](#re-auth-procedure)
  below).

- `jq` installed.

## Subcommands

### resources

```bash
atlassian resources | jq '.[] | {id, name, url}'
```

Returns the workspaces (Atlassian "sites") your authorized user can
access. Each has a `cloudId` you can pass to other subcommands via
`--cloud-id`. Most users have one workspace; use `--cloud-id` only
when needed.

### jql (Jira search)

```bash
# Basic
atlassian jql "project = INGEST AND status = 'In Progress'"

# Limit + workspace + field selection
atlassian jql "assignee = currentUser() AND updated > -7d" \
  --limit 20 --fields summary,status,priority,updated

# Pipe into jq for further filtering
atlassian jql "project = INGEST" --limit 100 \
  | jq '.issues[] | select(.fields.priority.name == "High") | {key, summary: .fields.summary}'
```

### cql (Confluence search)

```bash
atlassian cql 'space = "DEV" AND title ~ "FY26"'
atlassian cql 'creator = currentUser() AND lastModified > now("-30d")'
```

### issue (fetch one Jira issue)

```bash
atlassian issue INGEST-42 \
  --fields summary,description,status,assignee,priority,labels

# Full issue with everything (large payload)
atlassian issue INGEST-42
```

### page (fetch one Confluence page)

```bash
atlassian page 12345 | jq '{title, body: .body.storage.value}'
```

### comment-add (post a Jira comment)

```bash
atlassian comment-add INGEST-42 "Confirmed in standup — merging today."
```

The comment is posted immediately. For drafts that should be
reviewed first, build the comment text via the agent's normal flow
and only call `comment-add` after the user confirms.

### tools (discover the full MCP surface)

```bash
atlassian tools | jq '.[] | {name, title}'
```

Returns every MCP tool the supergateway-bridged Atlassian server
exposes. Use this when the CLI's named subcommands don't cover what
you need — then use `call` to invoke directly.

### call (raw escape hatch)

```bash
atlassian call searchJiraIssuesUsingJql '{"jql":"project = INGEST","maxResults":5}'
atlassian call createJiraIssue '{"projectKey":"INGEST","summary":"...","issueType":{"name":"Task"}}'
```

`call` lets you invoke any MCP tool by name with raw JSON arguments.
Use `tools` first to discover names; the MCP server's tool list is
authoritative.

### health

```bash
atlassian health
# → {"status":"healthy", "tools_responsive":true, ...}
# or → unhealthy + diagnostic next steps + exit 4
```

## Re-auth procedure

When `health` reports unhealthy AND the launchd log
(`/tmp/supergateway-atlassian-launchd.log`) shows
`"Refreshed token is still invalid"` repeated every 10 seconds, the
OAuth refresh-token has expired. mcp-remote can't recover this on its
own; the user must do a browser-based re-auth:

```bash
# 1. Stop the launchd job so it stops crashing
launchctl bootout gui/$(id -u)/com.ai-pa.supergateway-atlassian

# 2. Clear stale lock file (if present)
rm -f ~/.mcp-auth/mcp-remote-0.1.36/01910c24c5f2edcaf999bd1eaaeaeee8_lock.json

# 3. Run mcp-remote interactively to trigger the OAuth flow
cd /Volumes/main-drive/ai-PA/jira-rovo-server
npx mcp-remote "https://mcp.atlassian.com/v1/mcp"
# → opens https://auth.atlassian.com/authorize?... in your browser
# → sign in to Atlassian, click Allow
# → mcp-remote prints "Connection established" — Ctrl+C

# 4. Sync the freshly-extracted token into the cached .txt
node jira-rovo-server/extract-token-from-mcp-auth.js

# 5. Restart the launchd job
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ai-pa.supergateway-atlassian.plist

# 6. Verify
atlassian health
atlassian resources
```

Token refresh-tokens themselves have an expiry (typically several
months); when the refresh chain breaks like this it usually means
either a long idle period or an Atlassian-side policy change.

## Pattern: standup triage

When the user asks *"what's on my plate this morning?"*:

```bash
# All issues assigned to me, recently updated
atlassian jql "assignee = currentUser() AND updated > -3d" \
  --fields summary,status,priority \
  | jq '.issues | map({key, summary: .fields.summary, status: .fields.status.name, priority: .fields.priority.name})'
```

## Pattern: project status summary

```bash
# Open issues in a project by status
atlassian jql "project = INGEST AND statusCategory != Done" --limit 100 \
  | jq '.issues | group_by(.fields.status.name) | map({status: .[0].fields.status.name, count: length})'
```

## Failure modes + remediation

- **`supergateway unreachable at http://localhost:8091`**: bridge
  not running. `atlassian health` provides next-step guidance. Most
  common cause: OAuth refresh-token expired — see [Re-auth procedure](#re-auth-procedure).

- **`MCP error: ...`**: the MCP server returned a JSON-RPC error
  (usually a 4xx-equivalent). Common causes:
  - Invalid JQL/CQL syntax: validate against Atlassian's reference
    grammar.
  - Missing required arg: check `atlassian tools` for the schema.
  - Permission denied: the OAuth grant covers a specific scope set;
    some operations may not be authorized.

- **Empty JQL/CQL result**: query returned 0 hits — not an error.
  Verify project/space exists and you have access (`atlassian
  resources`).

- **Tool not found**: the named subcommand maps to an MCP tool that
  doesn't exist on this server version. Use `atlassian tools` to
  discover the actual names + use `atlassian call` to invoke.

## Migration history

- **Pre-2026-05-30**: agents called the `run_atlassian` Letta tool,
  which dispatched to ~30 underlying MCP operations via the
  supergateway bridge. The tool lived in the Letta-server tool
  runtime.

- **2026-05-30**: this CLI shipped. Surface includes named
  subcommands for the most common 6 operations + a `call` escape
  hatch + `tools` discovery for the rest. Built against the same
  supergateway bridge (port 8091), so any working route through
  the supergateway works here too.

  At the time of shipping, the supergateway service was crashing
  with expired OAuth — re-auth was required for end-to-end smoke.
  Static smokes (help, error paths, argument validation, JSON
  shape) all pass.

## Validation history

- **2026-05-30** — Shipped + static smoke-tested:
  - `--help` renders cleanly
  - `health` correctly reports `unhealthy` (the supergateway is
    down due to expired OAuth at the time of building) with a
    structured 4-line diagnostic next-steps block to stderr and
    exits 4
  - Argument-validation errors fire cleanly: `jql` without query,
    `issue` without key, `comment-add` without text, `call` with
    invalid JSON — all error + exit 2
  - Unknown subcommand errors out
  - `bash -n` passes (no syntax errors)
  - **End-to-end smoke deferred** until OAuth re-auth — the CLI
    structure mirrors the working `granola` CLI's supergateway+MCP
    pattern; once OAuth is refreshed, the same JSON-RPC tools/call
    flow works.
