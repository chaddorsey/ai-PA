# Drive Staleness Sweep — Design Document

**Date:** 2026-02-17
**Status:** Approved

## Problem

The drive-rag-service indexes 44,353 Google Drive documents. Of these, ~71% are shared from other users' personal Drives. The Google Drive Changes API (`changes.list`) only reports changes for files in the authenticated user's own Drive and Shared Drives — making those 31,000+ shared files invisible to the existing sync mechanism.

Additionally, the stats endpoint (`GET /v1/stats`) incorrectly reports 1,000 documents due to a `limit=1000` cap bug.

## Solution

A two-layer detection system:

1. **Activity API Poller** (fast path) — Google Drive Activity API v2 detects changes across ALL files including shared-from-others. Polls every 5 minutes, catches ~90%+ of changes within minutes.

2. **Tiered Metadata Sweep** (safety net) — Batch `files.get(fields=modifiedTime)` checks against indexed documents, tiered by recency. Catches anything the Activity API misses (Google caveat: "some activity may not be reported").

Both layers trigger the existing `ingest_document()` pipeline when staleness is detected. No changes to the ingestion pipeline itself.

## Architecture

```
                 ┌─────────────────────┐
                 │  Scheduler Service   │
                 │  (cron triggers)     │
                 └────────┬────────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
    ┌───────▼────────┐         ┌───────▼────────┐
    │ Activity Poller │         │ Metadata Sweep  │
    │ (every 5 min)   │         │ (tiered crons)  │
    └───────┬────────┘         └───────┬────────┘
            │                           │
            │  file_ids with changes    │
            └─────────────┬─────────────┘
                          │
                 ┌────────▼────────┐
                 │ ingest_document()│  (existing pipeline)
                 └─────────────────┘
```

### Layer 1: Activity API Poller

- Uses Drive Activity API v2 (`driveactivity.activity.query`)
- Queries with `ancestorName: "items/root"` to cover ALL files (owned + shared)
- Filters: `detail.action_detail_case` in (EDIT, CREATE, RENAME, MOVE, DELETE)
- Writes raw activity to `document_activity` table (already exists, currently empty)
- Identifies indexed files by joining `file_id` against `document_state`
- Triggers `ingest_document(file_id, force=True)` for matches
- Tracks cursor via `filter` timestamp to avoid reprocessing

**Cost:** ~1 API call per 5 minutes = 288 calls/day (well within quotas).

### Layer 2: Tiered Metadata Sweep

Batch-checks `files.get(fields=modifiedTime,trashed)` via Drive API batch requests (100 files per batch).

| Tier | Re-check Interval | Estimated Docs | Batches/Cycle |
|------|--------------------|----------------|---------------|
| Hot  | 30 min             | ~500           | 5             |
| Warm | 4 hours            | ~3,000         | 30            |
| Cool | 24 hours           | ~15,000        | 150           |
| Cold | 7 days             | ~26,000        | 260           |

**Tier assignment rules:**
- New document → starts at `warm`
- Change detected (by either layer) → promotes to `hot`
- No change found after N checks at current tier → demotes one tier
- Demotion thresholds: hot→warm after 6 checks (3 hrs), warm→cool after 4 checks (16 hrs), cool→cold after 3 checks (3 days)

**Comparison logic:** If `modifiedTime` from Drive > `modified_time` stored in `document_state`, the file is stale → trigger `ingest_document()`.

**Daily batch budget:** Hot runs 48×/day (5 batches each = 240), warm 6×/day (30 each = 180), cool 1×/day (150), cold ~0.14×/day (260/7 ≈ 37). Total: ~607 batch requests/day ≈ 60,700 metadata checks/day.

## Data Model Changes

### New columns on `document_state`

```sql
ALTER TABLE rag.document_state
  ADD COLUMN staleness_tier TEXT NOT NULL DEFAULT 'cold',
  ADD COLUMN last_checked_at TIMESTAMPTZ,
  ADD COLUMN last_activity_at TIMESTAMPTZ,
  ADD COLUMN check_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_doc_state_staleness_tier
  ON rag.document_state (staleness_tier, last_checked_at ASC NULLS FIRST);
```

