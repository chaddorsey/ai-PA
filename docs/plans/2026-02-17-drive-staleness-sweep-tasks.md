# Drive Staleness Sweep Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect and re-ingest stale documents across 44K indexed Drive files, including the 71% invisible to the Changes API.

**Architecture:** Two-layer detection — Activity API v2 poller (fast path, every 5 min) + tiered metadata sweep (safety net, hot/warm/cool/cold). Both layers trigger existing `ingest_document()`. Data stored via PostgREST HTTP client against Supabase `rag` schema.

**Tech Stack:** Python/FastAPI, Google Drive Activity API v2, Google Drive API v3 batch requests, PostgREST/Supabase, httpx, structlog

**Design Doc:** `docs/plans/2026-02-17-drive-staleness-sweep-design.md`

**Important context:**
- Service runs in Docker (`drive-rag-service`), code at `drive-rag-service/src/drive_rag/`
- DB is PostgREST (HTTP client in `db.py`), NOT SQLAlchemy — all queries are HTTP requests
- Auth uses `GoogleClient` singleton (`auth.py`) with lazy-init properties
- No existing test suite — verify via curl/httpie against running container
- All endpoints are async (FastAPI)
- Rebuild+restart after code changes: `docker compose up -d --build drive-rag-service`

---

### Task 1: Schema Migration — Add Staleness Columns

**Files:**
- Create: `drive-rag-service/migrations/003_staleness_columns.sql`

**Step 1: Write the migration SQL**

```sql
-- Migration 003: Add staleness sweep columns to document_state
--
-- Supports two-layer staleness detection:
-- 1. Activity API poller (writes to document_activity, updates last_activity_at)
-- 2. Tiered metadata sweep (uses staleness_tier, last_checked_at, check_count)

ALTER TABLE rag.document_state
  ADD COLUMN IF NOT EXISTS staleness_tier text NOT NULL DEFAULT 'cold',
  ADD COLUMN IF NOT EXISTS last_checked_at timestamp with time zone,
  ADD COLUMN IF NOT EXISTS last_activity_at timestamp with time zone,
  ADD COLUMN IF NOT EXISTS check_count integer NOT NULL DEFAULT 0;

-- Index for sweep candidate queries: "give me all 'hot' tier docs ordered by least recently checked"
CREATE INDEX IF NOT EXISTS idx_doc_state_staleness_tier
  ON rag.document_state (staleness_tier, last_checked_at ASC NULLS FIRST);

-- Add activity_poll_state to change_sync_state for tracking Activity API cursor
-- We reuse the same table with a different state_id ('activity_poll')
```

**Step 2: Apply the migration**

Run:
```bash
docker exec supabase-db psql -U postgres -d postgres -f /dev/stdin <<'SQL'
ALTER TABLE rag.document_state
  ADD COLUMN IF NOT EXISTS staleness_tier text NOT NULL DEFAULT 'cold',
  ADD COLUMN IF NOT EXISTS last_checked_at timestamp with time zone,
  ADD COLUMN IF NOT EXISTS last_activity_at timestamp with time zone,
  ADD COLUMN IF NOT EXISTS check_count integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_doc_state_staleness_tier
  ON rag.document_state (staleness_tier, last_checked_at ASC NULLS FIRST);
SQL
```

Expected: `ALTER TABLE` and `CREATE INDEX` success messages.

**Step 3: Verify columns exist**

Run:
```bash
docker exec supabase-db psql -U postgres -d postgres -c "\d rag.document_state" | grep -E "staleness_tier|last_checked_at|last_activity_at|check_count"
```

Expected: Four new columns visible.

**Step 4: Commit**

```bash
git add -f drive-rag-service/migrations/003_staleness_columns.sql
git commit -m "feat: add staleness sweep columns to document_state"
```

---

### Task 2: Fix Stats Endpoint Bug

