# MC Hub-and-Spoke — Laptop Spoke #1 (Failover Spine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the laptop a self-contained Kinara *spoke* that runs on a local brain when the hub is unreachable and reconciles automatically on reconnect, with no manual mode flip.

**Architecture:** A distinct laptop mini-me agent shares the hub's canonical memfs lineage. A laptop-loaded Letta Code **mod** auto-detects hub reachability and swaps the model cloud↔local; a **presence-lease** distinguishes a connectivity blip from a real departure; **action routing** sends irreversible actions directly to the fleet when online-and-capable, else queues them to the existing outbox for the hub to drain exactly-once. All transport is the existing memfs/bus git substrate.

**Tech Stack:** Python 3 (pure logic + existing bus code, pytest), bash (existing offline scripts), TypeScript (Letta Code mod), git/Gitea over SSH tunnel, oMLX + GLM-4.5-Air, Ollama. Reuses: `conn-probe.sh`, `sync-runner.sh`, `letta/offline/{envelope,outbox,drainer}.py`, the server drainer, `mc-quiesce.sh`/`mc-resume.sh`.

## Global Constraints
- **Transport:** git-over-SSH-tunnel substrate only (Gitea: canonical memfs lineage + bus repos). NO new database, NO new transport.
- **Identity:** hub Kinara is canonical; the laptop spoke is a **distinct agent ID** that **shares the hub's canonical memfs lineage**.
- **Authority (Invariant 1):** every irreversible action has exactly one executor chosen at action time by connectivity × capability — online+capable → act directly via the shared fleet services; else draft+queue for the hub to drain **exactly-once**; idempotency keys (content-hash envelope IDs) prevent double-execution.
- **Ownership (Invariant 2):** a spoke owns its **lease + queued work (outbox)**, NOT a memory namespace. No global live-writer lock.
- **Memory:** one shared canonical memfs lineage; **agents own their own memory organization**; infrastructure only guarantees frequent bidirectional sync + fold. Do NOT impose memory schema/namespaces.
- **Conversations are per-device**, reconciled by memory + recall, never synced.
- **Single-writer for any fold** is enforced hub-side by `mc-quiesce.sh`/`mc-resume.sh`.
- **Device tags:** every task is marked **[HUB]**, **[LAPTOP]**, or **[COORD]** (both). The MC agent id is `agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d` (the *hub* Kinara / canonical memfs lineage).
- **Source-of-truth spec:** `docs/plans/2026-06-23-mc-hub-and-spoke-design.md`.

## File Structure (created/modified by this plan)
- `letta/offline/lease.py` — pure lease logic (write heartbeat, evaluate present/expired). **Create.**
- `letta/offline/test_lease.py` — pytest for lease logic. **Create.**
- `letta/offline/routing.py` — pure action-routing decision (link-state × capability → `direct`|`queue`). **Create.**
- `letta/offline/test_routing.py` — pytest for routing. **Create.**
- `scripts/offline/lease-heartbeat.sh` — bash wrapper that renews the lease via `lease.py` (launchd-friendly). **Create.**
- `scripts/offline/setup-laptop-minime.sh` — creates/configures the distinct laptop mini-me agent + shared-memfs mount (per Spike A). **Create.**
- `scripts/offline/mods/connectivity-failover/` — tracked source of the Letta Code mod (installed to `~/.letta/mods/` on the laptop). **Create.**
- `docs/runbooks/2026-06-23-phase0-memfs-align.md` — the one-time coordinated cleanup procedure. **Create.**
- `docs/research/2026-06-23-spike-findings.md` — verified facts from the spikes (memfs mount, mod API, fleet auth). **Create.**

---

## Phase 0 — Gating cleanup (must complete before anything builds against shared memory)

### Task 0: Reconcile the memfs divergence  **[COORD]**  ✅ COMPLETE 2026-06-23

> **Status:** done. Hub canonical `560f81d` pushed to Gitea `main`; laptop `travel/laptop` rebased onto it (`9b1954c`), laptop `origin/main` == hub `main` == `560f81d`. Record: `docs/runbooks/2026-06-23-phase0-memfs-align.md`.

**Files:**
- Create: `docs/runbooks/2026-06-23-phase0-memfs-align.md`

