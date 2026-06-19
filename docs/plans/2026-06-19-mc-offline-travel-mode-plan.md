# MC Offline / Travel-Mode — Implementation Plan (MVP slice)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Mission Control a single continuous agent that travels on the laptop, stays usable offline on a local model, and auto-reconciles (memory, conversation, queued fleet commands + results) with home on every reconnect — without forking identity, running two live writers, or adding database tables.

**Architecture:** One MC identity. Laptop-primary while traveling; home runs automation only (namespaced). One git transport carries memory + conversation + a generic envelope outbox/inbox; a connectivity-aware sync runner drives it; a server-side drainer routes envelopes to the existing push-receiver / `task_queue`. Connectivity signal flips the model (cloud↔local) and MC's capability-awareness.

**Tech Stack:** letta-code (local backend), git + Gitea (memfs/conversation/envelope transport), launchd (runners), Postgres `pa_web.task_queue` (existing), push-receiver (`:8099`), litellm + `mc-model-manager` (`cross_provider_compat` scrub hook), a local model server on the laptop (selected in Phase 1).

## Global Constraints
- **No new database tables/columns.** Heterogeneous commands are git-synced envelope files, never DB rows. Only existing `pa_web.task_queue` is written, via existing paths.
- **One MC identity** (`agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d`) — never a second agent id; recall stays unified.
- **One transport = git.** No Dropbox/Syncthing/rsync. Idempotency = commit/content hash.
- **MC never drives transport or processing** — it only appends locally; runners/drainer do I/O.
- **Single writer in practice:** while traveling, laptop shapes memory + owns the live conversation; home automation writes only under an `automation/` namespace.
- **Authority rule:** outward side-effects (send/post/book) execute once, by one owner — home while traveling; offline laptop only drafts/queues.
- **Idempotent everywhere** (safe replay after a flap).
- **Don't disrupt running services:** the home fleet (kinara/email/docs/calendar/pulse/tasks), guardian, and roaming sessions keep working throughout.
- **Reuse, don't rebuild:** memfs/Gitea sync, push-receiver, `task_queue` poller, `mc-model-manager`, the mosh/tmux roaming layer.

---

## File / artifact structure (locked decomposition)

| Path | Responsibility |
|---|---|
| `letta/offline/envelope.py` | Envelope schema + (de)serialize + content-hash id. The one new data contract. |
| `letta/offline/outbox.py` | Append an envelope to the laptop outbox git repo; list pending; mark dispatched. |
| `letta/offline/drainer.py` | Server-side: read newly-synced envelopes, route by `target`/`verb` → push-receiver or `task_queue`; idempotent by id; write results to inbox. |
| `scripts/offline/sync-runner.sh` | Connectivity-aware: on network-up + debounced poll, git pull/merge/push for memory + conversation + outbox + inbox. |
| `scripts/offline/conn-probe.sh` | Emit a single source-of-truth link/capability state file the agent + model-manager read. |
| `scripts/offline/travel-mode.sh` | `on`/`off`/`status`: flip laptop-primary vs home-automation-only; set the namespace + authority flags. |
| `~/Library/LaunchAgents/com.ai-pa.offline-sync.plist` | Runs `sync-runner.sh` (laptop) on `WatchPaths`/network + interval. (Not git-tracked.) |
| `~/Library/LaunchAgents/com.ai-pa.offline-drainer.plist` | Runs `drainer.py` (server) on a short interval / inbox WatchPath. (Not git-tracked.) |
| `letta/offline/conversations/` (git repo) | Conversation-sync working tree (the canonical thread + travel tail). |
| `~/.letta/offline-bus/{outbox,inbox}/` (git repos) | The envelope bus working trees, synced both ends. |
| `mc-model-manager` (extend) | Add a connectivity input so model selection flips cloud↔local. |
| `docs/plans/2026-06-19-mc-offline-travel-mode-plan.md` | This plan (progress ledger). |

---

## Phase 0 — Discovery & prerequisites

### Task 0.1: Laptop capability + local-model selection
**Deliverable:** a recorded decision (append to this plan under "Phase 1 chosen model") naming the local model, its server, and the exact serve command — chosen by measurement, not guess.
- [ ] Record laptop specs: `system_profiler SPHardwareDataType | grep -E "Chip|Memory"`.
- [ ] Stand up 2–3 candidate local servers (e.g. Ollama / LM Studio / llama.cpp) and pull 2–3 candidate models sized to the RAM (a small + a mid model).
- [ ] For each, measure: cold-load time, tokens/sec on a 500-token prompt, and whether it speaks an OpenAI-compatible `/v1/chat/completions` (what litellm/letta need).
- [ ] **Exit:** chosen model + server + serve command recorded here; the server answers a curl `/v1/chat/completions` with a valid completion. Record that curl + its output in the transcript.

