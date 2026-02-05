"""Change monitoring for Drive documents.

This module detects when indexed documents have been modified in Google Drive
and triggers re-ingestion to update snapshots and chunks.

Monitoring uses priority tiers to efficiently handle large document sets:
- High: Documents modified in last 24h (most likely to change again)
- Medium: Documents modified 1-7 days ago
- Low: Older documents (sampled daily)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import structlog

from drive_rag.auth import get_google_client, GoogleClient
from drive_rag.db import get_db, Database
from drive_rag.ingestion import ingest_document
from drive_rag.settings import get_settings

logger = structlog.get_logger()

# Priority tier constants
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"
PRIORITY_ALL = "all"

# Default time thresholds (hours/days)
HIGH_PRIORITY_HOURS = 24
MEDIUM_PRIORITY_DAYS = 7


@dataclass
class ScanResult:
    """Result of a change monitoring scan."""

    priority: str
    documents_scanned: int = 0
    documents_changed: int = 0
    documents_reindexed: int = 0
    documents_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0
    dry_run: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "priority": self.priority,
            "documents_scanned": self.documents_scanned,
            "documents_changed": self.documents_changed,
            "documents_reindexed": self.documents_reindexed,
            "documents_skipped": self.documents_skipped,
            "errors": self.errors[:20],  # Limit errors in response
            "error_count": len(self.errors),
            "scan_duration_seconds": round(self.scan_duration_seconds, 2),
            "dry_run": self.dry_run,
        }


def get_documents_to_check(
    db: Database,
    priority: str,
    batch_size: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get documents to check based on priority tier.

    Priority tiers determine which documents to scan:
    - high: Modified in last 24 hours (recently active, likely to change)
    - medium: Modified 1-7 days ago
    - low: Older documents (rotating sample)
    - all: All documents

    Args:
        db: Database client
        priority: Priority tier (high, medium, low, all)
        batch_size: Maximum documents to return
        offset: Pagination offset

    Returns:
        List of document state records with file_id and revision info
    """
    now = datetime.utcnow()

    # Build filter based on priority
    if priority == PRIORITY_HIGH:
        # Documents modified in last 24 hours
        cutoff = (now - timedelta(hours=HIGH_PRIORITY_HOURS)).isoformat()
        modified_filter = f"gte.{cutoff}"
    elif priority == PRIORITY_MEDIUM:
        # Documents modified 1-7 days ago
        recent_cutoff = (now - timedelta(hours=HIGH_PRIORITY_HOURS)).isoformat()
        old_cutoff = (now - timedelta(days=MEDIUM_PRIORITY_DAYS)).isoformat()
        # PostgREST doesn't support between easily, we'll handle in SQL or use two filters
        modified_filter = None  # Will handle specially
    elif priority == PRIORITY_LOW:
        # Older documents
        cutoff = (now - timedelta(days=MEDIUM_PRIORITY_DAYS)).isoformat()
        modified_filter = f"lt.{cutoff}"
    else:
        # All documents
        modified_filter = None

    # Build query parameters
    params = {
        "select": "drive_file_id,title,last_seen_revision_id,modified_time,last_indexed_at",
        "order": "modified_time.desc",
        "limit": str(batch_size),
        "offset": str(offset),
    }

    # Add priority filter
    if priority == PRIORITY_HIGH:
        params["modified_time"] = f"gte.{(now - timedelta(hours=HIGH_PRIORITY_HOURS)).isoformat()}"
    elif priority == PRIORITY_MEDIUM:
        # For medium, we need documents between 1-7 days old
        params["modified_time"] = f"lt.{(now - timedelta(hours=HIGH_PRIORITY_HOURS)).isoformat()}"
        params["modified_time"] = f"gte.{(now - timedelta(days=MEDIUM_PRIORITY_DAYS)).isoformat()}"
        # Note: PostgREST requires special handling for ranges
    elif priority == PRIORITY_LOW:
        params["modified_time"] = f"lt.{(now - timedelta(days=MEDIUM_PRIORITY_DAYS)).isoformat()}"

    # Execute query
    response = db.client.get(db._url("document_state"), params=params)
    db._check_response(response, "get_documents_to_check")

    return response.json() or []


