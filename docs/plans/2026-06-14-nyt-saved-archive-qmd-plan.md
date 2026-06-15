# NYT Saved Articles → Markdown → qmd Archive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Chad's existing list of saved NYTimes article URLs into a local Markdown corpus (full body text, clean), indexed as a `qmd` collection — fetched via his logged-in session **without risking the account**.

**Architecture:** Input is **a file of NYT URLs already on the server** (Chad has it) — so we skip enumeration entirely (no `/saved` GraphQL capture). Pipeline mirrors `bookmark-archiver/`: read+dedup URLs → fetch each article with **Playwright driving a real, hand-logged-in browser profile** (legitimate fingerprint, mints the DataDome cookie), **slow + sequential + abort-on-block** → extract `section[name="articleBody"]` → Markdown + YAML frontmatter (`type: nyt-article`) → land in qmd collection. **One-time backfill** per decision; re-runnable for new URLs via state file.

**Tech Stack:** Python 3.13 + pytest, Playwright (Chromium, persistent context), trafilatura + BeautifulSoup/markdownify, `qmd`.

**Decisions already made (do not relitigate):**
- Storage = **qmd collection `nyt-saved`** at `~/.letta/reference-archive/raw/nyt-saved/`, NOT canonical git.
- Refresh = **one-time deliberate run** (no launchd); re-run manually for new URLs.
- Enumeration source = **Chad's URL-list file** (path provided at execution; see Task 1).

### NON-NEGOTIABLE SAFETY RULES (the user's top priority)
1. **Never submit credentials programmatically.** Log in ONCE by hand in a dedicated browser profile; the pipeline only ever *reuses* that session. This is the single biggest account-flag risk.
2. **Real browser only** (Playwright persistent context on the logged-in profile). No raw `requests`/curl — they fail DataDome's JA3/behavioral checks and can't refresh the bot cookie.
3. **Slow + sequential.** One article at a time, randomized 10–30s human delay. Never concurrent.
4. **Abort on first block.** On 403 / 429 / CAPTCHA / "we suspect that you're a robot", STOP the whole run immediately and resume hours later. Never retry-hammer.
5. **Home IP only.** No VPN/datacenter IP (instant DataDome distrust).
6. **Cache aggressively.** State file skips already-archived URLs so re-runs never re-fetch.

---

## File Structure

```
nyt-saved-archiver/                        # new sibling pkg to bookmark-archiver/
├── pyproject.toml
├── run-nyt-archive.sh                      # manual entrypoint (NOT launchd)
├── nyt_saved_archiver/
│   ├── __init__.py
│   ├── urls.py             # parse + normalize + dedup the URL-list file
│   ├── extract.py          # NYT article HTML -> clean Markdown
│   ├── frontmatter.py      # build YAML frontmatter (type: nyt-article)
│   ├── state.py            # seen-URLs persistence (skip on re-run)
│   ├── block.py            # detect NYT bot-block in a page -> abort signal
│   └── fetch.py            # Playwright real-profile fetch loop (slow/sequential/abort)
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   ├── article.html    # minimal NYT-layout article (section[name=articleBody])
    │   └── blocked.html    # a "suspect you're a robot" page
    ├── test_urls.py
    ├── test_extract.py
    ├── test_frontmatter.py
    ├── test_state.py
    └── test_block.py
```

Ops (not in repo): corpus `~/.letta/reference-archive/raw/nyt-saved/`; state `~/.letta/reference-archive/.state/nyt-saved.json`; browser profile `~/.letta/reference-archive/.nyt-profile/` (hand-logged-in, gitignored).

---

## Phase 0 — Prerequisites

### Task 0: Tooling + dirs + scaffold

- [ ] **Step 1: Install deps into the pa-tools venv**

Run:
```bash
~/.letta/pa-tools-venv/bin/pip install playwright trafilatura beautifulsoup4 lxml markdownify
~/.letta/pa-tools-venv/bin/playwright install chromium
```
Expected: installs succeed; Chromium downloaded.

- [ ] **Step 2: Dirs**

Run:
```bash
mkdir -p ~/.letta/reference-archive/raw/nyt-saved ~/.letta/reference-archive/.state ~/.letta/reference-archive/.nyt-profile
```

- [ ] **Step 3: Scaffold package** (same shape as evernote-archiver)