**Why:** the hub's local memfs is ahead (`560f81d`) of Gitea `main` (`248ba04`); the laptop is at `248ba04` on `travel/laptop`. Building/syncing against a stale canonical risks folding onto a divergent base. Align before anything else.

- [ ] **Step 1 [HUB]: Snapshot current state**

```bash
cd /Volumes/main-drive/ai-PA
MC=agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d
SRV="$HOME/.letta/lc-local-backend/memfs/$MC/memory"
git -C "$SRV" log --oneline -3; git -C "$SRV" status --short
```
Expected: local HEAD `560f81d` (or later), Gitea `main` behind.

- [ ] **Step 2 [HUB]: Quiesce the live hub MC (single-writer)**

```bash
~/bin/mc-quiesce.sh
ps -o stat= -p "$(pgrep -f 'letta --backend local --agent '"$MC" | head -1)"   # expect a 'T' (stopped) state
```
Expected: the kinara agent node shows stopped (`T`). If it does not hold, STOP — see `mc-quiesce.sh` orphaned-group note.

- [ ] **Step 3 [HUB]: Push the hub's canonical state to Gitea `main`**

```bash
git -C "$SRV" add -A && git -C "$SRV" diff --cached --quiet || git -C "$SRV" commit -q -m "phase0: capture hub memory before align"
git -C "$SRV" push origin HEAD:main
git -C "$SRV" rev-parse --short main
```
Expected: Gitea `main` now at the hub's HEAD.

- [ ] **Step 4 [LAPTOP]: Rebase the laptop onto the new canonical**

```bash
M=~/.letta/lc-local-backend/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory
git -C "$M" fetch origin && git -C "$M" rebase origin/main
git -C "$M" log --oneline -1; git -C "$M" log --oneline -1 origin/main
```
Expected: laptop `travel/laptop` tip rebased onto the new `origin/main`; no conflicts (if conflicts, resolve and note in the runbook).

- [ ] **Step 5 [HUB]: Resume the hub MC**

```bash
~/bin/mc-resume.sh
ps -o stat= -p "$(pgrep -f 'letta --backend local --agent '"$MC" | head -1)"   # expect running (no 'T')
```

- [ ] **Step 6 [COORD]: Write the runbook recording exactly what was done + the before/after commit hashes, then commit**

```bash
git add docs/runbooks/2026-06-23-phase0-memfs-align.md
git commit -m "docs: phase 0 memfs alignment runbook (hub->Gitea, laptop rebased)"
```

**Deliverable:** Gitea `main` = hub canonical; laptop rebased onto it; hub running; documented. Acceptance: `git -C "$M" rev-parse origin/main` (laptop) equals `git -C "$SRV" rev-parse main` (hub).

---

## Phase 1 — Spikes (resolve the open questions into verified facts)

Each spike ends with a concrete, validated finding written to `docs/research/2026-06-23-spike-findings.md`. The build tasks (Phase 2) consume these. Spikes are gates: do not start the dependent build task until its spike's finding is recorded.

### Task 1: Spike A — distinct agent + shared canonical memfs  **[LAPTOP]**

**Files:**
- Create/append: `docs/research/2026-06-23-spike-findings.md` (section "A: memfs mount")

**Goal:** determine the exact letta-code mechanism by which a *distinct* agent ID uses the *hub MC's* canonical memfs lineage (`agents/agent-local-8474bbbd….git`) as its memory, rather than getting its own per-agent memfs.

- [ ] **Step 1: Read how local-backend resolves an agent's memfs path**

Inspect (read-only): `src/backend/local/paths.ts` and `src/backend/local/local-store.ts` in the installed letta-code (find with `npm root -g`/the Homebrew cellar). Record how `memfs/<agentId>/memory` is derived and whether the path is overridable (env, agent config field, or symlink-respecting).

- [ ] **Step 2: Try the lowest-risk mount mechanism first (symlink), on a throwaway agent**

Create a throwaway distinct agent; symlink its `memfs/<newId>/memory` to the canonical repo working tree OR point it at a fresh clone of `agents/agent-local-8474bbbd….git`. Launch it and confirm it reads `system/` + `reference/` from the canonical lineage.

- [ ] **Step 3: Verify writes land on the canonical lineage and sync**

Have the throwaway agent write a memory note; confirm the change appears in the canonical repo (`git status` in the mount) and that `sync-runner.sh` folds it to `origin/main`.