def get_documents_by_priority_range(
    db: Database,
    min_age_hours: Optional[int] = None,
    max_age_days: Optional[int] = None,
    batch_size: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get documents within a specific age range.

    More flexible than get_documents_to_check for complex queries.

    Args:
        db: Database client
        min_age_hours: Minimum age in hours (documents older than this)
        max_age_days: Maximum age in days (documents newer than this)
        batch_size: Maximum documents to return
        offset: Pagination offset

    Returns:
        List of document state records
    """
    now = datetime.utcnow()

    params = {
        "select": "drive_file_id,title,last_seen_revision_id,modified_time,last_indexed_at",
        "order": "modified_time.desc",
        "limit": str(batch_size),
        "offset": str(offset),
    }

    # Build time filters
    if min_age_hours is not None:
        cutoff = (now - timedelta(hours=min_age_hours)).isoformat()
        params["modified_time"] = f"lt.{cutoff}"

    if max_age_days is not None:
        cutoff = (now - timedelta(days=max_age_days)).isoformat()
        # If we already have a filter, this becomes an AND condition
        # PostgREST handles multiple conditions on same column as AND
        params["modified_time"] = f"gte.{cutoff}"

    response = db.client.get(db._url("document_state"), params=params)
    db._check_response(response, "get_documents_by_priority_range")

    return response.json() or []


async def check_single_document_revision(
    google: GoogleClient,
    file_id: str,
    stored_revision_id: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Check if a document's revision has changed.

    Makes a lightweight metadata request to Drive API.

    Args:
        google: Google API client
        file_id: Google Drive file ID
        stored_revision_id: The revision ID we have stored

    Returns:
        Tuple of (has_changed, current_revision_id, error_message)
    """
    try:
        # Lightweight metadata request - only get revision info
        meta = google.drive.files().get(
            fileId=file_id,
            fields="id,headRevisionId",
            supportsAllDrives=True,
        ).execute()

        current_revision = meta.get("headRevisionId", "")
        has_changed = current_revision != stored_revision_id

        return has_changed, current_revision, None

    except Exception as e:
        error_msg = str(e)
        # Check for specific error types
        if "404" in error_msg or "File not found" in error_msg:
            logger.warning("document_not_found", file_id=file_id)
            return False, None, "Document not found (may have been deleted)"
        elif "403" in error_msg or "forbidden" in error_msg.lower():
            logger.warning("document_access_denied", file_id=file_id)
            return False, None, "Access denied"
        else:
            logger.error("revision_check_error", file_id=file_id, error=error_msg)
            return False, None, error_msg


async def scan_for_changes(
    priority: str = PRIORITY_HIGH,
    batch_size: int = 100,
    dry_run: bool = False,
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
) -> ScanResult:
    """Scan for changed documents and trigger re-ingestion.

    This is the main entry point for change monitoring. It:
    1. Gets documents to check based on priority tier
    2. Checks each document's revision against Drive API
    3. Triggers re-ingestion for changed documents

    Args:
        priority: Priority tier (high, medium, low, all)
        batch_size: Maximum documents to scan in this batch
        dry_run: If True, don't actually re-ingest - just report what would change
        google_client: Google API client (defaults to global)
        db: Database client (defaults to global)

    Returns:
        ScanResult with scan statistics
    """
    import time
    start_time = time.time()

    google = google_client or get_google_client()
    database = db or get_db()

    result = ScanResult(priority=priority, dry_run=dry_run)

    logger.info(
        "starting_change_scan",
        priority=priority,
        batch_size=batch_size,
        dry_run=dry_run,
    )

    # Get documents to check
    if priority == PRIORITY_MEDIUM:
        # Medium priority needs range query
        docs = get_documents_by_priority_range(
            database,
            min_age_hours=HIGH_PRIORITY_HOURS,
            max_age_days=MEDIUM_PRIORITY_DAYS,
            batch_size=batch_size,
        )
    else:
        docs = get_documents_to_check(database, priority, batch_size)

    result.documents_scanned = len(docs)

    if not docs:
        logger.info("no_documents_to_scan", priority=priority)
        result.scan_duration_seconds = time.time() - start_time
        return result

    # Check each document for changes
    for doc in docs:
        file_id = doc["drive_file_id"]
        stored_revision = doc.get("last_seen_revision_id", "")
        title = doc.get("title", "")[:50]

        try:
            # Check if revision has changed
            has_changed, current_revision, error = await check_single_document_revision(
                google, file_id, stored_revision
            )

            if error:
                result.errors.append(f"{file_id}: {error}")
                continue

            if not has_changed:
                result.documents_skipped += 1
                continue

            # Document has changed
            result.documents_changed += 1
            logger.info(
                "document_changed",
                file_id=file_id,
                title=title,
                old_revision=stored_revision[:16] if stored_revision else "",
                new_revision=current_revision[:16] if current_revision else "",
            )

            if dry_run:
                continue

            # Trigger re-ingestion
            try:
                ingest_result = await ingest_document(
                    file_id=file_id,
                    google_client=google,
                    db=database,
                    force=False,  # Use normal change detection
                )

                if ingest_result.status == "success":
                    result.documents_reindexed += 1
                    logger.info(
                        "document_reindexed",
                        file_id=file_id,
                        chunks_added=ingest_result.chunks_added,
                        chunks_updated=ingest_result.chunks_updated,
                    )
                else:
                    # Ingestion returned skip - content hash unchanged
                    logger.debug(
                        "document_skipped_after_fetch",
                        file_id=file_id,
                        reason=ingest_result.reason,
                    )

            except Exception as ingest_error:
                error_msg = f"{file_id}: Ingestion failed - {str(ingest_error)[:100]}"
                result.errors.append(error_msg)
                logger.error("reingestion_failed", file_id=file_id, error=str(ingest_error))

        except Exception as e:
            error_msg = f"{file_id}: {str(e)[:100]}"
            result.errors.append(error_msg)
            logger.error("document_scan_error", file_id=file_id, error=str(e))

    result.scan_duration_seconds = time.time() - start_time

    logger.info(
        "change_scan_complete",
        priority=priority,
        scanned=result.documents_scanned,
        changed=result.documents_changed,
        reindexed=result.documents_reindexed,
        errors=len(result.errors),
        duration_seconds=round(result.scan_duration_seconds, 2),
    )

    return result


async def scan_all_priorities(
    batch_size: int = 100,
    dry_run: bool = False,
) -> dict[str, ScanResult]:
    """Scan all priority tiers.

    Useful for the daily full scan.

    Args:
        batch_size: Batch size per priority tier
        dry_run: If True, don't actually re-ingest

    Returns:
        Dictionary mapping priority to ScanResult
    """
    results = {}

    for priority in [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]:
        results[priority] = await scan_for_changes(
            priority=priority,
            batch_size=batch_size,
            dry_run=dry_run,
        )

    return results


def get_scan_status_summary(results: dict[str, ScanResult]) -> dict:
    """Generate a summary from multiple scan results.

    Args:
        results: Dictionary of priority -> ScanResult

    Returns:
        Summary dictionary
    """
    total_scanned = sum(r.documents_scanned for r in results.values())
    total_changed = sum(r.documents_changed for r in results.values())
    total_reindexed = sum(r.documents_reindexed for r in results.values())
    total_errors = sum(len(r.errors) for r in results.values())

    return {
        "total_scanned": total_scanned,
        "total_changed": total_changed,
        "total_reindexed": total_reindexed,
        "total_errors": total_errors,
        "by_priority": {k: v.to_dict() for k, v in results.items()},
    }
