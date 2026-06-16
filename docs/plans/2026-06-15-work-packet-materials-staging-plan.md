# Work-Packet Materials & Staging Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a task is confirmed and promoted to OmniFocus, the work-packet note carries the *materials* needed to do it — clickable live links to the source artifact (Drive doc, meeting notes, email, Slack message) plus, where useful, a staged local copy the user can open offline — so both the agent and the user can cue up and engage with everything at the moment of tackling the task.

**Architecture:** Local-mode only. The live tasks-agent (`agent-local-30c45759`) runs on the host via the launchd runner and enriches tasks through the `task` CLI (`task-cli`), which imports the canonical Python tools in `letta/*_tool.py`. The OmniFocus note is the delivery surface: `pa-web-ui/app.py:_build_work_packet_segments()` renders `enrichment.packet_info.resources[]` into clickable rich-text segments via the host OmniFocus bridge (port 8889). Materials reach the note in three ways, in priority order: (1) **live URLs** harvested during fetch/backtrace and written into `resources[]` (universal — work on every device); (2) **staged copies** downloaded to `~/Dropbox/letta-shared-files/staged/{category}/{ref_id}/` and exposed as `openfile://` host paths (desktop offline access via the installed `OpenFileHandler.app`); (3) **inline-text staging** — agent-fetched note text (meeting transcript, email body) written to a local `.md` so the user can read it in place. The renderer shows both the cloud link and the staged copy when both exist.

**Tech Stack:** Python 3 (`click` CLI, `psycopg`, `urllib`, `subprocess`→`gws` CLI for Gmail/Drive, Granola Public API), Flask (`pa-web-ui`), OmniFocus OmniJS bridge (rich text via `setRichText`), `openfile://` URL handler (Swift `OpenFileHandler.app`), `pytest`.

---

## Background: what exists, what's broken

**Recovered former design (faithful translation targets):**
- `enrichment.packet_info.resources[]` — list of free-text lines, format `[priority] label — url (role)`. Renderer (`pa-web-ui/app.py:3355-3375`) already hyperlinks the **first** `openfile://` or `https://` URL per line; Slack permalinks render as the word "Permalink".
- `stage_resource(url, label, priority, ref_id)` (`letta/stage_resource_tool.py`) — downloads HTTP files / Gmail messages (via `gws`) / non-native Drive files (via `gws alt=media`) to `/data/shared/staged/{category}/{ref_id}/`, translates to host path `~/Dropbox/letta-shared-files/staged/...`, returns `openfile://<host-path>`. **Skips** Google-native docs and web pages (click-through to live URL is the design intent). 50MB cap, 24h idempotent reuse.
- Three-node backtrace: `direct_action` / `artifact_provenance` / `intent_genesis`.

**Root causes of "0/12 recent tasks have materials" (verified in scan):**
1. **Resource population is Slack-only.** The enrichment dispatch prompt (`scheduler-service/scripts/enrichment-scanner.py:207-213`) and the agent recipe (`task_cli_recipes.md`) only instruct the agent to emit a `resources` line for Slack permalinks. Email / meeting / docs-comment / Drive get no instruction → no resources written.
2. **Meeting permalink is not surfaced in metadata.** `fetch_source_content` (`letta/fetch_source_content_tool.py`) puts `web_url` into the prose `[Permalink: ...]` line but the meeting branch's `metadata` (lines 465-472) carries only `meeting_id` / `fetched_via`. Email, Slack, and docs-comment all expose `metadata.permalink`; meeting is the outlier.
3. **`backtrace_task` is meeting-blind and hop-stubbed.** It only fetches `gmail:` content (`letta/backtrace_task_tool.py:131`); `granola:` falls through to `source_text_field`. The archival hop search is stubbed (`archival_hits = []`, lines 261-272), so `artifact_candidates` / `intent_candidates` are always empty and never become resources.
4. **No staging in local mode.** `stage_resource` exists only in deprecated Letta-server modules (`letta/stage_resource_tool.py`, `letta/mc-tools/stage_resource.py`); there is **no `task stage` subcommand**, and the code hardcodes container paths (`CONTAINER_BASE = /data/shared/staged`) that don't apply when the agent runs on the host.
5. **Cross-device clickability gap.** `openfile://` resolves only on a Mac with `OpenFileHandler.app` installed AND Dropbox synced. The user also opens OF notes on iPhone/iPad where `openfile://` cannot resolve. The renderer's `re.search` grabs only the first URL per line, so a single resource line cannot offer both a universal cloud link and a device-local staged copy.

