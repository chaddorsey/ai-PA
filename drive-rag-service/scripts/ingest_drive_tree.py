#!/usr/bin/env python3
"""Full Google Drive tree ingestion.

Walks ALL accessible Drive content including:
- My Drive (personal files and folders)
- Shared Drives (team drives the user has access to)
- Shared with me (files shared directly with the user)

Supports comprehensive progress tracking and error logging with resumable state.

Usage:
    # Start full ingestion of all accessible content
    python scripts/ingest_drive_tree.py

    # Start from a specific folder
    python scripts/ingest_drive_tree.py --root FOLDER_ID

    # Ingest only specific sources
    python scripts/ingest_drive_tree.py --source my-drive
    python scripts/ingest_drive_tree.py --source shared-drives
    python scripts/ingest_drive_tree.py --source shared-with-me
    python scripts/ingest_drive_tree.py --source all  # default

    # Resume from previous run
    python scripts/ingest_drive_tree.py --resume

    # Map only (no ingestion)
    python scripts/ingest_drive_tree.py --map-only

    # With entity extraction
    python scripts/ingest_drive_tree.py --extract-entities
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_API_BASE = "http://localhost:8095"
STATE_FILE = Path("drive_tree_state.json")
LOG_FILE = Path("drive_tree_ingest.log")

# Google Drive MIME types
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SUPPORTED_FILE_TYPES = [
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/pdf",
]

# State file version for compatibility
STATE_VERSION = 3

# Drive sources
SOURCE_MY_DRIVE = "my-drive"
SOURCE_SHARED_DRIVES = "shared-drives"
SOURCE_SHARED_WITH_ME = "shared-with-me"
SOURCE_ALL = "all"
VALID_SOURCES = [SOURCE_MY_DRIVE, SOURCE_SHARED_DRIVES, SOURCE_SHARED_WITH_ME, SOURCE_ALL]

# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(log_file: Path, verbose: bool = False) -> logging.Logger:
    """Set up logging to file and console."""
    logger = logging.getLogger("drive_tree_ingest")
    logger.setLevel(logging.DEBUG)

    # File handler - detailed logging
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - summary logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


# ============================================================================
# State Management
# ============================================================================

class IngestionState:
    """Manages the state of the tree ingestion process."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = self._load_or_create()

    def _load_or_create(self) -> dict:
        """Load existing state or create new."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                data = json.load(f)
            if data.get("version") == STATE_VERSION:
                return data
            print(f"Warning: State file version mismatch, starting fresh")

        return {
            "version": STATE_VERSION,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
            "root_folder_id": None,
            # Source tracking
            "sources_requested": [],     # Sources to process
            "sources_completed": [],     # Fully processed sources
            "shared_drives_discovered": {},  # drive_id -> {name, discovered_at}
            "shared_drives_pending": [],     # Queue of shared drive IDs to process
            "shared_drives_completed": [],   # Fully processed shared drives
            # Folder tracking
            "folders_discovered": {},  # id -> {name, path, parent_id, discovered_at, source}
            "folders_pending": [],     # Queue of folder IDs to process
            "folders_completed": [],   # Fully processed folders
            "folders_failed": {},      # id -> error message
            # File tracking (for shared-with-me files that may not be in folders)
            "shared_files_pending": [],    # File IDs from "shared with me" to process
            "shared_files_completed": [],  # Processed shared files
            "files_discovered": 0,
            "files_indexed": [],       # Successfully indexed file IDs
            "files_skipped": [],       # Skipped (unchanged) file IDs
            "files_failed": {},        # id -> {name, error, folder_id}
            # Statistics
            "total_chunks": 0,
            "total_folders": 0,
            "total_files": 0,
        }

    def save(self):
        """Save state to file."""
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def set_sources(self, sources: list[str]):
        """Set the sources to be processed."""
        self.state["sources_requested"] = sources

    def mark_source_complete(self, source: str):
        """Mark a source as fully processed."""
        if source not in self.state["sources_completed"]:
            self.state["sources_completed"].append(source)

    def is_source_complete(self, source: str) -> bool:
        """Check if a source has been fully processed."""
        return source in self.state["sources_completed"]

    def add_shared_drive(self, drive_id: str, name: str):
        """Register a discovered shared drive."""
        if drive_id not in self.state["shared_drives_discovered"]:
            self.state["shared_drives_discovered"][drive_id] = {
                "name": name,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            self.state["shared_drives_pending"].append(drive_id)

    def get_next_shared_drive(self) -> Optional[str]:
        """Get next shared drive to process."""
        while self.state["shared_drives_pending"]:
            drive_id = self.state["shared_drives_pending"].pop(0)
            if drive_id not in self.state["shared_drives_completed"]:
                return drive_id
        return None

    def mark_shared_drive_complete(self, drive_id: str):
        """Mark a shared drive as fully processed."""
        if drive_id not in self.state["shared_drives_completed"]:
            self.state["shared_drives_completed"].append(drive_id)

    def add_shared_file(self, file_id: str):
        """Register a shared-with-me file for processing."""
        if file_id not in self.state["shared_files_pending"] and \
           file_id not in self.state["shared_files_completed"]:
            self.state["shared_files_pending"].append(file_id)

    def get_next_shared_file_batch(self, batch_size: int = 20) -> list[str]:
        """Get next batch of shared files to process."""
        batch = []
        while self.state["shared_files_pending"] and len(batch) < batch_size:
            file_id = self.state["shared_files_pending"].pop(0)
            if file_id not in self.state["shared_files_completed"]:
                batch.append(file_id)
        return batch

    def mark_shared_file_complete(self, file_id: str):
        """Mark a shared file as processed."""
        if file_id not in self.state["shared_files_completed"]:
            self.state["shared_files_completed"].append(file_id)

    def add_folder(self, folder_id: str, name: str, path: list[str], parent_id: Optional[str], source: str = SOURCE_MY_DRIVE):
        """Register a discovered folder."""
        if folder_id not in self.state["folders_discovered"]:
            self.state["folders_discovered"][folder_id] = {
                "name": name,
                "path": path,
                "parent_id": parent_id,
                "source": source,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            self.state["folders_pending"].append(folder_id)
            self.state["total_folders"] += 1

    def get_next_folder(self) -> Optional[str]:
        """Get next folder to process."""
        while self.state["folders_pending"]:
            folder_id = self.state["folders_pending"].pop(0)
            if folder_id not in self.state["folders_completed"]:
                return folder_id
        return None

    def mark_folder_complete(self, folder_id: str):
        """Mark a folder as fully processed."""
        if folder_id not in self.state["folders_completed"]:
            self.state["folders_completed"].append(folder_id)

    def mark_folder_failed(self, folder_id: str, error: str):
        """Mark a folder as failed."""
        self.state["folders_failed"][folder_id] = error

    def record_file_result(self, file_id: str, file_name: str, folder_id: str, result: dict):
        """Record the result of a file ingestion."""
        status = result.get("status", "error")

        if status == "indexed":
            self.state["files_indexed"].append(file_id)
            self.state["total_chunks"] += result.get("chunks_added", 0) + result.get("chunks_updated", 0)
        elif status == "skipped":
            self.state["files_skipped"].append(file_id)
        else:
            self.state["files_failed"][file_id] = {
                "name": file_name,
                "folder_id": folder_id,
                "error": result.get("reason", "unknown"),
            }

    def is_file_processed(self, file_id: str) -> bool:
        """Check if a file has already been processed."""
        return (
            file_id in self.state["files_indexed"] or
            file_id in self.state["files_skipped"] or
            file_id in self.state["files_failed"]
        )

    def get_folder_info(self, folder_id: str) -> Optional[dict]:
        """Get info about a discovered folder."""
        return self.state["folders_discovered"].get(folder_id)

    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            "sources_completed": len(self.state["sources_completed"]),
            "sources_requested": len(self.state["sources_requested"]),
            "shared_drives_discovered": len(self.state["shared_drives_discovered"]),
            "shared_drives_completed": len(self.state["shared_drives_completed"]),
            "shared_drives_pending": len(self.state["shared_drives_pending"]),
            "shared_files_pending": len(self.state["shared_files_pending"]),
            "shared_files_completed": len(self.state["shared_files_completed"]),
            "folders_discovered": len(self.state["folders_discovered"]),
            "folders_completed": len(self.state["folders_completed"]),
            "folders_pending": len(self.state["folders_pending"]),
            "folders_failed": len(self.state["folders_failed"]),
            "files_discovered": self.state["files_discovered"],
            "files_indexed": len(self.state["files_indexed"]),
            "files_skipped": len(self.state["files_skipped"]),
            "files_failed": len(self.state["files_failed"]),
            "total_chunks": self.state["total_chunks"],
        }


# ============================================================================
# Google Drive Operations
# ============================================================================

class DriveWalker:
    """Walks the Google Drive tree and lists contents."""

    def __init__(self):
        # Import here to avoid dependency at module load
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from drive_rag.auth import get_google_client
        self.google = get_google_client()

    def get_root_folder(self) -> dict:
        """Get metadata for the root folder."""
        return self.google.drive.files().get(
            fileId="root",
            fields="id,name"
        ).execute()

    def list_shared_drives(self) -> list[dict]:
        """List all shared drives the user has access to.

        Returns:
            List of shared drive metadata dicts with id and name
        """
        drives = []
        page_token = None

        while True:
            result = self.google.drive.drives().list(
                pageSize=100,
                pageToken=page_token,
                fields="nextPageToken,drives(id,name)",
            ).execute()

            drives.extend(result.get("drives", []))

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return drives

    def list_shared_with_me_files(self) -> list[dict]:
        """List all files shared with the user (not in shared drives).

        Returns:
            List of file metadata dicts
        """
        files = []
        page_token = None

        # Query for files shared with me that are supported types
        mime_filter = " or ".join([f"mimeType='{m}'" for m in SUPPORTED_FILE_TYPES + [FOLDER_MIME_TYPE]])
        query = f"sharedWithMe = true and trashed = false and ({mime_filter})"

        while True:
            result = self.google.drive.files().list(
                q=query,
                fields="nextPageToken,files(id,name,mimeType,modifiedTime,owners,parents)",
                pageSize=100,
                pageToken=page_token,
                # Include files from shared drives in this query
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            files.extend(result.get("files", []))

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return files

    def list_folder_contents(self, folder_id: str, drive_id: Optional[str] = None) -> tuple[list[dict], list[dict]]:
        """List all subfolders and files in a folder.

        Args:
            folder_id: The folder ID to list contents of
            drive_id: For shared drives, the drive ID (required for corpora='drive')

        Returns:
            Tuple of (subfolders, files)
        """
        subfolders = []
        files = []

        # Build query for all items in folder
        query = f"'{folder_id}' in parents and trashed = false"

        page_token = None
        while True:
            # For shared drives, use different parameters
            list_params = {
                "q": query,
                "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,owners)",
                "pageSize": 100,
                "pageToken": page_token,
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }

            # If this is a shared drive, specify the corpora
            if drive_id:
                list_params["corpora"] = "drive"
                list_params["driveId"] = drive_id

            result = self.google.drive.files().list(**list_params).execute()

            for item in result.get("files", []):
                if item.get("mimeType") == FOLDER_MIME_TYPE:
                    subfolders.append(item)
                elif item.get("mimeType") in SUPPORTED_FILE_TYPES:
                    files.append(item)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return subfolders, files

    def get_file_metadata(self, file_id: str) -> dict:
        """Get metadata for a specific file."""
        return self.google.drive.files().get(
            fileId=file_id,
            fields="id,name,mimeType,modifiedTime,owners,parents",
            supportsAllDrives=True,
        ).execute()

    def check_file_exists(self, file_id: str) -> bool:
        """Quick check if a file exists and is accessible.

        Uses minimal fields for fastest possible response.
        Returns False for 404 (deleted) or 403 (no access).
        """
        try:
            self.google.drive.files().get(
                fileId=file_id,
                fields="id",
                supportsAllDrives=True,
            ).execute()
            return True
        except Exception:
            return False

    def batch_check_files_exist(self, file_ids: list[str], max_concurrent: int = 10) -> dict[str, bool]:
        """Check multiple files for existence concurrently.

        Returns dict mapping file_id -> exists (True/False)
        """
        import concurrent.futures

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            future_to_id = {
                executor.submit(self.check_file_exists, fid): fid
                for fid in file_ids
            }
            for future in concurrent.futures.as_completed(future_to_id):
                file_id = future_to_id[future]
                try:
                    results[file_id] = future.result()
                except Exception:
                    results[file_id] = False

        return results

    def get_folder_path(self, folder_id: str) -> list[str]:
        """Get the full path to a folder."""
        try:
            path_names, _ = self.google.build_folder_path(folder_id)
            return path_names
        except Exception:
            return []


# ============================================================================
# Ingestion Operations
# ============================================================================

async def ingest_file(
    client: httpx.AsyncClient,
    file_id: str,
    api_base: str,
    force: bool = False,
    extract_entities: bool = False,
    timeout: float = 300.0,
) -> dict:
    """Ingest a single file via the API."""
    params = {}
    if force:
        params["force"] = "true"
    if extract_entities:
        params["extract_entities"] = "true"

    try:
        response = await client.post(
            f"{api_base}/v1/ingest/{file_id}",
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        return {"status": "error", "drive_file_id": file_id, "reason": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "drive_file_id": file_id, "reason": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"status": "error", "drive_file_id": file_id, "reason": str(e)}


# ============================================================================
# Main Ingestion Logic
# ============================================================================

def format_mime_type(mime_type: str) -> str:
    """Format MIME type for display."""
    type_map = {
        "application/vnd.google-apps.document": "Doc",
        "application/vnd.google-apps.spreadsheet": "Sheet",
        "application/vnd.google-apps.presentation": "Slides",
        "application/pdf": "PDF",
        "application/vnd.google-apps.folder": "Folder",
    }
    return type_map.get(mime_type, "File")


async def process_folder(
    folder_id: str,
    state: IngestionState,
    walker: DriveWalker,
    client: httpx.AsyncClient,
    api_base: str,
    logger: logging.Logger,
    force: bool = False,
    extract_entities: bool = False,
    map_only: bool = False,
    concurrency: int = 3,
    drive_id: Optional[str] = None,
    source: str = SOURCE_MY_DRIVE,
    precheck: bool = False,
) -> bool:
    """Process a single folder: discover contents and ingest files.

    Args:
        folder_id: Folder ID to process
        state: Ingestion state manager
        walker: Drive API wrapper
        client: HTTP client
        api_base: API base URL
        logger: Logger instance
        force: Force re-indexing
        extract_entities: Enable entity extraction
        map_only: Only map, don't ingest
        concurrency: Concurrent requests
        drive_id: Shared drive ID (if processing a shared drive)
        source: Source identifier for tracking
        precheck: Pre-check file existence before ingestion (faster for shared files)

    Returns:
        True if successful, False if failed
    """
    folder_info = state.get_folder_info(folder_id)
    folder_name = folder_info["name"] if folder_info else folder_id
    folder_path = "/".join(folder_info["path"]) if folder_info else ""

    logger.info(f"📁 Processing: {folder_path}/{folder_name}")

    try:
        # List folder contents
        subfolders, files = walker.list_folder_contents(folder_id, drive_id=drive_id)

        logger.debug(f"   Found {len(subfolders)} subfolders, {len(files)} files")

        # Register subfolders for future processing
        current_path = folder_info["path"] + [folder_name] if folder_info else [folder_name]
        for subfolder in subfolders:
            state.add_folder(
                folder_id=subfolder["id"],
                name=subfolder["name"],
                path=current_path,
                parent_id=folder_id,
                source=source,
            )

        state.state["files_discovered"] += len(files)

        if map_only:
            logger.info(f"   [MAP] {len(files)} files, {len(subfolders)} subfolders")
            state.mark_folder_complete(folder_id)
            state.save()
            return True

        # Filter out already processed files
        pending_files = [f for f in files if not state.is_file_processed(f["id"])]

        if not pending_files:
            logger.info(f"   All {len(files)} files already processed")
            state.mark_folder_complete(folder_id)
            state.save()
            return True

        # Pre-check file existence to skip deleted files quickly
        if precheck and len(pending_files) > 0:
            logger.debug(f"   Pre-checking {len(pending_files)} files...")
            file_ids = [f["id"] for f in pending_files]
            existence = walker.batch_check_files_exist(file_ids, max_concurrent=10)

            # Filter to only existing files, mark non-existent as failed
            existing_files = []
            for f in pending_files:
                if existence.get(f["id"], False):
                    existing_files.append(f)
                else:
                    # Record as failed (deleted)
                    state.record_file_result(
                        f["id"], f.get("name", "Unknown"), folder_id,
                        {"status": "error", "reason": "File not found (deleted or no access)"}
                    )

            skipped_count = len(pending_files) - len(existing_files)
            if skipped_count > 0:
                logger.info(f"   Skipped {skipped_count} deleted/inaccessible files")

            pending_files = existing_files

            if not pending_files:
                logger.info(f"   No accessible files to ingest")
                state.mark_folder_complete(folder_id)
                state.save()
                return True

        logger.info(f"   Ingesting {len(pending_files)} files...")

        # Process files with concurrency limit
        semaphore = asyncio.Semaphore(concurrency)

        async def ingest_with_semaphore(file: dict) -> tuple[dict, dict]:
            async with semaphore:
                result = await ingest_file(
                    client=client,
                    file_id=file["id"],
                    api_base=api_base,
                    force=force,
                    extract_entities=extract_entities,
                )
                return file, result

        tasks = [ingest_with_semaphore(f) for f in pending_files]

        # Process in batches to save state periodically
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)

            for item in results:
                if isinstance(item, Exception):
                    logger.error(f"   Exception during ingestion: {item}")
                    continue

                file, result = item
                file_name = file.get("name", "Unknown")
                file_type = format_mime_type(file.get("mimeType", ""))
                status = result.get("status", "error")

                state.record_file_result(file["id"], file_name, folder_id, result)

                if status == "indexed":
                    chunks = result.get("chunks_added", 0) + result.get("chunks_updated", 0)
                    logger.debug(f"   ✓ [{file_type}] {file_name[:40]} ({chunks} chunks)")
                elif status == "skipped":
                    logger.debug(f"   ○ [{file_type}] {file_name[:40]} (skipped)")
                else:
                    reason = result.get("reason", "unknown")[:50]
                    logger.warning(f"   ✗ [{file_type}] {file_name[:40]}: {reason}")

            # Save state after each batch
            state.save()

        state.mark_folder_complete(folder_id)
        state.save()

        stats = state.get_stats()
        logger.info(f"   Done. Total indexed: {stats['files_indexed']}, failed: {stats['files_failed']}")

        return True

    except Exception as e:
        logger.error(f"   Failed to process folder: {e}")
        state.mark_folder_failed(folder_id, str(e))
        state.save()
        return False


async def process_shared_files(
    state: IngestionState,
    walker: DriveWalker,
    client: httpx.AsyncClient,
    api_base: str,
    logger: logging.Logger,
    force: bool = False,
    extract_entities: bool = False,
    map_only: bool = False,
    concurrency: int = 3,
    precheck: bool = False,
) -> None:
    """Process files from 'Shared with me' that aren't in folders we walk.

    These are files shared directly with the user, not via folder sharing.
    """
    logger.info("")
    logger.info("=" * 40)
    logger.info("SHARED WITH ME FILES")
    logger.info("=" * 40)

    # Get pending files
    pending_files = state.state["shared_files_pending"][:]

    if not pending_files:
        logger.info("No pending shared files to process")
        return

    logger.info(f"Processing {len(pending_files)} shared files...")

    if map_only:
        logger.info(f"[MAP] {len(pending_files)} shared files discovered")
        return

    # Pre-check file existence to skip deleted files quickly
    if precheck and len(pending_files) > 0:
        logger.info(f"Pre-checking {len(pending_files)} shared files for existence...")
        existence = walker.batch_check_files_exist(pending_files, max_concurrent=20)

        existing_files = []
        deleted_count = 0
        for fid in pending_files:
            if existence.get(fid, False):
                existing_files.append(fid)
            else:
                # Record as failed (deleted) and mark complete
                state.record_file_result(
                    fid, "Unknown", "shared-with-me",
                    {"status": "error", "reason": "File not found (deleted or no access)"}
                )
                state.mark_shared_file_complete(fid)
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Skipped {deleted_count} deleted/inaccessible files")
            state.save()

        pending_files = existing_files
        # Update the state's pending list
        state.state["shared_files_pending"] = pending_files

        if not pending_files:
            logger.info("No accessible shared files to ingest")
            return

    # Process in batches
    semaphore = asyncio.Semaphore(concurrency)
    batch_size = 20

    async def ingest_with_semaphore(file_id: str) -> tuple[str, dict, dict]:
        async with semaphore:
            try:
                meta = walker.get_file_metadata(file_id)
            except Exception as e:
                meta = {"id": file_id, "name": "Unknown", "mimeType": "unknown"}
            result = await ingest_file(
                client=client,
                file_id=file_id,
                api_base=api_base,
                force=force,
                extract_entities=extract_entities,
            )
            return file_id, meta, result

    processed = 0
    while pending_files:
        batch = pending_files[:batch_size]
        pending_files = pending_files[batch_size:]

        tasks = [ingest_with_semaphore(fid) for fid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for item in results:
            if isinstance(item, Exception):
                logger.error(f"   Exception during ingestion: {item}")
                continue

            file_id, meta, result = item
            file_name = meta.get("name", "Unknown")
            file_type = format_mime_type(meta.get("mimeType", ""))
            status = result.get("status", "error")

            state.record_file_result(file_id, file_name, "shared-with-me", result)
            state.mark_shared_file_complete(file_id)

            if status == "indexed":
                chunks = result.get("chunks_added", 0) + result.get("chunks_updated", 0)
                logger.debug(f"   ✓ [{file_type}] {file_name[:40]} ({chunks} chunks)")
            elif status == "skipped":
                logger.debug(f"   ○ [{file_type}] {file_name[:40]} (skipped)")
            else:
                reason = result.get("reason", "unknown")[:50]
                logger.warning(f"   ✗ [{file_type}] {file_name[:40]}: {reason}")

            processed += 1

        state.save()
        if processed % 50 == 0:
            logger.info(f"   Processed {processed} shared files...")

    logger.info(f"Completed processing {processed} shared files")


async def run_tree_ingestion(
    root_folder_id: Optional[str] = None,
    api_base: str = DEFAULT_API_BASE,
    state_file: Path = STATE_FILE,
    log_file: Path = LOG_FILE,
    force: bool = False,
    extract_entities: bool = False,
    map_only: bool = False,
    concurrency: int = 3,
    verbose: bool = False,
    source: str = SOURCE_ALL,
    precheck: bool = False,
):
    """Run the full tree ingestion process.

    Processes all accessible Drive content:
    - My Drive: Personal files and folder tree
    - Shared Drives: Team drives the user has access to
    - Shared with me: Files shared directly with the user
    """
    # Setup
    logger = setup_logging(log_file, verbose)
    state = IngestionState(state_file)
    walker = DriveWalker()

    logger.info("=" * 60)
    logger.info("GOOGLE DRIVE COMPREHENSIVE INGESTION")
    logger.info("=" * 60)

    # Determine which sources to process
    if source == SOURCE_ALL:
        sources_to_process = [SOURCE_MY_DRIVE, SOURCE_SHARED_DRIVES, SOURCE_SHARED_WITH_ME]
    else:
        sources_to_process = [source]

    logger.info(f"Sources: {', '.join(sources_to_process)}")

    if map_only:
        logger.info("Mode: MAP ONLY (no ingestion)")
    if extract_entities:
        logger.info("Entity extraction: ENABLED")
    if force:
        logger.info("Force re-index: ENABLED")
    if precheck:
        logger.info("Pre-check: ENABLED (fast filtering of deleted files)")

    # Check API health
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{api_base}/health", timeout=10.0)
            if health.status_code != 200:
                logger.error(f"API not healthy at {api_base}")
                return
            logger.info(f"Connected to drive-rag-service at {api_base}")
        except Exception as e:
            logger.error(f"Cannot connect to API: {e}")
            return

        start_time = datetime.now(timezone.utc)

        # Track which sources we need to initialize
        if not state.state["sources_requested"]:
            state.set_sources(sources_to_process)
            state.save()

        # Detect resuming after map-only: sources completed but no files indexed
        # In this case, reset completion state to allow actual ingestion
        if not map_only and state.state["sources_completed"] and not state.state["files_indexed"]:
            logger.info("Detected resume after map-only scan. Resetting for ingestion...")
            # Reset folder completion to re-process all folders
            state.state["folders_completed"] = []
            # Reset source completion
            state.state["sources_completed"] = []
            # Re-queue all discovered folders
            state.state["folders_pending"] = list(state.state["folders_discovered"].keys())
            state.save()
            logger.info(f"Re-queued {len(state.state['folders_pending'])} folders for ingestion")

        try:
            # ================================================================
            # PHASE 1: MY DRIVE
            # ================================================================
            if SOURCE_MY_DRIVE in sources_to_process and not state.is_source_complete(SOURCE_MY_DRIVE):
                logger.info("")
                logger.info("=" * 40)
                logger.info("MY DRIVE")
                logger.info("=" * 40)

                # Initialize My Drive root if not already done
                if root_folder_id:
                    # User-specified root
                    if root_folder_id not in state.state["folders_discovered"]:
                        try:
                            folder_meta = walker.google.get_folder_metadata(root_folder_id)
                            root_name = folder_meta.get("name", "Root")
                        except Exception:
                            root_name = "Specified Root"
                        state.state["root_folder_id"] = root_folder_id
                        state.add_folder(root_folder_id, root_name, [], None, SOURCE_MY_DRIVE)
                        state.save()
                elif not any(
                    f.get("source") == SOURCE_MY_DRIVE
                    for f in state.state["folders_discovered"].values()
                ):
                    # Initialize My Drive root
                    root_meta = walker.get_root_folder()
                    root_id = root_meta["id"]
                    state.state["root_folder_id"] = root_id
                    state.add_folder(root_id, "My Drive", [], None, SOURCE_MY_DRIVE)
                    logger.info(f"Starting My Drive from root: {root_id}")
                    state.save()

                # Process My Drive folders
                folders_processed = 0
                while True:
                    folder_id = state.get_next_folder()
                    if folder_id is None:
                        break

                    folder_info = state.get_folder_info(folder_id)
                    folder_source = folder_info.get("source", SOURCE_MY_DRIVE) if folder_info else SOURCE_MY_DRIVE

                    # Only process My Drive folders in this phase
                    if folder_source != SOURCE_MY_DRIVE:
                        # Put it back for later
                        state.state["folders_pending"].insert(0, folder_id)
                        break

                    success = await process_folder(
                        folder_id=folder_id,
                        state=state,
                        walker=walker,
                        client=client,
                        api_base=api_base,
                        logger=logger,
                        force=force,
                        extract_entities=extract_entities,
                        map_only=map_only,
                        concurrency=concurrency,
                        source=SOURCE_MY_DRIVE,
                        precheck=precheck,
                    )

                    folders_processed += 1

                    if folders_processed % 10 == 0:
                        stats = state.get_stats()
                        logger.info(
                            f"[My Drive] Progress: {stats['folders_completed']}/{stats['folders_discovered']} folders, "
                            f"{stats['files_indexed']} indexed"
                        )

                state.mark_source_complete(SOURCE_MY_DRIVE)
                state.save()
                logger.info(f"My Drive complete: {folders_processed} folders processed")

            # ================================================================
            # PHASE 2: SHARED DRIVES
            # ================================================================
            if SOURCE_SHARED_DRIVES in sources_to_process and not state.is_source_complete(SOURCE_SHARED_DRIVES):
                logger.info("")
                logger.info("=" * 40)
                logger.info("SHARED DRIVES")
                logger.info("=" * 40)

                # Discover shared drives if not already done
                if not state.state["shared_drives_discovered"]:
                    logger.info("Discovering shared drives...")
                    shared_drives = walker.list_shared_drives()
                    logger.info(f"Found {len(shared_drives)} shared drives")

                    for drive in shared_drives:
                        state.add_shared_drive(drive["id"], drive["name"])
                        # Add root folder for this shared drive
                        state.add_folder(
                            folder_id=drive["id"],
                            name=drive["name"],
                            path=["Shared Drives"],
                            parent_id=None,
                            source=SOURCE_SHARED_DRIVES,
                        )
                        # Store drive_id in folder info for later
                        state.state["folders_discovered"][drive["id"]]["drive_id"] = drive["id"]

                    state.save()

                # Process shared drive folders
                folders_processed = 0
                while True:
                    folder_id = state.get_next_folder()
                    if folder_id is None:
                        break

                    folder_info = state.get_folder_info(folder_id)
                    folder_source = folder_info.get("source") if folder_info else None

                    # Only process Shared Drive folders in this phase
                    if folder_source != SOURCE_SHARED_DRIVES:
                        state.state["folders_pending"].insert(0, folder_id)
                        break

                    # Get the drive_id for this folder
                    drive_id = folder_info.get("drive_id")
                    if not drive_id:
                        # Try to find it from parent chain
                        parent_id = folder_info.get("parent_id")
                        while parent_id:
                            parent_info = state.get_folder_info(parent_id)
                            if parent_info and parent_info.get("drive_id"):
                                drive_id = parent_info["drive_id"]
                                break
                            parent_id = parent_info.get("parent_id") if parent_info else None

                    success = await process_folder(
                        folder_id=folder_id,
                        state=state,
                        walker=walker,
                        client=client,
                        api_base=api_base,
                        logger=logger,
                        force=force,
                        extract_entities=extract_entities,
                        map_only=map_only,
                        concurrency=concurrency,
                        drive_id=drive_id,
                        source=SOURCE_SHARED_DRIVES,
                        precheck=precheck,
                    )

                    # Propagate drive_id to child folders
                    if drive_id:
                        for fid, finfo in state.state["folders_discovered"].items():
                            if finfo.get("parent_id") == folder_id and not finfo.get("drive_id"):
                                finfo["drive_id"] = drive_id

                    folders_processed += 1

                    if folders_processed % 10 == 0:
                        stats = state.get_stats()
                        logger.info(
                            f"[Shared Drives] Progress: {folders_processed} folders, "
                            f"{stats['files_indexed']} indexed"
                        )

                state.mark_source_complete(SOURCE_SHARED_DRIVES)
                state.save()
                logger.info(f"Shared Drives complete: {folders_processed} folders processed")

            # ================================================================
            # PHASE 3: SHARED WITH ME
            # ================================================================
            if SOURCE_SHARED_WITH_ME in sources_to_process and not state.is_source_complete(SOURCE_SHARED_WITH_ME):
                logger.info("")
                logger.info("=" * 40)
                logger.info("SHARED WITH ME")
                logger.info("=" * 40)

                # Discover shared-with-me files if not already done
                if not state.state["shared_files_pending"] and not state.state["shared_files_completed"]:
                    logger.info("Discovering files shared with me...")
                    shared_items = walker.list_shared_with_me_files()

                    # Separate folders and files
                    shared_folders = [f for f in shared_items if f.get("mimeType") == FOLDER_MIME_TYPE]
                    shared_files = [f for f in shared_items if f.get("mimeType") != FOLDER_MIME_TYPE]

                    logger.info(f"Found {len(shared_folders)} shared folders, {len(shared_files)} shared files")

                    # Add shared folders to process
                    for folder in shared_folders:
                        # Check if this folder is already discovered (might be in a shared drive)
                        if folder["id"] not in state.state["folders_discovered"]:
                            state.add_folder(
                                folder_id=folder["id"],
                                name=folder["name"],
                                path=["Shared with me"],
                                parent_id=None,
                                source=SOURCE_SHARED_WITH_ME,
                            )

                    # Add shared files for direct processing
                    for file in shared_files:
                        # Skip if already processed
                        if not state.is_file_processed(file["id"]):
                            state.add_shared_file(file["id"])

                    state.state["files_discovered"] += len(shared_files)
                    state.save()

                # Process shared folders first
                folders_processed = 0
                while True:
                    folder_id = state.get_next_folder()
                    if folder_id is None:
                        break

                    folder_info = state.get_folder_info(folder_id)
                    folder_source = folder_info.get("source") if folder_info else None

                    if folder_source != SOURCE_SHARED_WITH_ME:
                        state.state["folders_pending"].insert(0, folder_id)
                        break

                    success = await process_folder(
                        folder_id=folder_id,
                        state=state,
                        walker=walker,
                        client=client,
                        api_base=api_base,
                        logger=logger,
                        force=force,
                        extract_entities=extract_entities,
                        map_only=map_only,
                        concurrency=concurrency,
                        source=SOURCE_SHARED_WITH_ME,
                        precheck=precheck,
                    )

                    folders_processed += 1

                # Process shared files directly
                await process_shared_files(
                    state=state,
                    walker=walker,
                    client=client,
                    api_base=api_base,
                    logger=logger,
                    force=force,
                    extract_entities=extract_entities,
                    map_only=map_only,
                    concurrency=concurrency,
                    precheck=precheck,
                )

                state.mark_source_complete(SOURCE_SHARED_WITH_ME)
                state.save()
                logger.info(f"Shared with me complete: {folders_processed} folders + shared files processed")

        except KeyboardInterrupt:
            logger.info("\nInterrupted by user. Progress saved.")
            state.save()
            return

        # Final summary
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        stats = state.get_stats()

        logger.info("")
        logger.info("=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Elapsed time:           {elapsed:.1f}s")
        logger.info(f"Sources completed:      {stats['sources_completed']}/{stats['sources_requested']}")
        logger.info(f"Shared drives:          {stats['shared_drives_completed']}/{stats['shared_drives_discovered']}")
        logger.info(f"Folders discovered:     {stats['folders_discovered']}")
        logger.info(f"Folders completed:      {stats['folders_completed']}")
        logger.info(f"Folders failed:         {stats['folders_failed']}")
        logger.info(f"Shared files processed: {stats['shared_files_completed']}")
        logger.info(f"Files discovered:       {stats['files_discovered']}")
        logger.info(f"Files indexed:          {stats['files_indexed']}")
        logger.info(f"Files skipped:          {stats['files_skipped']}")
        logger.info(f"Files failed:           {stats['files_failed']}")
        logger.info(f"Total chunks:           {stats['total_chunks']}")
        logger.info("")
        logger.info(f"State file: {state_file}")
        logger.info(f"Log file:   {log_file}")

        # List failed folders if any
        if state.state["folders_failed"]:
            logger.info("")
            logger.info("Failed folders:")
            for fid, error in state.state["folders_failed"].items():
                info = state.get_folder_info(fid)
                name = info["name"] if info else fid
                logger.info(f"  - {name}: {error[:60]}")

        # List failed files if any (just count, details in state file)
        if state.state["files_failed"]:
            logger.info("")
            logger.info(f"Failed files: {len(state.state['files_failed'])} (see state file for details)")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest all accessible Google Drive content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--root",
        metavar="FOLDER_ID",
        help="Start from specific folder instead of Drive root (only for my-drive source)",
    )

    parser.add_argument(
        "--source",
        choices=VALID_SOURCES,
        default=SOURCE_ALL,
        help=f"Which source(s) to ingest: {', '.join(VALID_SOURCES)} (default: {SOURCE_ALL})",
    )

    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"Base URL for drive-rag-service API (default: {DEFAULT_API_BASE})",
    )

    parser.add_argument(
        "--state-file",
        type=Path,
        default=STATE_FILE,
        help=f"State file for progress tracking (default: {STATE_FILE})",
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        default=LOG_FILE,
        help=f"Log file (default: {LOG_FILE})",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing even if documents haven't changed",
    )

    parser.add_argument(
        "--extract-entities",
        action="store_true",
        help="Extract entities to knowledge graph via Graphiti",
    )

    parser.add_argument(
        "--map-only",
        action="store_true",
        help="Only map the folder tree, don't ingest files",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing state file (default behavior if state exists)",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset state and start fresh",
    )

    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=3,
        help="Number of concurrent ingestion requests (default: 3)",
    )

    parser.add_argument(
        "--precheck",
        action="store_true",
        help="Pre-check file existence before ingestion (faster for shared files with many deletions)",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Handle reset
    if args.reset and args.state_file.exists():
        args.state_file.unlink()
        print(f"Reset: removed {args.state_file}")

    # Run
    asyncio.run(run_tree_ingestion(
        root_folder_id=args.root,
        api_base=args.api_base,
        state_file=args.state_file,
        log_file=args.log_file,
        force=args.force,
        extract_entities=args.extract_entities,
        map_only=args.map_only,
        concurrency=args.concurrency,
        verbose=args.verbose,
        source=args.source,
        precheck=args.precheck,
    ))


if __name__ == "__main__":
    main()
