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


# =============================================================================
# Drive Changes API Scanner (New, Preferred Method)
# =============================================================================

# Supported MIME types for indexing
SUPPORTED_MIME_TYPES = {
    "application/vnd.google-apps.document",      # Google Docs
    "application/vnd.google-apps.spreadsheet",   # Google Sheets
    "application/vnd.google-apps.presentation",  # Google Slides
    "application/pdf",                           # PDFs
    "text/plain",                                # Text files
    "text/markdown",                             # Markdown files
}


@dataclass
class ChangesSyncResult:
    """Result of a Changes API sync."""

    changes_processed: int = 0
    new_files: int = 0
    modified_files: int = 0
    deleted_files: int = 0
    skipped_unsupported: int = 0
    skipped_folders: int = 0
    ingested: int = 0
    errors: list[str] = field(default_factory=list)
    sync_duration_seconds: float = 0.0
    dry_run: bool = False
    token_initialized: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "changes_processed": self.changes_processed,
            "new_files": self.new_files,
            "modified_files": self.modified_files,
            "deleted_files": self.deleted_files,
            "skipped_unsupported": self.skipped_unsupported,
            "skipped_folders": self.skipped_folders,
            "ingested": self.ingested,
            "errors": self.errors[:20],  # Limit errors in response
            "error_count": len(self.errors),
            "sync_duration_seconds": round(self.sync_duration_seconds, 2),
            "dry_run": self.dry_run,
            "token_initialized": self.token_initialized,
        }


def is_supported_file_type(mime_type: Optional[str]) -> bool:
    """Check if the MIME type is supported for indexing.

    Args:
        mime_type: The file's MIME type

    Returns:
        True if we should index this file type
    """
    if not mime_type:
        return False
    return mime_type in SUPPORTED_MIME_TYPES


def categorize_change(change: dict) -> str:
    """Categorize a change from the Changes API.

    Args:
        change: A change object from changes.list

    Returns:
        Category: "new", "modified", "deleted", "unsupported", "folder"
    """
    # Check if file was removed (deleted or lost access)
    if change.get("removed", False):
        return "deleted"

    file_info = change.get("file", {})

    # Check if it's a folder
    if file_info.get("mimeType") == "application/vnd.google-apps.folder":
        return "folder"

    # Check if trashed
    if file_info.get("trashed", False):
        return "deleted"

    # Check if supported file type
    if not is_supported_file_type(file_info.get("mimeType")):
        return "unsupported"

    # It's a valid file change - we'll determine new vs modified
    # based on whether it exists in our index
    return "file_change"


