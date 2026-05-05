#!/usr/bin/env python3
"""Re-fetch all highlights' thumbnails as full-frame snapshots.

The earlier curator wrote bbox-cropped thumbnails (Frigate's
/api/events/{id}/thumbnail.jpg). We've since switched to full-frame
snapshots (/api/events/{id}/snapshot.jpg) — see the most recent
download_thumbnail() change in frigate_client.py.

This script walks every existing highlight and re-downloads the
snapshot, overwriting the on-disk thumb_path. Idempotent: rerun safe.
Skips events where snapshot.jpg returns 404 (older Frigate versions
or pruned recordings). Logs success/skip counts at the end.

Usage from the host (uses the same .env Frigate credentials):
  cd /Volumes/main-drive/ai-PA/frigate-curator
  ./venv/bin/python scripts/backfill_thumbnails.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

# Pull credentials from the same .env the curator service uses.
ENV_PATH = Path("/Volumes/main-drive/ai-PA/.env")
if ENV_PATH.is_file():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k, v)

# Make the package importable when run from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frigate_curator.frigate_client import FrigateClient  # noqa: E402

HIGHLIGHTS_ROOT = Path(os.environ.get(
    "HIGHLIGHTS_ROOT", "/Volumes/main-filestore/frigate-highlights"
))
DB_PATH = HIGHLIGHTS_ROOT / "index.db"
FRIGATE_BASE_URL = os.environ.get("FRIGATE_BASE_URL", "https://localhost:8971")
FRIGATE_USER = os.environ.get("FRIGATE_USER", "admin")
FRIGATE_PASS = os.environ.get("FRIGATE_PASS", "")


def main() -> int:
    client = FrigateClient(FRIGATE_BASE_URL, FRIGATE_USER, FRIGATE_PASS)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT event_id, thumb_path FROM highlights WHERE thumb_path IS NOT NULL"
    ).fetchall()
    conn.close()

    n_ok = 0
    n_skip = 0
    n_fail = 0
    for r in rows:
        eid = r["event_id"]
        thumb_path = HIGHLIGHTS_ROOT / r["thumb_path"]
        if not thumb_path.parent.exists():
            print(f"[skip] missing dir for {eid}: {thumb_path.parent}")
            n_skip += 1
            continue
        # download_thumbnail tries snapshot.jpg first, falls back to
        # the bbox thumbnail (handles older events whose snapshot was
        # pruned by Frigate's record_clip_retention).
        ok = client.download_thumbnail(eid, thumb_path)
        if ok:
            print(f"[ok]   {eid}  -> {thumb_path.relative_to(HIGHLIGHTS_ROOT)}")
            n_ok += 1
        else:
            print(f"[fail] {eid}")
            n_fail += 1

    print(f"\nDone. ok={n_ok}  skipped={n_skip}  failed={n_fail}  total={len(rows)}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
