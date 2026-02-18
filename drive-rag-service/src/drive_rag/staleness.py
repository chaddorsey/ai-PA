"""Tiered metadata sweep for staleness detection.

Batch-checks document modifiedTime via Drive API to find stale documents.
Documents are assigned to tiers (hot/warm/cool/cold) based on how recently
they were active. Each tier has a different check interval.

Tier promotion: Activity detected -> hot
Tier demotion: No changes found after N consecutive checks -> demote one tier
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
    "hot": 6,    # 6 x 30min = 3 hours
    "warm": 4,   # 4 x 4hr = 16 hours
    "cool": 3,   # 3 x 24hr = 3 days
    "cold": 0,   # cold is the floor -- no demotion
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
        Dict mapping file_id -> metadata dict or None if file not found/errored
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
                    # File not found or error -- mark check done, keep tier
                    database.update_staleness_check(
                        file_id=file_id,
                        new_tier=tier,
                        check_count=0,
                    )
                    continue

                if meta.get("trashed"):
                    # File trashed -- demote to cold, don't re-ingest
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
                    # Not stale -- increment check count, maybe demote
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
