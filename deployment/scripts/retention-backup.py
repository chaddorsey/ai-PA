#!/usr/bin/env python3
"""
retention-backup.py — tiered retention for pa-ecosystem backups.

Policy (all configurable):
  1. Last N days (default 14):   keep every backup
  2. Next M days (default 60):   keep the newest backup per ISO week
  3. Next K months (default 12): keep the newest backup per calendar month
  4. Beyond that:                delete

Safety rails:
  - Refuses to run if no backup exists within the daily window (suggests something is wrong).
  - Refuses to delete the backup referenced by the 'latest' symlink.
  - --dry-run mode prints the plan without deleting.

Usage:
  retention-backup.py [--dir DIR] [--daily-days N] [--weekly-days M]
                      [--monthly-months K] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import sys
from pathlib import Path

NAME_RE = re.compile(r"^pa-ecosystem-backup-(\d{8})_(\d{6})$")


def parse_ts(name: str) -> datetime.datetime | None:
    m = NAME_RE.match(name)
    if not m:
        return None
    return datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")


def dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="/Volumes/main-drive/ai-PA/deployment/backups",
                    help="Directory containing pa-ecosystem-backup-* entries (default: deployment/backups symlink)")
    ap.add_argument("--daily-days", type=int, default=14)
    ap.add_argument("--weekly-days", type=int, default=60)
    ap.add_argument("--monthly-months", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true", help="Print plan, don't delete")
    args = ap.parse_args()

    backup_dir = Path(args.dir).resolve()
    if not backup_dir.is_dir():
        print(f"ERROR: {backup_dir} not found", file=sys.stderr)
        return 2

    now = datetime.datetime.now()
    daily_cut = now - datetime.timedelta(days=args.daily_days)
    weekly_cut = now - datetime.timedelta(days=args.weekly_days)
    monthly_cut = now - datetime.timedelta(days=args.monthly_months * 30)

    latest_link = backup_dir / "latest"
    latest_target: Path | None = None
    if latest_link.is_symlink():
        latest_target = (backup_dir / os.readlink(latest_link)).resolve()

    backups: list[tuple[Path, datetime.datetime]] = []
    for entry in backup_dir.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue
        ts = parse_ts(entry.name)
        if ts is None:
            continue
        backups.append((entry.resolve(), ts))

    if not backups:
        print("No pa-ecosystem-backup-* directories found. Nothing to do.")
        return 0

    backups.sort(key=lambda x: x[1], reverse=True)

    recent = sum(1 for _, ts in backups if ts >= daily_cut)
    if recent < 1:
        print(f"SAFETY: no backups within last {args.daily_days} days; "
              "refusing to prune. Run a fresh backup first.", file=sys.stderr)
        return 2

    keep: set[Path] = set()
    weekly_seen: set[tuple[int, int]] = set()
    monthly_seen: set[tuple[int, int]] = set()

    for path, ts in backups:
        if latest_target and path == latest_target:
            keep.add(path)
            continue
        if ts >= daily_cut:
            keep.add(path)
        elif ts >= weekly_cut:
            week_key = ts.isocalendar()[:2]  # (iso_year, iso_week)
            if week_key not in weekly_seen:
                keep.add(path)
                weekly_seen.add(week_key)
        elif ts >= monthly_cut:
            month_key = (ts.year, ts.month)
            if month_key not in monthly_seen:
                keep.add(path)
                monthly_seen.add(month_key)
        # else: outside monthly window -> prune

    to_keep = [(p, t) for p, t in backups if p in keep]
    to_delete = [(p, t) for p, t in backups if p not in keep]

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"=== retention-backup.py [{mode}] at {now.isoformat(timespec='seconds')} ===")
    print(f"Dir:         {backup_dir}")
    print(f"Policy:      daily<{args.daily_days}d | weekly<{args.weekly_days}d | monthly<{args.monthly_months}mo")
    print(f"Latest link: {latest_target.name if latest_target else '<none>'}")
    print(f"Candidates:  {len(backups)} total -> keep {len(to_keep)}, delete {len(to_delete)}")
    print()

    print("KEEP:")
    for p, t in sorted(to_keep, key=lambda x: x[1], reverse=True):
        print(f"  {t.isoformat(sep=' ', timespec='seconds')}  {p.name}")
    print()

    print("DELETE:")
    freed = 0
    for p, t in sorted(to_delete, key=lambda x: x[1]):
        try:
            size = dir_size_bytes(p)
        except Exception:
            size = 0
        freed += size
        action = "would delete" if args.dry_run else "deleting"
        print(f"  {t.isoformat(sep=' ', timespec='seconds')}  {p.name}  ({size/(1024**3):.1f} GB)  [{action}]")
        if not args.dry_run:
            try:
                shutil.rmtree(p)
            except Exception as e:
                print(f"    error: {e}", file=sys.stderr)

    print()
    print(f"Total freed: {freed/(1024**3):.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