**Files:**
- Modify: `drive-rag-service/src/drive_rag/db.py` (add `get_document_count()`)
- Modify: `drive-rag-service/src/drive_rag/main.py:311-329` (fix `/v1/stats`)

**Step 1: Add `get_document_count()` to Database**

Add this method to the `Database` class in `db.py`, in the Document State Operations section (after `get_indexed_documents`):

```python
def get_document_count(self) -> int:
    """Get total count of indexed documents.

    Returns:
        Number of documents in document_state
    """
    response = self.client.get(
        self._url("document_state"),
        params={"select": "drive_file_id", "limit": "0"},
        headers={
            **self.client.headers,
            "Prefer": "count=exact",
        },
    )
    self._check_response(response, "get_document_count")

    content_range = response.headers.get("Content-Range", "")
    if "/" in content_range:
        try:
            return int(content_range.split("/")[1])
        except (ValueError, IndexError):
            pass
    return 0
```

This follows the exact same pattern as the existing `get_chunk_count()` method.

**Step 2: Fix the stats endpoint in main.py**

Replace lines 311-329 in `main.py`:

```python
@app.get("/v1/stats")
async def get_index_stats():
    """Get overall index statistics."""
    db = get_db()

    total_documents = db.get_document_count()
    total_chunks = db.get_chunk_count()

    return {
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "avg_chunks_per_document": (
            total_chunks / total_documents if total_documents else 0
        ),
    }
```

**Step 3: Rebuild and verify**

Run:
```bash
docker compose up -d --build drive-rag-service
sleep 5
curl -s http://localhost:8095/v1/stats | python3 -m json.tool
```

Expected: `total_documents` should show ~44,353 (not 1000).

**Step 4: Commit**

```bash
git add drive-rag-service/src/drive_rag/db.py drive-rag-service/src/drive_rag/main.py
git commit -m "fix: stats endpoint now returns correct document count"
```

---

### Task 3: Add Staleness DB Methods

**Files:**
- Modify: `drive-rag-service/src/drive_rag/db.py`

Add these methods to the `Database` class. Place them in a new section after the Change Sync State section:

**Step 1: Add staleness query methods**

