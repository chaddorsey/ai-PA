---
date: 2026-06-01
status: spec (awaiting prioritization)
type: architectural-change
scope: pa-web-ui → local-mode fleet
predecessor: 2026-05-31-mc-migration-plan.md
---

# pa-web-ui local-mode handoff — spec

Move pa-web-ui from talking to the Docker-mode fleet to talking to
the local-mode (lc-local-backend) fleet. Kills the two-headed runtime
pattern we've been carrying since the 5-agent migration started 2026-04.

## Why

After today's MC migration (2026-06-01), the fleet has the same
two-headed pattern for all 6 agents:

| Surface | Backend | Where today's edits live |
|---|---|---|
| `letta-*` TUI launchers | Local backend (`lc-local-backend`) | Today's audit fixes, fleet_awareness, canonical sync |
| pa-web-ui browser UI | Docker Letta server | Pre-2026-06-01 recipes (still uses `run_slack(...)` syntax, no fleet_awareness, still references identity blocks) |

The two-headed pattern was deliberate as a rollback-safety move during
per-agent migrations. Now that all 6 agents are migrated and proving
stable, we should consolidate. The downsides of staying two-headed:

- Every recipe / memfs edit has to land in two places (local working
  tree + Docker Gitea repo) or it diverges
- User experience differs between TUI and browser, which is
  surprising/confusing
- We're maintaining Docker agent records, Docker memfs Gitea repos,
  and Docker-side tool attachments we don't actually need anymore
- pa-web-ui's `letta-bg-fix-sidecar` exists to work around silent
  stalls on the Docker server path; local mode may avoid that
  problem entirely (worth confirming, would let us retire the sidecar)

## Current state (verified 2026-06-01)

- pa-web-ui runs in Docker (`pa-web-ui` container), `PA_WEB_UI_PHASE_1_ENABLED=true`
- Subprocess pool spawns `letta-code` subprocesses against
  `LETTA_BASE_URL=http://letta-bg-fix-sidecar:8284` (which proxies to
  the Docker Letta server `letta:8283`)
- `FLEET_AGENT_NAMES` dict (app.py:2740) has Docker agent IDs for all
  6 fleet agents
- `MISSION_CONTROL_AGENT_ID` env defaults to Docker MC's ID
  (`agent-90b2e860-...`); the Docker agent record was renamed to
  `XXX-PRE-LOCAL-Mission-Control` but the ID is preserved so
  pa-web-ui still resolves it
- 32 conversations in `pa_web.conversation_meta`, all keyed by Docker
  agent IDs
- LettaBot retirement (2026-06-01) removed the `LETTABOT_API_URL`/
  `LETTABOT_API_KEY` env path; the fallback code at app.py:2393-2416
  is dead code today

## Architectural options

Three viable approaches. Tradeoffs differ on container/host boundary
philosophy, code-change surface, and operational complexity.

### Option A — Bind-mount + flag flip (least architecture change)

Mount the host's `~/.letta/lc-local-backend/` into the pa-web-ui
container; spawn `letta --backend local` instead of relying on API
mode.

**Pros:**
- Smallest code diff — mostly compose + a single `--backend local` flag
  on the spawn command
- Conversation continuity model unchanged (subprocess per conv_id, etc.)
- Both Docker and local modes can coexist during rollout via env flag

**Cons:**
- Host filesystem leaks into container (permissions, UID mapping,
  potential corruption if multiple processes write the same files)
- Local-mode providers (LM Studio, future ChatGPT OAuth) require the
  container to access host network and `~/.letta/lc-local-backend/providers/auth.json`
- Memfs working trees are now host-managed; if pa-web-ui's container
  rebuilds or restarts, the working tree state could get inconsistent
  with what TUI users wrote

### Option B — Run pa-web-ui on host (eliminate container boundary)

Move pa-web-ui out of Docker entirely. Run as a launchd-managed
process on host. Eliminates the container/host boundary for the
backend access.

**Pros:**
- Cleanest model: pa-web-ui is "just another local-mode client" like
  the TUI launchers, no special filesystem-sharing or auth proxying
- Probably faster (no container overhead, no sidecar)
- Aligned with the broader direction of reducing Docker surface area
- Can use the same `letta --backend local` invocation pattern as
  `letta-mc` etc.