Run:
```bash
mkdir -p /Volumes/main-drive/ai-PA/nyt-saved-archiver/nyt_saved_archiver \
         /Volumes/main-drive/ai-PA/nyt-saved-archiver/tests/fixtures
cd /Volumes/main-drive/ai-PA/nyt-saved-archiver
touch nyt_saved_archiver/__init__.py tests/__init__.py
```

Create `pyproject.toml`:
```toml
[project]
name = "nyt-saved-archiver"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pyyaml>=6", "trafilatura>=1.8", "beautifulsoup4>=4.12", "markdownify>=0.11", "playwright>=1.40"]

[project.optional-dependencies]
test = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["."]
include = ["nyt_saved_archiver*"]
```

- [ ] **Step 4: Commit scaffold**

```bash
cd /Volumes/main-drive/ai-PA
git add nyt-saved-archiver/pyproject.toml nyt-saved-archiver/nyt_saved_archiver/__init__.py nyt-saved-archiver/tests/__init__.py
git commit -m "feat(nyt-saved-archiver): scaffold package"
```

---

## Phase 1 — Inputs (operational)

### Task 1: Locate the URL file + one-time hand login

- [ ] **Step 1: Confirm the URL-list file path**

Chad has a file of NYT URLs on the server. **Confirm its exact path** (e.g. `~/nyt-saved-urls.txt`) and peek at format:
```bash
wc -l <PATH>; head -5 <PATH>
```
Expected: one URL per line (or a format `urls.py` will normalize in Task 2). Record path → used as `--urls`.

- [ ] **Step 2: Hand-login into a dedicated browser profile** (ONE time, by hand)

Run:
```bash
~/.letta/pa-tools-venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
from pathlib import Path
prof = str(Path.home()/".letta/reference-archive/.nyt-profile")
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(prof, headless=False)
    page = ctx.new_page()
    page.goto("https://www.nytimes.com/saved")
    input("Log in fully in the opened window, confirm you can see your Saved page, then press Enter here...")
    ctx.close()
PY
```
Expected: a real Chrome window opens; you log in by hand (this is the ONLY auth, ever); session cookies persist in `.nyt-profile`.

---

## Phase 2 — URL parsing

### Task 2: `urls.py`

**Files:** Create `nyt_saved_archiver/urls.py`; Test `tests/test_urls.py`

- [ ] **Step 1: Failing test** (`tests/test_urls.py`)

```python
from nyt_saved_archiver.urls import load_urls


def test_load_filters_dedupes_and_strips(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(
        "https://www.nytimes.com/2024/01/02/world/a.html?smid=x\n"
        "  https://www.nytimes.com/2024/01/02/world/a.html  \n"   # dup after query strip
        "https://example.com/not-nyt\n"
        "\n# a comment\n"
        "https://www.nytimes.com/2023/05/05/science/b.html\n"
    )
    urls = load_urls(str(f))
    assert urls == [
        "https://www.nytimes.com/2024/01/02/world/a.html",
        "https://www.nytimes.com/2023/05/05/science/b.html",
    ]
```

- [ ] **Step 2: Run — expect FAIL.** `cd /Volumes/main-drive/ai-PA/nyt-saved-archiver && ~/.letta/pa-tools-venv/bin/python -m pytest tests/test_urls.py -q`

- [ ] **Step 3: Implement** (`nyt_saved_archiver/urls.py`)

```python
"""Load + normalize the saved-URL list (format-tolerant)."""
from urllib.parse import urlsplit, urlunsplit


def _normalize(u: str) -> str:
    parts = urlsplit(u.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))  # drop query/fragment


def load_urls(path: str) -> list[str]:
    seen, out = set(), []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "nytimes.com" not in line:
            continue
        n = _normalize(line)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out
```

- [ ] **Step 4: Run — expect PASS.** Same command.

- [ ] **Step 5: Commit.** `git add nyt-saved-archiver/nyt_saved_archiver/urls.py nyt-saved-archiver/tests/test_urls.py && git commit -m "feat(nyt-saved-archiver): URL list parsing"`

---

## Phase 3 — Extraction + frontmatter + state + block-detection

### Task 3: `extract.py` (HTML → Markdown)

**Files:** Create `nyt_saved_archiver/extract.py`; `tests/fixtures/article.html`; Test `tests/test_extract.py`

