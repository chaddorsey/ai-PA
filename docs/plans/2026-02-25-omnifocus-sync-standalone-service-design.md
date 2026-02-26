# OmniFocus Sync Standalone Service Design

**Date:** 2026-02-25
**Status:** Approved
**Supersedes:** `2026-02-23-omnifocus-completion-sync-design.md` (agent-based approach)

## Problem

The current OmniFocus completion sync runs as a Letta tool triggered by scheduler `agent_message` jobs every 15 minutes. This causes:

1. **Slack noise**: The agent reports every run to the user, even when nothing changed
2. **Unnecessary agent calls**: The sync logic is 100% deterministic — no LLM reasoning needed
3. **Wasted tokens**: Every run costs agent inference regardless of outcome
4. **Batch risk**: Multiple completions at once create unpredictable agent behavior

## Approach

**Host-based standalone HTTP service** (Approach A — Granola ingest pattern).

The sync logic is extracted from `letta/sync_omnifocus_completions_tool.py` into a dedicated Python HTTP service. The scheduler fires webhook requests instead of agent messages. The agent is only involved when the user clicks [Send Reply] or [Modify] on a Slack notification.

## Architecture & Core Loop

### Service

- Host-based Python HTTP service at **port 8091**
- Managed by **launchd** (`com.ai-pa.omnifocus-sync-service`)
- Scheduler fires `POST /v1/sync` via webhook action

### Sync Flow

```
scheduler cron → POST /v1/sync → sync service
  ├─ query Letta archival for status:confirmed passages
  ├─ batch-check OmniFocus bridge (localhost:8889)
  ├─ for each completed/dropped task:
  │   ├─ transition archival passage (insert new, delete old)
  │   ├─ if external-origin → POST to slackbot /api/notify
  │   └─ if self-originated → log only, no Slack
  └─ return result summary
```

### Routing Logic

- **External-origin** (`from_person` does not contain "Chad Dorsey"): Slack notification with approval buttons
- **Self-originated** (`from_person` contains "Chad Dorsey"): Silent — log and skip Slack
- **Zero changes**: Silent — log and exit

## Notification Format & Feedback Flow

### Completed Task (External Origin)

```
┌─────────────────────────────────────────────────┐
│ ✓ Task completed in OmniFocus                   │
│                                                 │
│ *Deploy updated analytics dashboard*            │
│                                                 │
│ ┊ From: AJ Patterson                            │
│ ┊ Source: Google Doc comment on Q1 Planning      │
│ ┊ "Can you deploy the updated analytics         │
│ ┊  dashboard by Friday?"                        │
│                                                 │
│ Reply template: "Done."                         │
│                                                 │
│ [Send Reply]  [Modify]  [Skip]                  │
└─────────────────────────────────────────────────┘
```

- Source context shown in Slack **context blocks** (small gray text)
- Context pulled from the passage's `SOURCE TEXT` section (no API calls needed)
- Template: **"Done."** (no first name, no embellishment)

### Dropped Task (External Origin)

```
┌─────────────────────────────────────────────────┐
│ ⚠️ Task DROPPED in OmniFocus                     │
│                                                 │
│ *Review vendor proposal*                        │
│                                                 │
│ ┊ From: Rebecca Liu                             │
│ ┊ Source: Email thread re: Vendor Selection      │
│                                                 │
│ Reply template: "Thanks"                        │
│                                                 │
│ [Send Reply]  [Modify]  [Skip]                  │
└─────────────────────────────────────────────────┘
```

- **Prominent dropped indicator** (warning emoji + bold "DROPPED")
- Template: **"Thanks"**
- Expected to be rare (OmniFocus archives poorly)

### Self-Originated Completions

No Slack notification. Logged by the service for audit trail only.

### Feedback Routing (on button click)

The `/api/notify` payload includes a `reply_context` dict:

```json
{
  "source_type": "google-docs-comment",
  "from_person": "AJ Patterson",
  "reference_id": "meeting-abc123",
  "reply_template": "Done.",
  "routing_tool": "prepare_completion_feedback",
  "routing_args": {
    "ref_id": "a1b2c3d4",
    "source_type": "google-docs-comment",
    "reply_text": "Done."
  }
}
```

