"""Document snapshot storage for edit tracking (Phase 2).

This module handles storage and retrieval of document content snapshots
for computing diffs and tracking changes over time.

Snapshots are stored as gzip-compressed JSON files on the filesystem:
  {base_path}/{file_id_prefix}/{file_id}/{revision_id}.json.gz

The database table rag.document_snapshots stores metadata and pointers.
"""

import gzip
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from drive_rag.models import NormalizedSnapshot, StructureBlock, DocumentRevision
from drive_rag.settings import get_settings

logger = structlog.get_logger()

# Default base path for snapshot storage
DEFAULT_SNAPSHOT_BASE_PATH = "/Volumes/main-filestore/ai-PA-data/drive-rag-snapshots"


def get_snapshot_base_path() -> Path:
    """Get the base path for snapshot storage."""
    path = os.environ.get("SNAPSHOT_BASE_PATH", DEFAULT_SNAPSHOT_BASE_PATH)
    return Path(path)


def _get_snapshot_path(file_id: str, revision_id: str) -> Path:
    """Generate the filesystem path for a snapshot.

    Uses first 2 characters of file_id as a prefix directory
    to avoid too many files in a single directory.

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID

    Returns:
        Full path to the snapshot file
    """
    prefix = file_id[:2] if len(file_id) >= 2 else file_id
    base = get_snapshot_base_path()
    return base / prefix / file_id / f"{revision_id}.json.gz"


def _get_relative_path(file_id: str, revision_id: str) -> str:
    """Get the relative path for database storage.

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID

    Returns:
        Relative path from base directory
    """
    prefix = file_id[:2] if len(file_id) >= 2 else file_id
    return f"{prefix}/{file_id}/{revision_id}.json.gz"


def save_snapshot(
    file_id: str,
    revision_id: str,
    snapshot: NormalizedSnapshot,
    modifier_email: Optional[str] = None,
    modifier_name: Optional[str] = None,
    modified_time: Optional[datetime] = None,
) -> dict[str, Any]:
    """Save a document snapshot to filesystem.

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID
        snapshot: Normalized document snapshot
        modifier_email: Email of user who made this revision
        modifier_name: Display name of modifier
        modified_time: Time of this revision

    Returns:
        Metadata dict for database storage including:
        - snapshot_path: Relative path to file
        - compressed_size_bytes: Size of compressed file
        - content_hash: Hash of content
        - normalized_text_length: Length of text
        - blocks_count: Number of structure blocks
    """
    path = _get_snapshot_path(file_id, revision_id)
    relative_path = _get_relative_path(file_id, revision_id)

    # Create directory structure
    path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize snapshot to JSON
    data = {
        "normalized_text": snapshot.normalized_text,
        "normalized_hash": snapshot.normalized_hash,
        "blocks": [
            {
                "block_id": b.block_id,
                "type": b.type,
                "outline_path": b.outline_path,
                "heading_level": b.heading_level,
                "list_level": b.list_level,
                "text_hash": b.text_hash,
                "char_start": b.char_start,
                "char_end": b.char_end,
                "text": b.text,
            }
            for b in snapshot.blocks
        ],
        # Metadata for context
        "file_id": file_id,
        "revision_id": revision_id,
        "modifier_email": modifier_email,
        "modifier_name": modifier_name,
        "modified_time": modified_time.isoformat() if modified_time else None,
        "saved_at": datetime.utcnow().isoformat(),
    }

    # Compress and write
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    with gzip.open(path, "wb") as f:
        f.write(json_bytes)

    compressed_size = path.stat().st_size

    logger.info(
        "saved_snapshot",
        file_id=file_id,
        revision_id=revision_id,
        path=str(relative_path),
        text_length=len(snapshot.normalized_text),
        blocks_count=len(snapshot.blocks),
        compressed_size=compressed_size,
    )

    return {
        "snapshot_path": relative_path,
        "compressed_size_bytes": compressed_size,
        "content_hash": snapshot.normalized_hash,
        "normalized_text_length": len(snapshot.normalized_text),
        "blocks_count": len(snapshot.blocks),
        "modifier_email": modifier_email,
        "modifier_name": modifier_name,
        "modified_time": modified_time,
    }


