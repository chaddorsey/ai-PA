---
date: 2026-05-30
status: backlog
priority: post-migration
triggered_by: docs/followups/2026-05-30-letta-code-tui-latency.md
---

# ai-PA directory bloat audit

## Why

During Docs migration TUI latency investigation, discovered that launching
`letta --backend local` from `/Volumes/main-drive/ai-PA` causes severe
typing lag (multiple seconds per keystroke). Root cause: letta-code's
project skill discovery walks the cwd tree on startup. The ai-PA tree has:

- **2,687** tracked files
- **243,204** total files (incl. untracked, build artifacts, virtualenvs,
  node_modules, etc.)

That ~90× ratio of total-to-tracked files indicates massive in-tree bloat
that's invisible to git but real to any tool that walks the directory.

External SSD itself is fine — stat timings are identical to internal SSD
(3.6-3.8 ms each across both). The bottleneck is sheer file count, not
storage media.

## Scope

After all 6 fleet agents have migrated to local mode and soaked
successfully, do a pass on ai-PA to identify and remove:

1. **Build artifacts**: `node_modules/`, `__pycache__/`, `.pytest_cache/`,
   `dist/`, `build/`, `target/` — many should be `.gitignore`'d already
   but may still be on disk in old subdirs.
2. **Virtualenvs**: `venv/`, `.venv/`, `env/`, `.env/` (the directory, not
   the file) at various levels. Particularly the `letta/env` venv known to
   bloat.
3. **Letta sandbox dirs**: `.letta/`, `letta-code/.letta/`, etc. — should
   be `.gitignore`'d but may have accumulated.
4. **Test outputs**: `playwright-report/`, `screenshots/`, `coverage/`,
   `*.png` / `*.jpg` left behind from manual testing.
5. **Backup tarballs / migration extracts**: `memfs-extract/`,
   `*.tar.gz`, `*-backup-*/` directories that should have moved to
   `/Volumes/main-filestore/ai-PA-backups/`.
6. **Old experiments / dead code**: `letta-code-patched/`, `letta-code/`,
   `lteams/`, `doi-ref-cli/`, etc. that appear in `git status` untracked
   list but may no longer be active.
7. **Symlinks pointing at gigantic external trees** (if any) — would
   make `find` traverse far beyond expected scope.

## Proposed approach

1. Audit phase (read-only):
   ```bash
   # Top 20 largest dirs by file count
   find /Volumes/main-drive/ai-PA -type d -not -path '*/.git/*' \
     | while read d; do
       echo "$(find "$d" -maxdepth 1 -type f 2>/dev/null | wc -l)  $d"
     done | sort -rn | head -20
   ```

2. Categorize the top offenders: gitignored-but-still-on-disk vs
   genuinely tracked but bloated.

3. For each bloat source:
   - If gitignored: remove from disk, no commit needed.
   - If tracked but obsolete: `git rm -r`, commit.
   - If experimental but worth keeping: move to a sibling dir outside
     ai-PA (e.g. `/Volumes/main-drive/ai-PA-experiments/`).

4. Verify by re-running letta-code from ai-PA after cleanup — typing
   should be snappy. If it isn't, the file count still isn't the cause
   and we need to look elsewhere.

## Out of scope until migration completes

This audit changes the working environment in ways that could destabilize
in-flight migrations. Defer until all 6 agents (Docs, Calendar, Tasks,
Email, Pulse, MC) are migrated and soaked. After that, this becomes a
~1-day-of-attention housekeeping task.

## Workaround in the meantime

Launch letta-code from a small dedicated dir (e.g. `~/letta-cwd` or
`/Volumes/main-drive/letta-launchpad`) via per-agent wrapper scripts. The
agent's Bash / Read / Edit tools all use absolute paths, so the agent can
still operate on ai-PA files; only the cwd for the letta process itself
needs to be small. See
[docs/followups/2026-05-30-multi-agent-tui-workflow.md] for the wrapper
script pattern and broader multi-agent setup.
