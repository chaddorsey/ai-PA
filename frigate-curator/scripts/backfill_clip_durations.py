#!/usr/bin/env python3
"""Re-probe every highlight's on-disk clip and update duration_s.

Original duration_s = end_time - start_time (the tracked-object
lifetime). The actual clip file is wrapped by Frigate's pre_capture +
post_capture seconds, so a 5s tracked event lands in a ~55s file and
the card's "5s" label didn't match what playback showed.

This one-shot fixes existing rows so the gallery numbers match the
clip files. New events get the correct duration directly via
curator.py's _probe_clip_duration call.

Usage:
  cd /Volumes/main-drive/ai-PA/frigate-curator
  ./venv/bin/python scripts/backfill_clip_durations.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ENV = Path("/Volumes/main-drive/ai-PA/.env")
if ENV.is_file():
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k, v)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frigate_curator.curator import _probe_clip_duration  # noqa: E402

HIGHLIGHTS_ROOT = Path(os.environ.get(
    "HIGHLIGHTS_ROOT", "/Volumes/main-filestore/frigate-highlights"))
DB = HIGHLIGHTS_ROOT / "index.db"


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT event_id, clip_path, duration_s FROM highlights "
        "WHERE clip_path IS NOT NULL"
    ).fetchall()
    n_ok = n_skip = n_fail = 0
    for r in rows:
        eid = r["event_id"]
        path = HIGHLIGHTS_ROOT / r["clip_path"]
        if not path.exists():
            print(f"[skip] {eid}: {path} missing")
            n_skip += 1
            continue
        d = _probe_clip_duration(path)
        if d is None:
            print(f"[fail] {eid}: ffprobe returned no value")
            n_fail += 1
            continue
        old = r["duration_s"] or 0
        # Always force-write the ffprobe value so the field never drifts
        # from the on-disk file, even when within tenths of a second.
        if abs(d - old) > 0.01:
            conn.execute(
                "UPDATE highlights SET duration_s = ? WHERE event_id = ?",
                [d, eid],
            )
            print(f"[ok]   {eid}: {old:.2f}s → {d:.2f}s")
        n_ok += 1
    conn.commit()
    conn.close()
    print(f"\nDone. updated/checked={n_ok}  skipped={n_skip}  failed={n_fail}  total={len(rows)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