**Cons:**
- Biggest deployment-shape change: docker-compose entry removed,
  launchd plist added, port mapping moves from Docker to host
- Postgres connection now goes over host port (5433) instead of
  Docker-internal (`supabase-db:5432`) — already supported by other
  CLIs but pa-web-ui's connection strings need updating
- Process supervision via launchd is different from Docker's
  restart-policy + healthcheck; ops semantics change
- Web access path changes (was `:5200` via Docker network, becomes
  `localhost:5200` via host) — fine for local use, matters if any
  external tunnel points at it

### Option C — Local-backend proxy service (most code, most flexible)

Build a thin host-side HTTP proxy that exposes the lc-local-backend
file operations as the Letta API surface. pa-web-ui in Docker keeps
its current API-mode subprocess pool; proxy translates to local
backend operations.

**Pros:**
- pa-web-ui code essentially unchanged (still uses API mode, just
  points at the proxy URL)
- Clean separation of concerns
- Can run multiple Docker clients against the same local backend
  without filesystem-sharing issues

**Cons:**
- Most code to write — building a Letta-API-compatible HTTP server
  over the local backend is non-trivial
- Yet another service to maintain and version-track against letta-code
- letta-code's API surface evolves; the proxy is a moving target

## Recommended path

**Option B (run pa-web-ui on host)** — strong recommendation, with one
caveat below.

Reasoning:
1. We've been moving toward "less Docker" all year. Putting more host
   filesystem inside the Docker container (Option A) goes the wrong
   direction.
2. The TUI launchers already prove the host-process-against-
   lc-local-backend pattern works cleanly. pa-web-ui-on-host is the
   same pattern with a Flask wrapper.
3. Option C is too much custom code for the value; we'd be building
   our own Letta server.

**Caveat:** Option B requires deciding what to do with the Docker
`pa-web-ui` container entry. Two sub-options:

- **B1**: Remove the docker-compose entry, run only on host via
  launchd. Single source of truth.
- **B2**: Keep the docker-compose entry as a fallback / non-fleet-
  agent path (talks to Docker Letta), add host-side launchd for the
  fleet-agent path. More moving parts but preserves rollback.

B1 is cleaner; B2 is safer for the first cutover. Default to B2 for
the migration, fold to B1 once soak ends.

## Scope of changes

If Option B/B2:

1. **pa-web-ui launchd plist** — new `~/Library/LaunchAgents/com.ai-pa.pa-web-ui.plist`, env block matching what the Docker container has (POSTGRES_PASSWORD, GITEA creds, Letta env, etc., plus the `letta --backend local` defaults)
2. **FLEET_AGENT_NAMES dict** — update with local agent IDs:
   ```
   "agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d": "Mission Control",
   "agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4": "Tasks",
   "agent-local-cd5ed5cd-44d5-4e32-b202-3d8dfcb5505c": "Calendar",
   "agent-local-d48b128a-b3a8-4930-a27f-b4127c96fe3a": "Pulse",
   "agent-local-3898b33a-2249-4f1c-9478-26a9aad26d4a": "Documents",
   "agent-local-93241bd6-ce9c-4ea6-89ca-318a6d873b0f": "Email",
   ```
3. **Subprocess spawn command** — add `--backend local` to the `letta`
   invocation in `subprocess_pool.py:_default_spawn_factory`
4. **MISSION_CONTROL_AGENT_ID env** — point at local MC ID
5. **Database connection** — pa_web access continues via `psycopg`
   to localhost:5433 (already the host-mapped port; no change inside
   pa-web-ui code, just config)
6. **LETTA_MEMFS_GIT_URL** — verify behavior with local backend. The
   memfs subprocess flag may not apply the same way for local agents
   (since their working tree is the source of truth, not Gitea). May
   need to drop `--memfs` from spawn command for local mode.
7. **letta-bg-fix-sidecar** — verify whether local mode exhibits the
   silent-stall issue. If not, retire the sidecar; if yes, decide
   whether to route through it or accept the stall risk
8. **Docker compose entry** — leave in place for B2 cutover; remove
   after soak

## Conversation continuity / data migration