**Improvements layered on the former design:**
- Resource population becomes **source-agnostic** (Phase 1).
- Staging is reimplemented **host-native** with an added **inline-text** mode so agent-fetched note text becomes a readable local `.md` (Phase 3) — directly serving "engage with via the note text as well."
- The renderer offers **both** the universal cloud link and the staged offline copy on one resource (Phase 4), resolving the cross-device gap.

**Non-negotiable constraints (carried from prior work):**
- **Do not corrupt the estimate/actuals eval loop.** This plan never touches `original_est_minutes` / `revised_est_minutes` / `actual_minutes` writers, nor the `Agent Estimate:` timer line. Resources rendering is additive.
- **Local mode only.** No Letta-server tool re-registration. Fixes land in `letta/*_tool.py` (imported by the CLI) and the CLI itself.
- **Don't `git add -A`** in the home dir. Commit only the specific repo files this plan touches.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `letta/fetch_source_content_tool.py` | Source content + metadata for all source types | Modify: meeting branch exposes `metadata.permalink` + `metadata.artifact_urls` |
| `letta/backtrace_task_tool.py` | Cross-source materials gathering | Modify: add `granola:` fetch; harvest URLs from `source_metadata`; light pa_web.tasks related-row search |
| `letta/stage_resource_tool.py` | Download/stage a material → `openfile://` | Rewrite: host-native paths (env-configurable); add inline-text staging mode |
| `task-cli/src/task_cli/cli.py` | Agent-facing CLI surface | Add: `task stage` subcommand |
| `scheduler-service/scripts/enrichment-scanner.py` | Enrichment dispatch prompt | Modify: source-agnostic resource + staging instructions |
| `~/.letta/lc-local-backend/memfs/agent-local-30c45759-.../memory/system/task_cli_recipes.md` | Agent operating recipe | Modify: document `task stage` + resource conventions (synced to Gitea by runner) |
| `pa-web-ui/app.py` | Work-packet note renderer | Modify: hyperlink **all** URLs per resource line w/ smart labels |
| `pa-web-ui/tests/test_work_packet_segments.py` | Renderer tests | Extend: dual-link cases |
| `task-cli/tests/test_stage_resource.py` | Staging tests | Create |
| `docs/plans/2026-06-15-work-packet-materials-staging-plan.md` | This plan | Create |

---

## Task 1: Surface the meeting permalink (and artifact URLs) in fetch metadata

**Why first:** smallest change, unblocks Phase 1's prompt from relying on a `metadata.permalink` that meetings don't currently provide.

**Files:**
- Modify: `letta/fetch_source_content_tool.py:380-484` (meeting branch)

- [ ] **Step 1: Capture `web_url` while composing the meeting bundle**

In the meeting branch, where `note.get("web_url")` is read into `bits` (around line 392), also stash it. Add a local before the `bits` loop:

```python
            meeting_web_url = ""
```
and set it when present:
```python
                    if note.get("web_url"):
                        meeting_web_url = note["web_url"]
                        bits.append(f"[Permalink: {note['web_url']}]")
```

- [ ] **Step 2: Put the permalink into `metadata` on the success path**

Where the meeting `metadata` dict is built (lines 465-472), add `permalink`:

```python
                metadata = {
                    "meeting_id": meeting_id,
                    "permalink": meeting_web_url,
                    "fetched_via": (
                        "granola_public_api"
                        if fetched_via_api
                        else "pa_web.tasks.source_metadata"
                    ),
                }
```

- [ ] **Step 3: Fall back to row source_metadata for the permalink**

Before composing `metadata`, if `meeting_web_url` is empty, try the row's stashed smeta:

```python
            if not meeting_web_url:
                _sm = locals().get("_row_smeta") or {}
                meeting_web_url = _sm.get("web_url") or _sm.get("permalink") or ""
```

(Insert immediately after the `if raw_transcript:` content assembly, before the `metadata = {...}` block.)

- [ ] **Step 4: Smoke-test against a real meeting task**

Run: `task fetch-source --ref-id <a-known-meeting-ref> | jq '.metadata'`
Expected: JSON contains a non-empty `permalink` (a `https://notes.granola.ai/...` or `web_url`) when the meeting note has one; `meeting_id` still present.

- [ ] **Step 5: Commit**

```bash
git add letta/fetch_source_content_tool.py
git commit -m "fix(work-packet): expose meeting permalink in fetch_source_content metadata

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Make resource population source-agnostic (prompt + recipe)

**Why:** this is the highest-leverage change — it lights up live links on every source type with no renderer change, because the renderer already hyperlinks `https://` URLs in `resources[]`.

