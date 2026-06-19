# MC Offline / Travel-Mode — Trip-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
> **Most steps run + verify ON THE LAPTOP.** The server-side Claude can author repo scripts (they git-sync) but cannot verify laptop behavior — run those tasks from a laptop session.

**Goal:** Turn the proven offline MVP (manual, placeholder model) into an *unattended, trip-ready* system: a real local brain on the laptop, automatic connectivity-aware sync, automatic cloud↔local model swap, and a one-action travel-mode flip — so MC stays one continuous agent across intermittent connectivity with no babysitting.

**Architecture:** Builds directly on `project_mc_offline_travel_mode` (MVP). Same invariants: one MC, git-over-SSH-tunnel transport to Gitea, envelope bus + server drainer, single-writer via `mc-quiesce`. This phase adds the *automation layer* (launchd-driven connectivity probe, tunnel, sync-runner, model swap, travel-mode flip) that the MVP did by hand.

**Tech Stack:** launchd (laptop), autossh, git, a local model server (Phase 0 choice), litellm + `mc-model-manager` + the `cross_provider_compat` scrub hook, Tailscale, the existing `letta/offline/` bus + `~/bin/mc-quiesce.sh`/`mc-resume.sh`.

## Global Constraints (carried from the MVP — all still binding)
- **No new Postgres tables/columns.** Bus stays git/envelope files.
- **One MC identity** `agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d`.
- **Transport = git over the SSH tunnel** (`autossh -L 3030:127.0.0.1:3030`); memfs/bus remotes keep `127.0.0.1:3030` — **no host rewrite**; Gitea stays loopback-only; push-receiver never reached from the laptop.
- **Secrets:** laptop holds ONLY `GITEA_MEMFS_TOKEN`; never via git; FileVault on.
- **Single-writer fold-in** via `~/bin/mc-quiesce.sh` — SIGSTOP the **agent node only** (not the pane leader; orphaned-group auto-CONT otherwise).
- **Never break** the home fleet (8 agents), guardian, or roaming tmux sessions; every server op stays read-only except the explicit quiesce/resume + git pushes.
- **Idempotent everywhere** (safe replay after a flap); debounce flapping; resumable/atomic transfers.
- **Reuse, don't rebuild:** existing bus, quiesce scripts, Gitea repos, `mc-model-manager`.

---

## File / artifact structure

| Path | Side | Responsibility |
|---|---|---|
| `scripts/offline/conn-probe.sh` | laptop (repo) | Write `~/.letta/offline-bus/link.json` = `{online, server_reachable, tunnel_up, services{...}, checked_at}`. Single source of truth for connectivity. |
| `scripts/offline/sync-runner.sh` | laptop (repo) | Connectivity-gated git pull/merge/push of memfs (`travel/laptop`↔`main`), conversation, outbox, inbox — debounced, locked, idempotent. Ensures the autossh tunnel is up first. |
| `scripts/offline/travel-mode.sh` | laptop (repo) | `on`/`off`/`status`: set laptop-primary vs home-automation-only; on `on`, trigger server `mc-quiesce`; on `off`, server `mc-resume` + final sync. |
| `scripts/offline/model-select.sh` | laptop (repo) | Map `link.json` → the model letta-mc-local should use (cloud alias when online, local alias when offline). |
| `~/Library/LaunchAgents/com.ai-pa.offline-tunnel.plist` | laptop | KeepAlive autossh `-L 3030:127.0.0.1:3030`. |
| `~/Library/LaunchAgents/com.ai-pa.offline-sync.plist` | laptop | RunAtLoad + StartInterval + WatchPaths → `sync-runner.sh`. |
| `~/bin/letta-mc-local` | laptop | Launches MC on the local backend with a connectivity-selected model (Phase 0/3). |
| laptop litellm config | laptop | `mc-local` (→ local model) + `mc-cloud` (→ cloud) routes + the `cross_provider_compat` scrub. |

---