This is the tricky part. Existing `pa_web.conversation_meta` rows
reference Docker agent IDs. Two sub-questions:

1. **Existing conversations** — when the user reopens a conversation
   that was started against Docker MC (`agent-90b2e860-...`), what
   happens?
   - **Option 1: Migrate the rows** — `UPDATE pa_web.conversation_meta
     SET agent_id = '<local-id>' WHERE agent_id = '<docker-id>'`.
     Conversations continue against the local agent, conversation
     history is whatever the local agent's conversation file has at
     that conv_id.
   - **Option 2: Hard cutover** — old conversations stay Docker-bound
     (read-only, archived). New conversations go to local. Users
     start fresh.
   - **Option 3: Leave it to natural decay** — Docker mode stays
     available for old conversations (B2 path); new conversations
     default to local. Old conversations slowly die off.

   Recommend Option 3 with a "you are talking to the legacy Docker
   MC, want to start a new conversation against local MC?" surface in
   the UI when an old conversation is reopened. Less surprising.

2. **Conversation ID format** — local-mode conversations have IDs
   like `local-conv-21` (per the smoke tests today). Docker IDs are
   like `conv-c50ef874-...`. The UI needs to handle both formats
   gracefully.

## Open questions

1. Does `letta --backend local` support `--output-format stream-json`
   and `--input-format stream-json` the same way Docker mode does?
   (Subprocess pool depends on this.)
2. Does the memfs flag `--memfs` work with local-backend agents, or
   is the local working tree always available without the flag?
3. Provider auth: do `letta connect chatgpt` tokens stored in
   `~/.letta/lc-local-backend/providers/auth.json` work for the
   subprocess pool's spawned processes when invoked from a different
   Flask process?
4. Does `pa_web.conversation_meta` schema need any new columns to
   distinguish Docker-mode from local-mode conversations? (e.g., a
   `backend` column?)
5. Will the auto-naming feature (in-band litellm call) work the same
   way for local-mode agents?
6. What's the expected behavior if a user opens pa-web-ui while a
   `letta-mc` TUI session is already running against the same agent?
   Conflicting concurrent access to the local agent's conversation
   files could corrupt state. May need a "TUI session detected,
   read-only mode" surface.

## Effort estimate

| Phase | Effort |
|---|---|
| A — Validate open questions (especially #1 and #2) | 1-2 hr |
| B — Build pa-web-ui launchd plist + host-mode startup | 1-2 hr |
| C — FLEET_AGENT_NAMES + spawn factory edits | 1 hr |
| D — Conversation-meta migration strategy decision + impl | 1-3 hr |
| E — End-to-end test of all 6 fleet agents via pa-web-ui-on-host | 2 hr |
| F — Cutover + soak + Docker-entry retirement (B2 → B1) | 1 hr active + 1-2 wk soak |

**Total active: ~7-11 hours** + soak. Smaller than MC migration.

## Out of scope

- Migrating non-fleet agents (the smaller agents we have records for
  but don't use in pa-web-ui) — they can stay Docker-mode forever
- Replacing pa-web-ui itself with a different UI framework
- Adding new pa-web-ui features (auto-naming, fork, multi-device are
  all already shipped)

## Related work / dependencies

- Today's audit fixes (run_*, fleet_awareness, etc.) all apply to
  local memfs trees; pa-web-ui's Docker memfs would also need them
  if we stay two-headed long-term. Doing the local-mode handoff
  obsoletes the need to mirror.
- Soak end for MC (1-2 weeks from 2026-06-01) is a natural moment to
  decide between "mirror to Docker memfs to preserve two-headed" vs
  "kill two-headed via this spec."
- letta-bg-fix-sidecar retirement (per MEMORY this was deployed for
  silent-stall #99; revisit after local-mode confirmed stable).

## Rough sequencing relative to other pending work

This is **not urgent** — pa-web-ui works fine today against Docker.
Sequence after:
1. MC soak completes cleanly (~mid-June)
2. Any post-soak detachment/cleanup of Docker MC tools (lower
   priority but should land first)
3. THEN consider this spec — by which point we'll have more soak data
   to inform open questions #3 and #6

If you find yourself wanting to be in pa-web-ui daily and noticing
the recipe gap, that's the trigger to start. Otherwise, defer.
