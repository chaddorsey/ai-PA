# Phase 0 — memfs alignment (hub→Gitea, laptop rebased)

**Date:** 2026-06-23 · **Task:** 0 of `docs/plans/2026-06-23-mc-hub-and-spoke-laptop-spoke-plan.md` · **Status:** ✅ complete

**Why:** the hub's local memfs was ahead of Gitea `main` by one unpushed commit; the laptop sat on the old canonical. Aligned before building spoke #1 against shared memory.

## Before
- Hub local memfs (`~/.letta/lc-local-backend/memfs/agent-local-8474bbbd…/memory`, branch `main`): **`560f81d`** ("fix(reflection): preserve Concord scheduling corrections"), clean tree. Remote name on hub = **`gitea`**.
- Gitea `main` (authoritative): **`248ba046`** (2026-06-19).
- Laptop memfs (`travel/laptop`): based on `248ba04` + trial-era commits (the `.letta/` gitignore). Remote name on laptop = **`origin`**.
- Ancestry check: `248ba046` is an ancestor of `560f81d` → push is a clean fast-forward (1 commit).

## Actions
1. **[HUB]** `~/bin/mc-quiesce.sh` → agent node (pid 1201) `SIGSTOP`'d (state `T`). Single-writer.
2. **[HUB]** `git -C <hub memfs> push gitea HEAD:main` → `248ba04..560f81d  HEAD -> main` (clean ff).
3. **[HUB]** `~/bin/mc-resume.sh` → node 1201 running again. (Resumed **immediately after the push**, deviating from the plan's "resume after laptop step", to keep the freeze window to seconds; correctness identical since the laptop rebases onto current `origin/main` regardless.)
4. **[LAPTOP]** `git fetch origin && git rebase origin/main` → "Successfully rebased and updated refs/heads/travel/laptop"; no conflicts.

## After (verified)
- Gitea / hub `main` = **`560f81d`**.
- Laptop `origin/main` = **`560f81d`** → **aligned with hub** ✅ (Task 0 acceptance: laptop `origin/main` == hub `main`).
- Laptop `travel/laptop` = **`9b1954c`** = `560f81d` + the laptop-only `.letta/` gitignore commit (not yet folded to `main`; harmless, folds via `sync-runner.sh` later).
- Hub MC running normally; automation/fleet untouched throughout.

## Notes for downstream tasks
- **Remote-name asymmetry:** hub memfs remote = `gitea`; laptop memfs remote = `origin`. Use the right name per machine.
- Nothing now blocks the Phase 1 spikes (all `[LAPTOP]`).
