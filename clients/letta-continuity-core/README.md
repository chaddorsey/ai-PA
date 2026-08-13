# @ai-pa/letta-continuity-core

Raw-WS client-core for the **sole-owner Letta App Server** (Multi-Surface Agent Continuity, Milestone 1 — Unit 4). Both M1 clients (terminal, web) import this one module; it speaks the App Server's full `/ws` protocol on a **single ordered connection**.

- Plan: `docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md` (Unit 4)
- Protocol (empirical, `letta 0.30.19`, `ws://127.0.0.1:4577/ws`): `docs/plans/2026-08-12-multi-surface-ws-spike-findings.md` §C/§E + Unit 4 live captures

## Why raw-WS-primary

Unit 1 proved a single `/ws` connection receives **all** broadcasts for a subscribed `{agent, conversation}` — own turns, foreign turns, and `update_subagent_state` — each frame carrying a per-connection monotonic `event_seq`. There is **no second observer connection and no cross-stream merge**. The `@letta-ai/letta-agent-sdk` covers only runtime/session/stream (not conversation CRUD, approvals, or subagent state), so the core speaks raw WS directly. **No SDK dependency.**

## Modules

| File | Responsibility |
|------|----------------|
| `src/protocol.ts` | **The sole home of every frame string + shape.** Builders, parsers, strict `validateInboundFrame` drift guards, `event_seq`/`delta.id` extractors, and the WS-hello server-version assertion. Nothing framing-related lives elsewhere. |
| `src/ws.ts` | One loopback WS connection: hello handshake, `request_id`-keyed RPC, **every wait bounded** (open/hello/RPC timeouts). No retry loop. |
| `src/stream.ts` | One ordered event stream keyed by per-connection `event_seq`; turn boundaries from `turn_finished`/`loop_status`. Renders own **and foreign** turns identically. |
| `src/catchup.ts` | Reconnect snapshot (`conversation_messages_list`) + **message-id watermark dedup** (`delta.id`, never `event_seq` — it resets per connection). |
| `src/connection.ts` | `connected` / `reconnecting` / `disconnected` state machine with a **bounded** reconnect budget. |
| `src/pointer.ts` | Reads the durable `{agent, conversation}` state file (a real UUID — never `default`, never recency). |
| `src/index.ts` | `ContinuityCore` facade wiring it all together, incl. approval **fail-closed** and reconnect→catch-up. |

## Approval policy (M1)

Approvals **fail closed**. The *injecting* client auto-sends `approval_send=deny` on any `approval_request_message` so an approval-gated turn resolves to a bounded deny, never hanging both surfaces. **Observers never respond** (no duplicate responses). The full `allow` round-trip is the rail/approval milestone.

## Server-version assertion

The App Server (0.30.19) exposes **no version field** anywhere (hello, `/v1/models`, `/version`). `assertServerVersion` future-proofs against a later build adding `server_version`/`version` to the hello; today it warns "unverifiable" and the **committed contract test is the real upgrade gate**.

## Contract test = the upgrade gate

`test/protocol.contract.test.ts` round-trips a canonical fixture of every used frame and **fails loudly** on drift (renamed/removed field). On a `letta` server upgrade, updating the fixtures is the deliberate, reviewed step that unblocks it — silent mis-parse is impossible.

## Commands

```bash
npm install
npm run typecheck   # tsc --noEmit
npm run lint        # biome check
npm test            # vitest (55 tests, deterministic, offline)
npm run check       # all three

# Opt-in live check against the real App Server (skipped by default):
LETTA_LIVE_WS=1 npx vitest run test/live.contract.test.ts
```

The default suite is fully offline against an in-process mock App Server (`test/helpers/mockServer.ts`) that emits the exact empirical 0.30.19 frames.