```python
# =====================
# Staleness Sweep Operations
# =====================

def get_sweep_candidates(
    self, tier: str, limit: int = 500
) -> list[dict]:
    """Get documents due for a metadata check in the given tier.

    Returns documents ordered by least-recently-checked first,
    so documents never checked (last_checked_at IS NULL) come first.

    Args:
        tier: Staleness tier (hot, warm, cool, cold)
        limit: Maximum documents to return

    Returns:
        List of dicts with drive_file_id and modified_time
    """
    response = self.client.get(
        self._url("document_state"),
        params={
            "staleness_tier": f"eq.{tier}",
            "select": "drive_file_id,modified_time",
            "order": "last_checked_at.asc.nullsfirst",
            "limit": str(limit),
        },
    )
    self._check_response(response, "get_sweep_candidates")
    return response.json() or []

def update_staleness_check(
    self,
    file_id: str,
    new_tier: str,
    check_count: int,
    last_activity_at: Optional[str] = None,
) -> None:
    """Update staleness tracking after a metadata check.

    Args:
        file_id: Google Drive file ID
        new_tier: New staleness tier
        check_count: Updated consecutive-no-change count
        last_activity_at: ISO timestamp if activity was detected
    """
    data: dict = {
        "staleness_tier": new_tier,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
        "check_count": check_count,
    }
    if last_activity_at:
        data["last_activity_at"] = last_activity_at

    response = self.client.patch(
        self._url("document_state"),
        params={"drive_file_id": f"eq.{file_id}"},
        json=data,
    )
    self._check_response(response, "update_staleness_check")

def get_staleness_stats(self) -> dict:
    """Get tier distribution and sweep status.

    Returns:
        Dict with tier counts, last check times, etc.
    """
    tiers = {}
    for tier in ("hot", "warm", "cool", "cold"):
        response = self.client.get(
            self._url("document_state"),
            params={
                "staleness_tier": f"eq.{tier}",
                "select": "drive_file_id",
                "limit": "0",
            },
            headers={
                **self.client.headers,
                "Prefer": "count=exact",
            },
        )
        self._check_response(response, f"get_staleness_stats_{tier}")
        content_range = response.headers.get("Content-Range", "")
        count = 0
        if "/" in content_range:
            try:
                count = int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass
        tiers[tier] = count

    # Count never-checked documents
    response = self.client.get(
        self._url("document_state"),
        params={
            "last_checked_at": "is.null",
            "select": "drive_file_id",
            "limit": "0",
        },
        headers={
            **self.client.headers,
            "Prefer": "count=exact",
        },
    )
    self._check_response(response, "get_staleness_stats_unchecked")
    content_range = response.headers.get("Content-Range", "")
    never_checked = 0
    if "/" in content_range:
        try:
            never_checked = int(content_range.split("/")[1])
        except (ValueError, IndexError):
            pass

    return {
        "tiers": tiers,
        "total": sum(tiers.values()),
        "never_checked": never_checked,
    }

def bulk_promote_tier(self, file_ids: list[str], tier: str) -> None:
    """Promote multiple documents to a higher tier (e.g., after Activity API detects changes).

    Args:
        file_ids: List of Drive file IDs
        tier: Target tier (usually 'hot')
    """
    if not file_ids:
        return

    now = datetime.now(timezone.utc).isoformat()

    for file_id in file_ids:
        response = self.client.patch(
            self._url("document_state"),
            params={"drive_file_id": f"eq.{file_id}"},
            json={
                "staleness_tier": tier,
                "last_activity_at": now,
                "check_count": 0,
            },
        )
        # Don't raise on individual failures
        if response.status_code >= 400:
            logger.warning(
                "bulk_promote_failed",
                file_id=file_id,
                status=response.status_code,
            )
```

**Step 2: Verify it compiles**

```bash
docker compose up -d --build drive-rag-service
sleep 5
curl -s http://localhost:8095/health
```

Expected: `{"status": "healthy", "service": "drive-rag-service"}`

**Step 3: Commit**

```bash
git add drive-rag-service/src/drive_rag/db.py
git commit -m "feat: add staleness sweep DB methods"
```

---

### Task 4: Activity API Client

**Files:**
- Create: `drive-rag-service/src/drive_rag/activity_client.py`
- Modify: `drive-rag-service/src/drive_rag/auth.py` (add `activity` property to `GoogleClient`)

**Step 1: Add `activity` property to GoogleClient**

In `auth.py`, add to the `GoogleClient` class after the `sheets` property:

```python
@property
def activity(self) -> Resource:
    """Get Drive Activity API service (lazy initialization)."""
    if not hasattr(self, "_activity") or self._activity is None:
        self._activity = build("driveactivity", "v2", credentials=self.creds)
    return self._activity
```

**Step 2: Create activity_client.py**