When the user clicks **[Send Reply]**, the button handler sends a message to the agent with the routing tool and args. The agent calls `prepare_completion_feedback` to dispatch the reply to the correct channel (Google Docs resolve, Slack thread, email draft).

When the user clicks **[Modify]**, a Slack modal opens for custom text. The modified text replaces `reply_text` in the routing args.

## Reliability & Crash Recovery

### State Tracking

The service is **stateless** — all durable state lives in Letta archival passages. A passage is either `status:confirmed` (needs checking) or `status:completed`/`status:dropped` (done). The insert-new-then-delete-old pattern ensures no data loss if the service crashes mid-transition.

### Idempotency

If the service crashes after inserting the new passage but before deleting the old one, the next run finds the old `status:confirmed` passage again, re-checks OmniFocus (still completed), inserts a duplicate, and deletes the old one. The duplicate is harmless.

To prevent **duplicate Slack notifications**, the service tracks notified ref_ids in `~/.omnifocus-sync/notified.json` (maps `ref_id → timestamp`). Before posting to `/api/notify`, it checks this file and skips already-notified tasks. The file is pruned on each run to remove entries older than 7 days.

### Missed-Task Prevention

OmniFocus completion status is permanent — completed tasks stay completed. A task completed while the service was down is caught on the next successful run.

### Bridge Unavailability

If the OmniFocus bridge (port 8889) is unreachable (laptop asleep, OmniFocus not running), the sync run logs a warning and exits cleanly. No passages are modified. Next run retries automatically.

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/sync` | POST | Trigger sync run (scheduler webhook target) |
| `/v1/status` | GET | Last run timestamp, result summary, service uptime |
| `/health` | GET | Health check for monitoring |

No authentication — host-only service, same as the OmniFocus bridge pattern.

`/v1/status` returns last run info persisted to `~/.omnifocus-sync/last_run.json`.

## Scheduler Migration

Replace three existing `agent_message` jobs with `webhook` jobs:

| Job | Cron | Current Action | New Action |
|-----|------|---------------|------------|
| Weekday Daytime | `*/15 11-22 * * 1-5` | `agent_message` → tasks-agent | `webhook` → `http://localhost:8091/v1/sync` |
| Weekday Overnight | `0 0-10,23 * * 1-5` | `agent_message` → tasks-agent | `webhook` → `http://localhost:8091/v1/sync` |
| Weekend | `0 */3 * * 0,6` | `agent_message` → tasks-agent | `webhook` → `http://localhost:8091/v1/sync` |

Old paused job (`c243c1e4`) deleted. Once stable, increase daytime frequency (e.g., `*/5` or `*/2`).

## Deployment

**Launchd plist**: `com.ai-pa.omnifocus-sync-service` in `~/Library/LaunchAgents/`

**Dependencies**: Python 3.11+, `httpx`, `uvicorn`, `fastapi`. No Docker.

**File layout**:
```
scripts/omnifocus_sync_service.py           # Single-file service
~/.omnifocus-sync/                          # Runtime state
  notified.json                             # Dedup tracking
  last_run.json                             # Last run status
deployment/launchd/com.ai-pa.omnifocus-sync-service.plist
```

**Logging**: stdout/stderr captured by launchd. Structured log lines with timestamps.

## Key Constants

From the existing tool:
- `ARCHIVE_ID`: `archive-f9bcaa87-7630-41c9-9694-41d46fc47d26`
- `BRIDGE_URL`: `http://localhost:8889` (host-based, not `host.docker.internal`)
- `LETTA_BASE_URL`: `http://localhost:8283`
- `AGENT_ID`: `agent-62edcfac-2cc7-41a5-a3c2-d417da393397` (tasks-agent-sleeptime)
- `SLACKBOT_URL`: `http://localhost:8081` (slackbot health check port)
- `USER_NAME`: `Chad Dorsey` (for external-origin detection)