- [ ] **Step 1: Fixture** (`tests/fixtures/article.html`) — minimal current NYT layout

```html
<html><head><title>Test Headline - The New York Times</title>
<meta property="article:published_time" content="2024-01-02T09:00:00Z">
<meta name="byl" content="By Jane Doe"></head>
<body><article>
<h1 data-testid="headline">Test Headline</h1>
<section name="articleBody">
  <p>First paragraph of the body.</p>
  <figure><img src="https://static01.nyt.com/x.jpg" alt="A photo"><figcaption>Cap text.</figcaption></figure>
  <p>Second paragraph with <a href="https://nyt.com/y">a link</a>.</p>
</section></article></body></html>
```

- [ ] **Step 2: Failing test** (`tests/test_extract.py`)

```python
from pathlib import Path
from nyt_saved_archiver.extract import extract_article

HTML = (Path(__file__).parent / "fixtures" / "article.html").read_text()


def test_extract_pulls_title_byline_date_and_body():
    art = extract_article(HTML, url="https://www.nytimes.com/2024/01/02/world/a.html")
    assert art["title"] == "Test Headline"
    assert art["byline"] == "By Jane Doe"
    assert art["published"] == "2024-01-02T09:00:00Z"
    assert "First paragraph of the body." in art["markdown"]
    assert "Second paragraph" in art["markdown"]
    assert "Cap text." in art["markdown"]           # caption preserved
    assert art["markdown"].strip()                   # non-empty


def test_extract_raises_on_missing_body():
    with __import__("pytest").raises(ValueError):
        extract_article("<html><body><p>no article body</p></body></html>", url="u")
```

- [ ] **Step 3: Run — expect FAIL.**

- [ ] **Step 4: Implement** (`nyt_saved_archiver/extract.py`)

```python
"""Extract a clean Markdown article from authenticated NYT HTML."""
from bs4 import BeautifulSoup
from markdownify import markdownify as md


def _meta(soup, **attrs):
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content") if tag and tag.get("content") else None


def extract_article(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("section", attrs={"name": "articleBody"})
    if body is None:                       # older layout fallback
        cols = soup.select("div.StoryBodyCompanionColumn")
        if cols:
            body = BeautifulSoup("<section></section>", "lxml").section
            for c in cols:
                body.append(c)
    if body is None or not body.get_text(strip=True):
        raise ValueError(f"no article body found for {url} (not logged in / paywalled / layout change)")

    title_tag = soup.find(attrs={"data-testid": "headline"}) or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else (soup.title.get_text() if soup.title else url)
    byline = _meta(soup, attrs={"name": "byl"}) or _meta(soup, **{"name": "byl"})
    published = _meta(soup, **{"property": "article:published_time"})

    markdown = md(str(body), heading_style="ATX", strip=["script", "style"]).strip()
    return {"title": title, "byline": byline, "published": published,
            "url": url, "markdown": markdown}
```

> Note: `_meta` is called two ways above for clarity in the test; keep the single `attrs=`-based implementation — the test uses `name="byl"`.

- [ ] **Step 5: Run — expect PASS.** (If `_meta` signature mismatches, simplify to one `extract_article` call path: `byline = _meta(soup, name="byl")`, `published = _meta(soup, property="article:published_time")`, with `def _meta(soup, **attrs)`.)

- [ ] **Step 6: Commit.** `git add ... && git commit -m "feat(nyt-saved-archiver): NYT HTML -> Markdown extraction"`

### Task 4: `frontmatter.py`

**Files:** Create `nyt_saved_archiver/frontmatter.py`; Test `tests/test_frontmatter.py`

- [ ] **Step 1: Failing test**

```python
from nyt_saved_archiver.frontmatter import build_document


def test_build_document_has_type_and_fields():
    art = {"title": "T", "byline": "By X", "published": "2024-01-02T09:00:00Z",
           "url": "https://www.nytimes.com/2024/01/02/world/a.html", "markdown": "Body."}
    doc = build_document(art, saved_date="2026-06-14")
    assert doc.startswith("---\n")
    assert "type: nyt-article" in doc
    assert "source: nyt-saved" in doc
    assert "Body." in doc
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement** (`nyt_saved_archiver/frontmatter.py`)

```python
"""Render an article dict into a frontmatter Markdown document for qmd."""
import yaml


