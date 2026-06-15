"""One-time NYT backfill: reuse the hand-logged-in profile, slow + sequential."""
import argparse
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from .urls import load_urls
from .extract import extract_article
from .frontmatter import build_document
from .state import State
from .block import is_blocked

MIN_DELAY, MAX_DELAY = 10, 30   # safety rule #3: human-like sequential pacing


def _slug(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1].replace(".html", "")
    return re.sub(r"[^a-zA-Z0-9._-]", "-", tail) or "article"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = all; else stop after N (use small for first smoke run)")
    a = ap.parse_args()

    urls = load_urls(a.urls)
    st = State(a.state)
    todo = [u for u in urls if not st.seen(u)]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(urls)} urls, {len(todo)} to fetch this run", flush=True)
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    done = 0

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(a.profile, headless=False)
        page = ctx.new_page()
        for i, url in enumerate(todo, 1):
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else 0
            html = page.content()
            if is_blocked(html, status):          # safety rule #4: abort the whole run
                print(f"BLOCKED at {url} (status {status}). Stopping. Resume later.", file=sys.stderr, flush=True)
                break
            try:
                art = extract_article(html, url)
            except ValueError as e:
                print(f"skip (no body): {url} :: {e}", file=sys.stderr, flush=True)
                st.mark(url); st.save(); continue   # mark so we don't retry-hammer
            (out_dir / f"{_slug(url)}.md").write_text(build_document(art, saved_date=today), encoding="utf-8")
            st.mark(url); st.save()
            done += 1
            print(f"[{i}/{len(todo)}] saved: {art['title']}", flush=True)
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        ctx.close()
    print(f"done: {done} new articles", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
