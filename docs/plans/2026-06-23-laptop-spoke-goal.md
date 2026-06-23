# /goal — Laptop Spoke #1 (MC Hub-and-Spoke Failover Spine)

> Goal artifact for the laptop (`cd-macbook`) implementer, derived from
> `docs/research/2026-06-23-laptop-handoff-brief.md`,
> `docs/plans/2026-06-23-mc-hub-and-spoke-design.md`, and
> `docs/plans/2026-06-23-mc-hub-and-spoke-laptop-spoke-plan.md`.
> **Scope decision:** the goal spans the full spine; **this session's executable scope is Phase 1 (the three spikes)**, with a hard server-review gate before Phase 2 (per the brief).

## Goal (what the full implementation achieves)
Make `cd-macbook` a self-contained Kinara **spoke**: a distinct laptop agent that shares the hub's canonical memfs lineage, runs on a local brain (GLM-4.5-Air via oMLX) when the hub is unreachable and the cloud brain when online, swaps **automatically** (no manual mode flip), and reconciles on reconnect — memory folds and offline-queued actions drain exactly-once — while hub automation runs undisturbed. *Architect for the practicalities (a fleet of distinct agents over one canonical memory); design for the feel ("one Kinara").*

## This session's self-contained scope — Phase 1: the three spikes
Resolve the three gating unknowns into **verified, copy-pasteable facts** in `docs/research/2026-06-23-spike-findings.md` (§A/B/C). No production build; investigation + one throwaway agent + one proof mod only.

- **Spike A — distinct agent + shared canonical memfs:** find letta-code's mechanism (read `src/backend/local/paths.ts`, `local-store.ts`) for a *distinct* agent ID to use the hub MC's canonical memfs lineage; prove the lowest-risk mount (symlink/shared-clone) on a **throwaway** agent — reads canonical `system/`+`reference/`, a write lands on canonical, `sync-runner.sh` folds it; record the recipe; **delete the throwaway**.
- **Spike B — connectivity-failover mod API:** establish hooks for a timer/turn event, `update_model`, and a statusline value (read `src/mods/types.ts`, `mod-engine.ts`, the `creating-mods` references/skill); build a minimal **proof mod** at `scripts/offline/mods/connectivity-failover/` that reads `~/.letta/offline-bus/link.json` → statusline and swaps the model on a manual command; install, validate, commit it.
- **Spike C — fleet auth from a spoke:** confirm a laptop caller can invoke **one** fleet service over Tailscale (e.g. enqueue to `pa_web.task_queue`); record endpoint + laptop-side auth, or the gap.

## Boundaries

**In scope (this session):** read-only source investigation; one throwaway agent (deleted after Spike A); one committed proof mod; the spike-findings doc; pushing the branch.

**Explicitly out of scope (gated behind the server's Phase-2 brief):** the production mini-me setup script (Task 5), the real failover mod (Task 6), lease/routing logic (Tasks 4/7), reconnect choreography (Task 8), and Phase-3 acceptance (Task 9). The goal *covers* these; this session does **not** build them.

**Hard constraints (inherited):**
- Reuse the existing substrate (`conn-probe.sh`, `sync-runner.sh`, `letta/offline/{envelope,outbox,drainer}.py`, server drainer, `mc-quiesce/resume`) — **no new DB, no new transport, no rebuilds**.
- Spikes are **read-only investigation + throwaway/proof — no irreversible world actions**.
- Repo hygiene: **never `git add -A`** (3000+ untracked); stage specific files; **do not touch the 13 pre-existing modified tracked files** (fox-cam, frigate, slackbot/chad_mention_signal, smaug-data, .gitignore); work on `fix/pulse-analytics-briefing-local-2026-06-07`, **not `main`**; **`git pull --rebase` before push**.
- Agent-launch correctness: launch from a launchpad dir (not the memfs), set `LETTA_LOCAL_BACKEND_DIR` **and** `MEMORY_DIR` (reuse the `~/bin/letta-mc` pattern); keep the memfs working tree clean (git guard); set `message_buffer_autoclear: false` on the throwaway memfs agent.
- Model config = a `.bak`'d JSON edit of the agent file — **not** `mc-model-manager.sh`. Use GLM (oMLX) for anything real.
- **Stop and ask, don't thrash:** if a mechanism doesn't exist or needs upstream Letta changes, record the finding and surface options rather than forcing it.

## Acceptance / exit criteria (this session is done when)
1. `docs/research/2026-06-23-spike-findings.md` exists with **§A, §B, §C**, each a concrete, copy-pasteable recipe (not prose).
2. **Spike A:** verified mechanism for "distinct agent → shared canonical memfs," demonstrated on the throwaway (canonical read confirmed; write lands on canonical; `sync-runner.sh` fold initiated). Throwaway agent deleted. *(Fold-reached-Gitea-`main` confirmation is a server touchpoint.)*
3. **Spike B:** verified mod hook signatures (event, `update_model`, statusline, file-read) **and** a committed proof mod that flips the statusline on `link.json`/`force-offline` and swaps the active model on command.
4. **Spike C:** one verified spoke-callable fleet action with its laptop-side auth recorded — **or** a clearly documented gap + options.
5. Each deliverable committed; branch pushed (after `--rebase`); the throwaway is gone and the memfs tree is clean.
6. No production Phase-2 code written; no irreversible world action taken; the 13 protected files untouched.

## Required interaction points (you / the server) before exit
- **[SERVER] Spike A fold confirmation:** whether the throwaway's write **folded to Gitea `main`** must be verified hub-side (the brief reserves this for the server Claude). Laptop records "fold pushed"; server confirms "fold landed."
- **[SERVER/COORD] Spike C landing confirmation:** if invoking the fleet action, the server may need to confirm the row/action actually landed hub-side.
- **[YOU] possible mid-spike decision:** if Spike A finds no clean shared-memfs mechanism (needs a config that doesn't exist or an upstream change), I stop and bring you options rather than improvise.
- **[YOU] the handoff relay:** at exit, you relay the handoff (below) to the server Claude, who reviews findings and authors the Phase-2 brief. **This is the self-contained boundary.**

## Handoff statement (to provide back to the server Claude)
> **Phase 1 (laptop spoke #1 spikes) complete.** Branch `fix/pulse-analytics-briefing-local-2026-06-07` pushed at commit `<hash>`. Findings in `docs/research/2026-06-23-spike-findings.md`.
> - **Spike A (distinct agent + shared canonical memfs):** `<one line — mechanism chosen (symlink/clone/config), validated yes/no, throwaway deleted>`. *Needs hub confirmation: did the throwaway write fold to Gitea `main`?*
> - **Spike B (failover mod API):** `<one line — hooks verified, proof mod swaps model + statusline yes/no>`.
> - **Spike C (fleet from spoke):** `<one line — which fleet action is spoke-callable + auth, or the gap>`.
> - **Blockers / decisions surfaced:** `<list, or "none">`.
> Please verify the two hub-side items above, then author the Phase-2 build brief (Tasks 4–8). The laptop is idle and not building until that brief lands.

## After the handoff (context — not this session)
Phase 2 (build: lease, mini-me, mod, routing, reconnect wiring) proceeds on the laptop **after** the server's Phase-2 brief; Phase 3 acceptance is **[COORD]** — the six spine checks (offline exchange on GLM; two-way memory fold; exactly-once drain; lease blip-vs-departure; hub automation unaffected; no double-execution) require hub-side verification and your involvement. The spine is "done" only when all six pass (design §3 Acceptance).