**Files:**
- Modify: `scheduler-service/scripts/enrichment-scanner.py:207-213` (RESOURCE FORMATTING block; volume-mounted → live without rebuild)
- Modify: `~/.letta/lc-local-backend/memfs/agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4/memory/system/task_cli_recipes.md`

- [ ] **Step 1: Replace the Slack-only RESOURCE FORMATTING block**

Replace the existing block (the `f"RESOURCE FORMATTING: when the source is slack, ..."` paragraph) with a source-agnostic instruction:

```python
        f"RESOURCE FORMATTING (ALL sources — not just slack): fetch_source_content "
        f"returns artifact URLs in `metadata`. ALWAYS populate the `resources` field "
        f"so the user can click straight to what they need:\n"
        f"  - The source permalink (metadata.permalink): the slack message, the email "
        f"(mail.google.com permalink), the Granola meeting note (web_url), or the docs "
        f"comment (disco-anchored doc URL). Use the EXACT permalink URL.\n"
        f"  - The PRIMARY ARTIFACT the task acts on, if different from the source: e.g. "
        f"a task to 'revise the SOW doc' → the Google Doc URL; 'review the attached PDF' "
        f"→ that file. Harvest these from the fetched content / backtrace anchors.\n"
        f"Format each on its own line: `[priority] <short label> — <url> (role)` where "
        f"priority is primary|secondary|background and role is a hint like edit, review, "
        f"reference, or read. Example:\n"
        f"  [primary] Audubon SOW draft — https://docs.google.com/document/d/XXX/edit (edit)\n"
        f"  [secondary] Kickoff meeting notes — https://notes.granola.ai/d/YYY (reference)\n"
        f"If a resource is a downloadable FILE (PDF, Word/Excel/PPT, a Gmail message you "
        f"want available offline, or note text the user should read in place), ALSO stage "
        f"a local copy — see step 4b.\n\n",
```

- [ ] **Step 2: Add a staging sub-step (4b) to the dispatch prompt**

Immediately after the existing step-4 paragraph (`backtrace_task` ... `write_packet_info`), insert:

```python
        f"4b. STAGING (optional but preferred for files & note text): for resources that "
        f"are real files or note text — NOT live Google-native docs (leave those as live "
        f"links so the user edits the current version) and NOT generic web pages — run "
        f"`task stage` to save a local copy and get an openfile:// link. Two forms:\n"
        f"   - Download a file/email/Drive attachment: "
        f'`task stage --url "<https-or-gmail:ID-or-drive-url>" --label "<label>" '
        f'--ref-id "{ref_id}" --priority primary`\n'
        f"   - Stage note text you already fetched (meeting transcript, email body) as "
        f'markdown: pipe the text in — `task fetch-source --ref-id {ref_id} | jq -r .content '
        f'| task stage --text - --label "Meeting notes" --ref-id "{ref_id}"`\n'
        f"   Each call returns an `openfile_url`. Add it to the SAME resource line as the "
        f"live link so the user can pick: "
        f"`[primary] <label> — <live-url> | offline: <openfile-url> (read)`. If there is no "
        f"live URL, the openfile:// link alone is fine.\n",
```

- [ ] **Step 3: Verify the scanner still imports/parses (no rebuild needed — volume-mounted)**

Run:
```bash
docker exec ai-pa-scheduler-service-1 python -c "import importlib.util, sys; \
spec = importlib.util.spec_from_file_location('es', '/app/scripts/enrichment-scanner.py'); \
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK, prompt builds')"
```
Expected: `OK, prompt builds` (the module imports cleanly; the f-string prompt is built at dispatch time, but import proves no syntax error).

- [ ] **Step 4: Update the agent recipe (`task_cli_recipes.md`)**

In the Phase A / Phase B sections, add the resource + staging conventions so the agent applies them outside the dispatch prompt too (e.g., user-triggered backtraces). Append a new subsection after "Phase B — backtrace":

```markdown
### Phase B.5 — materials (resources + staging)

Always populate `--resources` so the work-packet note carries clickable materials:

- One line per resource: `[priority] <label> — <url> (role)`.
- Include the **source permalink** (from `task fetch-source ... | jq .metadata.permalink`)
  and the **primary artifact URL** the task acts on.
- For files / note text (NOT live Google-native docs, NOT generic web pages), stage a
  local copy and append its openfile:// link to the same line:
  `[primary] <label> — <live-url> | offline: <openfile-url> (read)`

Staging:

```bash
# Download a file / Gmail message / Drive attachment:
task stage --url "gmail:1923ab..." --label "Vendor quote" --ref-id <ref> --priority primary

# Stage already-fetched note text as markdown:
task fetch-source --ref-id <ref> | jq -r .content \
  | task stage --text - --label "Meeting notes" --ref-id <ref>
```

