# Phase 2 build brief — laptop spoke #1 (post-spike)

**From:** server Claude (coordinator). **To:** laptop Claude. **Date:** 2026-06-23.
**Status:** Phase 0 ✅, Phase 1 spikes ✅ (merged `867ddb1a`). HUB-confirmed: canonical Gitea `main` = `560f81d` (untouched by Spike A); Letta API `:8283` up (HTTP 200).

## Spike verdicts (settled)
- **A** — distinct agent ⇒ **clone** the canonical lineage at `memfs/<id>/memory` (not `MEMORY_DIR`; not symlink).
- **B** — mod API verified, proof mod loads clean. **Open:** the model-swap trigger (see below).
- **C** — fleet-from-spoke (online) = Letta API `:8283` + the existing `LETTA_API_KEY`; offline = outbox→drainer. No new creds.

## Design decisions (resolved — flag if you disagree)
1. **Mini-me clone source + branch.** Clone canonical from the **Gitea URL** (`http://<token>@127.0.0.1:3030/agents/agent-local-8474bbbd-….git`), NOT the local path, so folds reach canonical. Use a **per-spoke branch `spoke/laptop`** off `main` — NOT `travel/laptop` (the legacy same-id memfs owns that branch on the remote; a distinct mini-me sharing it would collide). Per-spoke branches generalize to `spoke/glasses`.
2. **sync-runner parameterization.** `sync-runner.sh` currently folds `travel/laptop:main`. Add a branch param (env `SPOKE_BRANCH`, default `travel/laptop` for back-compat) so the mini-me folds `spoke/laptop:main`. Minimal, back-compatible change.
3. **`capable` rule (Task 7).** `capable=True` iff the action is performable via the Letta API `:8283` with `LETTA_API_KEY` while online; otherwise `queue`.

## Nail this FIRST — the model-swap mechanism (Task 6, Step 0)
The mod can detect link + render statusline + register commands, but `letta.setModel` is **not** on the mod API; model changes are an `update_model` WsProtocol command applied at the runtime layer. Resolve in this order, **before building the rest of the mod**:
- **Try mod-internal:** can the mod issue `update_model` via `letta.client` / `getClient()` (or a command `run` return)? If yes → the mod swaps directly. Smallest, cleanest. Record the exact call.
- **Fallback (known-good):** a tiny external watcher (`scripts/offline/model-swap-watcher.mjs`) that reads `~/.letta/offline-bus/mode.json` and issues `update_model` to the local runtime via the app-server WS (`letta --backend local app-server --listen ws://127.0.0.1:4500`, then a `runtime`/`update_model` frame — Ezra's documented path). The mod stays observability-only.
Either ships the spine. Decide by the test, record which in the findings, then build Task 6 accordingly.

## Build sequence (Tasks 4–8 — you implement, I review + HUB-confirm)
- **T4 presence-lease** — pure Python (`letta/offline/lease.py` + pytest) + `lease-heartbeat.sh`. Plan has the exact code; get pytest green.
- **T5 mini-me agent** — Spike-A recipe + decisions 1–2 (Gitea-URL clone, `spoke/laptop` branch, `message_buffer_autoclear:false`). Verify it reads canonical `system/`+`reference/` and a write folds `spoke/laptop→main` (**HUB-confirm with me** — I watch Gitea `main` advance).
- **T6 connectivity mod** — resolve the swap mechanism (above) first, then wire detect→swap + write `mode.json` + statusline. Validate **interactively**: statusline flips on `force-offline` within a tick, and the next turn actually runs on the swapped model.
- **T7 action routing** — pure Python (`routing.py` + pytest), the `capable` rule (decision 3); document the wiring rule (route → outbox `Envelope` for queue, or `:8283` call for direct).
- **T8 reconnect wiring** — on the online transition, run `sync-runner.sh` with `SPOKE_BRANCH=spoke/laptop`; **HUB-confirm** the fold reaches Gitea + the drainer runs exactly-once.

## HUB touchpoints (ping Chad → me)
- T5/T8 folds: I verify Gitea `main` advances with your spoke writes.
- T7 live `:8283` call + T8 drain: the **live mutating call is a real world-action — do it under coordination**, not solo; I confirm exactly-once server-side.

## Protocol
- `git pull origin fix/pulse-analytics-briefing-local-2026-06-07` FIRST (gets this brief). **Rebase `laptop-spoke-work` onto the new tip** before continuing.
- Push to `laptop-spoke-work`; ping Chad with the commit hash + one line per task + any blockers.
- **Stop-and-ask** if the swap mechanism resists both paths, or any fold hits a conflict.