```python
"""Google Drive Activity API v2 client for staleness detection.

Polls the Activity API to detect edits, creates, renames, moves, and deletes
across ALL indexed files — including files shared from other users' personal
Drives that the Changes API cannot see.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

from drive_rag.auth import GoogleClient, get_google_client
from drive_rag.db import Database, get_db

logger = structlog.get_logger()


@dataclass
class ActivityPollResult:
    """Result of an Activity API poll cycle."""

    activities_fetched: int = 0
    indexed_files_affected: int = 0
    files_promoted: int = 0
    ingestion_triggered: int = 0
    errors: list[str] = field(default_factory=list)
    poll_duration_seconds: float = 0.0


def _extract_file_ids_from_activity(activity: dict) -> list[str]:
    """Extract Drive file IDs from an activity record.

    The Activity API returns targets as 'items/DRIVE_ITEM_ID'.

    Args:
        activity: Single activity record from the API

    Returns:
        List of file IDs referenced in this activity
    """
    file_ids = []
    for target in activity.get("targets", []):
        drive_item = target.get("driveItem", {})
        name = drive_item.get("name", "")
        # Format: "items/FILE_ID"
        if name.startswith("items/"):
            file_ids.append(name[6:])
    return file_ids


async def poll_activity(
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
    since_minutes: int = 10,
) -> ActivityPollResult:
    """Poll the Drive Activity API for recent changes and trigger re-ingestion.

    Queries all activity in the last `since_minutes` minutes, cross-references
    with indexed documents, promotes affected files to 'hot' tier, and triggers
    re-ingestion for stale files.

    Args:
        google_client: Google API client (uses singleton if not provided)
        db: Database client (uses singleton if not provided)
        since_minutes: Look back window in minutes (default 10, overlaps with 5-min cron)

    Returns:
        ActivityPollResult with statistics
    """
    import time
    from drive_rag.ingestion import ingest_document

    start = time.monotonic()
    google = google_client or get_google_client()
    database = db or get_db()
    result = ActivityPollResult()

    try:
        # Build time filter: activities after (now - since_minutes)
        since_dt = datetime.now(timezone.utc).replace(microsecond=0)
        from datetime import timedelta
        filter_time = (since_dt - timedelta(minutes=since_minutes)).isoformat() + "Z"

        # Query Activity API
        # ancestorName "items/root" captures ALL activity including shared files
        body = {
            "ancestorName": "items/root",
            "filter": f'time >= "{filter_time}"',
            "pageSize": 100,
            "consolidationStrategy": {"legacy": {}},
        }

        all_activities = []
        page_token = None

        while True:
            if page_token:
                body["pageToken"] = page_token

            response = google.activity.activity().query(body=body).execute()
            activities = response.get("activities", [])
            all_activities.extend(activities)

            page_token = response.get("nextPageToken")
            if not page_token or len(all_activities) >= 1000:
                break

        result.activities_fetched = len(all_activities)

        if not all_activities:
            result.poll_duration_seconds = time.monotonic() - start
            return result

        # Extract all file IDs from activities
        activity_file_ids = set()
        for activity in all_activities:
            activity_file_ids.update(_extract_file_ids_from_activity(activity))

        # Cross-reference with indexed documents
        indexed_affected = []
        for file_id in activity_file_ids:
            if database.document_exists(file_id):
                indexed_affected.append(file_id)

        result.indexed_files_affected = len(indexed_affected)

        if not indexed_affected:
            result.poll_duration_seconds = time.monotonic() - start
            return result

        # Promote affected files to 'hot' tier
        database.bulk_promote_tier(indexed_affected, "hot")
        result.files_promoted = len(indexed_affected)

        # Store activity records in document_activity table
        now_iso = datetime.now(timezone.utc).isoformat()
        for activity in all_activities:
            action = activity.get("primaryActionDetail", {})
            action_type = "unknown"
            for key in ("edit", "create", "rename", "move", "delete", "permissionChange"):
                if key in action:
                    action_type = key
                    break

            actors = activity.get("actors", [])
            actor_email = None
            actor_name = None
            if actors:
                user = actors[0].get("user", {}).get("knownUser", {})
                actor_email = user.get("personName", "").replace("people/", "")

            activity_time = activity.get("timestamp")

            for file_id in _extract_file_ids_from_activity(activity):
                if file_id not in indexed_affected:
                    continue
                try:
                    database.client.post(
                        database._url("document_activity"),
                        json={
                            "drive_file_id": file_id,
                            "activity_type": action_type,
                            "actor_email": actor_email,
                            "activity_time": activity_time or now_iso,
                        },
                    )
                except Exception as e:
                    logger.warning("activity_store_failed", file_id=file_id, error=str(e))

        # Trigger re-ingestion for affected files
        for file_id in indexed_affected:
            try:
                await ingest_document(
                    file_id=file_id,
                    google_client=google,
                    db=database,
                    force=True,
                )
                result.ingestion_triggered += 1
            except Exception as e:
                error_msg = f"Ingest failed for {file_id}: {str(e)}"
                result.errors.append(error_msg)
                logger.warning("activity_ingest_failed", file_id=file_id, error=str(e))

    except Exception as e:
        result.errors.append(f"Activity poll error: {str(e)}")
        logger.exception("activity_poll_error", error=str(e))

    result.poll_duration_seconds = time.monotonic() - start
    return result
```