- [ ] **Step 4: Record the finding**

Write to spike-findings A: the exact mechanism (symlink vs config vs clone), the precise commands, and any gotchas (e.g., whether two agents sharing one working tree is safe, or whether each needs its own clone of the same remote). Delete the throwaway agent. Commit the findings doc.

**Deliverable:** a verified, copy-pasteable recipe for "distinct agent, shared canonical memfs." **Gates Task 5.**

### Task 2: Spike B — the connectivity-failover mod API surface  **[LAPTOP]**

**Files:**
- Create/append: `docs/research/2026-06-23-spike-findings.md` (section "B: mod API")
- Create: `scripts/offline/mods/connectivity-failover/` (a minimal "hello" mod that proves the hooks)

**Goal:** establish the exact mod hooks for (a) a periodic/turn event, (b) reading/writing the active model (`update_model`), and (c) a statusline value.

- [ ] **Step 1: Read the mod surface**

Read (read-only): `src/mods/types.ts`, `src/mods/mod-engine.ts`, and `src/skills/builtin/creating-mods/references/`. Run the in-harness `creating-mods` skill to scaffold a starter. Record the exact registration API for: lifecycle/turn or timer events, model get/set, statusline registration, and how a mod reads an external file (it must read the conn-probe `link.json`).

- [ ] **Step 2: Build a minimal proof mod**

In `scripts/offline/mods/connectivity-failover/`, write the smallest mod that: on a timer/turn event, reads `~/.letta/offline-bus/link.json`, and writes the `online` value to the statusline. Install to `~/.letta/mods/connectivity-failover/`, launch letta-code, confirm the statusline reflects link state and flips when you touch/remove `~/.letta/offline-bus/force-offline`.

- [ ] **Step 3: Prove the model swap**

Extend the proof mod to call the verified `update_model` API to switch between `ollama/qwen2.5:7b-instruct` (or the cloud model) and the local GLM endpoint on a manual command. Confirm the active model changes (subsequent turn runs on the new model).

- [ ] **Step 4: Record the finding + commit the proof mod**

Write spike-findings B: exact hook signatures, the `update_model` call shape, the statusline API, and the file-read pattern. Commit the proof mod (it becomes the skeleton for Task 6).

**Deliverable:** verified mod API + a working proof mod that reads link state and swaps the model. **Gates Task 6.**

### Task 3: Spike C — fleet auth/routing for spoke callers over Tailscale  **[LAPTOP]**

**Files:**
- Create/append: `docs/research/2026-06-23-spike-findings.md` (section "C: fleet from spoke")

**Goal:** confirm a laptop-side caller can invoke one fleet service (e.g., the tasks pipeline) over Tailscale, and record the auth/endpoint shape — or identify the gap.

- [ ] **Step 1: Identify one concrete fleet entry point**

Pick the lowest-risk fleet action that has a clear server endpoint reachable over the tunnel/tailnet (e.g., enqueue to `pa_web.task_queue`, or a fleet HTTP endpoint). Record its URL/auth from the hub config.

- [ ] **Step 2: Invoke it from the laptop**

From the laptop (online), perform the call over the tailnet and confirm it lands on the hub-side service (the row appears / the action runs). Record exact endpoint + auth (token/env) needed laptop-side.

- [ ] **Step 3: Record the finding**