- `staleness_tier`: one of `hot`, `warm`, `cool`, `cold`
- `last_checked_at`: when the metadata sweep last checked this file
- `last_activity_at`: when the Activity API last saw activity for this file
- `check_count`: consecutive checks at current tier with no change (for demotion logic)

### `document_activity` table (existing, no changes needed)

Already defined in `001_initial_schema.sql`. Will be populated going forward by the Activity API poller. No backfill needed — it fills naturally.

## New Code Components

### `activity_client.py` — Activity API v2 Client

Location: `drive-rag-service/src/drive_rag/activity_client.py`

Responsibilities:
- Build authenticated Activity API v2 client (scope `drive.activity.readonly` already configured in `auth.py`)
- `poll_recent_activity(since: datetime) -> list[ActivityEvent]` — queries Activity API, returns parsed events
- `store_activity(events: list[ActivityEvent], db: Database)` — writes to `document_activity` table
- `get_stale_file_ids(events: list[ActivityEvent], db: Database) -> list[str]` — cross-references with `document_state` to find indexed files with new activity

### `staleness.py` — Sweep Logic

Location: `drive-rag-service/src/drive_rag/staleness.py`

Responsibilities:
- `run_activity_poll(db, google_client) -> PollResult` — orchestrates a single Activity API poll cycle
- `run_metadata_sweep(tier: str, db, google_client) -> SweepResult` — batch-checks one tier
- `get_sweep_candidates(tier: str, db) -> list[str]` — queries `document_state` for files due for check
- `batch_check_metadata(file_ids: list[str], google_client) -> list[MetadataCheck]` — Drive API batch request
- `promote_tier(file_id, db)` / `maybe_demote_tier(file_id, db)` — tier transition logic

### New API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/v1/staleness/status` | Tier distribution, last poll/sweep times, pending stale count |
| `POST` | `/v1/staleness/poll` | Manual trigger for Activity API poll |
| `POST` | `/v1/staleness/sweep/{tier}` | Manual trigger for a specific tier sweep |

### Scheduling

Via the existing scheduler-service:
- Activity poll: every 5 minutes → `POST /v1/staleness/poll`
- Hot sweep: every 30 minutes → `POST /v1/staleness/sweep/hot`
- Warm sweep: every 4 hours → `POST /v1/staleness/sweep/warm`
- Cool sweep: daily at 3:00 AM → `POST /v1/staleness/sweep/cool`
- Cold sweep: weekly on Sunday at 4:00 AM → `POST /v1/staleness/sweep/cold`

## Stats Endpoint Bugfix

`main.py` line ~321: `get_indexed_documents(limit=1000)` then `len(documents)`.

Fix: Add a `get_document_count()` method to `Database` that runs `SELECT count(*)` (via PostgREST `HEAD` request with `Prefer: count=exact`), and use it in the stats endpoint.

## Exclusions

- **No changes to existing Changes API sync** — it continues to run and handle owned/shared-drive files
- **No backfill of historical activity** — `document_activity` fills going forward
- **No changes to ingestion pipeline** — staleness detection just triggers existing `ingest_document()`
- **Entity extraction** — disabled, on hold pending cost reduction strategy
- **Snapshot retention** — unchanged

## Migration Strategy

1. Apply schema migration (new columns + index)
2. Initialize all existing documents to `staleness_tier='cold'`, `last_checked_at=NULL`
3. Deploy updated service code
4. Register scheduler jobs
5. Cold sweep will naturally process all 44K docs within the first week, promoting active ones to higher tiers

## Monitoring

The `/v1/staleness/status` endpoint provides:
- Tier distribution (how many docs in each tier)
- Last poll timestamp and result count
- Last sweep timestamp per tier
- Count of documents never checked (`last_checked_at IS NULL`)
- Count of stale documents detected in last 24 hours
