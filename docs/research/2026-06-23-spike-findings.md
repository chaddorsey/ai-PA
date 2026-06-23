# Phase 1 Spike Findings — Laptop Spoke #1

> Verified facts that gate the Phase-2 build. Laptop `cd-macbook`, 2026-06-23.

## A: memfs mount — distinct agent + shared canonical memfs  ✅ MECHANISM PROVEN (read + write + commit)

### The mechanism (source-grounded)
letta-code (`@letta-ai/letta-code`, installed bundled at `/opt/homebrew/lib/node_modules/@letta-ai/letta-code/letta.js`; no `src/`, read the bundle + `dist/types`). The memfs root is computed **purely from the agent ID**:

```js
getLocalBackendMemoryFilesystemRoot(agentId, storageDir) → join(storageDir, "memfs", agentId, "memory")
getLocalBackendStorageDir() → process.env.LETTA_LOCAL_BACKEND_DIR ?? ~/.letta/lc-local-backend
getScopedMemoryFilesystemRoot(agentId) → getLocalBackendMemoryFilesystemRoot(agentId, storageDir)
getActiveMemoryDirectory(agentId) → getScopedMemoryFilesystemRoot(agentId)   // MEMORY_DIR is NOT consulted here
```

- The **memfs git layer** (load / watch / commit) **always** uses `<LETTA_LOCAL_BACKEND_DIR>/memfs/<agentId>/memory`. It does **not** consult `MEMORY_DIR`.
- `MEMORY_DIR` (read as `inheritedMemoryDir = process.env.MEMORY_DIR`) only roots the **file-tool** path resolution / apply-patch target. This is why it must **equal** the scoped path (gotcha #1): otherwise the file tools and the git layer disagree (split-brain).
- **Therefore:** you cannot point a distinct agent at canonical via `MEMORY_DIR` alone. The mount must happen at the **filesystem path** `memfs/<agentId>/memory`.

### Recommended mount: a git **clone** of the canonical lineage (design-aligned, concurrency-safe)
Make `memfs/<newId>/memory` an independent **clone** of the canonical memfs repo (own working tree, shared Gitea remote). This matches the design ("one canonical memfs lineage, cloned by every facet"). A **symlink to the canonical working tree** also works for reads but is **NOT recommended**: two agents/runtimes sharing one working tree can corrupt it / trip the git guard. Use a clone.

### Verified recipe (copy-pasteable)
```bash
# 1. Create a distinct LOCAL agent (force local backend + a valid local model handle):
letta --backend local agents create --model ollama/GLM-4.5-Air-4bit \
  --personality blank --name <name> --tags "<tags>"
#    → returns JSON with the new id, e.g. agent-local-<uuid>

# 2. Replace its fresh per-agent memfs with a clone of canonical:
NEW=agent-local-<uuid>
STORE=$HOME/.letta/lc-local-backend
CANON=$STORE/memfs/agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d/memory
rm -rf "$STORE/memfs/$NEW/memory"
git clone -q "$CANON" "$STORE/memfs/$NEW/memory"   # read-test used the local canonical repo
#    For the REAL mini-me, clone from the Gitea remote URL (the canonical lineage),
#    not the local path, so folds push to canonical:
#    git clone -q "http://<token>@127.0.0.1:3030/agents/agent-local-8474bbbd-....git" \
#      "$STORE/memfs/$NEW/memory" && git -C ... checkout travel/laptop   # (branch TBD, see open item)

# 3. Required agent setting (gotcha #3):
AJSON=$STORE/agents/$(printf '%s' "$NEW" | base64).json
python3 -c "import json;d=json.load(open('$AJSON'));d['message_buffer_autoclear']=False;json.dump(d,open('$AJSON','w'),indent=2)"

# 4. Launch from a launchpad dir (NOT the memfs), MEMORY_DIR = the new agent's own scoped path:
cd $STORE/../launchpad   # any non-memfs dir
export LETTA_LOCAL_BACKEND_DIR="$STORE"
export MEMORY_DIR="$STORE/memfs/$NEW/memory"
letta --backend local --agent "$NEW" ...
```

### Proof (this spike, on throwaway `agent-local-8d425a73-4573-4fec-9fd0-015eef5f1ecc`)
- **Read:** the distinct agent read canonical `system/human.md` (content quoted) and counted `reference/` (1 file). ✅
- **Write:** it created `system/spike_a_probe.md`, committed `6f1855b` on top of `9b1954c`, working tree clean (no git-guard error). ✅
- **Isolation:** canonical (`agent-local-8474bbbd…`) stayed at `9b1954c` — writes live in the spoke's clone until an explicit fold. ✅
- **Throwaway deleted** (memfs, agent JSON, conversations, settings entry) after the proof. Live fold to Gitea skipped by decision (no canonical pollution); HUB-confirm item deferred to the real mini-me / Phase 3.

### Gotchas / safety
- Each spoke needs its **own clone** (not a shared working tree). Symlink-to-shared-tree is unsafe under concurrency.
- The fresh agent's per-agent memfs (with its blank `persona.md`) is **discarded** by the clone; the spoke adopts canonical's blocks/persona. (Intended — it's a Kinara facet over shared memory. The spoke's distinct *persona* layer is a Phase-2 design choice, not a memfs-mount concern.)

### NOT exercised here (needs a decision + HUB confirmation — see report)
- **Fold to Gitea `main`** (plan Task 1 Step 3): NOT run on the throwaway, to avoid polluting canonical `main` with a test probe. The fold itself is existing validated substrate (`sync-runner.sh`); it gets exercised by the real mini-me (Task 5) + Phase 3 under coordination. **Open item:** for the real mini-me the clone's `origin` must be the **Gitea URL** (not the local path), and the **branch strategy** (shared `travel/laptop` vs a per-spoke branch) is unresolved — flag for the Phase-2 plan.

---

## B: mod API — connectivity-failover  ✅ FULLY RESOLVED (API verified, proof mod loads clean, model-swap mechanism closed)

### Verified (from the bundle — `letta.js`, no `src/`)
- **Mods load dir:** `getGlobalModsDirectory() → ~/.letta/mods` (currently empty). Loaded at session start; disable with `letta --no-mods` or `LETTA_DISABLE_MODS=1`.
- **Hooks present in the runtime:** `onTick` (periodic/timer event — ideal for polling `link.json`), `onTurn`, `setModel`/`updateModel` (model swap; also `update_model`), `statusline` registration (`statuslineRenderer`, `statuslineContext`), `registerModTool` / `registerModPermission` (+ `…ForOwner` variants), `ModContext`.
- Mods run in-process (Node) so an external-file read of `~/.letta/offline-bus/link.json` is straightforward.

### The bundle IS readable source (key correction)
letta-code ships as an **esbuild bundle that preserves the original `// src/…` sections** — so `src/mods/{mod-engine,context,event-emitter,mod-adapter,tool-registry,permission-registry}.ts` are all legible in `letta.js`. No in-harness skill was required to read the contract.

### Verified mod contract (from `letta.js`)
- **Mod files** live directly in `~/.letta/mods/` (the engine's `listModFiles` reads *files*, not subdirs; `MOD_FILE_EXTENSIONS = {.js, .mjs, .ts, .tsx}`; `.ts/.tsx` are transpiled via `ts.transpileModule`; loaded as ESM via `import(pathToFileURL)`). Disable with `letta --no-mods` / `LETTA_DISABLE_MODS=1`.
- **Export contract:** `getModFactory(module) → module.default (function) ?? module.activate`. So a mod is `export default function activate(letta) { … }`.
- **The `letta` API object** passed to `activate` (from `loadLocalMods`):
  - `events: { on(name, handler), off }` — subscribe to events; **`tick`** is the periodic hook (also `session_start`, `session_end`, `tool_start`).
  - `ui: { setStatus(key, text), setStatuslineRenderer(renderer), setStatus removal via null, openPanel(...) }` — statusline; `setStatus` takes a string value (gated by `capabilities.ui.statusValues`).
  - `commands: { register({ id, description, run }), unregister }` (gated by `capabilities.commands`).
  - `tools: { register(tool), unregister }`, `providers: { register(name, config) }`, `permissions: { register(p) }`, `client` / `getClient` (a Letta client), `capabilities`, `signal`.
- **Diagnostics:** written to `~/.letta/mods/diagnostics/latest.json` (`{report:{diagnostics,errorCount,warningCount}}`).

### Proof mod (built + committed): `scripts/offline/mods/connectivity-failover/connectivity-failover.mjs`
- On `tick`, reads `~/.letta/offline-bus/link.json` and sets statusline `connectivity` to `🟢 online · cloud` / `🔴 offline · local` / `⚪ link?`. Registers a `/connectivity` command reporting link + intended failover model.
- **Validated (self-contained):** installed to `~/.letta/mods/connectivity-failover.mjs`, launched letta-code headless → **`diagnostics/latest.json`: errorCount 0, warningCount 0** (the mod's `export default activate`, `events.on('tick')`, `ui.setStatus`, `commands.register` all loaded + ran without error).

### Model-swap mechanism (Task 6, Step 0) — RESOLVED BY TEST → **external watcher**
Empirical app-server test (`letta --backend local app-server --listen ws://127.0.0.1:4500`, WS v2 frames, scratch agent swapping `qwen2.5:0.5b` ↔ `qwen2.5:7b-instruct`, model read from the conversation transcript per turn):

| Turn | After | Model the turn actually used |
|---|---|---|
| 1 | baseline | `qwen2.5:0.5b` |
| 2 | **config update** (agent JSON `model`→7b, == what `client.agents.update({model})` does) | `qwen2.5:0.5b` — **NO live-swap** |
| 3 | **WS `update_model`** (→7b; resp `success:true, applied_to:"conversation"`) | `qwen2.5:7b-instruct` — **swapped** ✅ |

**Conclusions (definitive):**
- A **config update does NOT re-model a running conversation** — the runtime keeps its loaded model. So the mod-internal `client.agents.update({model})` path is **insufficient** for a live spoke session (it would only take effect on a brand-new session, not the next turn of an open one).
- The **WS `update_model` command DOES live-swap** (conversation-scoped, via `applyModelUpdateForRuntime`). But it is an **app↔runtime WsProtocol frame** — there is **no mod-facing way to send it** (no mod dispatch; command results limited to `prompt|output|handled`).
- **DECISION → the brief's fallback: an external watcher.** The connectivity mod stays **observability-only** (detect link on `tick` → statusline + write `~/.letta/offline-bus/mode.json`). A separate **`scripts/offline/model-swap-watcher.mjs`** reads `mode.json` and, on a transition, sends an `update_model` WS frame to the running app-server runtime (the exact frame shape is verified: `{type:"update_model", request_id, runtime:{agent_id,conversation_id}, payload:{model_handle}}` on the `control` channel; verified to live-swap).

**Proof-mod consequence:** the `swapModel()` (client.agents.update) path in the current proof mod is **wrong for live swap** and will be removed when Task 6 is built — the mod becomes detect→statusline→`mode.json`; the watcher does the swap. (Proof mod still validates the observability half + loads clean.)

### Verified WS frame shapes (for the watcher — Task 6)
- App-server: `letta --backend local app-server --listen ws://127.0.0.1:<port>`; channels `…/ws?channel=control` (commands+responses) and `…/ws?channel=stream` (deltas).
- `runtime_start`: `{type, request_id, agent_id, conversation_id | create_conversation}` → `runtime_start_response{success, runtime:{agent_id,conversation_id}, agent}`.
- `update_model`: `{type, request_id, runtime, payload:{model_handle | model_id}}` → `update_model_response{success, applied_to:"agent"|"conversation", model_handle}`.
- `input` (turn): `{type:"input", runtime, payload:{kind:"create_message", messages:[{role,content}]}}`.

### ⚠️ SUPERSEDED by Option C (LiteLLM proxy) — see the Option C section below
The Step-0 finding above (config-swap doesn't live-swap; only the WS `update_model` does; mods can't send it) stands as *fact*, but the **chosen design is Option C: a local LiteLLM failover proxy**, which removes the need to swap the model at all. The watcher / app-server path is **dropped**. The mod is now **observability-only**. Kept above for the record + the verified WS frame shapes.

## C: fleet from spoke  ✅ RESOLVED (spoke-callable path verified; direct DB is not, outbox covers it)

### What `task_queue` is
`pa_web.task_queue` is a **Postgres table** (schema `pa_web`), enqueued by `INSERT INTO pa_web.task_queue (source, source_ref, payload)` (slackbot, task-completion-service, gmail-watch-service). It is **not an HTTP endpoint**.

### Reachability from the laptop (verified, read-only)
- **Letta hub API `http://dorseys-mac-mini:8283` — REACHABLE + AUTHED.** `GET /v1/agents/?limit=3` with the laptop's existing `LETTA_API_KEY` (`~/.letta/settings.json` → `env.LETTA_API_KEY`, `at-let-…`) returned **HTTP 200** + agent list. So the laptop can invoke hub/fleet **agents** directly over the network (`POST /v1/agents/{id}/messages`).
- **Postgres `task_queue` — NOT reachable.** `dorseys-mac-mini:5433` and `:5432` are closed from the laptop (bound `127.0.0.1` on the server, per docker-compose). No direct DB enqueue from the spoke.
- **SSH-tunnel substrate is live:** `autossh -M 0 -N -L 3030:127.0.0.1:3030 dorseyhomeserver@100.99.171.119` running; `localhost:3030` (Gitea) → 200.

### Verdict (spoke-callable fleet, today)
1. **Direct, online path = the Letta hub API (`:8283`) with the laptop's `LETTA_API_KEY`.** Agent-mediated fleet actions are callable over the network now. *(A live mutating call — actually enqueuing/sending — was NOT performed: that's a fleet world-action needing HUB confirmation. Reachability + auth are proven; landing confirmation is a HUB/COORD touchpoint.)*
2. **Direct DB enqueue to `task_queue` is NOT spoke-callable** (loopback-only). Options if ever needed: (a) route through the hub Letta API (recommended, reuses `:8283`); (b) forward Postgres over an SSH tunnel + ship DB creds to the laptop (adds secret exposure — avoid); (c) **the existing `outbox → server drainer` already inserts into `task_queue` server-side** — so offline-queued actions need **no** laptop DB access.
3. **No blocker for the spine.** Online+capable → call the Letta API (`:8283`); offline → outbox→drainer (existing). The plan's "ship offline-queue-only for not-directly-callable actions" is satisfied; direct DB access is explicitly unnecessary.

### For Task 7 (action routing)
`capable=True` for the action set reachable via `:8283` with `LETTA_API_KEY` while online; everything else (or offline) → `queue`. Auth = the existing `LETTA_API_KEY`; no new creds needed for the API path.

---

## Task 7 wiring rule (the binding rule for the persona/recipe) — built
`letta/offline/routing.py::route_action(link, capable)` returns `"direct"` | `"queue"` (3 unit tests green). The persona/mod, **before any irreversible/external action**, applies:

1. Read `link` from `~/.letta/offline-bus/mode.json` (written by the connectivity mod; `"online"|"offline"`).
2. `capable` = is this action in the Spike-C spoke-callable set (reachable via Letta API `:8283` with `LETTA_API_KEY`)?
3. `route = route_action(link, capable)`:
   - **`"queue"`** → append an `Envelope` (`letta/offline/envelope.py`, idempotency key = content hash) to the **outbox** (`letta/offline/outbox.py`); the hub drainer executes it **exactly-once** on reconnect.
   - **`"direct"`** → perform the action now via the Spike-C path (Letta API `:8283`).

Mutually exclusive (Invariant 1): an action is **either** queued **or** executed directly, never both — the idempotency key is the backstop across an offline→online transition.

## T4/T7 build status (this push)
- **T4 presence-lease:** `letta/offline/lease.py` + `tests/test_lease.py` (4 ✅) + `scripts/offline/lease-heartbeat.sh` (verified writes `lease.json`; TTL default 180s, cadence « TTL). *Matched repo convention: flat imports via `tests/conftest.py`; heartbeat imports `letta.offline.lease` (namespace pkg) from repo root.*
- **T7 action-routing:** `letta/offline/routing.py` + `tests/test_routing.py` (3 ✅) + the wiring rule above.
- Full offline suite: **19 passed** (`uv run --with pytest --python 3.12 pytest letta/offline/tests/`).
- **T5 mini-me agent:** `scripts/offline/setup-laptop-minime.sh` (decision-1: Gitea-URL clone of canonical, `spoke/laptop` off `main`, `.letta/` gitignore safeguard, `message_buffer_autoclear:false`, records `~/.letta/offline-bus/minime.json`). Ran it → mini-me `agent-local-12d6fd5f-79bc-4132-8348-6afa71795753` on `spoke/laptop`. **Verified:** reads canonical `system/human.md`+`reference/`; a write commits cleanly on `spoke/laptop` (then reverted). **Fold `spoke/laptop→main` is HUB-coordinated** (not done solo; canonical `main` untouched). Persona is shared via canonical memfs (distinct facet-persona deferred — see §A note).
- **T6 connectivity mod (Option C):** rewritten **observability-only** — `scripts/offline/mods/connectivity-failover/connectivity-failover.mjs` reads `link.json` on `tick` → statusline (`🟢 online · cloud` / `🔴 offline · local`) + writes `~/.letta/offline-bus/mode.json` (the contract `routing.py` reads). No model swap. Loads clean (0/0); writes `mode.json` on activate. Visual statusline flip is a TUI-only in-session check (you).
- **Pending (server-gated):** the proxy **primary** (server LiteLLM) — needs `LITELLM_MASTER_KEY` + the server model alias (secrets/info); T8 (reconnect; HUB-confirm fold + exactly-once drain).

---

## Option C — LiteLLM failover proxy (the chosen model architecture)
**Decision:** the mini-me always points at a **local LiteLLM proxy**; the proxy does the failover transparently, so the agent's model handle never changes (no swap, no watcher, no app-server).

- **Proxy:** `scripts/offline/litellm-proxy/{config.yaml,start-proxy.sh}` (litellm `[proxy]` in `~/.letta/litellm-venv`), listens `127.0.0.1:4000`. Models:
  - `mc-brain` — **primary** = server LiteLLM `http://dorseys-mac-mini:4000/v1` (reachable over the **tailnet**, no tunnel); **fallback** = local GLM (oMLX `:8000`). `litellm_settings.fallbacks: [{mc-brain:[mc-brain-local]}]`.
  - `mc-brain-local` — local GLM (oMLX). `GLM-4.5-Air-4bit` — passthrough (keeps the existing `letta-mc` daily driver working).
- **Wiring:** letta `ollama` provider `base_url → http://127.0.0.1:4000/v1`, key `sk-mc-local`; mini-me model `ollama/mc-brain`. `letta-mc` gate now also ensures the proxy.
- **Verified:** primary unreachable → request to `mc-brain` **falls back to local GLM** (proxy log: `mc-brain-local`); with the real primary but no key, the 401 also **falls back to GLM**; the mini-me **reads canonical through the proxy** end-to-end. So offline already works; the cloud primary activates the moment the server key + model alias land.
- **Server-gated (the only remaining piece for online):** `LITELLM_MASTER_KEY` + the server LiteLLM model alias for `SERVER_MODEL_HANDLE` (provision to the laptop / set in `start-proxy.sh` env). Until then the proxy serves the local GLM fallback for everything.
