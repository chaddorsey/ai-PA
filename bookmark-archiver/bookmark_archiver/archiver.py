"""Bookmark archive + reply-knowledge orchestrator.

Flow: twitter-cli read bookmarks --json -> dedup -> per new bookmark:
core summary (+gate1) -> if reply_worth and reply_count>=THRESHOLD: read tweet,
parse top-N replies, mine (gate2) -> render -> write archive (+knowledge) -> mark seen.
"""
import json
import os
import subprocess
import sys

from bookmark_archiver import canonical, render, replies, state, summarize

TWITTER_CLI = os.environ.get("TWITTER_CLI_BIN", "twitter-cli")
STATE_PATH = os.environ.get("BOOKMARK_STATE",
                            "/Volumes/main-drive/ai-PA/smaug-data/.state/bookmark-archive-state.json")
ARCHIVE_PATH = "reference/twitter-bookmarks.md"
KNOWLEDGE_PATH = "reference/twitter-reply-knowledge.md"
REPLY_FLOOR = int(os.environ.get("BOOKMARK_REPLY_FLOOR", "25"))
REPLY_TOPN = int(os.environ.get("BOOKMARK_REPLY_TOPN", "25"))
FETCH_COUNT = int(os.environ.get("BOOKMARK_FETCH_COUNT", "40"))


def _twitter_json(args: list[str]) -> dict | list:
    out = subprocess.run([TWITTER_CLI, *args], capture_output=True, text=True, timeout=90)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"twitter-cli {args} failed rc={out.returncode}: {out.stderr[:200]}")
    return json.loads(out.stdout)


def archive_items(items: list[dict]) -> dict:
    """Dedup a batch of bookmarks, summarize + selectively reply-mine each new
    one, write to canonical, and mark seen. Reused by both the daily run and
    the historical backfill. Returns per-batch counts."""
    fresh = state.new_bookmarks(items, STATE_PATH)
    archive_entries, knowledge_entries, processed = [], [], []
    for bm in fresh:
        core = summarize.summarize_core(bm)
        anchor = None
        if core.get("reply_worth") and (bm.get("reply_count", 0) or 0) >= REPLY_FLOOR:
            try:
                detail = _twitter_json(["read", "tweet", bm["id"], "--json"])
                top = replies.parse_reply_chain(detail, top_n=REPLY_TOPN)
                mined = summarize.mine_replies(bm, top) if top else None
                if mined:
                    anchor = bm["id"]
                    knowledge_entries.append(render.knowledge_entry(bm, mined, anchor=anchor))
            except Exception as e:  # reply mining is best-effort; never block the archive
                print(f"  ! reply-mine failed for {bm['id']}: {e}", file=sys.stderr)
        ka = f"twitter-reply-knowledge.md#{anchor}" if anchor else None
        archive_entries.append(render.bookmark_entry(bm, core, knowledge_anchor=ka))
        processed.append(bm["id"])

    if archive_entries:
        canonical.write_entries(ARCHIVE_PATH, archive_entries, title="Twitter Bookmarks")
    if knowledge_entries:
        canonical.write_entries(KNOWLEDGE_PATH, knowledge_entries, title="Twitter Reply-Chain Knowledge")
    if processed:
        state.mark_seen(processed, STATE_PATH)
    return {"new": len(fresh), "archived": len(archive_entries),
            "knowledge": len(knowledge_entries)}


def run() -> dict:
    raw = _twitter_json(["read", "bookmarks", "--count", str(FETCH_COUNT), "--json"])
    items = raw if isinstance(raw, list) else raw.get("tweets", [])
    result = archive_items(items)
    result["fetched"] = len(items)
    return result


def main() -> int:
    try:
        r = run()
        print(json.dumps(r))
        return 0
    except Exception as e:
        import traceback
        print(json.dumps({"status": "error", "error": str(e),
                          "trace": traceback.format_exc()[-1200:]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