`task stage` skips live Google-native docs and generic web pages (returns
`status:"skipped"`) — for those, keep the live URL in resources, no openfile copy.
```

- [ ] **Step 5: Commit the tracked files** (the memfs recipe is synced to Gitea by the runner, not this repo)

```bash
git add scheduler-service/scripts/enrichment-scanner.py
git commit -m "feat(work-packet): source-agnostic resource population + staging step in enrichment prompt

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Rewrite `stage_resource` host-native + add inline-text mode

**Files:**
- Rewrite: `letta/stage_resource_tool.py`

- [ ] **Step 1: Parameterize the staging base (host-native, env-overridable)**

Replace the hardcoded `CONTAINER_BASE` / `HOST_BASE` block (lines 66-84) with:

```python
        # Host-native staging (local mode): the tasks-agent runs on the host via
        # the launchd runner, so it writes directly to the Dropbox-synced staging
        # tree and the openfile:// URL is that same real path — no container
        # translation. STAGE_BASE_DIR overrides for tests / future relocation.
        # STAGE_OPENFILE_BASE lets a containerized caller map the write path to a
        # host path for the URL (defaults to STAGE_BASE_DIR → identity mapping).
        DEFAULT_BASE = "/Users/dorseyhomeserver/Dropbox/letta-shared-files/staged"
        STAGE_BASE = os.environ.get("STAGE_BASE_DIR", DEFAULT_BASE)
        OPENFILE_BASE = os.environ.get("STAGE_OPENFILE_BASE", STAGE_BASE)

        try:
            os.makedirs(STAGE_BASE, exist_ok=True)
        except Exception as e:
            return {"status": "error",
                    "error_message": f"Cannot access staging directory {STAGE_BASE}: {e}"}
        if not os.access(STAGE_BASE, os.W_OK):
            return {"status": "error",
                    "error_message": f"Staging directory {STAGE_BASE} is not writable"}
```

Then replace every later `CONTAINER_BASE` reference with `STAGE_BASE`, and every host-path translation
`target_path.replace(CONTAINER_BASE, HOST_BASE, 1)` with:

```python
                host_path = target_path.replace(STAGE_BASE, OPENFILE_BASE, 1)
```

(There are reuse/return blocks at ~lines 161, 302, 347 — update all.)

- [ ] **Step 2: Add an inline-text staging mode**

Add a `text` parameter to the signature:

```python
def stage_resource(
    url: Optional[str] = None,
    label: str = "",
    priority: Optional[str] = None,
    ref_id: Optional[str] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
```

Update the docstring `Args:` to document `text` ("Inline note text to stage as a markdown file instead of downloading a url; mutually exclusive with url."). Then, right after `priority = priority or "secondary"` and the base-dir setup, add the text branch BEFORE the URL-category logic:

```python
        if not label:
            return {"status": "error", "error_message": "label is required"}
        if not url and text is None:
            return {"status": "error", "error_message": "either url or text is required"}

        if text is not None:
            # Inline-text staging → markdown file the user can read in place.
            category = "notes"
            extension = "md"
            ref_id_part = ref_id or "orphan"
            target_dir = os.path.join(STAGE_BASE, category, ref_id_part)
            os.makedirs(target_dir, exist_ok=True)
            safe_label = re.sub(r"[^a-zA-Z0-9\-_]", "-", label)[:60].strip("-") or "note"
            filename = f"{safe_label}.{extension}"
            target_path = os.path.join(target_dir, filename)
            body = text if text.lstrip().startswith("#") else f"# {label}\n\n{text}"
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(body)
            host_path = target_path.replace(STAGE_BASE, OPENFILE_BASE, 1)
            return {
                "status": "ok",
                "local_path": target_path,
                "openfile_url": f"openfile://{host_path}",
                "filename": filename,
                "size_bytes": len(body.encode("utf-8")),
                "category": category,
                "priority": priority,
                "reused": False,
            }
```

Guard the existing URL logic so it only runs when `url` is set (it already references `url` throughout; the `if not url and text is None` check above plus the early `return` in the text branch makes this safe).

- [ ] **Step 3: Read `--text -` from stdin handled at the CLI layer** (no tool change) — see Task 4.

- [ ] **Step 4: Commit**

```bash
git add letta/stage_resource_tool.py
git commit -m "feat(work-packet): host-native stage_resource + inline-text markdown staging

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Add the `task stage` CLI subcommand

**Files:**
- Modify: `task-cli/src/task_cli/cli.py` (add command after `packet_write`, ~line 502)

- [ ] **Step 1: Add the command**

```python
# ─── stage ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--url", default=None,
              help="Source to download: https URL, 'gmail:MSG_ID', or a Drive/Docs URL. "
                   "Mutually exclusive with --text.")
