"""Snapshot retention policy management.

This module implements tiered retention for document snapshots:
- Tier 1 (0-7 days): Keep ALL snapshots (full edit history)
- Tier 2 (8-90 days): Keep ONE snapshot per day per document
- Tier 3 (90+ days): Keep ONE snapshot per document (most recent from that era)

IMPORTANT: No snapshots are deleted entirely - we always keep at least
one persistent copy per document.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from drive_rag.db import get_db, Database
from drive_rag.models import DocumentSnapshot
from drive_rag.snapshots import delete_snapshot
from drive_rag.settings import get_settings

logger = structlog.get_logger()


@dataclass
class RetentionResult:
    """Result of applying retention policy."""

    snapshots_analyzed: int = 0
    snapshots_kept: int = 0
    snapshots_deleted: int = 0
    space_freed_bytes: int = 0
    dry_run: bool = True
    errors: list[str] = field(default_factory=list)

    # Breakdown by tier
    tier1_kept: int = 0  # 0-7 days: all kept
    tier2_kept: int = 0  # 8-90 days: daily kept
    tier2_deleted: int = 0  # 8-90 days: extras deleted
    tier3_kept: int = 0  # 90+ days: one per document kept
    tier3_deleted: int = 0  # 90+ days: extras deleted

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "snapshots_analyzed": self.snapshots_analyzed,
            "snapshots_kept": self.snapshots_kept,
            "snapshots_deleted": self.snapshots_deleted,
            "space_freed_bytes": self.space_freed_bytes,
            "space_freed_mb": round(self.space_freed_bytes / (1024 * 1024), 2),
            "dry_run": self.dry_run,
            "error_count": len(self.errors),
            "errors": self.errors[:20],  # Limit errors in response
            "breakdown": {
                "tier1_full_retention": {"days": "0-7", "kept": self.tier1_kept},
                "tier2_daily_retention": {
                    "days": "8-90",
                    "kept": self.tier2_kept,
                    "deleted": self.tier2_deleted,
                },
                "tier3_archive": {
                    "days": "90+",
                    "kept": self.tier3_kept,
                    "deleted": self.tier3_deleted,
                },
            },
        }




def apply_retention_policy(
    dry_run: bool = True,
    tier1_days: Optional[int] = None,
    tier2_days: Optional[int] = None,
    db: Optional[Database] = None,
) -> RetentionResult:
    """Apply tiered retention policy to snapshot storage.

    Retention tiers:
    - Tier 1 (0 to tier1_days): Keep ALL snapshots
    - Tier 2 (tier1_days to tier2_days): Keep ONE per day per document
    - Tier 3 (older than tier2_days): Keep ONE per document total

    Args:
        dry_run: If True, don't actually delete - just report what would happen
        tier1_days: Days for full retention (default from settings: 7)
        tier2_days: Days for daily retention (default from settings: 90)
        db: Database client (defaults to global)

    Returns:
        RetentionResult with statistics
    """
    settings = get_settings()
    database = db or get_db()

    # Get retention thresholds
    if tier1_days is None:
        tier1_days = settings.snapshot_full_retention_days
    if tier2_days is None:
        tier2_days = settings.snapshot_daily_retention_days

    result = RetentionResult(dry_run=dry_run)

    # Use timezone-aware datetime to match database timestamps
    now = datetime.now(timezone.utc)
    tier1_cutoff = now - timedelta(days=tier1_days)
    tier2_cutoff = now - timedelta(days=tier2_days)

    logger.info(
        "starting_retention_policy",
        dry_run=dry_run,
        tier1_cutoff=tier1_cutoff.isoformat(),
        tier2_cutoff=tier2_cutoff.isoformat(),
    )

    # Get all snapshots
    all_snapshots = database.get_all_snapshots()
    result.snapshots_analyzed = len(all_snapshots)

    if not all_snapshots:
        logger.info("no_snapshots_to_process")
        return result

    # Group snapshots by file_id and by date
    by_file: dict[str, list[DocumentSnapshot]] = defaultdict(list)
    for snap in all_snapshots:
        by_file[snap.drive_file_id].append(snap)

    to_delete: list[DocumentSnapshot] = []
    to_keep: list[DocumentSnapshot] = []

    for file_id, snapshots in by_file.items():
        # Sort by modified_time descending (newest first)
        sorted_snaps = sorted(
            snapshots,
            key=lambda s: s.modified_time or datetime.min,
            reverse=True,
        )

        # Track what we keep per tier
        file_to_keep: list[DocumentSnapshot] = []
        file_to_delete: list[DocumentSnapshot] = []

        # Group by date for tier 2 processing
        by_date: dict[str, list[DocumentSnapshot]] = defaultdict(list)
        tier3_snaps: list[DocumentSnapshot] = []

        for snap in sorted_snaps:
            if snap.modified_time is None:
                # No timestamp - keep it (can't determine age)
                file_to_keep.append(snap)
                continue

            snap_date = snap.modified_time.date()

            if snap.modified_time >= tier1_cutoff:
                # Tier 1: Keep all
                file_to_keep.append(snap)
                result.tier1_kept += 1
            elif snap.modified_time >= tier2_cutoff:
                # Tier 2: Group by date
                by_date[str(snap_date)].append(snap)
            else:
                # Tier 3: Older than tier2_cutoff
                tier3_snaps.append(snap)

        # Process Tier 2: Keep one per day
        for date_str, date_snaps in by_date.items():
            # Sort by modified_time descending, keep the newest
            date_snaps.sort(
                key=lambda s: s.modified_time or datetime.min,
                reverse=True,
            )
            file_to_keep.append(date_snaps[0])
            result.tier2_kept += 1

            # Mark extras for deletion
            for snap in date_snaps[1:]:
                file_to_delete.append(snap)
                result.tier2_deleted += 1

        # Process Tier 3: Keep one per document (the most recent from tier 3)
        if tier3_snaps:
            # Sort by modified_time descending
            tier3_snaps.sort(
                key=lambda s: s.modified_time or datetime.min,
                reverse=True,
            )
            file_to_keep.append(tier3_snaps[0])
            result.tier3_kept += 1

            # Mark the rest for deletion
            for snap in tier3_snaps[1:]:
                file_to_delete.append(snap)
                result.tier3_deleted += 1

        to_keep.extend(file_to_keep)
        to_delete.extend(file_to_delete)

    result.snapshots_kept = len(to_keep)
    result.snapshots_deleted = len(to_delete)

    # Calculate space that would be freed
    for snap in to_delete:
        if snap.compressed_size_bytes:
            result.space_freed_bytes += snap.compressed_size_bytes

    logger.info(
        "retention_analysis_complete",
        analyzed=result.snapshots_analyzed,
        to_keep=result.snapshots_kept,
        to_delete=result.snapshots_deleted,
        space_freed_mb=round(result.space_freed_bytes / (1024 * 1024), 2),
    )

    # Execute deletions if not dry run
    if not dry_run and to_delete:
        logger.info("executing_deletions", count=len(to_delete))

        for snap in to_delete:
            try:
                # Delete filesystem snapshot
                deleted = delete_snapshot(snap.drive_file_id, snap.revision_id)

                # Delete database metadata
                database.delete_snapshot_metadata(snap.drive_file_id, snap.revision_id)

                if not deleted:
                    logger.warning(
                        "snapshot_file_not_found",
                        file_id=snap.drive_file_id,
                        revision_id=snap.revision_id,
                    )

            except Exception as e:
                error_msg = f"{snap.drive_file_id}/{snap.revision_id}: {str(e)[:100]}"
                result.errors.append(error_msg)
                logger.error(
                    "snapshot_deletion_failed",
                    file_id=snap.drive_file_id,
                    revision_id=snap.revision_id,
                    error=str(e),
                )

        logger.info(
            "retention_policy_complete",
            deleted=result.snapshots_deleted - len(result.errors),
            errors=len(result.errors),
        )

    return result


def get_retention_preview(
    tier1_days: Optional[int] = None,
    tier2_days: Optional[int] = None,
) -> dict:
    """Get a preview of what retention policy would do.

    This is a convenience wrapper around apply_retention_policy with dry_run=True.

    Args:
        tier1_days: Days for full retention (default from settings: 7)
        tier2_days: Days for daily retention (default from settings: 90)

    Returns:
        Dictionary with retention statistics
    """
    result = apply_retention_policy(
        dry_run=True,
        tier1_days=tier1_days,
        tier2_days=tier2_days,
    )
    return result.to_dict()