async def sync_changes_api(
    dry_run: bool = False,
    reset_token: bool = False,
    max_changes: int = 10000,
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
) -> ChangesSyncResult:
    """Sync changes using the Drive Changes API.

    This is the preferred method for detecting document changes. It:
    1. Gets or initializes the change tracking token
    2. Fetches all changes since last sync
    3. Categorizes and processes each change
    4. Updates the token for next sync

    Args:
        dry_run: If True, don't actually ingest - just report what would happen
        reset_token: If True, reset the token and start fresh
        max_changes: Maximum changes to process in one sync
        google_client: Google API client (defaults to global)
        db: Database client (defaults to global)

    Returns:
        ChangesSyncResult with sync statistics
    """
    import time
    start_time = time.time()

    google = google_client or get_google_client()
    database = db or get_db()

    result = ChangesSyncResult(dry_run=dry_run)

    logger.info(
        "starting_changes_api_sync",
        dry_run=dry_run,
        reset_token=reset_token,
    )

    # Get or initialize sync state
    sync_state = database.get_sync_state()

    if reset_token or sync_state is None:
        # Initialize with current token
        start_token = google.get_changes_start_token()
        database.reset_sync_state(start_token)
        result.token_initialized = True

        if reset_token:
            logger.info("reset_sync_token", new_token_prefix=start_token[:20])
        else:
            logger.info("initialized_sync_token", token_prefix=start_token[:20])

        # On first init, we don't have any changes to process
        result.sync_duration_seconds = time.time() - start_time
        return result

    page_token = sync_state["page_token"]

    # Fetch all changes
    try:
        all_changes, new_token = google.list_all_changes(page_token, max_changes)
    except Exception as e:
        error_msg = str(e)
        if "Invalid Credentials" in error_msg or "invalid_grant" in error_msg:
            # Token might be invalid - try reinitializing
            logger.warning("sync_token_invalid_reinitializing", error=error_msg)
            start_token = google.get_changes_start_token()
            database.reset_sync_state(start_token)
            result.token_initialized = True
            result.errors.append(f"Token was invalid, reinitialized: {error_msg[:100]}")
            result.sync_duration_seconds = time.time() - start_time
            return result
        else:
            raise

    result.changes_processed = len(all_changes)

    if not all_changes:
        logger.info("no_changes_to_process")
        result.sync_duration_seconds = time.time() - start_time
        return result

    logger.info(
        "processing_changes",
        change_count=len(all_changes),
    )

    # Process each change
    for change in all_changes:
        file_id = change.get("fileId")
        if not file_id:
            continue

        category = categorize_change(change)
        file_info = change.get("file", {})
        title = file_info.get("name", "")[:50]

        if category == "deleted":
            result.deleted_files += 1
            logger.debug("change_deleted", file_id=file_id, title=title)

            if not dry_run:
                database.mark_document_deleted(file_id)

        elif category == "folder":
            result.skipped_folders += 1

        elif category == "unsupported":
            result.skipped_unsupported += 1
            logger.debug(
                "change_unsupported",
                file_id=file_id,
                mime_type=file_info.get("mimeType"),
            )

        elif category == "file_change":
            # Determine if new or modified
            exists = database.document_exists(file_id)

            if exists:
                result.modified_files += 1
                logger.debug("change_modified", file_id=file_id, title=title)
            else:
                result.new_files += 1
                logger.info("change_new_file", file_id=file_id, title=title)

            if not dry_run:
                # Ingest the document
                try:
                    ingest_result = await ingest_document(
                        file_id=file_id,
                        google_client=google,
                        db=database,
                        force=False,
                    )

                    if ingest_result.status == "success":
                        result.ingested += 1
                        logger.info(
                            "document_ingested",
                            file_id=file_id,
                            title=title,
                            new_file=not exists,
                        )
                    else:
                        logger.debug(
                            "document_skipped",
                            file_id=file_id,
                            reason=ingest_result.reason,
                        )

                except Exception as e:
                    error_msg = f"{file_id}: {str(e)[:100]}"
                    result.errors.append(error_msg)
                    logger.error(
                        "ingestion_failed",
                        file_id=file_id,
                        error=str(e),
                    )

    # Update sync state with new token
    if not dry_run and new_token:
        database.update_sync_state(
            page_token=new_token,
            changes_processed=result.changes_processed,
            new_files=result.new_files,
            modified_files=result.modified_files,
            deleted_files=result.deleted_files,
        )

    result.sync_duration_seconds = time.time() - start_time

    logger.info(
        "changes_api_sync_complete",
        changes_processed=result.changes_processed,
        new_files=result.new_files,
        modified_files=result.modified_files,
        deleted_files=result.deleted_files,
        ingested=result.ingested,
        errors=len(result.errors),
        duration_seconds=round(result.sync_duration_seconds, 2),
    )

    return result


async def get_sync_status(db: Optional[Database] = None) -> dict:
    """Get the current status of change sync.

    Args:
        db: Database client (defaults to global)

    Returns:
        Dictionary with sync status information
    """
    database = db or get_db()
    sync_state = database.get_sync_state()

    if sync_state is None:
        return {
            "initialized": False,
            "message": "Sync not initialized. Call POST /v1/sync/changes to start.",
        }

    return {
        "initialized": True,
        "last_sync_at": sync_state["last_sync_at"].isoformat() if sync_state["last_sync_at"] else None,
        "total_changes_processed": sync_state["total_changes_processed"],
        "new_files_count": sync_state["new_files_count"],
        "modified_files_count": sync_state["modified_files_count"],
        "deleted_files_count": sync_state["deleted_files_count"],
        "last_error": sync_state["last_error"],
        "token_prefix": sync_state["page_token"][:20] + "..." if sync_state["page_token"] else None,
    }