**Step 3: Verify it compiles**

```bash
docker compose up -d --build drive-rag-service
sleep 5
curl -s http://localhost:8095/health
```

**Step 4: Commit**

```bash
git add drive-rag-service/src/drive_rag/activity_client.py drive-rag-service/src/drive_rag/auth.py
git commit -m "feat: add Activity API v2 client for staleness detection"
```

---

### Task 5: Staleness Sweep Logic

**Files:**
- Create: `drive-rag-service/src/drive_rag/staleness.py`

**Step 1: Create staleness.py**

```python
"""Tiered metadata sweep for staleness detection.

Batch-checks document modifiedTime via Drive API to find stale documents.
Documents are assigned to tiers (hot/warm/cool/cold) based on how recently
they were active. Each tier has a different check interval.

Tier promotion: Activity detected → hot
Tier demotion: No changes found after N consecutive checks → demote one tier
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

from drive_rag.auth import GoogleClient, get_google_client
from drive_rag.db import Database, get_db, _deserialize_datetime

logger = structlog.get_logger()

# Consecutive no-change checks before demotion
DEMOTION_THRESHOLDS = {
    "hot": 6,    # 6 × 30min = 3 hours
    "warm": 4,   # 4 × 4hr = 16 hours
    "cool": 3,   # 3 × 24hr = 3 days
    "cold": 0,   # cold is the floor — no demotion
}

DEMOTION_TARGET = {
    "hot": "warm",
    "warm": "cool",
    "cool": "cold",
}

BATCH_SIZE = 100  # Drive API batch limit


@dataclass
class SweepResult:
    """Result of a metadata sweep for one tier."""

    tier: str = ""
    candidates_checked: int = 0
    stale_found: int = 0
    ingestion_triggered: int = 0
    promotions: int = 0
    demotions: int = 0
    errors: list[str] = field(default_factory=list)
    sweep_duration_seconds: float = 0.0


def _batch_get_metadata(
    file_ids: list[str], google: GoogleClient
) -> dict[str, Optional[dict]]:
    """Batch-fetch modifiedTime and trashed status for multiple files.

    Uses individual files.get calls (Drive batch API requires httplib2 which
    we don't use). Fetches only the fields needed for staleness comparison.

    Args:
        file_ids: List of Drive file IDs to check
        google: Google API client

    Returns:
        Dict mapping file_id → metadata dict or None if file not found/errored
    """
    results = {}
    for file_id in file_ids:
        try:
            meta = google.drive.files().get(
                fileId=file_id,
                fields="id,modifiedTime,trashed",
                supportsAllDrives=True,
            ).execute()
            results[file_id] = meta
        except Exception as e:
            error_str = str(e)
            if "404" in error_str or "notFound" in error_str:
                results[file_id] = None  # File deleted
            else:
                logger.warning("metadata_fetch_error", file_id=file_id, error=error_str)
                results[file_id] = None
    return results


async def run_sweep(
    tier: str,
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
    limit: int = 500,
) -> SweepResult:
    """Run a metadata sweep for a single tier.

    Fetches candidates, batch-checks modifiedTime against stored value,
    triggers re-ingestion for stale files, and manages tier transitions.

    Args:
        tier: Which tier to sweep (hot, warm, cool, cold)
        google_client: Google API client (uses singleton if not provided)
        db: Database client (uses singleton if not provided)
        limit: Max documents to check in this sweep

    Returns:
        SweepResult with statistics
    """
    import time
    from drive_rag.ingestion import ingest_document

    start = time.monotonic()
    google = google_client or get_google_client()
    database = db or get_db()
    result = SweepResult(tier=tier)

    try:
        # Get candidates for this tier
        candidates = database.get_sweep_candidates(tier, limit=limit)
        result.candidates_checked = len(candidates)

        if not candidates:
            result.sweep_duration_seconds = time.monotonic() - start
            return result

        # Batch check metadata
        file_ids = [c["drive_file_id"] for c in candidates]

        # Process in batches
        for batch_start in range(0, len(file_ids), BATCH_SIZE):
            batch_ids = file_ids[batch_start : batch_start + BATCH_SIZE]
            metadata_map = _batch_get_metadata(batch_ids, google)

            for file_id in batch_ids:
                meta = metadata_map.get(file_id)

                if meta is None:
                    # File not found or error — mark check done, keep tier
                    database.update_staleness_check(
                        file_id=file_id,
                        new_tier=tier,
                        check_count=0,
                    )
                    continue

                if meta.get("trashed"):
                    # File trashed — demote to cold, don't re-ingest
                    database.update_staleness_check(
                        file_id=file_id,
                        new_tier="cold",
                        check_count=0,
                    )
                    continue

                # Compare modifiedTime
                drive_modified = meta.get("modifiedTime", "")
                stored_state = database.get_document_state(file_id)
                if not stored_state:
                    continue

                stored_modified = stored_state.modified_time
                drive_modified_dt = _deserialize_datetime(drive_modified)

                is_stale = False
                if drive_modified_dt and stored_modified:
                    is_stale = drive_modified_dt > stored_modified
                elif drive_modified_dt and not stored_modified:
                    is_stale = True  # Never had a stored time

                if is_stale:
                    result.stale_found += 1

                    # Promote to hot
                    now_iso = datetime.now(timezone.utc).isoformat()
                    database.update_staleness_check(
                        file_id=file_id,
                        new_tier="hot",
                        check_count=0,
                        last_activity_at=now_iso,
                    )
                    result.promotions += 1

                    # Trigger re-ingestion
                    try:
                        await ingest_document(
                            file_id=file_id,
                            google_client=google,
                            db=database,
                            force=True,
                        )
                        result.ingestion_triggered += 1
                    except Exception as e:
                        result.errors.append(f"Ingest {file_id}: {str(e)}")
                        logger.warning("sweep_ingest_failed", file_id=file_id, error=str(e))
                else:
                    # Not stale — increment check count, maybe demote
                    # Get current check_count from the candidate data
                    current_count = 0
                    if stored_state:
                        # Need to read from DB since candidate select doesn't include check_count
                        response = database.client.get(
                            database._url("document_state"),
                            params={
                                "drive_file_id": f"eq.{file_id}",
                                "select": "check_count",
                            },
                        )
                        data = response.json()
                        if data:
                            current_count = data[0].get("check_count", 0)

                    new_count = current_count + 1
                    threshold = DEMOTION_THRESHOLDS.get(tier, 0)
                    target_tier = DEMOTION_TARGET.get(tier)

                    if threshold > 0 and new_count >= threshold and target_tier:
                        # Demote
                        database.update_staleness_check(
                            file_id=file_id,
                            new_tier=target_tier,
                            check_count=0,
                        )
                        result.demotions += 1
                    else:
                        # Stay in current tier
                        database.update_staleness_check(
                            file_id=file_id,
                            new_tier=tier,
                            check_count=new_count,
                        )

    except Exception as e:
        result.errors.append(f"Sweep error: {str(e)}")
        logger.exception("sweep_error", tier=tier, error=str(e))

    result.sweep_duration_seconds = time.monotonic() - start
    return result
```

