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

## B: mod API — connectivity-failover  ⚠️ API SURFACE VERIFIED; authoring blocked on tooling (decision needed)

### Verified (from the bundle — `letta.js`, no `src/`)
- **Mods load dir:** `getGlobalModsDirectory() → ~/.letta/mods` (currently empty). Loaded at session start; disable with `letta --no-mods` or `LETTA_DISABLE_MODS=1`.
- **Hooks present in the runtime:** `onTick` (periodic/timer event — ideal for polling `link.json`), `onTurn`, `setModel`/`updateModel` (model swap; also `update_model`), `statusline` registration (`statuslineRenderer`, `statuslineContext`), `registerModTool` / `registerModPermission` (+ `…ForOwner` variants), `ModContext`.
- Mods run in-process (Node) so an external-file read of `~/.letta/offline-bus/link.json` is straightforward.

### Blocker (why the proof mod isn't built yet)
- letta-code ships **bundled/minified** — there is **no `src/mods/types.ts` / `mod-engine.ts`** to read, and **no shipped mod template, example, README section, or `letta mods` scaffolder**.
- The plan's intended authoring path — the **`creating-mods` skill** — is an **in-harness skill of the letta-code agent**, NOT available in the Claude Code harness doing this spike. Reconstructing the exact mod **export contract** (how `onTick`/`setModel`/`statusline` are registered/exported by a mod module) from the minified bundle is feasible but error-prone — the kind of thrash the brief says to avoid.

### Decision needed (see report) — two paths to finish Spike B
1. **(Recommended) Run `creating-mods` from a letta-code session.** A letta-code agent (the hub MC, or a scratch agent) runs the in-harness `creating-mods` skill to scaffold + author the `connectivity-failover` proof mod per Spike B steps; it has the correct API reference. This spike is genuinely a *letta-code-harness* task, not a Claude Code one.
2. **Reverse-engineer from the bundle.** Claude Code reconstructs the mod export contract from `letta.js` and hand-authors the proof mod, validating by install + launch. Slower, higher risk of an invalid contract.

## B (cont.) — not yet built
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
## C: fleet from spoke  ⏳ not started
