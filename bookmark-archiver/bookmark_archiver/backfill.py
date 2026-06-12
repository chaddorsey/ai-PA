"""One-time historical bookmark backfill — paginates the FULL bookmark set.

Throttled + resumable + single-flight:
- Walks `twitter-cli read bookmarks --paged [--cursor C]` page by page.
- Each page is handed to archiver.archive_items (dedup -> summarize -> selective
  reply-mine -> write canonical -> mark seen), so re-runs skip already-archived
  bookmarks for free.
- Persists the next cursor after every page (state `backfill_cursor`), so a
  crash/restart resumes where it left off; sets `backfill_done` at the end.
- Sleeps BACKFILL_PAGE_SLEEP between pages; the twitter-cli client also self-
  throttles (jittered delay + 429 backoff). Bounded by BACKFILL_MAX_PAGES/run.
- A lock file prevents the launchd guard from starting a second concurrent run.
"""
import json
import os
import sys
import time
from pathlib import Path

from bookmark_archiver import archiver, state

PAGE_SIZE = int(os.environ.get("BACKFILL_PAGE_SIZE", "60"))
PAGE_SLEEP = float(os.environ.get("BACKFILL_PAGE_SLEEP", "12"))
MAX_PAGES = int(os.environ.get("BACKFILL_MAX_PAGES", "60"))  # /run safety cap (~3600 bookmarks)
LOCK_PATH = os.environ.get("BACKFILL_LOCK", "/Volumes/main-drive/ai-PA/smaug-data/.state/bookmark-backfill.lock")
LOCK_STALE_SEC = 12 * 3600  # a full run can take hours; only treat the lock as
                            # abandoned well beyond any real run to avoid the
                            # hourly guard starting a 2nd concurrent backfill.


def _fetch_page(cursor):
    args = ["read", "bookmarks", "--count", str(PAGE_SIZE), "--paged", "--json"]
    if cursor:
        args += ["--cursor", cursor]
    page = archiver._twitter_json(args)
    if isinstance(page, list):  # defensive: shouldn't happen with --paged
        return page, None
    return page.get("tweets", []), page.get("next_cursor")


def _lock_held() -> bool:
    p = Path(LOCK_PATH)
    if not p.exists():
        return False
    try:
        age = time.time() - p.stat().st_mtime
    except OSError:
        return False
    return age < LOCK_STALE_SEC


def backfill(sleeper=time.sleep) -> dict:
    sp = archiver.STATE_PATH
    if state.get_meta("backfill_done", sp):
        return {"status": "already_done"}
    if _lock_held():
        return {"status": "locked"}
    Path(LOCK_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(LOCK_PATH).write_text(str(int(time.time())))
    totals = {"pages": 0, "new": 0, "archived": 0, "knowledge": 0, "status": "running"}
    try:
        cursor = state.get_meta("backfill_cursor", sp)
        while totals["pages"] < MAX_PAGES:
            Path(LOCK_PATH).touch()  # keep the lock fresh for the whole run
            tweets, next_cursor = _fetch_page(cursor)
            if not tweets:
                state.set_meta("backfill_done", True, sp)
                totals["status"] = "complete"
                break
            r = archiver.archive_items(tweets)
            totals["pages"] += 1
            totals["new"] += r["new"]
            totals["archived"] += r["archived"]
            totals["knowledge"] += r["knowledge"]
            print(json.dumps({"page": totals["pages"], **r,
                              "cumulative_new": totals["new"]}), flush=True)
            state.set_meta("backfill_cursor", next_cursor, sp)
            if not next_cursor:
                state.set_meta("backfill_done", True, sp)
                totals["status"] = "complete"
                break
            cursor = next_cursor
            sleeper(PAGE_SLEEP)
        else:
            totals["status"] = "page_cap_reached"  # resume on next run
    finally:
        try:
            Path(LOCK_PATH).unlink()
        except OSError:
            pass
    return totals


def main() -> int:
    try:
        print(json.dumps(backfill()), flush=True)
        return 0
    except Exception as e:
        import traceback
        print(json.dumps({"status": "error", "error": str(e),
                          "trace": traceback.format_exc()[-1200:]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
