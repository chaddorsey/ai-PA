# @ai-pa/continuity-controller

The resident **Continuity Controller** (plan `docs/plans/2026-08-15-006-feat-continuity-controller-plan.md`,
R21): the sole interactive WS client of the sole-owner Letta App Server. Two separately
supervised processes share one SQLite authority:

- **worker** — journaled, replay-complete subscriptions to every hot runtime; registry
  authority; forward-progress liveness (`sync` round-trip → atomic liveness file); later units
  add the turn pipeline (C4), the surface API (C5), scheduler ingress (C7), and routing (C8).
- **anchor** — subscribe-only, near-zero logic, read-only registry view. Its only job is being
  the *second* subscriber, which live-verified platform behaviour (C1 S1/S1proc) shows keeps a
  turn alive when the submitting connection dies — so the worker can restart without
  cancelling in-flight turns.

## Run

```bash
npm start                 # worker
npm run start:anchor      # anchor
npx tsx src/main.ts registry list
npx tsx src/main.ts registry add --agent <agent-id> [--label kinara] [--temp hot]
npx tsx src/main.ts registry set-temp --agent <id> --conversation <id> --temp cold
```

Env (see `src/config.ts`): `CONTINUITY_WS_URL` (default `ws://127.0.0.1:4577/ws`),
`CONTINUITY_STATE_DIR` (default `~/Library/Application Support/continuity-controller`),
`CONTINUITY_LIVENESS_INTERVAL_MS` / `_DEADLINE_MS`, `CONTINUITY_HOTSET_POLL_MS`.

launchd: tracked reference plists in `launchd/` (`com.ai-pa.continuity-controller`,
`com.ai-pa.continuity-anchor`) both exec `scripts/run-continuity-controller.sh <role>`; logs
under `~/Library/Logs/continuity-controller/`. Clone validation points `CONTINUITY_WS_URL` at
a clone server and `CONTINUITY_STATE_DIR` at a scratch dir — in the local plist copy only.

## State

Host-local SQLite (`controller.sqlite3`, WAL, dir 0700 / files 0600) — a deliberate deviation
from the Postgres-`pa_web` convention so the controller journals through Docker outages. A
corrupt db is set aside (never deleted) and the rebuild is **visible**: journaled
(`state_db_degraded`) and carried in the liveness file. Registry rows must reference CREATED
conversations — never the `default` alias (C1 S3: the alias is unresolvable by
`conversation_messages_list`, which C4's exactly-once reconciliation depends on).

## Surface protocol (C5)

Loopback WS on `CONTINUITY_SURFACE_PORT` (default 4610), path `/surface`,
**protocol_version 1** (`src/surface/protocol.ts`). Attach = first-frame auth with the 0600
token file (`<state>/surface-token`) → declare capabilities → name a runtime → journal replay
from your cursor (journal row id — gapless and duplicate-free by construction) + live events.

Capability sets (R28; unknown strings degrade with a warning, never a rejection):

| set | grants | degradation when absent |
|---|---|---|
| `core` | attach · replay · send · presence (mandatory) | — |
| `abort` | operator turn kill | feature absent |
| `approvals` | receive + answer approval requests (first answer wins) | another capable surface, else held-pending + unseen marker |
| `rail` | conversation CRUD (C9) | feature absent |
| `notify` | awareness rendering (C7) | unseen markers |
| `direct` | direct-lane addressing (C8) | feature absent |
| `subagent` | subagent-state rendering | feature absent |

Approval survival across controller restarts is **anchor-load-bearing** (live-probed): with no
second subscriber the parked turn and its approval are cancelled by the worker's detach; with
the anchor subscribed, reconnect re-broadcasts the pending `control_request`
(`recover_approvals` default). Proof P5: `test/live.approvals.contract.test.ts` on a
permission-flipped clone.

## Testing

```bash
npm run check                      # typecheck + biome + vitest (mock App Server, offline)
node ../tools/mutate.mjs --list    # the falsifiability harness; C3 entries are ids 64–72
```

Wire types bind to the vendor's `@letta-ai/letta-code/app-server-protocol` export at compile
time (`test/vendor-binding.compile.test.ts`); the devDependency is PINNED to the version the
supervisor runs. Behavioural pins live in the core package's opt-in live gates
(`live.contract.test.ts`, `live.detach-hold.contract.test.ts`) — run them against a clone at
every server version bump.