def build_document(art: dict, saved_date: str | None = None) -> str:
    fm = {
        "type": "nyt-article",
        "source": "nyt-saved",
        "title": art.get("title"),
        "byline": art.get("byline"),
        "url": art.get("url"),
        "published": art.get("published"),
        "saved_date": saved_date,
        "tags": [],
    }
    fm = {k: v for k, v in fm.items() if v is not None}
    head = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{head}\n---\n\n# {art.get('title','')}\n\n{art['markdown']}\n"
```

- [ ] **Step 4: Run — expect PASS. Step 5: Commit.**

### Task 5: `state.py`

**Files:** Create `nyt_saved_archiver/state.py`; Test `tests/test_state.py`

- [ ] **Step 1: Failing test**

```python
from nyt_saved_archiver.state import State


def test_state_roundtrip_and_skip(tmp_path):
    s = State(str(tmp_path / "st.json"))
    assert not s.seen("u1")
    s.mark("u1"); s.save()
    s2 = State(str(tmp_path / "st.json"))
    assert s2.seen("u1") and not s2.seen("u2")
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement** (`nyt_saved_archiver/state.py`)

```python
"""Persistent seen-URL set so re-runs never re-fetch (caching requirement)."""
import json
from pathlib import Path


class State:
    def __init__(self, path: str):
        self.path = Path(path)
        self._seen = set(json.loads(self.path.read_text())["seen"]) if self.path.exists() else set()

    def seen(self, url: str) -> bool:
        return url in self._seen

    def mark(self, url: str) -> None:
        self._seen.add(url)

    def save(self) -> None:
        self.path.write_text(json.dumps({"seen": sorted(self._seen)}, indent=2))
```

- [ ] **Step 4: Run — PASS. Step 5: Commit.**

### Task 6: `block.py` (bot-block detection → abort)

**Files:** Create `nyt_saved_archiver/block.py`; `tests/fixtures/blocked.html`; Test `tests/test_block.py`

- [ ] **Step 1: Fixture** (`tests/fixtures/blocked.html`)

```html
<html><body><h1>Hmm, we suspect that you're a robot</h1>
<p>Please confirm you are a human.</p></body></html>
```

- [ ] **Step 2: Failing test** (`tests/test_block.py`)

```python
from pathlib import Path
from nyt_saved_archiver.block import is_blocked

BLOCKED = (Path(__file__).parent / "fixtures" / "blocked.html").read_text()
OK = "<html><body><section name='articleBody'><p>hi</p></section></body></html>"


def test_detects_block_page():
    assert is_blocked(BLOCKED, status=200) is True

def test_detects_block_status():
    assert is_blocked(OK, status=403) is True

def test_clean_page_not_blocked():
    assert is_blocked(OK, status=200) is False
```

- [ ] **Step 3: Run — FAIL. Step 4: Implement** (`nyt_saved_archiver/block.py`)

```python
"""Detect NYT bot-block so the fetch loop aborts immediately (safety rule #4)."""
SIGNALS = ("suspect that you're a robot", "pardon our interruption",
           "confirm you are a human", "access denied", "unusual activity")


def is_blocked(html: str, status: int) -> bool:
    if status in (403, 429):
        return True
    low = html.lower()
    return any(s in low for s in SIGNALS)
```

- [ ] **Step 5: Run — PASS. Step 6: Commit.**

---

## Phase 4 — Fetch loop (Playwright, real profile)

### Task 7: `fetch.py` + entrypoint

**Files:** Create `nyt_saved_archiver/fetch.py`, `run-nyt-archive.sh`

- [ ] **Step 1: Implement** (`nyt_saved_archiver/fetch.py`) — slow, sequential, abort-on-block, cached.