@click.option("--text", default=None,
              help="Inline note text to stage as markdown. Use '-' to read from stdin.")
@click.option("--label", required=True, help="Short label (used in the filename).")
@click.option("--priority", default="secondary",
              type=click.Choice(["primary", "secondary", "background"]),
              help="Resource priority marker.")
@click.option("--ref-id", default=None, help="Task ref_id (organizes files by task).")
def stage(url, text, label, priority, ref_id):
    """Stage a material (download a file or write note text) → openfile:// link.

    Skips live Google-native docs and generic web pages (returns status=skipped);
    keep those as live links in resources instead.
    """
    from letta.stage_resource_tool import stage_resource
    if text == "-":
        text = sys.stdin.read()
    if not url and text is None:
        _emit_json({"status": "error",
                    "error_message": "either --url or --text required"})
        return
    _emit_json(stage_resource(url=url, text=text, label=label,
                              priority=priority, ref_id=ref_id))
```

- [ ] **Step 2: Reinstall the editable CLI**

Run: `pipx reinstall task-cli` (or, if installed from path, `pipx install --force -e /Volumes/main-drive/ai-PA/task-cli`)
Expected: reinstall succeeds; `task stage --help` lists `--url/--text/--label/--priority/--ref-id`.

- [ ] **Step 3: Manual smoke — inline text**

Run:
```bash
echo "Test note body" | task stage --text - --label "Smoke test" --ref-id testref01 | jq
```
Expected: `status:"ok"`, `openfile_url` like `openfile:///Users/dorseyhomeserver/Dropbox/letta-shared-files/staged/notes/testref01/Smoke-test.md`, and the file exists:
```bash
cat ~/Dropbox/letta-shared-files/staged/notes/testref01/Smoke-test.md
```
Expected: `# Smoke test\n\nTest note body`.

- [ ] **Step 4: Manual smoke — skip behavior**

Run: `task stage --url "https://example.com/some-page" --label "Web page" --ref-id testref01 | jq .status`
Expected: `"skipped"` (web page → click-through).

- [ ] **Step 5: Clean up the smoke artifacts and commit**

```bash
rm -rf ~/Dropbox/letta-shared-files/staged/notes/testref01
git add task-cli/src/task_cli/cli.py
git commit -m "feat(work-packet): add 'task stage' subcommand (download + inline-text staging)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Staging unit tests

**Files:**
- Create: `task-cli/tests/test_stage_resource.py`

- [ ] **Step 1: Write failing tests for the text mode + skip + path mapping**

```python
import os
import sys
import importlib.util

import pytest

# Load the tool module directly from the repo (same path the CLI uses).
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location(
    "stage_resource_tool", os.path.join(_REPO, "letta", "stage_resource_tool.py"))
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
stage_resource = _mod.stage_resource


def test_inline_text_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("STAGE_OPENFILE_BASE", str(tmp_path))
    r = stage_resource(text="Body text", label="My Note", ref_id="abc123ef")
    assert r["status"] == "ok"
    assert r["openfile_url"].startswith(f"openfile://{tmp_path}")
    assert r["openfile_url"].endswith("My-Note.md")
    written = r["local_path"]
    assert os.path.exists(written)
    with open(written) as f:
        assert f.read() == "# My Note\n\nBody text"


def test_inline_text_preserves_existing_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("STAGE_OPENFILE_BASE", str(tmp_path))
    r = stage_resource(text="# Already Titled\n\nx", label="L", ref_id="abc123ef")
    with open(r["local_path"]) as f:
        assert f.read() == "# Already Titled\n\nx"


def test_web_page_url_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    r = stage_resource(url="https://example.com/article", label="Page")
    assert r["status"] == "skipped"


