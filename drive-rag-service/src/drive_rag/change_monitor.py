"""Change monitoring for Drive documents.

This module detects when indexed documents have been modified in Google Drive
and triggers re-ingestion to update snapshots and chunks.

Uses the Drive Changes API for efficient change detection — a single API call
returns all changes since the last sync token.
"""

from dataclasses import dataclass, field
from typing import Optional

import structlog

from drive_rag.auth import get_google_client, GoogleClient
from drive_rag.db import get_db, Database
from drive_rag.ingestion import ingest_document

logger = structlog.get_logger()


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
