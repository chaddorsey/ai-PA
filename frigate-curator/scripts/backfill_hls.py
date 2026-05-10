#!/usr/bin/env python3
"""One-off HLS backfill for existing highlights.

Walks every clip in the DB and runs ffmpeg to produce its HLS bundle
if not already present. Designed to run alongside live curator
traffic without competing for resources:

  - os.nice(19) at startup pushes this process + its ffmpeg children
    to the lowest CPU priority. Live curator threads + API requests
    win every CPU contention.
  - One ffmpeg at a time (no parallelism). Bulk media volume disk
    bandwidth + sqlite reads on the SSD shouldn't saturate.
  - Idempotent: skips clips that already have a valid index.m3u8.
    Safe to re-run if interrupted.
  - Newest-first: most-likely-watched clips get HLS first; older
    archive clips fill in last.

Run via:
  /Volumes/main-drive/ai-PA/frigate-curator/venv/bin/python \
    /Volumes/main-drive/ai-PA/frigate-curator/scripts/backfill_hls.py

Recommend redirecting stdout to a log file when running in background:
  ... > ~/Library/Logs/frigate-curator/hls-backfill.log 2>&1 &

Race with curator's lazy-render path: low-probability. Both processes
call ensure_hls_rendered() and could collide on _hls.tmp/. The first
one to atomically rename wins; the loser sees its partial dir wiped
and exits with a logged failure for that clip. Lazy-render catches
those clips on the next user request.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Be polite. Lowest CPU priority for this process + every ffmpeg
# subprocess it spawns. macOS doesn't have ionice but `taskpolicy
# -d throughput` would push to background I/O class — call out to
# it via subprocess if you want that too. For now, nice alone has
# been enough in our testing.
try:
    os.nice(19)
except Exception:
    pass  # not critical

# Make the package importable regardless of cwd.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from frigate_curator import db, hls  # noqa: E402

HIGHLIGHTS_ROOT = Path(os.environ.get(
    "HIGHLIGHTS_ROOT", "/Volumes/main-filestore/frigate-highlights"
))
DB_PATH = Path(os.environ.get(
    "CURATOR_DB", "/Volumes/main-drive/ai-PA/curator-data/index.db"
))


def main() -> int:
    if not DB_PATH.exists():
        print(f"FATAL: DB missing at {DB_PATH}", flush=True)
        return 1
    if not HIGHLIGHTS_ROOT.exists():
        print(f"FATAL: highlights root missing at {HIGHLIGHTS_ROOT}", flush=True)
        return 1

    print(f"HLS backfill starting", flush=True)
    print(f"  DB:               {DB_PATH}", flush=True)
    print(f"  HIGHLIGHTS_ROOT:  {HIGHLIGHTS_ROOT}", flush=True)

    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT event_id, clip_path FROM highlights "
            "WHERE clip_path IS NOT NULL "
            "ORDER BY start_time DESC"
        ).fetchall()

    total = len(rows)
    print(f"  total highlights: {total}", flush=True)
    print("", flush=True)

    rendered = 0
    skipped_already = 0
    skipped_missing_src = 0
    failed = 0
    started = time.monotonic()

    for i, row in enumerate(rows, 1):
        clip_relpath = row["clip_path"]

        if hls.is_rendered(HIGHLIGHTS_ROOT, clip_relpath):
            skipped_already += 1
        else:
            src = HIGHLIGHTS_ROOT / clip_relpath
            if not src.exists():
                skipped_missing_src += 1
                if i <= 5 or i % 100 == 0:
                    print(f"  [{i}/{total}] SKIP missing source: {clip_relpath}", flush=True)
            else:
                t0 = time.monotonic()
                result = hls.ensure_hls_rendered(HIGHLIGHTS_ROOT, clip_relpath)
                dt = time.monotonic() - t0
                if result is None:
                    failed += 1
                    print(f"  [{i}/{total}] FAIL {clip_relpath}  ({dt:.1f}s)", flush=True)
                else:
                    rendered += 1
                    if rendered <= 5 or rendered % 25 == 0:
                        print(f"  [{i}/{total}] ok {clip_relpath}  ({dt:.1f}s)", flush=True)

        # Progress heartbeat every 50 clips
        if i % 50 == 0 or i == total:
            elapsed = time.monotonic() - started
            rate = i / max(elapsed, 1)
            remaining = (total - i) / max(rate, 0.001)
            print(f"  --- progress {i}/{total}  "
                  f"rendered={rendered} skip-already={skipped_already} "
                  f"skip-missing={skipped_missing_src} failed={failed}  "
                  f"elapsed={elapsed:.0f}s  eta={remaining:.0f}s", flush=True)

    elapsed = time.monotonic() - started
    print("", flush=True)
    print("HLS backfill DONE", flush=True)
    print(f"  total:       {total}", flush=True)
    print(f"  newly built: {rendered}", flush=True)
    print(f"  already had: {skipped_already}", flush=True)
    print(f"  src missing: {skipped_missing_src}", flush=True)
    print(f"  failed:      {failed}", flush=True)
    print(f"  elapsed:     {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