**Step 2: Verify it compiles**

```bash
docker compose up -d --build drive-rag-service
sleep 5
curl -s http://localhost:8095/health
```

**Step 3: Commit**

```bash
git add drive-rag-service/src/drive_rag/staleness.py
git commit -m "feat: add tiered metadata sweep logic"
```

---

### Task 6: API Endpoints

**Files:**
- Modify: `drive-rag-service/src/drive_rag/main.py`

**Step 1: Add staleness endpoints**

Add a new section to `main.py` before the `if __name__` block (before line 1236):

```python
# =====================
# Staleness Sweep Endpoints
# =====================


@app.get("/v1/staleness/status")
async def get_staleness_status():
    """Get staleness sweep status and tier distribution.

    Returns tier counts, last check times, and sweep health metrics.
    """
    db = get_db()

    try:
        stats = db.get_staleness_stats()
        return {
            "status": "ok",
            **stats,
        }
    except Exception as e:
        logger.exception("staleness_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/staleness/poll")
async def trigger_activity_poll(
    since_minutes: int = Query(10, ge=1, le=60, description="Look-back window in minutes"),
):
    """Trigger an Activity API poll to detect recent changes.

    This is the fast path — polls Drive Activity API v2 for edits/creates
    across ALL files including shared-from-others.
    """
    from drive_rag.activity_client import poll_activity

    try:
        result = await poll_activity(since_minutes=since_minutes)
        return {
            "status": "ok",
            "activities_fetched": result.activities_fetched,
            "indexed_files_affected": result.indexed_files_affected,
            "files_promoted": result.files_promoted,
            "ingestion_triggered": result.ingestion_triggered,
            "errors": result.errors,
            "poll_duration_seconds": round(result.poll_duration_seconds, 2),
        }
    except Exception as e:
        logger.exception("activity_poll_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/staleness/sweep/{tier}")
async def trigger_metadata_sweep(
    tier: str,
    limit: int = Query(500, ge=1, le=5000, description="Max documents to check"),
):
    """Trigger a metadata sweep for a specific tier.

    Batch-checks modifiedTime from Drive API against stored values.
    Re-ingests stale documents and manages tier transitions.
    """
    from drive_rag.staleness import run_sweep

    valid_tiers = ("hot", "warm", "cool", "cold")
    if tier not in valid_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier}'. Must be one of: {', '.join(valid_tiers)}",
        )

    try:
        result = await run_sweep(tier=tier, limit=limit)
        return {
            "status": "ok",
            "tier": result.tier,
            "candidates_checked": result.candidates_checked,
            "stale_found": result.stale_found,
            "ingestion_triggered": result.ingestion_triggered,
            "promotions": result.promotions,
            "demotions": result.demotions,
            "errors": result.errors,
            "sweep_duration_seconds": round(result.sweep_duration_seconds, 2),
        }
    except Exception as e:
        logger.exception("metadata_sweep_failed", tier=tier, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 2: Rebuild and verify endpoints exist**

```bash
docker compose up -d --build drive-rag-service
sleep 5
curl -s http://localhost:8095/v1/staleness/status | python3 -m json.tool
```

Expected: JSON with tier distribution (all 44K should be 'cold' initially, never_checked = 44353).

**Step 3: Commit**

```bash
git add drive-rag-service/src/drive_rag/main.py
git commit -m "feat: add staleness sweep API endpoints"
```

---

### Task 7: Integration Smoke Test

**Step 1: Verify the full flow**

```bash
# 1. Check tier distribution
curl -s http://localhost:8095/v1/staleness/status | python3 -m json.tool

