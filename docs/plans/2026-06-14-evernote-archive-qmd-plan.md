# Evernote → Markdown + Media → qmd Archive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror Chad's full Evernote library into a local Markdown corpus (every note, with all media preserved as files), indexed as a `qmd` collection so fleet agents recall it on demand — refreshed weekly.

**Architecture:** Three stages, mirroring `bookmark-archiver/`. (1) **Extract** with `evernote-backup` (OAuth, no dev token) → local SQLite DB holding all notes + binary resources. (2) **Convert** with `yarle` → Markdown + `_resources/` media + YAML frontmatter. (3) **Post-process** (small Python pkg `evernote-archiver`) → normalize frontmatter (`type`/`tags`), land files in the qmd collection dir, and **reconcile counts** (yarle silently drops ~10% at scale, so this gate is mandatory). A launchd job runs the whole chain weekly (incremental `sync`, idempotent re-convert).

**Tech Stack:** `evernote-backup` (pipx), `yarle` (npx), Python 3.13 + pytest (post-processor), `qmd` CLI, launchd.

**Decisions already made (do not relitigate):**
- Storage = **qmd collection `evernote`**, NOT the canonical Gitea repo (media would bloat it).
- Corpus root = `~/.letta/reference-archive/raw/evernote/` (parallel to `~/.letta/history-archive/raw/`).
- Refresh = **ongoing**, weekly launchd (a personal note library doesn't need daily).
- The SQLite DB + ENEX are kept as lossless cold backups; Markdown is the derived layer.

---

## File Structure

```
evernote-archiver/                         # new sibling pkg to bookmark-archiver/
├── pyproject.toml                         # pkg metadata; pytest dep
├── yarle-config.json                      # yarle conversion config (committed)
├── run-evernote-archive.sh               # launchd wrapper: sync→export→yarle→post-process→reindex→reconcile
├── evernote_archiver/
│   ├── __init__.py
│   ├── frontmatter.py                     # parse + augment yarle frontmatter (add type/tags/source)
│   ├── organize.py                        # land .md + _resources into the collection dir
│   ├── reconcile.py                       # DB note-count vs output .md count → pass/fail gate
│   └── run.py                             # orchestrate post-process stage (frontmatter→organize→reconcile)
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   └── sample-note.md                 # a yarle-style note (frontmatter + body + media link)
    ├── test_frontmatter.py
    └── test_reconcile.py
```

Corpus + ops (not in repo):
- `~/.letta/reference-archive/raw/evernote/<notebook>/<note>.md` + `_resources/`
- `~/.letta/reference-archive/.state/evernote-archive.json` (last-run metadata)
- `~/Library/LaunchAgents/com.ai-pa.evernote-archive.plist` (NOT git-tracked — per host-ops memory)
- Backups: `~/.letta/reference-archive/.backup/en_backup.db`, `enex_out/`

---

## Phase 0 — Prerequisites (operational)

### Task 0: Tooling + dirs

- [ ] **Step 1: Install the extractor**

Run:
```bash
pipx install evernote-backup
evernote-backup --version    # expect >= 1.13.x
```
Expected: version prints, no error.

- [ ] **Step 2: Verify yarle reachable (no global install needed)**

Run: `npx -y -p yarle-evernote-to-md@latest yarle --version`
Expected: a 6.x version prints.

- [ ] **Step 3: Create corpus + backup dirs**

Run:
```bash
mkdir -p ~/.letta/reference-archive/raw/evernote
mkdir -p ~/.letta/reference-archive/.state ~/.letta/reference-archive/.backup
```
Expected: dirs exist (`ls ~/.letta/reference-archive`).

- [ ] **Step 4: Scaffold the package**

Run:
```bash
mkdir -p /Volumes/main-drive/ai-PA/evernote-archiver/evernote_archiver \
         /Volumes/main-drive/ai-PA/evernote-archiver/tests/fixtures
cd /Volumes/main-drive/ai-PA/evernote-archiver
touch evernote_archiver/__init__.py tests/__init__.py
```

Create `pyproject.toml`:
```toml
[project]
name = "evernote-archiver"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pyyaml>=6"]

[project.optional-dependencies]
test = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["."]
include = ["evernote_archiver*"]
```

- [ ] **Step 5: Commit scaffold**

```bash
cd /Volumes/main-drive/ai-PA
git add evernote-archiver/pyproject.toml evernote-archiver/evernote_archiver/__init__.py evernote-archiver/tests/__init__.py
git commit -m "feat(evernote-archiver): scaffold package"
```

---

## Phase 1 — Extract (operational, one-time auth)

### Task 1: Authenticate + first full sync

> **Auth note:** `evernote-backup` 1.13.1 uses OAuth via browser + 2FA **by default** for the international Evernote backend — **no `--oauth` flag** (that errors) and **no developer token**. `--user`/`--password` are China/Yinxiang-backend only. This is the most fragile step; do it early.

- [ ] **Step 1: Init DB (OAuth is the default)**

Run:
```bash
cd ~/.letta/reference-archive/.backup
evernote-backup init-db          # OAuth browser flow opens automatically
```
Expected: browser opens → log in → enter 2FA code → "Successfully authenticated" and `en_backup.db` created. (Advanced: `--oauth-host`/`--oauth-port` tune the local callback server if needed.)

- [ ] **Step 2: Full sync (all notes + attachments → SQLite)**

Run: `evernote-backup sync`
Expected: progress over notebooks; ends with a note count. **Record that count** — it's the reconciliation baseline.

- [ ] **Step 3: Capture the authoritative note count**

Run:
```bash
sqlite3 ~/.letta/reference-archive/.backup/en_backup.db \
  "SELECT count(*) FROM notes WHERE is_active = 1;"
```
Expected: an integer N (active, non-trashed notes). Save N for Task 4.

---

## Phase 2 — Convert (ENEX → Markdown + media)

### Task 2: Export ENEX + configure yarle

- [ ] **Step 1: Export to ENEX**

Run:
```bash
cd ~/.letta/reference-archive/.backup
evernote-backup export ./enex_out/
```
Expected: one `.enex` per notebook in `enex_out/`, attachments base64-embedded.

- [ ] **Step 2: Write `yarle-config.json`** (committed)

Create `/Volumes/main-drive/ai-PA/evernote-archiver/yarle-config.json`:
```json
{
  "enexSources": ["/Users/dorseyhomeserver/.letta/reference-archive/.backup/enex_out"],
  "outputDir": "/Users/dorseyhomeserver/.letta/reference-archive/raw/evernote",
  "outputFormat": "ObsidianMD",
  "isMetadataNeeded": true,
  "isNotebookNameNeeded": true,
  "isZettelkastenNeeded": false,
  "useZettelIdAsFilename": false,
  "plainTextNotesOnly": false,
  "skipWebClips": false,
  "useHashTags": true,
  "nestedTags": { "separatorInEN": "_", "replaceSeparatorWith": "/", "replaceSpaceWith": "-" },
  "resources": "_resources",
  "turndownOptions": { "headingStyle": "atx", "codeBlockStyle": "fenced" }
}
```
Rationale: ObsidianMD → `[[wikilinks]]` (matches canonical convention); `isMetadataNeeded` emits frontmatter with created/updated/tags/source-URL; `_resources` holds media beside notes.

- [ ] **Step 3: Run the conversion**

Run:
```bash
npx -y -p yarle-evernote-to-md@latest yarle \
  --configFile /Volumes/main-drive/ai-PA/evernote-archiver/yarle-config.json
```
Expected: notes written under `~/.letta/reference-archive/raw/evernote/<notebook>/`, media under `_resources/`.

- [ ] **Step 4: Commit the yarle config**

```bash
cd /Volumes/main-drive/ai-PA
git add evernote-archiver/yarle-config.json
git commit -m "feat(evernote-archiver): yarle conversion config"
```

---

## Phase 3 — Post-process (frontmatter normalization + reconcile)

### Task 3: Frontmatter augmentation

**Files:**
- Create: `evernote-archiver/evernote_archiver/frontmatter.py`
- Create: `evernote-archiver/tests/fixtures/sample-note.md`
- Test: `evernote-archiver/tests/test_frontmatter.py`

- [ ] **Step 1: Write the fixture** (`tests/fixtures/sample-note.md`)

```markdown
---
title: Espresso dialing-in notes
created: 2021-03-04T10:00:00Z
updated: 2022-08-01T12:30:00Z
tags: [coffee, gear]
source-url: https://example.com/espresso
notebook: Kitchen
---

# Espresso dialing-in notes

Grind finer if the shot runs fast. ![photo](_resources/shot.jpg)
```

- [ ] **Step 2: Write the failing test** (`tests/test_frontmatter.py`)

```python
from pathlib import Path
from evernote_archiver.frontmatter import augment_frontmatter

FIX = Path(__file__).parent / "fixtures" / "sample-note.md"


def test_augment_adds_type_and_preserves_fields():
    out = augment_frontmatter(FIX.read_text())
    fm, body = _split(out)
    assert fm["type"] == "evernote-note"          # OKF-style discriminator added
    assert fm["tags"] == ["coffee", "gear"]        # existing tags preserved
    assert fm["title"] == "Espresso dialing-in notes"
    assert fm["source"] == "evernote"              # provenance stamp
    assert "Grind finer" in body                   # body untouched


def test_augment_is_idempotent():
    once = augment_frontmatter(FIX.read_text())
    twice = augment_frontmatter(once)
    assert once == twice


def _split(text):
    import yaml
    _, fm_raw, body = text.split("---", 2)
    return yaml.safe_load(fm_raw), body
```

- [ ] **Step 3: Run it — expect failure**

Run: `cd /Volumes/main-drive/ai-PA/evernote-archiver && python -m pytest tests/test_frontmatter.py -q`
Expected: FAIL (`ModuleNotFoundError: evernote_archiver.frontmatter`).

- [ ] **Step 4: Implement** (`evernote_archiver/frontmatter.py`)

```python
"""Normalize yarle-emitted frontmatter for the qmd evernote corpus."""
import yaml

TYPE = "evernote-note"
SOURCE = "evernote"


def augment_frontmatter(text: str) -> str:
    """Add type/source discriminators without disturbing existing fields or body.

    Idempotent: re-running yields identical output (safe for weekly re-convert).
    Tolerates notes that have no frontmatter (yarle still emits it, but be safe).
    """
    if text.startswith("---"):
        _, fm_raw, body = text.split("---", 2)
        fm = yaml.safe_load(fm_raw) or {}
    else:
        fm, body = {}, "\n" + text
    fm["type"] = TYPE
    fm["source"] = SOURCE
    fm.setdefault("tags", [])
    new_fm = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{new_fm}\n---{body}"
```

- [ ] **Step 5: Run — expect pass**

Run: `python -m pytest tests/test_frontmatter.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add evernote-archiver/evernote_archiver/frontmatter.py evernote-archiver/tests/test_frontmatter.py evernote-archiver/tests/fixtures/sample-note.md
git commit -m "feat(evernote-archiver): frontmatter augmentation (type/source, idempotent)"
```

### Task 4: Reconciliation gate

**Files:**
- Create: `evernote-archiver/evernote_archiver/reconcile.py`
- Test: `evernote-archiver/tests/test_reconcile.py`

- [ ] **Step 1: Write the failing test** (`tests/test_reconcile.py`)

```python
from evernote_archiver.reconcile import reconcile


def test_pass_when_within_tolerance():
    r = reconcile(db_count=1000, md_count=995, tolerance=0.02)
    assert r["ok"] is True
    assert r["missing"] == 5


def test_fail_when_drop_exceeds_tolerance():
    r = reconcile(db_count=1000, md_count=870, tolerance=0.02)
    assert r["ok"] is False
    assert r["missing"] == 130
```

- [ ] **Step 2: Run — expect failure**

Run: `python -m pytest tests/test_reconcile.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement** (`evernote_archiver/reconcile.py`)

```python
"""Reconcile SQLite note count vs converted .md count (yarle silent-drop guard)."""
from pathlib import Path


def count_md(corpus_dir: str) -> int:
    """Count .md files in the corpus, excluding yarle index/meta files."""
    root = Path(corpus_dir)
    return sum(
        1 for p in root.rglob("*.md")
        if "_resources" not in p.parts and p.name.lower() not in {"index.md", "log.md"}
    )


def reconcile(db_count: int, md_count: int, tolerance: float = 0.02) -> dict:
    """ok=True iff missing/db_count <= tolerance. Returns details for logging."""
    missing = db_count - md_count
    frac = (missing / db_count) if db_count else 0.0
    return {"ok": frac <= tolerance, "db_count": db_count,
            "md_count": md_count, "missing": missing, "fraction": round(frac, 4)}
```

- [ ] **Step 4: Run — expect pass**

Run: `python -m pytest tests/test_reconcile.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add evernote-archiver/evernote_archiver/reconcile.py evernote-archiver/tests/test_reconcile.py
git commit -m "feat(evernote-archiver): reconciliation gate vs SQLite count"
```

### Task 5: Orchestrator (post-process stage)

**Files:**
- Create: `evernote-archiver/evernote_archiver/run.py`

- [ ] **Step 1: Implement** (`evernote_archiver/run.py`) — applies frontmatter to every note in the corpus, then reconciles.

```python
"""Post-process the yarle output corpus in place: augment frontmatter, reconcile."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .frontmatter import augment_frontmatter
from .reconcile import count_md, reconcile


def _db_active_count(db_path: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT count(*) FROM notes WHERE is_active = 1").fetchone()[0]
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    touched = 0
    for md in corpus.rglob("*.md"):
        if "_resources" in md.parts or md.name.lower() in {"index.md", "log.md"}:
            continue
        original = md.read_text(encoding="utf-8")
        updated = augment_frontmatter(original)
        if updated != original:
            md.write_text(updated, encoding="utf-8")
            touched += 1

    rec = reconcile(_db_active_count(args.db), count_md(str(corpus)), args.tolerance)
    Path(args.state).write_text(json.dumps({"reconcile": rec, "frontmatter_touched": touched}, indent=2))
    print(json.dumps(rec, indent=2))
    if not rec["ok"]:
        print(f"RECONCILE FAILED: {rec['missing']} notes missing "
              f"({rec['fraction']:.1%}) — investigate before trusting the corpus", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run against the real corpus**

Run:
```bash
cd /Volumes/main-drive/ai-PA/evernote-archiver
python -m evernote_archiver.run \
  --corpus ~/.letta/reference-archive/raw/evernote \
  --db ~/.letta/reference-archive/.backup/en_backup.db \
  --state ~/.letta/reference-archive/.state/evernote-archive.json
```
Expected: JSON with `"ok": true`; if false, STOP and investigate (compare notebook-by-notebook before proceeding).

- [ ] **Step 3: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add evernote-archiver/evernote_archiver/run.py
git commit -m "feat(evernote-archiver): post-process orchestrator (frontmatter + reconcile gate)"
```

---

## Phase 4 — Index (qmd collection)

### Task 6: Register + verify the collection

- [ ] **Step 1: Add the collection**

Run:
```bash
qmd collection add evernote ~/.letta/reference-archive/raw/evernote
qmd collection list
```
Expected: `evernote` appears in the list.

- [ ] **Step 2: Verify retrieval**

Run: `qmd query "espresso dialing in" --collection evernote` (substitute a topic you know is in your notes)
Expected: relevant note(s) returned with `#docid`; `qmd get <file>` shows the note with frontmatter.

- [ ] **Step 3: Spot-check media links resolve**

Run: pick a note with an image, confirm its `_resources/...` path exists on disk next to the note.
Expected: media file present.

---

## Phase 5 — Ongoing refresh (weekly launchd)

### Task 7: Wrapper script

**Files:**
- Create: `evernote-archiver/run-evernote-archive.sh`

- [ ] **Step 1: Implement** (`run-evernote-archive.sh`)

```bash
#!/usr/bin/env bash
# Weekly: incremental sync -> re-export -> re-convert (idempotent) -> post-process -> reindex.
set -euo pipefail
BK="$HOME/.letta/reference-archive/.backup"
CORPUS="$HOME/.letta/reference-archive/raw/evernote"
STATE="$HOME/.letta/reference-archive/.state/evernote-archive.json"
CFG="/Volumes/main-drive/ai-PA/evernote-archiver/yarle-config.json"
PKG="/Volumes/main-drive/ai-PA/evernote-archiver"

cd "$BK"
evernote-backup sync                      # incremental; refreshes en_backup.db
rm -rf enex_out && evernote-backup export ./enex_out/
rm -rf "$CORPUS" && mkdir -p "$CORPUS"    # clean re-convert (idempotent, avoids orphans)
npx -y -p yarle-evernote-to-md@latest yarle --configFile "$CFG"

cd "$PKG"
python -m evernote_archiver.run --corpus "$CORPUS" --db "$BK/en_backup.db" --state "$STATE"
# run.py exits non-zero on reconcile failure -> launchd logs it; corpus already written for inspection

qmd collection reindex evernote 2>/dev/null || qmd collection add evernote "$CORPUS"
echo "evernote-archive done: $(date)"
```

- [ ] **Step 2: Make executable + smoke test**

Run:
```bash
chmod +x /Volumes/main-drive/ai-PA/evernote-archiver/run-evernote-archive.sh
/Volumes/main-drive/ai-PA/evernote-archiver/run-evernote-archive.sh
```
Expected: completes, reconcile ok, "evernote-archive done".

- [ ] **Step 3: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add evernote-archiver/run-evernote-archive.sh
git commit -m "feat(evernote-archiver): weekly refresh wrapper"
```

### Task 8: launchd job (operational — NOT git-tracked)

> **Host-ops rules (memory):** logs must NOT live on `/Volumes` (EX_CONFIG/78 at spawn) → use `~/Library/Logs`. Plists aren't git-tracked. Runner env is minimal — the wrapper hard-codes paths and relies on PATH having `/opt/homebrew/bin` (npx, qmd) — confirm.

- [ ] **Step 1: Create** `~/Library/LaunchAgents/com.ai-pa.evernote-archive.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ai-pa.evernote-archive</string>
  <key>ProgramArguments</key>
  <array><string>/Volumes/main-drive/ai-PA/evernote-archiver/run-evernote-archive.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>4</integer><key>Minute</key><integer>0</integer></dict>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StandardOutPath</key><string>/Users/dorseyhomeserver/Library/Logs/evernote-archive/stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/dorseyhomeserver/Library/Logs/evernote-archive/stderr.log</string>
</dict></plist>
```

- [ ] **Step 2: Load + verify**

Run:
```bash
mkdir -p ~/Library/Logs/evernote-archive
launchctl unload ~/Library/LaunchAgents/com.ai-pa.evernote-archive.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ai-pa.evernote-archive.plist
launchctl list | grep evernote-archive
```
Expected: job listed.

---

## Phase 6 — Agent recall

### Task 9: Teach agents the collection

**Files:**
- Create (memfs, MC): `.../agent-local-8474bbbd-.../memory/system/reference_recall.md`

- [ ] **Step 1: Write `reference_recall.md`** (mirrors `historical_recall.md` shape)

```markdown
---
description: |
  How to recall Chad's personal reference corpora (Evernote, later NYT) via qmd.
  Stable instructional content. Collections live in ~/.letta/reference-archive/raw/.
type: policy
---

# Reference recall (personal corpora)

Beyond conversation history, you can search Chad's personal reference archives with `qmd`.
These are NOT in context — search on demand, same find→get→answer loop as historical recall.

## Collections
- `evernote` — Chad's full Evernote library (notes + media), frontmatter `type: evernote-note`.

## When to reach for it
- Chad references something he "wrote down", "saved in Evernote", a recipe/spec/checklist/trip note.
- A question needs durable personal knowledge not in canonical reference/ and not live state.

## How
    qmd query "<topic>" --collection evernote
    qmd get <file>            # full note incl. frontmatter (tags/notebook/dates)
Media sits in `_resources/` beside each note. Cite the note title when you use it.
```

- [ ] **Step 2: Commit + push to MC's Gitea repo**

```bash
cd ~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory
git add system/reference_recall.md
git -c user.name="Chad Dorsey" -c user.email="cdorsey@concord.org" \
  commit -m "recipe: reference recall (evernote qmd collection)"
git push gitea HEAD
```

---

## Self-Review

- **Spec coverage:** all-media-preserved (yarle `_resources` + media spot-check Task 6.3) ✓; Markdown + readable/indexable (yarle MD + frontmatter + qmd Tasks 3,6) ✓; full library (evernote-backup sync, Task 1) ✓; ongoing refresh (Tasks 7-8) ✓; agent access (Task 9) ✓.
- **Reconciliation** (Task 4/5) directly addresses the yarle silent-drop risk surfaced in research.
- **Open items to confirm during execution:** (a) Evernote login is not SSO-only (test Task 1 early); (b) library scale — if > ~10k notes, expect a longer first sync + heavier weekly job (consider monthly); (c) `qmd collection reindex` is the correct subcommand on the installed qmd version (Task 7 falls back to re-`add`).
```