```python
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
    print(f"{len(urls)} urls, {len(todo)} to fetch this run")
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
                print(f"BLOCKED at {url} (status {status}). Stopping. Resume later.", file=sys.stderr)
                break
            try:
                art = extract_article(html, url)
            except ValueError as e:
                print(f"skip (no body): {url} :: {e}", file=sys.stderr)
                st.mark(url); st.save(); continue   # mark so we don't retry-hammer
            (out_dir / f"{_slug(url)}.md").write_text(build_document(art, saved_date=today), encoding="utf-8")
            st.mark(url); st.save()
            done += 1
            print(f"[{i}/{len(todo)}] saved: {art['title']}")
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        ctx.close()
    print(f"done: {done} new articles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Entrypoint** (`run-nyt-archive.sh`)

```bash
#!/usr/bin/env bash
# MANUAL one-time/incremental NYT backfill. NOT a launchd job (account-safety).
# Usage: ./run-nyt-archive.sh <urls-file> [limit]
set -euo pipefail
URLS="${1:?path to NYT urls file required}"
LIMIT="${2:-0}"
~/.letta/pa-tools-venv/bin/python -m nyt_saved_archiver.fetch \
  --urls "$URLS" \
  --profile "$HOME/.letta/reference-archive/.nyt-profile" \
  --out "$HOME/.letta/reference-archive/raw/nyt-saved" \
  --state "$HOME/.letta/reference-archive/.state/nyt-saved.json" \
  --limit "$LIMIT"
```

- [ ] **Step 3: SMOKE TEST on 2 URLs** (validates login/profile + DataDome before any volume)

Run:
```bash
chmod +x /Volumes/main-drive/ai-PA/nyt-saved-archiver/run-nyt-archive.sh
cd /Volumes/main-drive/ai-PA/nyt-saved-archiver
./run-nyt-archive.sh <URLS_PATH> 2
```
Expected: 2 `.md` files in the corpus with real body text. If BLOCKED on the first call → the `/saved` endpoint's DataDome config differs / session not valid; re-log (Task 1.2) and try a single URL. **Do not proceed to full run until a 2-URL smoke run is clean.**

- [ ] **Step 4: Commit.** `git add nyt-saved-archiver/nyt_saved_archiver/fetch.py nyt-saved-archiver/run-nyt-archive.sh && git commit -m "feat(nyt-saved-archiver): slow sequential fetch loop with abort-on-block"`

### Task 8: Full backfill (operational, paced)

- [ ] **Step 1: Run the full set** (only after a clean smoke run)

Run: `./run-nyt-archive.sh <URLS_PATH>`
Behavior: sequential, 10–30s apart, auto-skips cached, **auto-stops on any block**. For a large list this spans hours — that's intended. If it stops on a block, wait several hours and re-run (state resumes where it left off).

- [ ] **Step 2: Verify count** — compare `.md` count to URL count minus known no-body skips:
```bash
ls ~/.letta/reference-archive/raw/nyt-saved/*.md | wc -l
```

---

## Phase 5 — Index + agent recall

### Task 9: qmd collection

- [ ] **Step 1: Add + verify**

Run:
```bash
qmd collection add nyt-saved ~/.letta/reference-archive/raw/nyt-saved
qmd query "<a topic you saved>" --collection nyt-saved
```
Expected: relevant article(s) returned; `qmd get` shows body + frontmatter.

### Task 10: Extend reference recall doc

> If the Evernote plan already created `system/reference_recall.md`, ADD to it; else create it (see Evernote plan Task 9).

- [ ] **Step 1: Add the `nyt-saved` collection block** to `.../memory/system/reference_recall.md`:

```markdown
- `nyt-saved` — full text of Chad's saved NYTimes articles, frontmatter `type: nyt-article`
  (fields: title, byline, url, published, saved_date). Use for "that NYT piece I saved about…".
```

- [ ] **Step 2: Commit + push** to MC's Gitea repo (same as Evernote Task 9 Step 2).

---

## Self-Review

- **Spec coverage:** Markdown body of NYT articles (Task 3) ✓; scraped via login (Task 1.2 hand-login + Task 7 profile reuse) ✓; care not to flag/invalidate account (the 6 NON-NEGOTIABLE rules, baked into `block.py`/`fetch.py` pacing + smoke-gate) ✓; indexed (Task 9) ✓; agent access (Task 10) ✓.
- **Simplification vs research:** the URL-list file removes the entire `/saved` GraphQL-enumeration phase — lower risk and less code.
- **Placeholder scan:** the `<URLS_PATH>` token is a real input to confirm in Task 1.1, not a code placeholder. `_meta` dual-call note in Task 3.5 flags the one signature to keep simple — resolve at implement time.
- **Open items:** (a) confirm the URL-file path + format (Task 1.1); (b) confirm `/saved`-era articles still render `section[name="articleBody"]` (smoke run, Task 7.3); (c) total count → expect a multi-hour backfill.
```