def test_requires_url_or_text(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    r = stage_resource(label="L")
    assert r["status"] == "error"


def test_openfile_base_translation(tmp_path, monkeypatch):
    # Simulate container write-path → host openfile-path mapping.
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("STAGE_OPENFILE_BASE", "/HOST/staged")
    r = stage_resource(text="x", label="L", ref_id="r")
    assert r["openfile_url"] == "openfile:///HOST/staged/notes/r/L.md"
```

- [ ] **Step 2: Run — expect failures before Task 3 lands; pass after**

Run: `cd /Volumes/main-drive/ai-PA/task-cli && python -m pytest tests/test_stage_resource.py -v`
Expected (after Task 3 implemented): all 5 pass.

- [ ] **Step 3: Commit**

```bash
git add task-cli/tests/test_stage_resource.py
git commit -m "test(work-packet): stage_resource inline-text + skip + path-mapping tests

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Backtrace — granola fetch + URL harvest from metadata

**Files:**
- Modify: `letta/backtrace_task_tool.py:126-156` (Step 2 fetch), `:182-189` (anchor URL collection)

- [ ] **Step 1: Add `granola:` fetch alongside the existing `gmail:` fetch**

In Step 2 (`if fetch_hint:` block, after the `gmail:` branch closes), add an `elif`:

```python
                elif fetch_hint.startswith("granola:"):
                    mid = fetch_hint.split(":", 1)[1]
                    api_key = os.environ.get("GRANOLA_API_KEY", "")
                    if mid and api_key:
                        try:
                            g_req = urllib.request.Request(
                                f"https://public-api.granola.ai/v1/notes/{mid}?include=transcript",
                                headers={"Authorization": f"Bearer {api_key}",
                                         "Accept": "application/json"},
                            )
                            with urllib.request.urlopen(g_req, timeout=15) as g_resp:
                                note = json.loads(g_resp.read().decode("utf-8"))
                            bits = []
                            if note.get("web_url"):
                                bits.append(note["web_url"])  # harvestable URL
                            if note.get("summary_text") or note.get("summary_markdown"):
                                bits.append(note.get("summary_text") or note.get("summary_markdown"))
                            t = note.get("transcript")
                            if isinstance(t, list):
                                bits.extend(f"{e.get('speaker','')}: {e.get('text','')}"
                                            for e in t[:200] if e.get("text"))
                            elif isinstance(t, str):
                                bits.append(t)
                            full_content = "\n".join(bits)
                        except Exception:
                            pass
```

- [ ] **Step 2: Harvest URLs from `source_metadata` even when absent from body text**

After `all_text` is built (line 158) and before/around the URL `re.findall` (lines 182-189), seed `anchors_urls` from the row's metadata so permalinks always become hop candidates:

```python
        # Seed artifact URLs from source_metadata (permalink / web_url / source_url)
        # so a clean task body without inline links still surfaces the source as a
        # hop candidate.
        for _k in ("permalink", "web_url", "source_url"):
            _v = (smeta or {}).get(_k)
            if _v and _v not in anchors_urls:
                anchors_urls.append(_v)
```

(Place this right after `anchors_urls = []` initialization, before the `urls_found = re.findall(...)` loop, so dedup against body-found URLs works.)

- [ ] **Step 3: Smoke-test backtrace on a meeting task**

Run: `task backtrace <a-meeting-ref> | jq '{content: (.source_content|length), urls: .anchors.urls, hops: .hop_candidates}'`
Expected: `source_content` length > 0 (granola fetch populated it), and `anchors.urls` includes the meeting `web_url`.

- [ ] **Step 4: Commit**

```bash
git add letta/backtrace_task_tool.py
git commit -m "feat(work-packet): backtrace granola fetch + URL harvest from source_metadata

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Renderer — hyperlink every URL per resource line (cross-device dual links)

**Files:**
- Modify: `pa-web-ui/app.py:3354-3375` (Resources rendering block)
- Test: `pa-web-ui/tests/test_work_packet_segments.py`

- [ ] **Step 1: Write the failing renderer tests**

Add to `pa-web-ui/tests/test_work_packet_segments.py`:

```python
def test_resource_line_with_live_and_offline_links_renders_both():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[primary] SOW draft — https://docs.google.com/document/d/X/edit | offline: openfile:///Users/u/Dropbox/letta-shared-files/staged/notes/r/SOW.md (read)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    urls = [s["url"] for s in segs if isinstance(s, dict) and s.get("url")]
    assert "https://docs.google.com/document/d/X/edit" in urls
    assert "openfile:///Users/u/Dropbox/letta-shared-files/staged/notes/r/SOW.md" in urls


def test_offline_link_gets_offline_display_text():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[primary] Notes — openfile:///Users/u/x.md (read)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    offline = [s for s in segs if isinstance(s, dict) and s.get("url", "").startswith("openfile://")]
    assert offline and offline[0]["text"].strip() in ("Open", "Offline copy")


def test_single_https_resource_still_renders_once():
    enrichment = {"packet_info": {"direct_action": "x", "resources": [
        "[secondary] Doc — https://example.com/a (reference)"
    ]}}
    segs = _build_work_packet_segments("ref00001", "", enrichment=enrichment)
    urls = [s["url"] for s in segs if isinstance(s, dict) and s.get("url")]
    assert urls == ["https://example.com/a"]
```

(Ensure the test module imports `_build_work_packet_segments` — the existing tests already do; reuse that import.)

- [ ] **Step 2: Run — expect failures**

Run: `cd /Volumes/main-drive/ai-PA/pa-web-ui && python -m pytest tests/test_work_packet_segments.py -v`
Expected: the two new dual-link tests FAIL (only first URL hyperlinked); the single-URL test passes.

- [ ] **Step 3: Replace the Resources rendering block with multi-URL handling**

Replace lines 3355-3375 (`if pi.get("resources"):` … the `else:` plain-line branch) with:

```python
    # Resources — hyperlink EVERY url on the line so a single resource can carry
    # both a universal cloud link (works on every device) and a device-local
    # staged openfile:// copy (desktop offline). Label renders once; each url
    # becomes its own clickable chip with smart display text.
    if pi.get("resources"):
        segments.append("\n")
        segments.append({"text": "Resources\n", "bold": True, "size": 13})
        for item in pi["resources"]:
            urls = re.findall(r"(openfile://\S+|https?://\S+)", item)
            if urls:
                urls = [u.rstrip(") ").rstrip("|").strip() for u in urls]
                # Label = text before the first url, minus the leading [priority]
                # marker and the trailing em-dash separator.
                first = re.search(r"(openfile://\S+|https?://\S+)", item)
                label = item[:first.start()].strip()
                label = re.sub(r"^\[(primary|secondary|background)\]\s*", "", label)
                label = label.rstrip("—|").strip()
                role_match = re.search(r"\((\w+)\)\s*$", item)
                role = f" ({role_match.group(1)})" if role_match else ""
                segments.append({"text": f"  {label}{role}: ", "size": 11})
                for idx, url in enumerate(urls):
                    if url.startswith("openfile://"):
                        display = "Offline copy"
                    elif "slack.com/archives/" in url:
                        display = "Permalink"
                    else:
                        display = url[:60] + ("..." if len(url) > 60 else "")
                    sep = "" if idx == 0 else "   ·   "
                    if sep:
                        segments.append({"text": sep, "size": 11})
                    segments.append({"text": f"{display}", "url": url,
                                     "underline": True, "size": 11})
                segments.append("\n")
            else:
                for line in _lines(item):
                    segments.append(f"  • {line}\n")
```

- [ ] **Step 4: Run — expect all pass**

Run: `cd /Volumes/main-drive/ai-PA/pa-web-ui && python -m pytest tests/test_work_packet_segments.py -v`
Expected: all tests (existing + 3 new) PASS.

- [ ] **Step 5: Hot-deploy app.py (image is baked; buildkit deferred) and verify health**

```bash
docker cp /Volumes/main-drive/ai-PA/pa-web-ui/app.py ai-pa-pa-web-ui-1:/app/app.py
docker restart ai-pa-pa-web-ui-1
# wait for healthy
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai-pa-pa-web-ui-1)" = "healthy" ]; do sleep 3; done
echo "pa-web-ui healthy"
```

- [ ] **Step 6: Commit**

```bash
git add pa-web-ui/app.py pa-web-ui/tests/test_work_packet_segments.py
git commit -m "feat(work-packet): render dual (live + offline) links per resource line

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: End-to-end validation on a real task

