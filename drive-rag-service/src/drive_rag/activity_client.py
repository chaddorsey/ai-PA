"""Google Drive Activity API v2 client for staleness detection.

Polls the Activity API to detect edits, creates, renames, moves, and deletes
across ALL indexed files -- including files shared from other users' personal
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
    from datetime import timedelta

    from drive_rag.ingestion import ingest_document

    start = time.monotonic()
    google = google_client or get_google_client()
    database = db or get_db()
    result = ActivityPollResult()

    try:
        # Build time filter: activities after (now - since_minutes)
        since_dt = datetime.now(timezone.utc).replace(microsecond=0)
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
