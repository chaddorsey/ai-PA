"""Periodic discovery of newly-shared Drive files.

Queries the Drive API for files recently shared with the authenticated user
and ingests any that aren't already in the index. This closes the gap where
the Changes API can't see files shared from other users' personal Drives.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from drive_rag.auth import GoogleClient, get_google_client
from drive_rag.db import Database, get_db

logger = structlog.get_logger()

# MIME types we index (matches ingestion.py)
SUPPORTED_MIME_TYPES = [
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/pdf",
]

DISCOVERY_STATE_ID = "shared_discovery"


@dataclass
class DiscoveryResult:
    """Result of a shared-with-me discovery scan."""

    files_found: int = 0
    already_indexed: int = 0
    new_files: int = 0
    ingested: int = 0
    errors: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


async def discover_shared_files(
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
    since_hours: int = 24,
) -> DiscoveryResult:
    """Scan for newly-shared files and ingest any not already indexed.

    Queries Drive API with sharedWithMe filter and a time cutoff based on
    sharedWithMeTime. Files already in the index are skipped.

    Args:
        google_client: Google API client (uses singleton if not provided)
        db: Database client (uses singleton if not provided)
        since_hours: Look back window in hours (default 24)

    Returns:
        DiscoveryResult with statistics
    """
    import time
    from drive_rag.ingestion import ingest_document

    start = time.monotonic()
    google = google_client or get_google_client()
    database = db or get_db()
    result = DiscoveryResult()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

        # Build MIME type filter
        mime_filter = " or ".join(
            [f"mimeType='{m}'" for m in SUPPORTED_MIME_TYPES]
        )

        # Note: sharedWithMeTime is not a queryable field in Drive API.
        # Use modifiedTime as proxy — newly shared files have recent modifiedTime.
        query = (
            f"sharedWithMe = true and trashed = false"
            f" and modifiedTime > '{cutoff_str}'"
            f" and ({mime_filter})"
        )

        # Paginate through results
        all_files = []
        page_token = None

        while True:
            params = {
                "q": query,
                "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,owners,sharedWithMeTime)",
                "pageSize": 100,
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if page_token:
                params["pageToken"] = page_token

            response = google.drive.files().list(**params).execute()
            files = response.get("files", [])
            all_files.extend(files)

            page_token = response.get("nextPageToken")
            if not page_token or len(all_files) >= 1000:
                break

        result.files_found = len(all_files)

        if not all_files:
            logger.info("discovery_no_new_shared_files", since_hours=since_hours)
            result.scan_duration_seconds = time.monotonic() - start
            return result

        # Filter to files not already indexed
        for file_info in all_files:
            file_id = file_info.get("id")
            if not file_id:
                continue

            if database.document_exists(file_id):
                result.already_indexed += 1
                continue

            result.new_files += 1
            title = file_info.get("name", "")[:60]

            logger.info(
                "discovery_new_file",
                file_id=file_id,
                title=title,
                mime_type=file_info.get("mimeType"),
                shared_time=file_info.get("sharedWithMeTime"),
            )

            try:
                await ingest_document(
                    file_id=file_id,
                    google_client=google,
                    db=database,
                    force=False,
                )
                result.ingested += 1
            except Exception as e:
                error_msg = f"Ingest {file_id}: {str(e)[:100]}"
                result.errors.append(error_msg)
                logger.warning(
                    "discovery_ingest_failed",
                    file_id=file_id,
                    error=str(e),
                )

        # Update last scan timestamp using sync state
        try:
            state = database.get_sync_state(DISCOVERY_STATE_ID)
            if state is None:
                database.initialize_sync_state("n/a", state_id=DISCOVERY_STATE_ID)
            else:
                database.update_sync_state(
                    page_token="n/a",
                    new_files=result.new_files,
                    state_id=DISCOVERY_STATE_ID,
                )
        except Exception as e:
            logger.warning("discovery_state_update_failed", error=str(e))

    except Exception as e:
        result.errors.append(f"Discovery scan error: {str(e)}")
        logger.exception("discovery_scan_error", error=str(e))

    result.scan_duration_seconds = time.monotonic() - start

    logger.info(
        "discovery_scan_complete",
        files_found=result.files_found,
        already_indexed=result.already_indexed,
        new_files=result.new_files,
        ingested=result.ingested,
        errors=len(result.errors),
        duration=round(result.scan_duration_seconds, 2),
    )

    return result
