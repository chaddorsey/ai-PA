# Drive Watch — Targeted Document Monitoring

**Status:** Planned
**Created:** 2026-04-16
**Estimated effort:** 4-6 hours
**Risk:** Low (additive — no changes to existing sync pipeline)

---

## Problem

The current drive-rag sync pipeline monitors **all** indexed documents via the Changes API on a 10-minute cron cycle. There's no way to say "watch this specific spreadsheet closely and notify me when it changes with the exact diff." The user wants per-document monitoring with:

1. **Timely detection** — faster than the 10-minute global sweep for priority files
2. **Content-level diff** — not just "it changed" but "what specifically changed" (cells, rows, values)
3. **Push notification** — proactive alert via Slack or Letta agent, not a poll-and-check

## Existing Infrastructure to Build On

| Component | What it does | Where |
|---|---|---|
| `ingest_document` | Fetches content, creates snapshot, chunks, embeds | `drive-rag-service/src/drive_rag/ingestion.py` |
| Snapshots | Full content stored per {file_id, revision_id} as gzip JSON on disk | `/Volumes/main-filestore/ai-PA-data/drive-rag-snapshots/` |
| `/v1/diff/{file_id}` | Compares two snapshots and returns structural diff | `drive-rag-service/src/drive_rag/main.py:648`, `differ.py` |
| `/v1/edits/{file_id}` | Returns per-block edit history across revisions | `drive-rag-service/src/drive_rag/main.py:486` |
| `document_revisions` table | Who modified when, per revision | `rag.document_revisions` in Postgres |
| Google `files.get` | Single-file metadata check (cheap, fast, ~100ms) | `drive_rag/auth.py` (GoogleClient) |
| `send_slack_dm` tool | Letta agent → Slack DM delivery | Already attached to tasks-agent-sleeptime |
| Scheduler service | Cron job management | `http://localhost:8087/v1/jobs` |

## Design

### New Components

**1. Watchlist table: `rag.watched_files`**

```sql
CREATE TABLE rag.watched_files (
    file_id        TEXT PRIMARY KEY,
    label          TEXT,               -- human-friendly name ("Kate's tracking sheet")
    poll_interval  INTEGER DEFAULT 120, -- seconds between checks
    notify_via     TEXT DEFAULT 'slack', -- 'slack', 'letta', 'both'
    notify_target  TEXT,               -- Slack channel/user ID or agent ID
    diff_mode      TEXT DEFAULT 'auto', -- 'auto', 'full', 'summary'
    enabled        BOOLEAN DEFAULT true,
    last_checked   TIMESTAMPTZ,
    last_revision  TEXT,               -- headRevisionId at last check
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
```

**2. New drive-rag-service endpoints**

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/watch` | List all watched files |
| POST | `/v1/watch` | Add a file to the watchlist |
| DELETE | `/v1/watch/{file_id}` | Remove a file from the watchlist |
| POST | `/v1/watch/poll` | Manually trigger a poll cycle (also called by cron) |

**3. Poll logic (`watch_poller.py`)**

New module. Called by the `/v1/watch/poll` endpoint and a dedicated cron job.

```
for each enabled file in rag.watched_files:
    if now - last_checked < poll_interval: skip
    
    current_revision = google.get_file_metadata(file_id).headRevisionId
    if current_revision == last_revision: update last_checked, skip
    
    # Change detected
    ingest_document(file_id, force=True)  # creates new snapshot + chunks
    
    diff = compute_diff(file_id, old_revision, current_revision)
    
    notify(file, diff)  # Slack DM or Letta agent message
    
    update last_checked, last_revision
```

**4. Spreadsheet-aware diff**

The existing `differ.py` operates on normalized blocks (designed for Google Docs structure). For spreadsheets (exported as CSV), we need a lightweight cell-level diff:

- Parse old CSV snapshot and new CSV snapshot
- Diff rows: added, removed, modified
- For modified rows: highlight which cells changed and their old → new values
- Return as structured JSON suitable for a Slack Block Kit message

This can be a small addition to `differ.py` — a `diff_csv(old_text, new_text)` function that the watch poller calls when `mime_type == spreadsheet`.

**5. Notification**

For Slack delivery: format the diff into a Block Kit message via `send_slack_dm` (already exists). Template:

```
📊 *Watched file updated:* Kate's tracking sheet
*Modified by:* Kate Grigsby · 2 min ago
*Changes:*
  • Row 12 "Budget" column: $45,000 → $52,000
  • Row 15 added: "New vendor: Acme Corp"
  • 3 other cell changes (details in thread)
```

For Letta delivery: send as a system message to the specified agent with structured diff data.

**6. Scheduler cron job**

Register one new job:

```json
{
    "title": "Drive Watch: Priority file poll",
    "schedule_expression": {"cron": "*/2 * * * *"},
    "actions": [{
        "action_type": "http",
        "config": {
            "method": "POST",
            "url": "http://drive-rag-service:8000/v1/watch/poll",
            "timeout": 30,
            "retries": 0
        }
    }]
}
```

Every 2 minutes. The poll endpoint is fast (~100ms per file for the revision check) so even 10+ watched files complete well within the timeout. Only files whose `poll_interval` has elapsed since `last_checked` are actually checked.

### What This Does NOT Do

- **Real-time push** — still poll-based (2 min minimum). Google Drive webhooks (Phase B) would be needed for sub-minute latency.
- **Collaborative edit tracking** — doesn't identify which collaborator made which cell change within a single revision (Google Docs API doesn't expose this at cell granularity for Sheets).
- **Undo/revert** — read-only monitoring, no write-back capability.

## Implementation Sequence

| Step | Task | Depends on | Effort |
|---|---|---|---|
| 1 | Create `rag.watched_files` table via migration | — | 15 min |
| 2 | Implement `watch_poller.py` (poll logic + revision check) | Step 1 | 1 hr |
| 3 | Add `/v1/watch` CRUD endpoints to `main.py` | Step 1 | 30 min |
| 4 | Add `diff_csv()` to `differ.py` for spreadsheet diffs | — | 1 hr |
| 5 | Add Slack notification formatter (Block Kit template) | Step 4 | 45 min |
| 6 | Wire notification delivery in watch_poller (Slack + Letta) | Steps 2, 5 | 30 min |
| 7 | Register scheduler cron job | Step 3 | 10 min |
| 8 | Add a sidebar UI element or CLI for managing the watchlist | Step 3 | 1 hr (optional) |

Steps 1-7 are the core. Step 8 is quality-of-life.

## Testing Plan

1. Add a test spreadsheet to the watchlist via `POST /v1/watch`
2. Edit the spreadsheet in Google Sheets
3. Wait ≤2 min for the poll cycle
4. Verify: new snapshot created, diff computed, Slack DM received with cell-level changes
5. Verify: editing a non-watched file does NOT trigger notifications
6. Verify: disabling a watched file stops polling

## Future Extensions (Phase B)

- **Google Drive webhooks** (`changes.watch`) for sub-minute detection on watched files
- **Conditional alerts** — only notify if specific cells/columns change (e.g., "alert me when the Budget column changes but not when Notes change")
- **Digest mode** — batch changes over N minutes into one notification instead of firing per-revision
- **pa-web-ui integration** — "Watch this file" button in the sidebar, watchlist dashboard