# 2. Run Activity API poll (should work even with no recent activity)
curl -s -X POST "http://localhost:8095/v1/staleness/poll?since_minutes=30" | python3 -m json.tool

# 3. Run a small cold sweep (just 5 docs)
curl -s -X POST "http://localhost:8095/v1/staleness/sweep/cold?limit=5" | python3 -m json.tool

# 4. Check stats endpoint is fixed
curl -s http://localhost:8095/v1/stats | python3 -m json.tool

# 5. Check tier distribution again (should show some movement if docs were stale)
curl -s http://localhost:8095/v1/staleness/status | python3 -m json.tool
```

**Step 2: Fix any issues found during smoke test**

If errors, check logs:
```bash
docker compose logs -f drive-rag-service --tail=50
```

**Step 3: Commit any fixes**

```bash
git add -u
git commit -m "fix: address integration test findings"
```

---

### Task 8: Register Scheduled Jobs

**Files:**
- No code changes — uses existing scheduler-service API

**Step 1: Register the cron jobs**

```bash
# Activity poll: every 5 minutes
curl -s -X POST http://localhost:8001/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(grep SCHEDULER_API_KEY .env | cut -d= -f2)" \
  -d '{
    "name": "drive-staleness-activity-poll",
    "schedule": "*/5 * * * *",
    "job_type": "http",
    "config": {
      "url": "http://drive-rag-service:8000/v1/staleness/poll?since_minutes=10",
      "method": "POST"
    },
    "enabled": true
  }' | python3 -m json.tool