## Phase R — Reproducibility (DO FIRST): commit the scripts that drove the MVP
The MVP acceptance was driven by scripts that lived **outside git**, so the
landed lineage isn't reproducible until they're committed. Phases 1/2/4 below
then **harden** these (launchd, debounce, robustness) — they are NOT created
from scratch.
- [x] **SERVER (done 2026-06-19, `15f21fd2`):** `~/bin/mc-quiesce.sh`/`mc-resume.sh` → `scripts/offline/` (canonical); `~/bin` symlinks to them.
- [ ] **LAPTOP:** commit the existing `scripts/offline/{conn-probe.sh,sync-runner.sh,travel-mode.sh}` (the versions that drove the acceptance). First scan for secrets (`grep -nE "token|secret|password|[0-9a-f]{32,}|xox|sk-" scripts/offline/*.sh` → expect clean; the token lives in `.env`/remote URLs, not the scripts). Then `git add scripts/offline/*.sh && git commit && git push`.
- [ ] **Exit:** `scripts/offline/` in the repo contains all five scripts; a fresh clone can reproduce the MVP loop. Update the runbook's script references to the repo paths.

## Phase 0 — Real local model (LAPTOP; discovery + decision)

### Task 0.1: Choose + install the local model
- [ ] Measure 2–3 candidates sized to this laptop's RAM (record `system_profiler SPHardwareDataType | grep -E "Chip|Memory"`): cold-load, tokens/sec on a 500-tok prompt, OpenAI-compatible `/v1/chat/completions`.
- [ ] Pick one; record the model + server + serve command in this file under "Phase 0 chosen model".
- [ ] **Exit:** `curl localhost:<port>/v1/chat/completions …` returns a real completion offline (paste it). Replaces the `qwen2.5:0.5b` placeholder.

---

## Phase 1 — Connectivity layer (LAPTOP)

### Task 1.1: `conn-probe.sh`
**Files:** Create `scripts/offline/conn-probe.sh`.
- [ ] Probe: `tailscale ping -c1 --timeout 2s dorseys-mac-mini` (reachable), and `curl -s -o /dev/null -w %{http_code} http://127.0.0.1:3030/api/v1/version` (tunnel up → Gitea). Write `~/.letta/offline-bus/link.json`.
- [ ] **Verify:** tunnel up → `{"online":true,"tunnel_up":true}`; kill the tunnel → `tunnel_up:false`; Wi-Fi off → `online:false`. Paste the three.
- [ ] **Exit:** `link.json` reflects all three states correctly.

### Task 1.2: autossh tunnel as launchd
**Files:** `~/Library/LaunchAgents/com.ai-pa.offline-tunnel.plist` (laptop; not git-tracked).
- [ ] `autossh -M 0 -N -L 3030:127.0.0.1:3030 dorseyhomeserver@dorseys-mac-mini.tailf9b999.ts.net`, KeepAlive, RunAtLoad; logs to `~/Library/Logs/offline-tunnel.log`. `brew install autossh` if needed.
- [ ] **Verify:** `launchctl print gui/$(id -u)/com.ai-pa.offline-tunnel` loaded; `curl 127.0.0.1:3030/api/v1/version` → 200; kill the ssh pid → autossh respawns it within ~30s (Gitea reachable again).
- [ ] **Exit:** tunnel self-heals; survives a network drop+return.

---

## Phase 2 — Automated sync (LAPTOP)

