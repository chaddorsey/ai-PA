"""Diff engine for comparing document snapshots (Phase 2).

This module computes block-level diffs between two document snapshots
to identify what changed, when, and by whom.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import structlog

from drive_rag.models import NormalizedSnapshot, StructureBlock

logger = structlog.get_logger()


class ChangeType(str, Enum):
    """Type of change detected between snapshots."""

    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"
    MOVED = "moved"


@dataclass
class BlockChange:
    """A single block-level change between snapshots."""

    change_type: ChangeType
    block_id: str
    block_type: str
    outline_path: list[str]

    # Content
    old_text: Optional[str] = None
    new_text: Optional[str] = None

    # Position
    old_char_start: Optional[int] = None
    old_char_end: Optional[int] = None
    new_char_start: Optional[int] = None
    new_char_end: Optional[int] = None


@dataclass
class SnapshotDiff:
    """Result of comparing two snapshots."""

    # Identifiers
    file_id: str
    baseline_revision: str
    target_revision: str

    # Attribution
    baseline_time: Optional[datetime] = None
    target_time: Optional[datetime] = None
    modifier_email: Optional[str] = None
    modifier_name: Optional[str] = None

    # Changes
    changes: list[BlockChange] = None

    # Summary statistics
    blocks_added: int = 0
    blocks_deleted: int = 0
    blocks_modified: int = 0
    chars_added: int = 0
    chars_deleted: int = 0

    def __post_init__(self):
        if self.changes is None:
            self.changes = []

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self.changes) > 0

    @property
    def change_summary(self) -> str:
        """Generate a human-readable summary of changes."""
        parts = []
        if self.blocks_added > 0:
            parts.append(f"+{self.blocks_added} blocks")
        if self.blocks_deleted > 0:
            parts.append(f"-{self.blocks_deleted} blocks")
        if self.blocks_modified > 0:
            parts.append(f"~{self.blocks_modified} modified")
        return ", ".join(parts) if parts else "no changes"


def diff_snapshots(
    baseline: NormalizedSnapshot,
    target: NormalizedSnapshot,
    file_id: str = "",
    baseline_revision: str = "",
    target_revision: str = "",
    baseline_time: Optional[datetime] = None,
    target_time: Optional[datetime] = None,
    modifier_email: Optional[str] = None,
    modifier_name: Optional[str] = None,
) -> SnapshotDiff:
    """Compare two snapshots and identify changes.

    Uses block-level comparison based on text_hash for efficient change detection.
    Blocks with the same text_hash are considered unchanged.

    Args:
        baseline: The earlier snapshot (before changes)
        target: The later snapshot (after changes)
        file_id: Google Drive file ID
        baseline_revision: Revision ID of baseline
        target_revision: Revision ID of target
        baseline_time: Timestamp of baseline revision
        target_time: Timestamp of target revision
        modifier_email: Email of user who made the changes
        modifier_name: Display name of modifier

    Returns:
        SnapshotDiff with all detected changes
    """
    changes: list[BlockChange] = []

    # Build lookup maps by text_hash
    baseline_by_hash = {b.text_hash: b for b in baseline.blocks}
    target_by_hash = {b.text_hash: b for b in target.blocks}

    # Also track by block_id for position changes
    baseline_by_id = {b.block_id: b for b in baseline.blocks}
    target_by_id = {b.block_id: b for b in target.blocks}

    # Find deleted and modified blocks
    for block in baseline.blocks:
        if block.text_hash not in target_by_hash:
            # Block was deleted or modified
            # Check if block_id exists with different content
            if block.block_id in target_by_id:
                # Same block ID, different content = modified
                target_block = target_by_id[block.block_id]
                changes.append(
                    BlockChange(
                        change_type=ChangeType.MODIFIED,
                        block_id=block.block_id,
                        block_type=block.type,
                        outline_path=block.outline_path,
                        old_text=block.text,
                        new_text=target_block.text,
                        old_char_start=block.char_start,
                        old_char_end=block.char_end,
                        new_char_start=target_block.char_start,
                        new_char_end=target_block.char_end,
                    )
                )
            else:
                # Block ID doesn't exist in target = deleted
                changes.append(
                    BlockChange(
                        change_type=ChangeType.DELETED,
                        block_id=block.block_id,
                        block_type=block.type,
                        outline_path=block.outline_path,
                        old_text=block.text,
                        old_char_start=block.char_start,
                        old_char_end=block.char_end,
                    )
                )

    # Find added blocks
    for block in target.blocks:
        if block.text_hash not in baseline_by_hash:
            # Block is new or modified (modified already handled above)
            if block.block_id not in baseline_by_id:
                # Completely new block
                changes.append(
                    BlockChange(
                        change_type=ChangeType.ADDED,
                        block_id=block.block_id,
                        block_type=block.type,
                        outline_path=block.outline_path,
                        new_text=block.text,
                        new_char_start=block.char_start,
                        new_char_end=block.char_end,
                    )
                )

    # Calculate statistics
    blocks_added = sum(1 for c in changes if c.change_type == ChangeType.ADDED)
    blocks_deleted = sum(1 for c in changes if c.change_type == ChangeType.DELETED)
    blocks_modified = sum(1 for c in changes if c.change_type == ChangeType.MODIFIED)

    chars_added = sum(len(c.new_text or "") for c in changes if c.change_type == ChangeType.ADDED)
    chars_added += sum(
        max(0, len(c.new_text or "") - len(c.old_text or ""))
        for c in changes
        if c.change_type == ChangeType.MODIFIED
    )

    chars_deleted = sum(len(c.old_text or "") for c in changes if c.change_type == ChangeType.DELETED)
    chars_deleted += sum(
        max(0, len(c.old_text or "") - len(c.new_text or ""))
        for c in changes
        if c.change_type == ChangeType.MODIFIED
    )

    logger.info(
        "computed_diff",
        file_id=file_id,
        baseline_revision=baseline_revision[:16] if baseline_revision else "",
        target_revision=target_revision[:16] if target_revision else "",
        blocks_added=blocks_added,
        blocks_deleted=blocks_deleted,
        blocks_modified=blocks_modified,
    )

    return SnapshotDiff(
        file_id=file_id,
        baseline_revision=baseline_revision,
        target_revision=target_revision,
        baseline_time=baseline_time,
        target_time=target_time,
        modifier_email=modifier_email,
        modifier_name=modifier_name,
        changes=changes,
        blocks_added=blocks_added,
        blocks_deleted=blocks_deleted,
        blocks_modified=blocks_modified,
        chars_added=chars_added,
        chars_deleted=chars_deleted,
    )


def format_diff_summary(diff: SnapshotDiff, max_preview_chars: int = 100) -> str:
    """Format a diff as a human-readable summary.

    Args:
        diff: The diff to format
        max_preview_chars: Maximum characters to show in text previews

    Returns:
        Formatted summary string
    """
    lines = []

    # Header
    if diff.modifier_name or diff.modifier_email:
        modifier = diff.modifier_name or diff.modifier_email
        lines.append(f"Changes by {modifier}")
    if diff.target_time:
        lines.append(f"at {diff.target_time.strftime('%Y-%m-%d %H:%M')}")

    lines.append(f"\nSummary: {diff.change_summary}")
    lines.append("")

    # Group changes by type
    for change_type in [ChangeType.ADDED, ChangeType.MODIFIED, ChangeType.DELETED]:
        type_changes = [c for c in diff.changes if c.change_type == change_type]
        if not type_changes:
            continue

        lines.append(f"## {change_type.value.title()} ({len(type_changes)})")
        lines.append("")

        for change in type_changes[:10]:  # Limit to first 10 per type
            outline = " > ".join(change.outline_path) if change.outline_path else "(root)"
            lines.append(f"- [{change.block_type}] {outline}")

            if change.change_type == ChangeType.ADDED and change.new_text:
                preview = change.new_text[:max_preview_chars]
                if len(change.new_text) > max_preview_chars:
                    preview += "..."
                lines.append(f"  + {preview}")

            elif change.change_type == ChangeType.DELETED and change.old_text:
                preview = change.old_text[:max_preview_chars]
                if len(change.old_text) > max_preview_chars:
                    preview += "..."
                lines.append(f"  - {preview}")

            elif change.change_type == ChangeType.MODIFIED:
                if change.old_text:
                    preview = change.old_text[:max_preview_chars // 2]
                    if len(change.old_text) > max_preview_chars // 2:
                        preview += "..."
                    lines.append(f"  - {preview}")
                if change.new_text:
                    preview = change.new_text[:max_preview_chars // 2]
                    if len(change.new_text) > max_preview_chars // 2:
                        preview += "..."
                    lines.append(f"  + {preview}")

            lines.append("")

        if len(type_changes) > 10:
            lines.append(f"  ... and {len(type_changes) - 10} more")
            lines.append("")

    return "\n".join(lines)


def get_affected_sections(diff: SnapshotDiff) -> list[str]:
    """Get list of document sections affected by changes.

    Args:
        diff: The diff to analyze

    Returns:
        List of unique section paths (from outline_path)
    """
    sections = set()
    for change in diff.changes:
        if change.outline_path:
            # Add each level of the path
            for i in range(len(change.outline_path)):
                section = " > ".join(change.outline_path[: i + 1])
                sections.add(section)
        else:
            sections.add("(document root)")

    return sorted(sections)