Write spike-findings C: which fleet actions are spoke-callable today, what auth they need laptop-side, and which (if any) require hub-side changes to accept spoke callers. Commit. (If a gap exists, note it as a follow-up; the spine can ship with offline-queue-only for actions that aren't yet spoke-callable.)

**Deliverable:** verified list of spoke-callable fleet actions + auth. **Informs Task 7.**

---

## Phase 2 — Build the failover spine

### Task 4: Presence-lease logic (pure, TDD)  **[LAPTOP]**

**Files:**
- Create: `letta/offline/lease.py`
- Test: `letta/offline/test_lease.py`
- Create: `scripts/offline/lease-heartbeat.sh`

**Interfaces:**
- Produces: `renew_lease(path: str, spoke_id: str, ttl_secs: int, now: float) -> dict` (writes `{spoke_id, renewed_at, ttl_secs}` JSON to `path`, returns it); `lease_state(path: str, now: float) -> str` (returns `"present"` if `now - renewed_at < ttl_secs`, else `"expired"`, `"absent"` if no file).

- [ ] **Step 1: Write the failing tests**

```python
# letta/offline/test_lease.py
import json, os, tempfile
from letta.offline.lease import renew_lease, lease_state

def test_renew_writes_and_returns():
    p = tempfile.mktemp()
    out = renew_lease(p, "laptop", 90, now=1000.0)
    assert out == {"spoke_id": "laptop", "renewed_at": 1000.0, "ttl_secs": 90}
    assert json.load(open(p)) == out

def test_state_present_within_ttl():
    p = tempfile.mktemp(); renew_lease(p, "laptop", 90, now=1000.0)
    assert lease_state(p, now=1050.0) == "present"   # 50s < 90s

def test_state_expired_past_ttl():
    p = tempfile.mktemp(); renew_lease(p, "laptop", 90, now=1000.0)
    assert lease_state(p, now=1200.0) == "expired"   # 200s > 90s

def test_state_absent_when_no_file():
    assert lease_state(tempfile.mktemp(), now=1000.0) == "absent"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Volumes/main-drive/ai-PA && python -m pytest letta/offline/test_lease.py -v`
Expected: FAIL (ModuleNotFoundError: lease).

- [ ] **Step 3: Implement**

```python
# letta/offline/lease.py
import json, os
def renew_lease(path: str, spoke_id: str, ttl_secs: int, now: float) -> dict:
    data = {"spoke_id": spoke_id, "renewed_at": now, "ttl_secs": ttl_secs}
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(data, f)
    os.replace(tmp, path)
    return data
def lease_state(path: str, now: float) -> str:
    if not os.path.exists(path): return "absent"
    d = json.load(open(path))
    return "present" if (now - d["renewed_at"]) < d["ttl_secs"] else "expired"
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest letta/offline/test_lease.py -v`
Expected: 4 passed.

- [ ] **Step 5: Write the heartbeat wrapper**

```bash
# scripts/offline/lease-heartbeat.sh
#!/usr/bin/env bash
# Renews the laptop presence lease in the bus dir. Run on a timer (≪ TTL).
set -euo pipefail
BUS="${OFFLINE_BUS_DIR:-$HOME/.letta/offline-bus}"; mkdir -p "$BUS"
TTL="${LEASE_TTL_SECS:-180}"   # tune in Phase 3; heartbeat cadence must be ≪ TTL
cd "${PA_AI_REPO_ROOT:-$HOME/ai-PA}"
python -c "import time; from letta.offline.lease import renew_lease; renew_lease('$BUS/lease.json','laptop',$TTL, time.time())"
```

- [ ] **Step 6: Commit**

```bash
chmod +x scripts/offline/lease-heartbeat.sh
git add letta/offline/lease.py letta/offline/test_lease.py scripts/offline/lease-heartbeat.sh
git commit -m "feat(offline): presence-lease logic + heartbeat wrapper"
```

### Task 5: The distinct laptop mini-me agent  **[LAPTOP]** — *gated by Spike A*

**Files:**
- Create: `scripts/offline/setup-laptop-minime.sh`

**Interfaces:**
- Consumes: Spike A's verified mount recipe (`docs/research/2026-06-23-spike-findings.md` §A).
- Produces: a distinct agent ID (recorded in the script as `LAPTOP_MINIME_ID`) whose memfs is the shared canonical lineage; model config = cloud when online / local GLM (oMLX) when offline.

- [ ] **Step 1: Encode Spike A's recipe into a setup script**

Write `scripts/offline/setup-laptop-minime.sh` performing exactly the verified §A steps: create the distinct agent (own persona — a local-aware Kinara facet), mount the canonical memfs per §A, set the model config (cloud primary + local GLM fallback endpoint), set `message_buffer_autoclear: false` (required on memfs agents — see project memory), and print the new agent ID.

- [ ] **Step 2: Run it; verify shared memory reads**

Launch the mini-me; ask it to list its memory dir and read `system/human.md`. Expected: it reads the *canonical* `system/`+`reference/` content (same as hub), confirming the shared mount.

- [ ] **Step 3: Verify a write folds to canonical**

Have it write a small note; run `sync-runner.sh`; confirm the note reaches `origin/main`. Expected: canonical updated.

- [ ] **Step 4: Commit**

```bash
chmod +x scripts/offline/setup-laptop-minime.sh
git add scripts/offline/setup-laptop-minime.sh
git commit -m "feat(offline): laptop mini-me agent setup (distinct id, shared canonical memfs)"
```

**Deliverable:** a distinct laptop Kinara facet reading/writing the shared canonical memory. Acceptance: its memory reads match the hub's canonical; a write folds to `origin/main`.

### Task 6: The connectivity-failover mod  **[LAPTOP]** — *gated by Spike B*

**Files:**
- Modify/extend: `scripts/offline/mods/connectivity-failover/` (from Spike B's proof mod) → installed to `~/.letta/mods/connectivity-failover/`

**Interfaces:**
- Consumes: Spike B's verified hooks (event, `update_model`, statusline, file-read); `~/.letta/offline-bus/link.json` from `conn-probe.sh`; the mini-me's cloud + local model identifiers from Task 5.
- Produces: a `link_state` the action-routing reads (written to `~/.letta/offline-bus/mode.json` as `{"link":"online"|"offline","model":"cloud"|"local","at":<ts>}`).

- [ ] **Step 1: On event, read link state and decide target model**

Using the §B event hook: every tick, run `conn-probe.sh` (or read its fresh `link.json`); if `online==false` → target `local`; else → target `cloud`.

- [ ] **Step 2: Swap the model only on transitions**

If target ≠ current active model, call the §B `update_model` to swap, and write `~/.letta/offline-bus/mode.json` with the new link+model. Do nothing if unchanged (avoid churn). On swap failure, keep last-good model and write the failure into `mode.json` (surface, don't crash).

- [ ] **Step 3: Statusline**

Register a statusline value: `🟢 cloud` / `🔴 local` plus lease state (read `lease.json` via `lease_state`).

- [ ] **Step 4: Validate the swap end-to-end**

Install the mod; launch the mini-me. With the tunnel up: statusline shows `cloud`. `touch ~/.letta/offline-bus/force-offline` → within one tick statusline flips to `local`, `mode.json` shows `local`, and the next turn runs on GLM. `rm` the flag → flips back to `cloud`. Record the result.

- [ ] **Step 5: Commit**

```bash
git add scripts/offline/mods/connectivity-failover/
git commit -m "feat(offline): connectivity-failover mod (auto model-swap + statusline)"
```

**Deliverable:** auto cloud↔local model swap driven by link state, with visible status. Acceptance: forcing offline/online flips the active model within one tick, no manual command.

### Task 7: Action routing — direct-vs-queue (pure logic TDD + wiring)  **[LAPTOP]** — *informed by Spike C*

**Files:**
- Create: `letta/offline/routing.py`
- Test: `letta/offline/test_routing.py`

**Interfaces:**
- Consumes: `mode.json` (Task 6) for link state; Spike C's spoke-callable fleet list for the capability flag; existing `letta/offline/outbox.py` for queuing.
- Produces: `route_action(link: str, capable: bool) -> str` returning `"direct"` or `"queue"`.

- [ ] **Step 1: Write the failing tests**

```python
# letta/offline/test_routing.py
from letta.offline.routing import route_action

def test_online_capable_goes_direct():
    assert route_action("online", True) == "direct"
def test_online_not_capable_queues():
    assert route_action("online", False) == "queue"   # thin/uncredentialed action → hub
def test_offline_always_queues():
    assert route_action("offline", True) == "queue"
    assert route_action("offline", False) == "queue"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest letta/offline/test_routing.py -v` — Expected: FAIL (no module).

- [ ] **Step 3: Implement**

```python
# letta/offline/routing.py
def route_action(link: str, capable: bool) -> str:
    """Exactly one executor: online+capable acts directly; otherwise queue for the hub."""
    return "direct" if (link == "online" and capable) else "queue"
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest letta/offline/test_routing.py -v` — Expected: 3 passed.

- [ ] **Step 5: Document the wiring contract (no agent-tool code here — that's the mod/agent's job)**

Append to spike-findings: the agent/mod, before any irreversible action, calls `route_action(link_from_mode_json, capable=action_in_spikeC_list)`. If `"queue"`, it appends an `Envelope` (existing `letta/offline/envelope.py`, idempotency key = content hash) to the outbox; if `"direct"`, it calls the fleet action from Spike C. Record this as the binding rule for the persona/recipe.

- [ ] **Step 6: Commit**

```bash
git add letta/offline/routing.py letta/offline/test_routing.py docs/research/2026-06-23-spike-findings.md
git commit -m "feat(offline): action-routing decision (direct vs queue) + wiring contract"
```

**Deliverable:** a verified routing decision + the documented rule the persona follows. Acceptance: the 3 unit tests pass and the wiring rule is recorded.

### Task 8: Reconnect choreography wiring  **[LAPTOP]**

**Files:**
- Modify: the laptop launchd/timer set (document in `docs/runbooks/2026-06-23-phase0-memfs-align.md` appendix or a new `scripts/offline/README` note) to run, on reconnect (link flips online in `mode.json`): `sync-runner.sh` (fold + the existing drainer drains the outbox server-side).

- [ ] **Step 1: Trigger sync on the online transition**

Have the mod (Task 6), when it writes `mode.json` with `link: online` after having been offline, also invoke `scripts/offline/sync-runner.sh` once (fold memory; the server-side drainer picks up the outbox). Confirm via `offline-sync.log` that a fold runs on reconnect.

- [ ] **Step 2: Confirm exactly-once drain**

Queue one action while offline; reconnect; confirm the server drainer executes it once (dispatched marker present) and the result lands in inbox. Re-run the drain; confirm replay is a no-op (`[]`).

- [ ] **Step 3: Commit any wiring/config + a short note**

```bash
git add -p   # only the touched offline wiring/config files
git commit -m "feat(offline): reconnect choreography — fold + exactly-once drain on online transition"
```

**Deliverable:** on reconnect, memory folds and queued actions drain exactly-once, automatically. Acceptance: see Phase 3 checks 2 + 3.

---

## Phase 3 — Acceptance (the spine is done)

### Task 9: Run the failover-spine acceptance  **[COORD]**

**Files:**
- Create: `docs/runbooks/2026-06-23-laptop-spoke-acceptance.md` (record results + the chosen lease TTL / heartbeat cadence)

Run each check, record PASS/FAIL + evidence:

- [ ] **Check 1 — Offline exchange on local brain:** force offline; have a real exchange with the mini-me; confirm it runs on GLM (statusline `local`, coherent answer grounded in shared memory).
- [ ] **Check 2 — Memory folds both ways:** offline, write a memory note; reconnect; confirm it reaches `origin/main` AND a hub-side canonical change made meanwhile is pulled to the laptop.
- [ ] **Check 3 — Exactly-once drain:** queue one irreversible action offline; reconnect; confirm it executes once (dispatched marker), result in inbox, replay `[]`.
- [ ] **Check 4 — Lease blip vs departure:** drop < TTL then return → no handoff (hub never reclaimed); drop > TTL → `lease_state`=`expired` and the hub holds its posture. Record the TTL/cadence used.
- [ ] **Check 5 — Hub automation unaffected:** throughout, confirm the hub fleet/crons/inbound keep running (spot-check one cron + the analytics pipeline ran).
- [ ] **Check 6 — No double-execution:** perform an action right at the offline→online boundary; confirm it ran exactly once (not both directly and via drain).

- [ ] **Final: commit the acceptance runbook**

```bash
git add docs/runbooks/2026-06-23-laptop-spoke-acceptance.md
git commit -m "docs: laptop spoke #1 failover-spine acceptance results"
```

**Deliverable:** all 6 checks PASS, recorded. The failover spine is complete; the rejoin-summary (L1) is the documented fast-follow (own plan).

---

## Notes for the implementer
- **Reuse, don't rebuild:** `conn-probe.sh`, `sync-runner.sh`, `letta/offline/{envelope,outbox,drainer}.py`, the server drainer, and `mc-quiesce/resume` already exist and are validated — wire to them.
- **Two machines:** respect the **[HUB]/[LAPTOP]/[COORD]** tags; HUB steps run on the server (`/Users/dorseyhomeserver`, `/Volumes/main-drive/ai-PA`), LAPTOP steps on `cd-macbook` (`/Users/chaddorsey`, `~/ai-PA`).
- **Spikes gate builds:** Task 5 needs Spike A; Task 6 needs Spike B; Task 7 is informed by Spike C. Do not write the build task's integration code before its spike finding is recorded.
- **Lease TTL** starts at 180s (heartbeat every ~30–45s); tune in Check 4.
