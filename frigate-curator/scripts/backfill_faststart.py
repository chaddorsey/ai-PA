#!/usr/bin/env python3
"""Re-mux every existing clip with -movflags +faststart.

Frigate writes the MP4 in a way that puts the moov atom at the END
of the file. Browsers using <video> read a small initial buffer to
populate video.duration, so the scrubber shows ~3s at first and
only catches up once the trailing moov is fetched. This rewrites
each clip in place so the moov is at the start and total duration
is known to the browser on the first byte.

Idempotent — re-running on already-faststart-ed files is a no-op
container rewrite. Skips files where ffmpeg is unavailable or fails.

Usage:
  cd /Volumes/main-drive/ai-PA/frigate-curator
  ./venv/bin/python scripts/backfill_faststart.py
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
from frigate_curator.curator import _faststart_remux, _probe_clip_duration  # noqa: E402

HIGHLIGHTS_ROOT = Path(os.environ.get(
    "HIGHLIGHTS_ROOT", "/Volumes/main-filestore/frigate-highlights"))
DB = HIGHLIGHTS_ROOT / "index.db"


def main() -> int:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT event_id, clip_path FROM highlights WHERE clip_path IS NOT NULL"
    ).fetchall()
    n_ok = n_skip = n_fail = 0
    for r in rows:
        eid = r["event_id"]
        path = HIGHLIGHTS_ROOT / r["clip_path"]
        if not path.exists():
            print(f"[skip] {eid}: file missing")
            n_skip += 1
            continue
        ok = _faststart_remux(path)
        if ok:
            d = _probe_clip_duration(path)
            if d:
                conn.execute(
                    "UPDATE highlights SET duration_s = ? WHERE event_id = ?",
                    [d, eid],
                )
            print(f"[ok]   {eid}  ({d:.2f}s)" if d else f"[ok]   {eid}")
            n_ok += 1
        else:
            print(f"[fail] {eid}")
            n_fail += 1
    conn.commit()
    conn.close()
    print(f"\nDone. ok={n_ok} skipped={n_skip} failed={n_fail} total={len(rows)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