**Files:** none (validation only). Uses the read-only harness `scripts/eval-work-packet.py` from prior work.

- [ ] **Step 1: Pick a fresh task with a rich source (Drive doc or meeting) and re-dispatch enrichment**

Use the scheduler container's importlib path (bypasses the status-claim gate without touching status), as documented in `project_task_eval_loop` memory:

```bash
docker exec ai-pa-scheduler-service-1 python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('es','/app/scripts/enrichment-scanner.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.dispatch_enrichment({'ref_id':'<REF>','source':'<SRC>','source_ref':'<SREF>','raw_description':'<DESC>'}))
"
```

- [ ] **Step 2: Wait for enrichment, then inspect the stored resources**

Run: `task read <REF> | jq '.enrichment.packet_info.resources'`
Expected: a non-empty array with at least the source permalink; for file/note tasks, an `openfile://` segment present alongside the live URL.

- [ ] **Step 3: Re-assemble the OF note and verify on-device**

Trigger the pa-web-ui reassemble endpoint (CSRF handshake required — Origin `http://localhost:5200`, `X-CSRF-Token`, cookie) for `<REF>`, then open the task in OmniFocus and confirm:
- A **Resources** section is present.
- The live link opens the artifact in the browser.
- The "Offline copy" link (if staged) opens the local file via `OpenFileHandler.app`.

- [ ] **Step 4: Confirm the estimate/actuals lines are untouched**

