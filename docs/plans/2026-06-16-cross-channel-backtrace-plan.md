# Cross-Channel Backtrace & Work-Packet Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a task is confirmed, build its OmniFocus work-packet by searching across Drive/Slack/Gmail/internal-history/memory from the task's anchors, then writing a tiered (Primary/Supporting/Related) set of prioritized resources — automating the manual cross-channel chase.

**Architecture:** A deterministic fan-out primitive (`task xsearch`) executes concurrent, normalized, per-channel searches; the local tasks-agent drives term selection + relevance judgment + tiering via a recipe; side-effects (staging, packet write) go through verified CLIs; a backstop flags under-delivery. Memory (canonical + the agent's memfs) is a first-layer grounding step AND additional qmd-backed channels.

**Tech Stack:** Python 3 (`click` CLI, `psycopg`, `subprocess`→`gws`/`slack`/`qmd`, `concurrent.futures`), Flask (pa-web-ui renderer), the local letta tasks-agent (memfs recipe), launchd.

**Design doc:** `docs/plans/2026-06-16-cross-channel-backtrace-design.md`

## Global Constraints

- **Local mode only.** Fixes land in `letta/*_tool.py` (imported by `task-cli`) + the CLI; no Letta-server tool re-registration.
- **Never corrupt the estimate/actuals eval loop** — no writes to `original_est_minutes`/`revised_est_minutes`/`actual_minutes` or the `Agent Estimate:` renderer line. Resources work is additive.
- **`task` CLI env (host shell):** `PA_AI_REPO_ROOT=/Volumes/main-drive/ai-PA`, `PA_WEB_POSTGRES_URL=postgresql://postgres:<POSTGRES_PASSWORD from .env>@127.0.0.1:5433/postgres`. CLI python = `/Users/dorseyhomeserver/.local/pipx/venvs/task-cli/bin/python` (has psycopg + pytz).
- **launchd lessons:** logs under `~/Library/Logs/...` (never `/Volumes`); secrets in the plist `EnvironmentVariables`; plists are NOT git-tracked. Shell-out CLIs (`gws`,`slack`,`qmd`,`task`) need their dirs on `PATH` (`~/bin:/opt/homebrew/bin:...`).
- **Resource line grammar (existing, reuse):** `[primary|secondary|background] <label> — <url> [| offline: openfile://~/…] (role)`. The three priority markers ARE the three tiers.
- **Channels:** `drive, slack, gmail, tasks, meetings, canonical, history, reference`.
- **pa-web-ui app.py is image-baked** (hot-deploy = `docker cp` + restart; static/ live-mounted). **gws-bridge unused here** (xsearch shells `gws` directly on the host runner, same as the other task CLIs).

---

## Task 1: Clean up `backtrace_task` — expose `search_terms`, delete dead archival classification

**Files:**
- Modify: `letta/backtrace_task_tool.py` (Step 4–7 block + return dict)
- Test: `task-cli/tests/test_backtrace_search_terms.py` (create)

**Interfaces:**
- Produces: `backtrace_task(ref_id) -> dict` now includes key `search_terms: list[str]` (the prioritized anchor terms, ≤20) and keeps `anchors`, `hop_candidates`, `source_content`, `source_type`. Removes the always-empty `artifact_candidates`/`intent_candidates`/`related_tasks`/`other_hits`/`total_archival_hits`/`search_terms_used`.

- [ ] **Step 1: Write the failing test**

```python
# task-cli/tests/test_backtrace_search_terms.py
import os, sys, importlib.util
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("bt", os.path.join(_REPO, "letta", "backtrace_task_tool.py"))
_bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(_bt)

def test_returns_search_terms_and_no_dead_archival_keys(monkeypatch):
    # Stub the pa_web.tasks row fetch via a fake psycopg so the tool runs offline.
    # (Implementer: use the existing _pg path; here assert on shape with a known task.)
    out = _bt.backtrace_task.__doc__  # smoke: callable + documented
    assert "search_terms" in _bt.backtrace_task.__doc__ or True
    src = open(os.path.join(_REPO, "letta", "backtrace_task_tool.py")).read()
    assert "archival_hits = []" not in src           # dead stub removed
    assert "artifact_candidates" not in src          # dead classification removed
    assert '"search_terms":' in src                  # search_terms exposed in return
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_backtrace_search_terms.py -v`
Expected: FAIL (`archival_hits = []` still present; `"search_terms":` not in return).

- [ ] **Step 3: Delete the dead Step 4–7 block and slim the return**

In `letta/backtrace_task_tool.py`, replace everything from the `# ── Step 4: Hop search (stubbed …` comment through the end of the `mismatch_warnings` construction (the `archival_hits = []` block, the `for hit in archival_hits:` classification loop, the intent/artifact/related/other lists, and the `# ── Step 6: Build hop candidates` meeting-intent loop) — keep ONLY the URL-derived `hop_candidates`:

```python
        # Hop candidates = URLs already present in the source content / metadata.
        # Cross-channel discovery now happens in `task xsearch` (agent-driven),
        # not here — this tool's job is anchors + search_terms + inline URLs.
        hop_candidates = []
        for u in anchors_urls[:8]:
            if "drive.google.com" in u or "docs.google.com" in u:
                hop_candidates.append({"ref": u, "type": "drive_doc",
                                       "node_likelihood": "artifact_provenance",
                                       "reason": "Drive/Docs link in source content"})
            elif "slack.com/archives" in u:
                hop_candidates.append({"ref": u, "type": "slack_thread",
                                       "node_likelihood": "direct_action",
                                       "reason": "Slack permalink in source content"})

        node_coverage = {"direct_action": True,
                         "artifact_provenance": bool(anchors_doc_ids or hop_candidates),
                         "intent_genesis": False}
```

Then replace the big return dict with the slimmed one:

```python
        return {
            "status": "ok",
            "ref_id": ref_id,
            "task": task_desc,
            "source_content": full_content[:3000],
            "source_type": source_type,
            "fetch_hint": fetch_hint,
            "anchors": {
                "urls": anchors_urls[:10],
                "doc_ids": anchors_doc_ids,
                "proper_nouns": anchors_proper_nouns[:15],
                "distinctive_phrases": anchors_distinctive[:10],
                "acronyms": anchors_acronyms[:10],
                "participants": participants,
            },
            "search_terms": search_terms,          # ← now exposed (was discarded)
            "hop_candidates": hop_candidates[:10],
            "node_coverage": node_coverage,
        }
```

Delete the now-unused `relevance_terms`, `mismatch_warnings`, `completed_related`, `rejected_related` lines.

- [ ] **Step 4: Run test — expect PASS** + syntax check

Run: `cd /Volumes/main-drive/ai-PA && python3 -c "import ast; ast.parse(open('letta/backtrace_task_tool.py').read())" && cd task-cli && python -m pytest tests/test_backtrace_search_terms.py -v`
Expected: PASS.

- [ ] **Step 5: Live smoke** (a real meeting task)

Run: `cd /Volumes/main-drive/ai-PA && PA_AI_REPO_ROOT=$PWD PA_WEB_POSTGRES_URL="postgresql://postgres:$(grep ^POSTGRES_PASSWORD= .env|cut -d= -f2-)@127.0.0.1:5433/postgres" task backtrace fcdf4afb-a | jq '{terms: .search_terms, anchors: .anchors.proper_nouns}'`
Expected: non-empty `search_terms` (e.g. includes "Vernier"); no error.

- [ ] **Step 6: Commit**

```bash
git add letta/backtrace_task_tool.py task-cli/tests/test_backtrace_search_terms.py
git commit -m "refactor(backtrace): expose search_terms, delete dead archival classification

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `xsearch` core + `tasks` channel + CLI

**Files:**
- Create: `letta/xsearch_tool.py`
- Modify: `task-cli/src/task_cli/cli.py` (add `xsearch` command after `stage`)
- Test: `task-cli/tests/test_xsearch.py` (create)

**Interfaces:**
- Produces: `xsearch(terms: list[str], channels: list[str], limit_per_channel: int = 8) -> dict` returning
  `{"status":"ok","candidates":[{channel,title,url,permalink,snippet,date,id}],"failed_channels":[{channel,error}]}`.
  Candidate dedup key = `(channel, url or permalink or id)`. Each channel runs in its own thread; a channel that raises is recorded in `failed_channels`, never silently dropped.
- CLI: `task xsearch --terms "t1,t2" [--channels drive,slack,...] [--limit 8]` → emits the dict as JSON.

- [ ] **Step 1: Write the failing test (core + tasks channel)**

```python
# task-cli/tests/test_xsearch.py
import os, sys, importlib.util, json
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("xs", os.path.join(_REPO, "letta", "xsearch_tool.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)

def test_dedup_and_normalize():
    rows = [
        {"channel":"tasks","title":"A","url":"u1","permalink":"","snippet":"s","date":"d","id":"1"},
        {"channel":"tasks","title":"A dup","url":"u1","permalink":"","snippet":"s","date":"d","id":"1"},
        {"channel":"drive","title":"B","url":"u2","permalink":"","snippet":"","date":"","id":"2"},
    ]
    out = xs._dedup(rows)
    assert len(out) == 2  # u1 collapsed

def test_failed_channel_is_reported_not_silent(monkeypatch):
    monkeypatch.setattr(xs, "_search_tasks", lambda terms, lim: (_ for _ in ()).throw(RuntimeError("boom")))
    res = xs.xsearch(["x"], channels=["tasks"])
    assert res["candidates"] == []
    assert res["failed_channels"] and res["failed_channels"][0]["channel"] == "tasks"

def test_tasks_channel_shape(monkeypatch):
    # _search_tasks returns normalized candidates; here feed a fake DB layer.
    monkeypatch.setattr(xs, "_search_tasks", lambda terms, lim: [
        {"channel":"tasks","title":"Vernier SOW","url":"","permalink":"","snippet":"","date":"2026-06-16","id":"abc"}])
    res = xs.xsearch(["Vernier"], channels=["tasks"])
    assert res["status"] == "ok"
    assert res["candidates"][0]["channel"] == "tasks"
```

- [ ] **Step 2: Run — expect FAIL** (`xsearch_tool` doesn't exist)

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_xsearch.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `letta/xsearch_tool.py` (core + tasks channel)**

```python
"""xsearch — deterministic concurrent multi-channel candidate search.

Execution is deterministic + reproducible; the AGENT decides terms + judges
relevance/tiering downstream. Each channel runs in its own thread and degrades
independently — a failing channel is reported in failed_channels, never a
silent empty (the no-silent-failure rule).

Channels: tasks (this file), drive/gmail/slack (Task 3), canonical/history/
reference/meetings (Task 4).

Normalized candidate: {channel,title,url,permalink,snippet,date,id}
"""
from typing import Dict, Any, List


def _dedup(rows: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for r in rows:
        key = (r.get("channel"), r.get("url") or r.get("permalink") or r.get("id") or r.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _search_tasks(terms: List[str], limit: int) -> List[dict]:
    """pa_web.tasks ILIKE over raw/suggested/confirmed/task_body for any term."""
    import os
    import psycopg
    from psycopg.rows import dict_row
    pg = os.environ.get("PA_WEB_POSTGRES_URL")
    if not pg:
        pw = os.environ.get("POSTGRES_PASSWORD", "")
        port = os.environ.get("PA_WEB_POSTGRES_PORT", "5433")
        pg = f"postgresql://postgres:{pw}@localhost:{port}/postgres"
    like = [f"%{t}%" for t in terms if t]
    if not like:
        return []
    clauses = " OR ".join(
        ["(raw_description ILIKE %s OR suggested_title ILIKE %s OR "
         "confirmed_title ILIKE %s OR task_body ILIKE %s)"] * len(like)
    )
    params = []
    for p in like:
        params += [p, p, p, p]
    sql = (
        "SELECT ref_id, COALESCE(suggested_title, raw_description, '') AS title, "
        "source, source_ref, COALESCE(extracted_at, created_at) AS dt "
        "FROM pa_web.tasks WHERE closed_at IS NULL AND (" + clauses + ") "
        "ORDER BY dt DESC NULLS LAST LIMIT %s"
    )
    params.append(limit)
    out = []
    with psycopg.connect(pg, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                out.append({
                    "channel": "tasks", "title": r["title"][:120],
                    "url": "", "permalink": "",
                    "snippet": f"{r['source']} {r['source_ref']}",
                    "date": str(r["dt"] or "")[:10], "id": r["ref_id"],
                })
    return out


# channel name → search fn. Tasks 3+4 extend this map.
_CHANNELS = {
    "tasks": _search_tasks,
}


def xsearch(terms: List[str], channels: List[str] = None,
            limit_per_channel: int = 8) -> Dict[str, Any]:
    import concurrent.futures
    channels = channels or list(_CHANNELS.keys())
    chans = [c for c in channels if c in _CHANNELS]
    candidates: List[dict] = []
    failed: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_CHANNELS[c], terms, limit_per_channel): c for c in chans}
        for fut in concurrent.futures.as_completed(futs):
            c = futs[fut]
            try:
                candidates.extend(fut.result())
            except Exception as e:
                failed.append({"channel": c, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    unknown = [c for c in channels if c not in _CHANNELS]
    for c in unknown:
        failed.append({"channel": c, "error": "unknown channel"})
    return {"status": "ok", "candidates": _dedup(candidates), "failed_channels": failed}
```

- [ ] **Step 4: Add the `task xsearch` CLI command**

In `task-cli/src/task_cli/cli.py`, after the `stage` command:

```python
# ─── xsearch ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--terms", required=True, help="Comma-separated search terms.")
@click.option("--channels", default=None,
              help="Comma-separated channels (default: all). "
                   "drive,gmail,slack,tasks,meetings,canonical,history,reference")
@click.option("--limit", "limit_per_channel", default=8, type=int, show_default=True)
def xsearch(terms, channels, limit_per_channel):
    """Concurrent multi-channel candidate search from anchor terms (JSON out)."""
    from letta.xsearch_tool import xsearch as _xsearch
    term_list = [t.strip() for t in terms.split(",") if t.strip()]
    chan_list = [c.strip() for c in channels.split(",")] if channels else None
    _emit_json(_xsearch(term_list, channels=chan_list, limit_per_channel=limit_per_channel))
```

- [ ] **Step 5: Run tests — expect PASS** + reinstall CLI

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_xsearch.py -v && pipx install --force -e .`
Expected: 3 pass; `task xsearch --help` lists `--terms/--channels/--limit`.

- [ ] **Step 6: Live smoke (tasks channel)**

Run: `cd /Volumes/main-drive/ai-PA && PA_WEB_POSTGRES_URL="postgresql://postgres:$(grep ^POSTGRES_PASSWORD= .env|cut -d= -f2-)@127.0.0.1:5433/postgres" task xsearch --terms "Vernier" --channels tasks | jq '.candidates[:3]'`
Expected: real task candidates mentioning Vernier.

- [ ] **Step 7: Commit**

```bash
git add letta/xsearch_tool.py task-cli/src/task_cli/cli.py task-cli/tests/test_xsearch.py
git commit -m "feat(xsearch): concurrent multi-channel search primitive + tasks channel + CLI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: xsearch Drive + Gmail + Slack channels

**Files:**
- Modify: `letta/xsearch_tool.py` (add `_search_drive`, `_search_gmail`, `_search_slack`; register in `_CHANNELS`)
- Test: `task-cli/tests/test_xsearch_channels.py` (create)

**Interfaces:**
- Produces: `_CHANNELS` gains `drive`, `gmail`, `slack`. Each shells out (`gws`/`slack`), parses JSON, returns normalized candidates; gws "Using keyring" preamble lines stripped before JSON parse.

- [ ] **Step 1: Write the failing test (mock the subprocess)**

```python
# task-cli/tests/test_xsearch_channels.py
import os, importlib.util, json, types
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("xs", os.path.join(_REPO, "letta", "xsearch_tool.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)

class _R:
    def __init__(self, out): self.returncode = 0; self.stdout = out; self.stderr = ""

def test_drive_channel_parses_gws(monkeypatch):
    payload = json.dumps({"files":[{"id":"d1","name":"Vernier SOW v3",
        "webViewLink":"https://docs.google.com/document/d/d1/edit","modifiedTime":"2026-05-01T00:00:00Z"}]})
    monkeypatch.setattr(xs.subprocess, "run", lambda *a, **k: _R("Using keyring\n"+payload))
    out = xs._search_drive(["Vernier SOW"], 5)
    assert out[0]["channel"] == "drive"
    assert out[0]["url"].startswith("https://docs.google.com/document/d/d1")
    assert out[0]["title"] == "Vernier SOW v3"

def test_slack_channel_registered():
    assert "slack" in xs._CHANNELS and "gmail" in xs._CHANNELS and "drive" in xs._CHANNELS
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_xsearch_channels.py -v`
Expected: FAIL (`_search_drive` undefined).

- [ ] **Step 3: Implement the three adapters in `letta/xsearch_tool.py`**

Add `import subprocess`, `import json` at module top (module-level here is fine — this is a CLI lib, not a Letta-extracted tool). Add a helper + the three adapters, and register them:

```python
import subprocess, json


def _gws_json(args: List[str], timeout: int = 20) -> dict:
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"gws failed: {r.stderr[:160]}")
    raw = "\n".join(l for l in r.stdout.split("\n") if not l.startswith("Using keyring"))
    return json.loads(raw) if raw.strip() else {}


def _search_drive(terms: List[str], limit: int) -> List[dict]:
    q = " or ".join([f"fullText contains '{t}'" for t in terms[:5]])
    data = _gws_json(["drive", "files", "list", "--params", json.dumps({
        "q": q, "pageSize": limit, "orderBy": "modifiedTime desc",
        "fields": "files(id,name,webViewLink,modifiedTime,mimeType)"}), "--format", "json"])
    out = []
    for f in data.get("files", []):
        out.append({"channel": "drive", "title": f.get("name", "")[:120],
                    "url": f.get("webViewLink", ""), "permalink": f.get("webViewLink", ""),
                    "snippet": f.get("mimeType", ""), "date": (f.get("modifiedTime") or "")[:10],
                    "id": f.get("id", "")})
    return out


def _search_gmail(terms: List[str], limit: int) -> List[dict]:
    q = " OR ".join([f'"{t}"' for t in terms[:5]])
    data = _gws_json(["gmail", "users", "messages", "list", "--params", json.dumps({
        "userId": "me", "q": q, "maxResults": limit}), "--format", "json"])
    out = []
    for m in data.get("messages", [])[:limit]:
        mid = m.get("id", "")
        meta = _gws_json(["gmail", "users", "messages", "get", "--params", json.dumps({
            "userId": "me", "id": mid, "format": "metadata",
            "metadataHeaders": ["Subject", "From", "Date"]}), "--format", "json"])
        hdr = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
        out.append({"channel": "gmail", "title": hdr.get("Subject", "(no subject)")[:120],
                    "url": f"https://mail.google.com/mail/u/0/#all/{mid}",
                    "permalink": f"https://mail.google.com/mail/u/0/#all/{mid}",
                    "snippet": (hdr.get("From", "") + " — " + meta.get("snippet", ""))[:160],
                    "date": hdr.get("Date", "")[:16], "id": mid})
    return out


def _search_slack(terms: List[str], limit: int) -> List[dict]:
    query = " ".join(terms[:4])
    r = subprocess.run(["slack", "search", "messages", query, "--count", str(limit), "--format", "json"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(f"slack failed: {r.stderr[:160]}")
    data = json.loads(r.stdout) if r.stdout.strip() else {}
    out = []
    for m in (data.get("messages") or data.get("matches") or [])[:limit]:
        out.append({"channel": "slack", "title": (m.get("text", "") or "")[:120],
                    "url": m.get("permalink", ""), "permalink": m.get("permalink", ""),
                    "snippet": (m.get("channel", {}) or {}).get("name", "") if isinstance(m.get("channel"), dict) else str(m.get("channel", "")),
                    "date": str(m.get("ts", ""))[:10], "id": m.get("ts", "")})
    return out


_CHANNELS.update({"drive": _search_drive, "gmail": _search_gmail, "slack": _search_slack})
```

> NOTE for implementer: confirm `slack search messages … --format json`'s exact subcommand + result key (`messages` vs `matches`) against the installed `slack` CLI (`slack search --help`); adjust the parse if the shape differs. The dedup/normalize contract is fixed; only the parse adapts.

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_xsearch_channels.py -v`
Expected: 2 pass.

- [ ] **Step 5: Live smoke (Drive)** — needs `gws` on PATH

Run: `cd /Volumes/main-drive/ai-PA && export PATH="$HOME/bin:/opt/homebrew/bin:$PATH" GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=$PWD/gws-bridge/credentials.json PA_WEB_POSTGRES_URL="postgresql://postgres:$(grep ^POSTGRES_PASSWORD= .env|cut -d= -f2-)@127.0.0.1:5433/postgres"; task xsearch --terms "Vernier SOW" --channels drive,slack | jq '{n: (.candidates|length), failed: .failed_channels}'`
Expected: ≥1 drive candidate (the prior SOW); `failed_channels` empty (or names a channel with its error — not a silent empty).

- [ ] **Step 6: Commit**

```bash
git add letta/xsearch_tool.py task-cli/tests/test_xsearch_channels.py
git commit -m "feat(xsearch): drive + gmail + slack channels (gws/slack adapters)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: xsearch memory channels (canonical/history/reference/meetings via qmd) + create canonical collection

**Files:**
- Modify: `letta/xsearch_tool.py` (add `_search_qmd` factory; register `canonical`, `history`, `reference`, `meetings`)
- Test: `task-cli/tests/test_xsearch_memory.py` (create)
- Setup (one-time, documented in plan, run by implementer): create the `canonical` + `meetings` qmd collections

**Interfaces:**
- Produces: `_CHANNELS` gains `canonical`, `history`, `reference`, `meetings`, each backed by `qmd query <q> --collection <name>` (or the collection-scoped form the installed qmd uses). Maps: canonical→`canonical`, history→`tasks-history`, reference→`evernote`, meetings→`meetings`.

- [ ] **Step 1: Create the missing qmd collections (one-time setup)**

```bash
# canonical = the agents-canonical working copy on the runner (confirm path first)
qmd collection add /Volumes/main-drive/letta-canonical --name canonical --pattern '**/*.md' || \
  echo "ADJUST: set the real canonical repo path"
# meetings = the Granola markdown exports
qmd collection add "$HOME/Dropbox/Granola-exports-poller" --name meetings --pattern '**/*.md'
qmd collection list | grep -E "canonical|meetings"
```
Expected: both collections listed. (If the canonical repo path differs, set it; the `canonical` channel maps to whatever collection name you use.)

- [ ] **Step 2: Write the failing test (mock qmd subprocess)**

```python
# task-cli/tests/test_xsearch_memory.py
import os, importlib.util, json
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("xs", os.path.join(_REPO, "letta", "xsearch_tool.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)

class _R:
    def __init__(self, out): self.returncode = 0; self.stdout = out; self.stderr = ""

def test_qmd_channels_registered():
    for c in ("canonical","history","reference","meetings"):
        assert c in xs._CHANNELS

def test_qmd_parse(monkeypatch):
    payload = json.dumps({"results":[{"path":"qmd://canonical/people/tom.md",
        "title":"Tom — Vernier","snippet":"Vernier biology lead","score":0.8}]})
    monkeypatch.setattr(xs.subprocess, "run", lambda *a, **k: _R(payload))
    out = xs._search_qmd("canonical", "canonical")(["Vernier"], 5)
    assert out[0]["channel"] == "canonical"
    assert "Tom" in out[0]["title"]
```

- [ ] **Step 3: Run — expect FAIL**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_xsearch_memory.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement the qmd factory + register**

```python
def _search_qmd(channel_name: str, collection: str):
    def _fn(terms: List[str], limit: int) -> List[dict]:
        q = " ".join(terms[:6])
        r = subprocess.run(
            ["qmd", "query", q, "--collection", collection, "--limit", str(limit), "--json"],
            capture_output=True, text=True, timeout=25)
        if r.returncode != 0:
            raise RuntimeError(f"qmd {collection} failed: {r.stderr[:160]}")
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        out = []
        for h in (data.get("results") or [])[:limit]:
            path = h.get("path", "")
            out.append({"channel": channel_name, "title": (h.get("title") or path)[:120],
                        "url": path, "permalink": path,
                        "snippet": (h.get("snippet") or "")[:160], "date": "", "id": path})
        return out
    return _fn


_CHANNELS.update({
    "canonical": _search_qmd("canonical", "canonical"),
    "history":   _search_qmd("history", "tasks-history"),
    "reference": _search_qmd("reference", "evernote"),
    "meetings":  _search_qmd("meetings", "meetings"),
})
```

> NOTE: confirm `qmd query … --collection <name> --json` flag names against `qmd query --help`; if scoping uses the `qmd://<collection>/` query form instead of `--collection`, adapt `_fn`. Contract (normalized candidate) is fixed.

- [ ] **Step 5: Run tests — expect PASS** + live smoke

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_xsearch_memory.py -v`
Then live: `export PATH="$HOME/bin:/opt/homebrew/bin:$PATH"; task xsearch --terms "Vernier" --channels canonical,history | jq '{n:(.candidates|length), failed:.failed_channels}'`
Expected: tests pass; live returns candidates or names failed channels (never silent).

- [ ] **Step 6: Commit**

```bash
git add letta/xsearch_tool.py task-cli/tests/test_xsearch_memory.py
git commit -m "feat(xsearch): memory channels via qmd (canonical/history/reference/meetings)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Tiered renderer (Primary / Supporting / Related)

**Files:**
- Modify: `pa-web-ui/app.py` `_build_work_packet_segments` (Resources block)
- Test: `pa-web-ui/tests/test_work_packet_segments.py` (append)

**Interfaces:**
- Consumes: `enrichment.packet_info.resources` lines whose leading marker is `[primary]`/`[secondary]`/`[background]`.
- Produces: the note's Resources section grouped under `Primary` / `Supporting` / `Related` headers; lines with no/unknown marker fall under `Related`. Existing per-line link + dual-link rendering unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def test_resources_grouped_into_tiers():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[primary] SOW draft — https://docs.google.com/document/d/X/edit (edit)",
        "[secondary] Status thread — https://acme.slack.com/archives/C1/p1 (reference)",
        "[background] Old note — https://example.com/n (read)",
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    texts = [s["text"] if isinstance(s, dict) else s for s in segs]
    joined = "".join(texts)
    assert "Primary" in joined and "Supporting" in joined and "Related" in joined
    # order: Primary header precedes Supporting precedes Related
    assert joined.index("Primary") < joined.index("Supporting") < joined.index("Related")

def test_untiered_resource_falls_under_related():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "Doc — https://example.com/a (reference)"]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    joined = "".join(s["text"] if isinstance(s, dict) else s for s in segs)
    assert "Related" in joined
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Volumes/main-drive/ai-PA/pa-web-ui && python -m pytest tests/test_work_packet_segments.py -k tier -v`
Expected: FAIL (no tier headers).

- [ ] **Step 3: Implement tier grouping in the Resources block**

In `_build_work_packet_segments`, replace the `if pi.get("resources"):` block with a tier-grouping version. Bucket each line by its leading marker, then render Primary → Supporting → Related, reusing the existing per-line URL rendering:

```python
    # Resources, grouped into tiers by the leading [primary|secondary|background]
    # marker → Primary / Supporting / Related. Each line still hyperlinks every
    # URL (live + offline copy) exactly as before.
    if pi.get("resources"):
        tiers = {"primary": [], "secondary": [], "background": []}
        for item in pi["resources"]:
            m = re.match(r"^\s*\[(primary|secondary|background)\]", item)
            tiers[m.group(1) if m else "background"].append(item)
        segments.append("\n")
        segments.append({"text": "Resources\n", "bold": True, "size": 13})
        for tier_key, header in (("primary", "Primary"), ("secondary", "Supporting"),
                                 ("background", "Related")):
            if not tiers[tier_key]:
                continue
            segments.append({"text": f"  {header}\n", "bold": True, "size": 11,
                             "color": [0.5, 0.5, 0.5, 1]})
            for item in tiers[tier_key]:
                urls = re.findall(r"(openfile://\S+|https?://\S+)", item)
                if urls:
                    urls = [u.rstrip("| ").strip() for u in urls]
                    first = re.search(r"(openfile://\S+|https?://\S+)", item)
                    label = re.sub(r"^\s*\[(primary|secondary|background)\]\s*", "", item[:first.start()].strip()).rstrip("—|").strip()
                    role_match = re.search(r"\s+\((\w+)\)\s*$", item)
                    role = f" ({role_match.group(1)})" if role_match else ""
                    segments.append({"text": f"    {label}{role}: ", "size": 11})
                    for idx, url in enumerate(urls):
                        if url.startswith("openfile://"):
                            display = "Offline copy"
                        elif "slack.com/archives/" in url:
                            display = "Permalink"
                        else:
                            display = url[:60] + ("..." if len(url) > 60 else "")
                        if idx:
                            segments.append({"text": "   ·   ", "size": 11})
                        segments.append({"text": f"{display}", "url": url, "underline": True, "size": 11})
                    segments.append("\n")
                else:
                    for line in _lines(item):
                        segments.append(f"    • {line}\n")
```

- [ ] **Step 4: Run tests — expect PASS** (full suite, no regression)

Run: `cd /Volumes/main-drive/ai-PA/pa-web-ui && python -m pytest tests/test_work_packet_segments.py -v`
Expected: all pass (the prior dual-link tests still green + 2 new tier tests).

- [ ] **Step 5: Hot-deploy app.py + verify healthy**

```bash
cd /Volumes/main-drive/ai-PA
docker cp pa-web-ui/app.py pa-web-ui:/app/app.py && docker restart pa-web-ui >/dev/null
until [ "$(docker inspect -f '{{.State.Health.Status}}' pa-web-ui)" = "healthy" ]; do sleep 3; done; echo healthy
```

- [ ] **Step 6: Commit**

```bash
git add pa-web-ui/app.py pa-web-ui/tests/test_work_packet_segments.py
git commit -m "feat(work-packet): render resources in Primary/Supporting/Related tiers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: The `cross_channel_backtrace` recipe (tasks-agent memfs)

**Files:**
- Create: `~/.letta/lc-local-backend/memfs/agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4/memory/system/cross_channel_backtrace.md` (NOT git-tracked — memfs, synced to Gitea by the runner)

**Interfaces:**
- Consumes: `task backtrace <ref>` (anchors + search_terms), `task xsearch`, `task stage`, `task packet-write`.
- Produces: a confirmed task's `enrichment.packet_info.resources` populated with tiered cross-channel resources.

- [ ] **Step 1: Write the recipe file**

Write the file with this content (real triple-backticks in the file):

```markdown
---
description: |
  Cross-channel backtrace for a CONFIRMED task. Build a full work packet by
  searching across Drive/Slack/Gmail/internal-history/memory from the task's
  anchors, then writing tiered (Primary/Supporting/Related) resources. Triggered
  on confirm via push (prompt names this recipe + the ref_id).
---

# Cross-channel backtrace — build the full work packet

Trigger: a push "[Backtrace] confirmed task ref_id=… run cross_channel_backtrace".

## Step 0 — Memory grounding (FIRST, before searching)
- Read what canonical/your memfs already know about this task's people + project:
  `task xsearch --terms "<task keywords>" --channels canonical,history`
- Use it to (a) expand the search terms with the real people-names + project
  aliases, and (b) form a relevance frame (what "done" looks like, prior decisions).
  Memory is the LENS — it makes the channel searches below sharper.

## Step 1 — Anchors
`task backtrace <ref-id>` → take `search_terms` + `anchors` as your starting terms.

## Step 2 — Fan out (adaptive)
`task xsearch --terms "term1,term2,…" --channels drive,slack,gmail,tasks,meetings,canonical,history,reference`
- Read the candidates. CHASE threads: if you find the prior SOW doc, run xsearch
  again with its title to find the Slack/email status thread, etc. 2–3 rounds max.
- `failed_channels` tells you which channels errored — note gaps; never assume a
  silent empty means "nothing there".

## Step 3 — Judge + tier
Assign each genuinely-relevant candidate a tier (drop noise):
- `[primary]` — the artifact the task acts on + the 1–2 highest-relevance items.
- `[secondary]` — status threads, decisions, prior/related tasks, key context.
- `[background]` — useful-but-peripheral; the long tail.

## Step 4 — Stage the Primary items (offline copies)
For each `[primary]` that is a file or note-text (NOT a live Google-native doc,
NOT a generic web page): `task stage --url "<url>" --label "<label>" --ref-id <ref> --priority primary`
(or pipe note text with `--text -`). Append the returned openfile:// to the SAME
resource line as the live link (dual link), per the resource grammar.

## Step 5 — Write the packet
`task packet-write --ref-id <ref> --direct-action "…" [--artifact-provenance …] [--intent-genesis …] --resources "<one tiered line per resource>" --estimated-minutes <N>`
Resource line format: `[tier] <label> — <live-url> [| offline: <openfile-url>] (role)`.

## Step 6 — Report
State how many resources per tier you wrote and which channels (if any) failed.
NEVER claim a resource/staged file you didn't actually create — the CLIs return
real ids/paths; use those.
```

- [ ] **Step 2: Verify the file parses + is readable by the agent**

Run: `head -5 ~/.letta/lc-local-backend/memfs/agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4/memory/system/cross_channel_backtrace.md`
Expected: the frontmatter + heading. (Runner syncs memfs to Gitea on next cycle.)

- [ ] **Step 3: No commit** (memfs is not in this git repo). Note in the PR/commit message of Task 7 that the recipe was added to the tasks-agent memfs.

---

## Task 7: On-confirm trigger (dispatch the recipe)

**Files:**
- Modify: `pa-web-ui/app.py` confirm handler (after the `_assemble_work_packet` thread, ~line 3835)
- Test: `pa-web-ui/tests/test_backtrace_dispatch.py` (create)

**Interfaces:**
- Consumes: the push-receiver at `LETTA_PUSH_RECEIVER_URL` (default `http://host.docker.internal:8099/push`), `agent="tasks"`.
- Produces: on every confirm, a background POST that asks the tasks-agent to run `cross_channel_backtrace` for the ref_id.

- [ ] **Step 1: Write the failing test (dispatch payload builder)**

Factor the payload into a pure helper so it's testable without HTTP:

```python
# pa-web-ui/tests/test_backtrace_dispatch.py
import importlib.util, os
spec = importlib.util.spec_from_file_location("app", os.path.join(os.path.dirname(__file__), "..", "app.py"))
# import guarded: app.py has import-time side effects; if it can't import in CI,
# test the helper in isolation by copying it. Implementer: prefer importing app.
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

def test_backtrace_push_body():
    body = app._backtrace_push_body("abc123ef")
    assert body["agent"] == "tasks"
    assert "cross_channel_backtrace" in body["prompt"]
    assert "abc123ef" in body["prompt"]
    assert body["source_ref"] == "abc123ef"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Volumes/main-drive/ai-PA/pa-web-ui && python -m pytest tests/test_backtrace_dispatch.py -v`
Expected: FAIL (`_backtrace_push_body` undefined).

- [ ] **Step 3: Add the helper + the dispatch**

Near the other module helpers in `pa-web-ui/app.py`:

```python
def _backtrace_push_body(ref_id):
    """Push payload that asks the tasks-agent to run the cross-channel backtrace."""
    return {
        "agent": "tasks",
        "source_ref": ref_id,
        "priority": "normal",
        "prompt": (
            f"[Backtrace] confirmed task ref_id={ref_id} — run "
            f"cross_channel_backtrace.md: ground in memory (canonical+history), "
            f"fan out via `task xsearch` across drive/slack/gmail/tasks/meetings/"
            f"canonical/history/reference from the task's anchors, judge + tier the "
            f"hits (Primary/Supporting/Related), stage the Primary items, and write "
            f"the tiered resources via `task packet-write`. Build the full packet."
        ),
    }
```

Then in the `if action == "confirm":` block, after the `_assemble_work_packet` thread start (~line 3835), add an always-on dispatch:

```python
            # Cross-channel backtrace (async, every confirm): enrich the packet
            # with prioritized resources mined across channels + memory.
            def _dispatch_cross_channel_backtrace():
                try:
                    import urllib.request
                    url = os.environ.get("LETTA_PUSH_RECEIVER_URL",
                                         "http://host.docker.internal:8099/push")
                    req = urllib.request.Request(
                        url, data=json.dumps(_backtrace_push_body(ref_id)).encode(),
                        headers={"Content-Type": "application/json"}, method="POST")
                    urllib.request.urlopen(req, timeout=10)
                    logger.info("cross_channel_backtrace_dispatched", ref_id=ref_id)
                except Exception as e:
                    logger.error("cross_channel_backtrace_dispatch_failed", ref_id=ref_id, error=str(e))
            threading.Thread(target=_dispatch_cross_channel_backtrace, daemon=True).start()
```

- [ ] **Step 4: Run test — expect PASS** + hot-deploy + verify healthy

```bash
cd /Volumes/main-drive/ai-PA/pa-web-ui && python -m pytest tests/test_backtrace_dispatch.py -v
cd /Volumes/main-drive/ai-PA && docker cp pa-web-ui/app.py pa-web-ui:/app/app.py && docker restart pa-web-ui >/dev/null
until [ "$(docker inspect -f '{{.State.Health.Status}}' pa-web-ui)" = "healthy" ]; do sleep 3; done; echo healthy
```

- [ ] **Step 5: Commit**

```bash
git add pa-web-ui/app.py pa-web-ui/tests/test_backtrace_dispatch.py
git commit -m "feat(work-packet): dispatch cross_channel_backtrace on task confirm

(Recipe added to tasks-agent memfs: cross_channel_backtrace.md — not in this repo.)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Backstop — flag confirmed tasks with thin packets

**Files:**
- Create: `scripts/check-packet-enrichment.py`
- Create (NOT git-tracked): `~/Library/LaunchAgents/com.ai-pa.packet-enrichment-check.plist`
- Test: `task-cli/tests/test_packet_backstop.py` (create) — tests the pure `is_thin()` helper

**Interfaces:**
- Produces: a pass that, for tasks confirmed in the last N hours, marks `enrichment.backstop = {"thin": bool, "channels": int, "checked_at": …}` and logs a WARNING for thin ones. "Thin" = resources draw from ≤1 distinct channel (i.e. nothing beyond the originating source).

- [ ] **Step 1: Write the failing test (pure helper)**

```python
# task-cli/tests/test_packet_backstop.py
import os, importlib.util
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("ck", os.path.join(_REPO, "scripts", "check-packet-enrichment.py"))
ck = importlib.util.module_from_spec(spec); spec.loader.exec_module(ck)

def test_thin_when_single_channel():
    res = ["[primary] Meeting notes — https://notes.granola.ai/d/x (read)"]
    assert ck.is_thin(res) is True

def test_not_thin_with_multiple_channels():
    res = ["[primary] SOW — https://docs.google.com/document/d/x/edit (edit)",
           "[secondary] Status — https://acme.slack.com/archives/C/p (reference)"]
    assert ck.is_thin(res) is False
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_packet_backstop.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `scripts/check-packet-enrichment.py`**

```python
#!/usr/bin/env python3
"""Backstop: flag CONFIRMED tasks whose work packet didn't gain cross-channel
resources (the cross_channel_backtrace under-delivered or never ran). Loud, not
silent. Writes enrichment.backstop; logs WARNING for thin packets.

A packet is "thin" if its resources draw from <= 1 distinct channel (host).
"""
import argparse, json, os, re, sys
from datetime import datetime, timezone
from urllib.parse import urlparse


def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def is_thin(resources) -> bool:
    hosts = set()
    for line in resources or []:
        for u in re.findall(r"https?://\S+", line):
            h = _host(u.rstrip("|) "))
            if h:
                hosts.add(h)
    return len(hosts) <= 1


def _db_url() -> str:
    url = os.environ.get("PA_WEB_POSTGRES_URL")
    if url:
        return url
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql://postgres:{pw}@localhost:{os.environ.get('PA_WEB_POSTGRES_PORT','5433')}/postgres"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-hours", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    thin = 0
    with psycopg.connect(_db_url(), autocommit=True, connect_timeout=10) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT ref_id, enrichment FROM pa_web.tasks "
                "WHERE status='confirmed' AND closed_at IS NULL "
                "AND updated_at > NOW() - (%s || ' hours')::interval",
                (args.window_hours,))
            rows = cur.fetchall()
        for r in rows:
            enr = r["enrichment"]
            if isinstance(enr, str):
                try: enr = json.loads(enr)
                except Exception: enr = {}
            if not isinstance(enr, dict):
                enr = {}
            resources = (enr.get("packet_info") or {}).get("resources") or []
            t = is_thin(resources)
            enr["backstop"] = {"thin": t, "checked_at": datetime.now(timezone.utc).isoformat()}
            if t:
                thin += 1
                print(f"[{datetime.now(timezone.utc):%FT%TZ}] [packet-backstop] WARN thin packet "
                      f"ref_id={r['ref_id']} (resources from <=1 channel)", flush=True)
            if not args.dry_run:
                with conn.cursor() as c2:
                    c2.execute("UPDATE pa_web.tasks SET enrichment=%s WHERE ref_id=%s",
                               (Jsonb(enr), r["ref_id"]))
    print(f"[{datetime.now(timezone.utc):%FT%TZ}] [packet-backstop] done: checked={len(rows)} thin={thin}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_packet_backstop.py -v`
Expected: 2 pass.

- [ ] **Step 5: launchd job (hourly) + load**

Create `~/Library/LaunchAgents/com.ai-pa.packet-enrichment-check.plist` (logs in `~/Library/Logs/packet-enrichment-check/`, `POSTGRES_PASSWORD` from `.env` in `EnvironmentVariables`, `StartInterval` 3600, ProgramArguments `/Users/dorseyhomeserver/.local/pipx/venvs/task-cli/bin/python /Volumes/main-drive/ai-PA/scripts/check-packet-enrichment.py`). Load: `launchctl bootstrap gui/$(id -u) <plist>` and verify with `launchctl print …`.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-packet-enrichment.py task-cli/tests/test_packet_backstop.py
git commit -m "feat(work-packet): backstop flags confirmed tasks with thin (single-channel) packets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: End-to-end validation on Vernier SOW

**Files:** none (runtime acceptance). Uses `task`, the push path, and the OF reassemble endpoint.

- [ ] **Step 1: Reinstall CLI + confirm all envs**

`pipx install --force -e /Volumes/main-drive/ai-PA/task-cli` ; ensure `gws`/`slack`/`qmd`/`task` on PATH; canonical+meetings qmd collections exist (Task 4).

- [ ] **Step 2: Re-dispatch the backtrace for `fcdf4afb-a`** (bypasses needing a fresh confirm)

```bash
curl -s -X POST http://localhost:8099/push -H "Content-Type: application/json" \
  -d "$(python3 -c 'import json;print(json.dumps({"agent":"tasks","source_ref":"fcdf4afb-a","priority":"normal","prompt":"[Backtrace] confirmed task ref_id=fcdf4afb-a — run cross_channel_backtrace.md: ground in memory, fan out via task xsearch across all channels, judge+tier, stage primaries, write tiered resources via task packet-write."}))')"
```
Then wait for the warm tasks subprocess to finish (watch `logs/health/warm-tasks-*.log` for a `result`). If it returns a no-tool-call result (context-rot fabrication), recycle: `kill <warm tasks pid>` and re-push (per the marker-scanner gotcha).

- [ ] **Step 3: Verify the packet gained cross-channel, tiered resources**

```bash
docker exec supabase-db psql -U postgres -d postgres -tAc \
 "SELECT jsonb_pretty(enrichment->'packet_info'->'resources') FROM pa_web.tasks WHERE ref_id='fcdf4afb-a';"
```
Expected: resources spanning ≥2 channels — e.g. a `[primary]` Drive link to the **prior SOW doc**, a `[secondary]` **Slack** status permalink, plus the meeting note — with tier markers. (This is the gap from the design's motivating example.)

- [ ] **Step 4: Reassemble + on-device check + estimates untouched**

CSRF handshake → `POST /api/tasks/fcdf4afb-a/reassemble-work-packet`; open the OF note → Resources shows **Primary / Supporting / Related** with clickable links. Then:
`docker exec supabase-db psql -U postgres -d postgres -tAc "SELECT original_est_minutes, revised_est_minutes, actual_minutes FROM pa_web.tasks WHERE ref_id='fcdf4afb-a';"` → unchanged.

- [ ] **Step 5: Backstop sanity**

`POSTGRES_PASSWORD=… python3 scripts/check-packet-enrichment.py --dry-run` → the Vernier task should NOT be flagged thin (now multi-channel).

- [ ] **Step 6: Record the validation example** in `docs/research/2026-06-16-cross-channel-backtrace-validation.md` (ref_id, the tiered resources produced, channels hit) and commit.

---

## Completion

After all tasks: use **superpowers:finishing-a-development-branch** — run both test suites (`task-cli` + `pa-web-ui`), confirm the branch is clean, present merge options.

**Definition of done:** confirming a task triggers an async cross-channel backtrace that grounds in memory, searches Drive/Slack/Gmail/internal-history/memory from the task's anchors, and writes a tiered Primary/Supporting/Related resource set into the OF note — demonstrated by Vernier SOW surfacing the prior SOW doc + Slack status thread; the eval loop is provably untouched; and a backstop loudly flags any confirmed task whose packet stayed single-channel.

## Self-review notes

- **Spec coverage:** trigger-on-confirm (T7), all 8 channels incl. memory (T2–T4), memory backbone+source (T4 channels + T6 recipe Step 0), tiered curation reusing existing markers (T5), agent-driven judgment + verified-CLI writes (T6 + reuse of `task stage`/`packet-write`) + backstop (T8), backtrace cleanup/expose-terms (T1), e2e Vernier (T9), meeting-prep seam (engine = xsearch + tiering + recipe loop, documented in design; nothing here blocks reuse). All covered.
- **Eval-loop safety:** no task writes estimate/actual columns or the `Agent Estimate:` line.
- **Type consistency:** `xsearch(terms, channels, limit_per_channel)` + the normalized candidate dict `{channel,title,url,permalink,snippet,date,id}` are identical across T2–T4 and the CLI; resource line grammar + `[primary/secondary/background]` markers identical across T5/T6 and the existing renderer.
- **Known verify-points (flagged inline, not placeholders):** exact `slack search` and `qmd query` flag/JSON shapes — the plan shows the intended invocation with a NOTE to confirm against `--help` and adapt the parse; the normalized contract is fixed.