# Hot sweep: every 30 minutes
curl -s -X POST http://localhost:8001/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(grep SCHEDULER_API_KEY .env | cut -d= -f2)" \
  -d '{
    "name": "drive-staleness-sweep-hot",
    "schedule": "*/30 * * * *",
    "job_type": "http",
    "config": {
      "url": "http://drive-rag-service:8000/v1/staleness/sweep/hot",
      "method": "POST"
    },
    "enabled": true
  }' | python3 -m json.tool

# Warm sweep: every 4 hours
curl -s -X POST http://localhost:8001/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(grep SCHEDULER_API_KEY .env | cut -d= -f2)" \
  -d '{
    "name": "drive-staleness-sweep-warm",
    "schedule": "0 */4 * * *",
    "job_type": "http",
    "config": {
      "url": "http://drive-rag-service:8000/v1/staleness/sweep/warm",
      "method": "POST"
    },
    "enabled": true
  }' | python3 -m json.tool

# Cool sweep: daily at 3:00 AM ET (8:00 UTC)
curl -s -X POST http://localhost:8001/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(grep SCHEDULER_API_KEY .env | cut -d= -f2)" \
  -d '{
    "name": "drive-staleness-sweep-cool",
    "schedule": "0 8 * * *",
    "job_type": "http",
    "config": {
      "url": "http://drive-rag-service:8000/v1/staleness/sweep/cool",
      "method": "POST"
    },
    "enabled": true
  }' | python3 -m json.tool

# Cold sweep: weekly Sunday 4:00 AM ET (9:00 UTC)
curl -s -X POST http://localhost:8001/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(grep SCHEDULER_API_KEY .env | cut -d= -f2)" \
  -d '{
    "name": "drive-staleness-sweep-cold",
    "schedule": "0 9 * * 0",
    "job_type": "http",
    "config": {
      "url": "http://drive-rag-service:8000/v1/staleness/sweep/cold?limit=5000",
      "method": "POST"
    },
    "enabled": true
  }' | python3 -m json.tool
```

**Step 2: Verify jobs are registered**

```bash
curl -s http://localhost:8001/api/v1/jobs \
  -H "X-API-Key: $(grep SCHEDULER_API_KEY .env | cut -d= -f2)" | \
  python3 -c "import sys,json; jobs=json.load(sys.stdin); [print(f'{j[\"name\"]}: {j[\"schedule\"]} ({\"enabled\" if j[\"enabled\"] else \"disabled\"})') for j in jobs if 'staleness' in j['name']]"
```

Expected: All 5 staleness jobs listed and enabled.

**Step 3: Commit docker-compose change from entity extraction disable**

```bash
git add docker-compose.yml
git commit -m "chore: disable entity extraction, will re-enable with cost reduction strategy"
```