### Task 2.1: `sync-runner.sh`
**Files:** Create `scripts/offline/sync-runner.sh`.
- [ ] If `link.json.tunnel_up`: with a flock, for memfs (branch `travel/laptop`): commit local shaping, `git pull --rebase origin main`, push `travel/laptop`; for conversation + outbox + inbox: commit + `git pull --rebase` + push. Debounce (skip if ran < 30s ago). Each repo independent (one failing doesn't block others). Log to `~/Library/Logs/offline-sync.log`.
- [ ] **Verify:** make an offline memfs edit on `travel/laptop`; bring the tunnel up; runner pushes; confirm on the server the commit reached Gitea. Paste the server-side `git -C <memfs> ls-remote gitea travel/laptop`.
- [ ] **Exit:** an offline edit syncs to Gitea on the next online window with no manual git.

### Task 2.2: sync launchd
**Files:** `~/Library/LaunchAgents/com.ai-pa.offline-sync.plist` (laptop).
- [ ] RunAtLoad + StartInterval (debounced) + WatchPaths on the memfs/conversation/bus working trees + a network-change path.
- [ ] **Verify:** toggle the network → a sync fires automatically (log shows a run); flapping doesn't thrash (debounce honored).
- [ ] **Exit:** sync is fully automatic on connectivity change; no thrash.

---

## Phase 3 — Dynamic cloud↔local model swap (LAPTOP brain; server scrub reused)

### Task 3.1: laptop litellm with both routes + scrub
**Files:** laptop litellm config.
- [ ] Add `mc-local` (→ Phase-0 local model) and `mc-cloud` (→ the cloud model MC uses at home) routes; enable the `cross_provider_compat` scrub hook (mirror the server's) so a mid-conversation provider swap doesn't poison reasoning-field signatures.
- [ ] **Verify:** `curl` both aliases return completions; a conversation that switches alias mid-thread doesn't error on signatures.
- [ ] **Exit:** both routes work; swap is signature-safe.

### Task 3.2: `model-select.sh` + wire into `letta-mc-local`
**Files:** Create `scripts/offline/model-select.sh`; update `~/bin/letta-mc-local`.
- [ ] `model-select.sh` reads `link.json` → echoes `mc-cloud` if online else `mc-local`. `letta-mc-local` (or a turn-level hook) selects the model accordingly, swapping mid-session on connectivity transitions.
- [ ] **Verify:** start online (cloud), drop the tunnel mid-thread → next turn served by `mc-local` (footer/logs), restore → back to cloud, same thread, no error.
- [ ] **Exit:** MC's brain follows connectivity automatically with thread continuity.

---

## Phase 4 — Travel-mode flip (LAPTOP state + SERVER coordination)

### Task 4.1: `travel-mode.sh on|off|status`
**Files:** Create `scripts/offline/travel-mode.sh`.
- [ ] `on`: mark laptop-primary; ssh the server to run `~/bin/mc-quiesce.sh` (single writer); start the tunnel+sync launchd if not running. `off`: final `sync-runner` pass, then ssh `~/bin/mc-resume.sh`; mark home-primary. `status`: show current side + tunnel + sync health.
- [ ] **Verify:** `travel-mode on` → server MC frozen (`ps stat T+`), sync running; `off` → server MC resumed, all 8 sessions healthy. (Reuses the verified quiesce scripts.)
- [ ] **Exit:** one command each way; never touches the other 7 agents/guardian.

### Task 4.2 (optional/refine): presence-auto trigger
- [ ] Heuristic (network SSID / location / tailnet-reach) that calls `travel-mode on/off` automatically, with a manual override. Defer if Task 4.1 manual flip is sufficient for the first trip.

---

## Phase 5 — Unattended trip-cycle acceptance (the exit conditions)

### Task 5.1: Hands-off intermittent cycle
- [ ] `travel-mode on`; with the **real** model: hold an offline exchange + shape memory across **≥2 automatic** connect/drop cycles (no manual git, no manual quiesce) → on each online window the sync-runner folds memory + conversation to Gitea; the model swaps cloud↔local automatically.
- [ ] Issue a fleet command offline → it drains exactly once on reconnect (existing drainer) and the result returns.
- [ ] `travel-mode off` → server MC resumes carrying all the trip's memory + conversation; all 8 sessions healthy; Postgres schema unchanged (`diff` vs baseline).
- [ ] **Exit:** the full cycle runs with **zero manual git/ssh/quiesce** beyond the two `travel-mode` flips, and ends with one continuous MC + no DB drift.

---

## Out of scope (later)
- Fleet-slice (tasks) mirroring onto MC for richer offline task work.
- Multi-device (phone) travel.
- Hardening the presence-auto heuristic beyond a first cut.

## Self-review notes
- Covers all design §9/§10 deferred items: real model (P0), automated sync+tunnel (P1/P2), model swap (P3), travel-mode flip (P4), unattended acceptance (P5). ✓
- Reuses (doesn't rebuild) the MVP bus, drainer, quiesce scripts, Gitea repos. ✓
- Constraints (no DB, one identity, tunnel transport, minimal secrets, single-writer, don't-break-fleet, idempotent) restated and bound to tasks. ✓
- Laptop-vs-server execution tagged per phase; discovery task (P0 model) has a concrete recorded output, not a placeholder. ✓
