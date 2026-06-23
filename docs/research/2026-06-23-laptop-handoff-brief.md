# Handoff brief — laptop Claude: Phase 1 spikes (MC hub-and-spoke spoke #1)

**From:** the server-side Claude (coordinator). **To:** the laptop Claude on `cd-macbook` (implementer).
**Date:** 2026-06-23. **Bus:** git `origin` (github.com/chaddorsey/ai-PA), branch `fix/pulse-analytics-briefing-local-2026-06-07`.

## Start here
1. `cd ~/ai-PA && git pull origin fix/pulse-analytics-briefing-local-2026-06-07` (gets the spec, plan, Phase-0 runbook, this brief).
2. Read, in order: `docs/plans/2026-06-23-mc-hub-and-spoke-design.md` (the spec) and `docs/plans/2026-06-23-mc-hub-and-spoke-laptop-spoke-plan.md` (the plan). **Phase 0 is DONE** (commit `019687cb`); you start at **Phase 1 (Tasks 1–3, the spikes)**.

## Your job: the three spikes — produce verified facts, not implementation
Write each finding to `docs/research/2026-06-23-spike-findings.md` (§A/B/C). These gate the build, so be concrete and copy-pasteable.

- **Spike A — distinct agent + shared canonical memfs.** How does a *distinct* agent ID use the **hub MC's** canonical memfs lineage (`agents/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d.git`) as its memory, instead of getting its own per-agent memfs? Read `src/backend/local/paths.ts` + `local-store.ts` in the installed letta-code (find via `npm root -g @letta-ai/letta-code` or the Homebrew cellar). Try the lowest-risk mount (symlink, or a shared clone of that repo) on a **throwaway** agent; confirm it reads canonical `system/`+`reference/`, that a write lands on canonical, and that `sync-runner.sh` folds it. Record the exact recipe; delete the throwaway.
- **Spike B — connectivity-failover mod API.** Establish the hooks for (a) a timer/turn event, (b) `update_model`, (c) a statusline value. Read `src/mods/types.ts`, `src/mods/mod-engine.ts`, `src/skills/builtin/creating-mods/references/`; use the in-harness `creating-mods` skill. Build a minimal proof mod under `scripts/offline/mods/connectivity-failover/` that reads `~/.letta/offline-bus/link.json` → statusline, then swaps the model via `update_model` on a manual command. Install to `~/.letta/mods/connectivity-failover/`, validate, commit the proof mod.
- **Spike C — fleet auth from a spoke.** Confirm a laptop caller can invoke ONE fleet service over Tailscale (e.g. enqueue to `pa_web.task_queue`). Record the endpoint + laptop-side auth, or the gap.

## Gotchas you can't get from the repo (from the server's project memory — these will bite you otherwise)
1. **Launch env matters.** Launch the local agent from a **launchpad dir, NOT the memfs** (CWD=memfs dumps a `.letta/` cache into the memory repo and trips the git guard). Set `LETTA_LOCAL_BACKEND_DIR=$HOME/.letta/lc-local-backend` **and** `MEMORY_DIR=$LETTA_LOCAL_BACKEND_DIR/memfs/<agentId>/memory` — without `MEMORY_DIR`, the agent's `$MEMORY_DIR` paths don't resolve and it flails/confabulates. (A working `~/bin/letta-mc` wrapper pattern was built this session — reuse it.)
2. **memfs git guard:** memory tools refuse to run if the memfs working tree is dirty. Keep it clean. `.letta/` is gitignored in the memfs.
3. **`message_buffer_autoclear: false` is REQUIRED** on memfs-enabled agents (default `true` breaks pending-approval state). Set it on the mini-me before use (Task 5, but note it for Spike A's throwaway).
4. **Model config = a JSON edit** of `~/.letta/lc-local-backend/agents/<base64-agentId>.json` (`model` + `model_settings`), with a `.bak` first. **NOT** `mc-model-manager.sh` (that targets the old Docker Letta server API).
5. **Local brains:** `GLM-4.5-Air` via **oMLX** is the validated daily driver. `ollama` also has `qwen2.5:7b-instruct` (too weak — mangles filenames) + `0.5b` (placeholder). Use GLM for anything real.
6. **Remote names differ:** laptop memfs remote = `origin`; hub memfs remote = `gitea`. Laptop `~/ai-PA` remote = `origin` (GitHub). The canonical memfs `main` is `560f81d`; laptop `travel/laptop` is `9b1954c` (= `560f81d` + an unfolded `.gitignore` commit — don't be confused by it).
7. **Reused substrate exists — do NOT rebuild:** `conn-probe.sh` (writes `~/.letta/offline-bus/link.json`; `force-offline` flag simulates drops), `sync-runner.sh`, `letta/offline/{envelope,outbox,drainer}.py`, the hub-side drainer + `mc-quiesce/resume`.
8. **Repo hygiene:** NEVER `git add -A` (3000+ untracked files) — stage specific files. Do **not** touch the 13 pre-existing modified tracked files (fox-cam, frigate, slackbot/chad_mention_signal, smaug-data, .gitignore). Work on this branch, not `main`.

## Protocol back to the server Claude
- **Pull --rebase before you push.** You're the sole implementer on this branch for the laptop work; the server Claude only reads/coordinates while you work.
- Spikes are **read-only investigation + a throwaway/proof** — no irreversible world actions.
- **Stop and ask (don't thrash)** if a mechanism doesn't exist or needs upstream Letta changes — record the finding and surface options.
- **Anything needing HUB-side confirmation** (did a write fold to Gitea `main`? does the drainer run exactly-once?) — note it in the findings and tell Chad; the server Claude verifies from the server.
- **When Phase 1 is done:** push, then tell Chad: the commit hash + one line per spike (A/B/C result) + any blockers. Chad relays to the server Claude, who reviews and writes the Phase-2 brief.