### Task 0.2: Secrets posture for the traveling laptop
**Deliverable:** documented + applied token/disk posture.
- [ ] Confirm FileVault on (`fdesetup status`).
- [ ] Inventory which creds the laptop MC actually needs offline (memfs/Gitea token; local-model none) vs which stay server-only (Gmail/Slack/Drive — never on laptop). Record the list here.
- [ ] **Exit:** only the minimal token set is present on the laptop; the list is recorded; `fdesetup status` shows On (paste output).

---

## Phase 1 — Laptop local-model node + MC runtime offline

### Task 1.1: Serve the chosen local model behind an OpenAI-compatible endpoint
**Files:** none in-repo (host config); record the launch in `scripts/offline/` if scripted.
- [ ] Start the Phase-0 server; verify health.
- [ ] **Verify:** `curl -s localhost:<port>/v1/chat/completions -d '{"model":"<m>","messages":[{"role":"user","content":"say PONG"}]}'` returns a completion containing a model reply.
- [ ] **Exit:** non-empty completion in the transcript.

### Task 1.2: A laptop "local" litellm route for the local model
**Files:** Modify the laptop litellm config (mirror the server's `litellm` model list shape).
- [ ] Add a model alias (e.g. `mc-local`) routing to `localhost:<port>` OpenAI-compatible.
- [ ] **Verify:** `curl localhost:4000/v1/chat/completions` (laptop litellm) with `model=mc-local` returns a completion.
- [ ] **Exit:** laptop litellm proxies to the local model; paste the curl output.

### Task 1.3: MC runtime runs against a memfs clone on the laptop, on `mc-local`
**Files:** laptop clone of MC memfs (`~/.letta/lc-local-backend/memfs/<MC>/memory/.git`); a laptop `letta-mc-local` launcher mirroring `~/bin/letta-mc` but with `--model mc-local` (or agent model override).
- [ ] Clone MC's memfs + a copy of the canonical conversation onto the laptop backend dir.
- [ ] Launch MC locally pointed at `mc-local`.
- [ ] **Verify:** with the laptop network OFF (`sudo ifconfig en0 down` or Wi-Fi off), MC answers a prompt that needs no external data ("summarize your current working loops from memory").
- [ ] **Exit:** MC produces a coherent memory-grounded reply with no network; paste a transcript excerpt + confirm interfaces unreachable.

---

## Phase 2 — Sync substrate (memory + conversation), connectivity-driven

> **Transport (decided 2026-06-19):** Gitea/push-receiver bind loopback, so the laptop reaches Gitea via an **SSH tunnel** (`autossh -L 3030:127.0.0.1:3030`) — memfs/bus remotes keep `127.0.0.1:3030` (no host rewrite), token reused, Gitea stays private, push-receiver never reached from the laptop. Bus repos exist: `agents/mc-offline-{outbox,inbox,conversation}`. The sync-runner manages the tunnel + owns the git pull/push. See the laptop sub-plan's TRANSPORT DECISION section.

### Task 2.1: `conn-probe.sh` — single link/capability state
**Files:** Create `scripts/offline/conn-probe.sh`.
- [ ] Probe the server over the tailnet (e.g. `tailscale ping -c1 --timeout 2s dorseys-mac-mini` AND a TCP check to the push-receiver) and write `~/.letta/offline-bus/link.json` = `{online:bool, server_reachable:bool, services:{gmail:false,...}, checked_at}`.
- [ ] **Verify:** run with link up → `online:true`; disable network → `online:false`. Paste both.
- [ ] **Exit:** `link.json` flips correctly across a real network toggle.

### Task 2.2: `sync-runner.sh` — connectivity-aware git sync for memory + conversation
**Files:** Create `scripts/offline/sync-runner.sh`; extend/mirror the existing memfs runner-side pull-rebase-before/push-after logic.
- [ ] If `link.json.online`: for the memfs repo and the conversation repo — `git pull --rebase` (laptop branch off `main`), commit local changes, `git push`. Debounce (skip if ran < N s ago); lock to avoid overlap.
- [ ] Namespacing: home automation commits only under `automation/`; laptop shaping commits elsewhere → non-overlapping.
- [ ] **Verify:** make a memory edit on the laptop while offline → it commits to the laptop branch; bring network up → runner pushes; confirm on the server the change is on `main` after merge. Paste the server-side `git log --oneline -3`.
- [ ] **Exit:** an offline memory edit lands on the server `main` after one online window; a concurrent `automation/` edit on the server merges without conflict.

### Task 2.3: Conversation tail fold-in (single-owner)
**Files:** conversation repo handling in `sync-runner.sh`.
- [ ] Enforce single-owner: while `travel-mode on`, only the laptop appends to the live thread; sync appends the tail (append-only `messages.jsonl`, unique ids) into the canonical thread on the server.
- [ ] **Verify:** hold an offline exchange on the laptop; reconnect; confirm those messages appear in the canonical thread on the server with no duplication (grep message ids).
- [ ] **Exit:** offline conversation tail is present, once, in the unified thread server-side.

### Task 2.4: launchd for the sync runner
**Files:** `~/Library/LaunchAgents/com.ai-pa.offline-sync.plist` (laptop; not git-tracked).
- [ ] RunAtLoad + `StartInterval` (debounced) + `WatchPaths` on the working trees and a network-change path; logs to `~/Library/Logs/offline-sync.log`.
- [ ] **Verify:** `launchctl print gui/$(id -u)/com.ai-pa.offline-sync` shows it loaded; toggling network triggers a sync (log shows a run).
- [ ] **Exit:** sync fires automatically on network-up without manual invocation.

---

## Phase 3 — Outbox / inbox envelope log + drainer

### Task 3.1: `envelope.py` — the one new contract
**Files:** Create `letta/offline/envelope.py`; Test `task-cli/tests/test_envelope.py` (or a sibling test dir).
- [ ] Define `Envelope` = `{id, created_at, target, verb, args, idempotency_key, reply_to}`; `id` = stable content hash; serialize to a JSON file `<id>.json`.
- [ ] **Test (failing first):** round-trip serialize/deserialize; identical content → identical `id`; differing content → different `id`.
- [ ] **Run → fail → implement → pass.** `python3 -m pytest <test> -v`.
- [ ] **Exit:** tests green; deterministic ids.

### Task 3.2: `outbox.py` — append/list/mark on the laptop
**Files:** Create `letta/offline/outbox.py`; writes to `~/.letta/offline-bus/outbox/` (git repo).
- [ ] `append(envelope)` writes `<id>.json` + `git commit`; `list_pending()`; dispatched-state via a `dispatched/<id>` marker file (so it survives sync, idempotent).
- [ ] **Test:** append 2 envelopes → both pending; mark 1 → 1 pending; re-append same content → no duplicate (same id).
- [ ] **Exit:** tests green; append never duplicates by id.

### Task 3.3: `drainer.py` — server-side router (the only new processing)
**Files:** Create `letta/offline/drainer.py`; Test `.../test_drainer_routing.py` (mock push-receiver + DB).
- [ ] For each new inbox-of-outbox envelope not yet dispatched: route by `target`/`verb` — generic command → POST to push-receiver (`:8099/push` with the agent + prompt from the envelope); task-class verb → existing `task_queue` insert path. Mark dispatched by id (idempotent: skip if already dispatched).
- [ ] Write the handler's result to `~/.letta/offline-bus/inbox/<reply_to>.json`.
- [ ] **Test (mocked):** a `verb=email.search` envelope → exactly one push-receiver call with the right agent+prompt; replaying the same envelope → zero additional calls; a `verb=task.extract` → one `task_queue` insert.
- [ ] **Exit:** routing + idempotency tests green; **no schema change** (assert only `task_queue` touched).

### Task 3.4: drainer launchd + end-to-end bus test
**Files:** `~/Library/LaunchAgents/com.ai-pa.offline-drainer.plist` (server; not git-tracked).
- [ ] Short interval / inbox WatchPath; logs to `~/Library/Logs/offline-drainer.log`.
- [ ] **Verify (live):** laptop offline → MC appends a `email.search` envelope to the outbox; reconnect → sync pushes it → drainer dispatches to email-agent via push-receiver → email-agent result lands in inbox → syncs back → MC reads it. Paste the inbox result + confirm one push only.
- [ ] **Exit:** a command issued offline runs exactly once on reconnect and its result returns to MC.

---

## Phase 4 — Connectivity-automatic model swap + MC offline-awareness

### Task 4.1: model-manager reads `link.json` and flips cloud↔local
**Files:** Modify `mc-model-manager` (add a connectivity input alongside rate-limit failover).
- [ ] When `online:false` → select `mc-local`; when `online:true` → restore the cloud model. Rely on the existing `cross_provider_compat` scrub hook for the signature edge across the swap.
- [ ] **Verify:** start a conversation online (cloud), drop network mid-thread → next turn served by `mc-local` (model footer/logs show it), reconnect → back to cloud, same thread, no signature error.
- [ ] **Exit:** model swaps automatically on the link transition with thread continuity; paste the before/after model indicator.

### Task 4.2: MC offline-awareness (capability gating)
**Files:** the MC system/runtime context that reads `link.json` + a static capability map (which agent needs which service).
- [ ] Offline: MC reasons "service X unreachable → draft + queue (don't attempt live)"; surface "queued — runs on reconnect" to the user.
- [ ] **Verify:** offline, ask MC to "email Bob" → it drafts + queues an envelope (no failed live call, no hang) and says so.
- [ ] **Exit:** offline requests are queued with an honest message, never a hang/silent failure.

---

## Phase 5 — Travel-mode flip + authority rule

### Task 5.1: `travel-mode.sh on|off|status`
**Files:** Create `scripts/offline/travel-mode.sh`.
- [ ] `on`: mark laptop as live conversational MC + memory shaper; set authority flag so the laptop only drafts/queues outward sends; signal home to run automation-only (e.g. a flag the server reads to skip live-conversation/outward-send autonomy attribution to the laptop). `off`: reverse; final sync; laptop returns to thin-client.
- [ ] **Verify:** `travel-mode on` → status shows laptop-primary + authority=home-sends; `off` → status shows home-primary.
- [ ] **Exit:** flip toggles the documented flags; a dry-run "send" offline is queued (not sent) under `on`.

### Task 5.2: authority enforcement (no double-send)
**Files:** the outward-send path (drainer + home send path) honors the authority flag.
- [ ] An outward-send envelope queued offline executes once, on reconnect, by the home owner; the laptop never sends directly while `travel-mode on`.
- [ ] **Verify:** queue a draft-send offline; reconnect; confirm exactly one send occurred (check the sent record) and the laptop made no direct send.
- [ ] **Exit:** single send, by home, idempotent on replay.

---

## Phase 6 — End-to-end MVP acceptance (the design §1 success criteria)

### Task 6.1: Full intermittent-cycle dry run
- [ ] **Continuity:** offline laptop MC exchange → reconnect → the exchange is in MC's one home thread (no duplicate agent/thread). Paste evidence.
- [ ] **Memory:** teach MC a preference offline → after reconnect it's in home MC memory, merged cleanly. Paste server `git log`/diff.
- [ ] **Command durability:** issue a fleet command offline across ≥2 simulated drops → runs exactly once → result returns. Paste push count + inbox result.
- [ ] **Automation co-existence:** confirm home fleet + briefings ran during the offline window and nothing collided (namespaced). Paste evidence.
- [ ] **No DB growth:** `psql` schema diff before/after shows no new tables/columns.
- [ ] **Exit:** all five acceptance checks demonstrably pass in the transcript.

---

## Deferred (not in this plan)
- Mirroring fleet slices (esp. tasks) onto MC for richer offline task work (design §9 deferred).
- Fully presence-automatic travel-mode trigger.
- Sync tuning + inbox→model reactivity refinement (design §10) — done against this running MVP, not pre-specified.

## Self-review notes
- **Spec coverage:** D1–D10 each map to a phase (D1→P1, D2/D5→P2.3, D3/D6→P4/P5, D4→P2.2, D7→untouched-by-design, D8/D9→P3, D10→P2/P3 transport). ✓
- **No-DB-table constraint:** asserted in Global Constraints + tested in Task 3.3 + Task 6.1. ✓
- **Discovery vs placeholder:** Phase 0/1 model choice is a measured discovery task with a recorded, verifiable output, not a TBD. ✓
- **Idempotency:** content-hash ids (3.1), dispatched markers (3.2/3.3), single-send (5.2) — consistent naming `id`/`idempotency_key` throughout. ✓
</content>