Run: `task read <REF> | jq '{orig: .original_est_minutes, rev: .revised_est_minutes, act: .actual_minutes}'`
Expected: values match pre-run state (resources work did not write any estimate/actual column). The note's `Agent Estimate:` line still renders as a duration string.

- [ ] **Step 5: Record the validation example** in `docs/research/2026-06-15-work-packet-materials-validation.md` (the ref_id, the rendered resources, screenshots/paths) and commit it.

```bash
git add docs/research/2026-06-15-work-packet-materials-validation.md
git commit -m "docs(work-packet): materials/staging end-to-end validation example

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Staging lifecycle + cross-device handler (operational closeout)

**Files:**
- Create: `scripts/prune-staged-materials.sh`
- Create/document: laptop `OpenFileHandler.app` install note in `openfile-handler/README.md`

- [ ] **Step 1: Write the prune script (age-based, safe)**

```bash
#!/usr/bin/env bash
# Prune staged work-packet materials older than N days. Safe: only touches the
# staged tree, never the rest of letta-shared-files.
set -euo pipefail
STAGE_DIR="${STAGE_BASE_DIR:-/Users/dorseyhomeserver/Dropbox/letta-shared-files/staged}"
DAYS="${STAGE_PRUNE_DAYS:-30}"
[ -d "$STAGE_DIR" ] || { echo "no staged dir"; exit 0; }
find "$STAGE_DIR" -type f -mtime +"$DAYS" -print -delete
# Remove now-empty ref_id / category dirs.
find "$STAGE_DIR" -mindepth 1 -type d -empty -delete
```

- [ ] **Step 2: Schedule it (launchd, logs under ~/Library/Logs — never /Volumes)**

Create `~/Library/LaunchAgents/com.ai-pa.prune-staged-materials.plist` running weekly. Per the launchd lesson in memory, set `StandardOutPath`/`StandardErrorPath` under `~/Library/Logs/`, NOT `/Volumes`. Load with `launchctl bootstrap gui/$(id -u) <plist>`.
Expected: `launchctl print gui/$(id -u)/com.ai-pa.prune-staged-materials` shows the job loaded.

- [ ] **Step 3: Document cross-device reality in `openfile-handler/README.md`**

State plainly:
- `openfile://` resolves **only** on a Mac that has `OpenFileHandler.app` installed AND the Dropbox-synced `letta-shared-files` folder present.
- The **home server** has it installed (`~/Applications/OpenFileHandler.app`). To use staged copies on the **laptop**, run `openfile-handler/install.sh` there.
- On **iPhone/iPad**, `openfile://` will not resolve — this is why every resource also carries a universal cloud link. Staged copies are a desktop-offline convenience, never the only access path.

- [ ] **Step 4: Commit**

```bash
git add scripts/prune-staged-materials.sh openfile-handler/README.md
git commit -m "feat(work-packet): staged-materials prune job + cross-device handler docs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Completion

After all tasks: use **superpowers:finishing-a-development-branch** to verify the full suite
(`task-cli` + `pa-web-ui` pytest), confirm the branch is clean, and present merge options.

**Definition of done:** a newly confirmed task whose source is a Drive doc / meeting / email
shows a **Resources** section in its OmniFocus note with (a) a clickable live link that opens
the artifact on any device, and (b) where the material is a file or note text, an "Offline copy"
`openfile://` link that opens the staged local file on the desktop — with the estimate/actuals
eval loop provably untouched.

---

## Self-review notes

- **Spec coverage:** live-URL materials (Tasks 1,2,6), staged-file materials (Tasks 3,4), inline note-text "engage with the text" (Tasks 3,4), three-node backtrace links (Task 6), clickable note surface (Task 7), cross-device robustness (Tasks 7,9), local-mode translation (Tasks 3,4 host-native paths; no Letta-server tools), validation (Task 8). All map to the user's intent.
- **Eval-loop safety:** no task writes `original_est_minutes`/`revised_est_minutes`/`actual_minutes` or the `Agent Estimate:` timer line; Task 8 Step 4 asserts this.
- **Ordering:** Phase 1 (Tasks 1-2) ships value with zero renderer/CLI risk; staging (3-5) and dual rendering (7) are independent and each testable; backtrace (6) deepens but isn't required for first links.
- **Type/naming consistency:** `stage_resource(url, text, label, priority, ref_id)` signature is identical across the tool, CLI, and tests; `STAGE_BASE_DIR`/`STAGE_OPENFILE_BASE` env names used identically in tool + tests; resource line grammar (`[priority] label — url | offline: url (role)`) is identical in prompt, recipe, renderer, and renderer tests.