def load_snapshot(file_id: str, revision_id: str) -> Optional[NormalizedSnapshot]:
    """Load a document snapshot from filesystem.

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID

    Returns:
        NormalizedSnapshot if found, None otherwise
    """
    path = _get_snapshot_path(file_id, revision_id)

    if not path.exists():
        logger.warning("snapshot_not_found", file_id=file_id, revision_id=revision_id)
        return None

    try:
        with gzip.open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))

        blocks = [
            StructureBlock(
                block_id=b["block_id"],
                type=b["type"],
                outline_path=b.get("outline_path", []),
                heading_level=b.get("heading_level"),
                list_level=b.get("list_level"),
                text_hash=b["text_hash"],
                char_start=b.get("char_start"),
                char_end=b.get("char_end"),
                text=b.get("text", ""),
            )
            for b in data.get("blocks", [])
        ]

        logger.debug(
            "loaded_snapshot",
            file_id=file_id,
            revision_id=revision_id,
            text_length=len(data.get("normalized_text", "")),
            blocks_count=len(blocks),
        )

        return NormalizedSnapshot(
            normalized_text=data["normalized_text"],
            normalized_hash=data["normalized_hash"],
            blocks=blocks,
        )

    except Exception as e:
        logger.exception("snapshot_load_error", file_id=file_id, revision_id=revision_id, error=str(e))
        return None


def load_snapshot_from_path(relative_path: str) -> Optional[NormalizedSnapshot]:
    """Load a snapshot using its relative path.

    Args:
        relative_path: Relative path from base directory

    Returns:
        NormalizedSnapshot if found, None otherwise
    """
    base = get_snapshot_base_path()
    path = base / relative_path

    if not path.exists():
        logger.warning("snapshot_not_found_by_path", path=relative_path)
        return None

    try:
        with gzip.open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))

        blocks = [
            StructureBlock(
                block_id=b["block_id"],
                type=b["type"],
                outline_path=b.get("outline_path", []),
                heading_level=b.get("heading_level"),
                list_level=b.get("list_level"),
                text_hash=b["text_hash"],
                char_start=b.get("char_start"),
                char_end=b.get("char_end"),
                text=b.get("text", ""),
            )
            for b in data.get("blocks", [])
        ]

        return NormalizedSnapshot(
            normalized_text=data["normalized_text"],
            normalized_hash=data["normalized_hash"],
            blocks=blocks,
        )

    except Exception as e:
        logger.exception("snapshot_load_error", path=relative_path, error=str(e))
        return None


def delete_snapshot(file_id: str, revision_id: str) -> bool:
    """Delete a snapshot file.

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID

    Returns:
        True if deleted, False if not found
    """
    path = _get_snapshot_path(file_id, revision_id)

    if not path.exists():
        return False

    try:
        path.unlink()
        logger.info("deleted_snapshot", file_id=file_id, revision_id=revision_id)

        # Clean up empty directories
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            grandparent = parent.parent
            if grandparent.exists() and not any(grandparent.iterdir()):
                grandparent.rmdir()

        return True

    except Exception as e:
        logger.exception("snapshot_delete_error", file_id=file_id, revision_id=revision_id, error=str(e))
        return False


def list_snapshots(file_id: str) -> list[str]:
    """List all revision IDs that have snapshots for a file.

    Args:
        file_id: Google Drive file ID

    Returns:
        List of revision IDs with snapshots
    """
    prefix = file_id[:2] if len(file_id) >= 2 else file_id
    base = get_snapshot_base_path()
    file_dir = base / prefix / file_id

    if not file_dir.exists():
        return []

    revision_ids = []
    for path in file_dir.glob("*.json.gz"):
        revision_id = path.stem.replace(".json", "")
        revision_ids.append(revision_id)

    return revision_ids


def get_snapshot_stats() -> dict[str, Any]:
    """Get statistics about snapshot storage.

    Returns:
        Dictionary with storage statistics
    """
    base = get_snapshot_base_path()

    if not base.exists():
        return {
            "base_path": str(base),
            "exists": False,
            "total_files": 0,
            "total_size_bytes": 0,
        }

    total_files = 0
    total_size = 0
    unique_files = set()

    for gz_file in base.rglob("*.json.gz"):
        total_files += 1
        total_size += gz_file.stat().st_size
        # Extract file_id from path: prefix/file_id/revision.json.gz
        if len(gz_file.parts) >= 2:
            unique_files.add(gz_file.parent.name)

    return {
        "base_path": str(base),
        "exists": True,
        "total_snapshots": total_files,
        "unique_documents": len(unique_files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }
