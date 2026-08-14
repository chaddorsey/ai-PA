# letta-terminal

Text-first terminal surface for the sole-owner Letta App Server — Unit 5 of
[the M1 continuity plan](../../docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md).

It attaches to the `{agent, conversation}` named by the continuity pointer and streams that
conversation live. Turns typed here and turns from any other surface appear in the same
transcript, labelled by origin.

```
you › what's on today?
agent › Two meetings, both after 2pm.
— a turn from another surface is starting
peer › FROM-THE-OTHER-SURFACE
— reconnecting…
— connected
```

## Why this exists instead of the stock TUI

The stock letta-code TUI **cannot** be used against the App-Server-owned backend. Two separate
reasons, both established empirically (2026-08-13, letta 0.30.20):

1. **There is no attach mode.** `--backend` accepts only `cloud` or `local`
   (`serverKeyForBackendMode()` is a two-way branch); `LETTA_BASE_URL` drives the *REST* client
   (`api.letta.com`), which the App Server does not serve; and the binary's only App-Server
   client (`createAppServerClient`) is used solely by `letta channel-gateway`, a headless
   chat-channel relay with no TTY.
2. **Running it anyway would corrupt state.** `letta --backend local` opens
   `~/.letta/lc-local-backend` *directly*. With the App Server sole-owning that backend, a
   second opener means two divergent in-memory conversation projections — the multi-writer race
   R1/R4 exist to prevent.

This client is a pure WS client of the App Server. It never opens the backend, so it composes
with the App Server instead of fighting it. The old `~/bin/letta-<slug>` wrappers remain usable
only against backends the App Server does **not** own (scratch, or Docker Letta).

## Usage

```bash
letta-continuity                          # attach using the default pointer
letta-continuity --pointer /path/p.json   # a specific {agent, conversation}
letta-continuity --reasoning              # also stream the model's reasoning
letta-continuity --strict-version         # refuse an unverified server build
letta-continuity --help
```

Type a message and press Enter to send. `Ctrl-C` or `/exit` detaches — **the conversation and
any running turn continue on the server**, because this client is only a viewer/injector, never
the owner of the runtime.

### Pointer file

Targeting is pointer-driven on purpose: not by recency (enrichment turns pollute it) and not the
literal `"default"` conversation (the legacy wrapper target → cross-talk).

```json
{
  "agent_id": "agent-local-…",
  "conversation_id": "local-conv-…",
  "label": "MC"
}
```

Default path `~/.letta/continuity-pointer.json`, overridable with `--pointer` or
`$LETTA_CONTINUITY_POINTER`. The pointer is seeded once at cutover (Unit 8) via the
`conversation_create` WS RPC.

**Not hardcoded here:** the slug → `agent-local-*` fleet registry lives in
`letta-push-receiver/.../config.py::DEFAULT_AGENTS`. Copying it into TypeScript would create a
second source of truth that silently drifts, so this client takes its target from the pointer
instead. Multi-agent slug routing arrives with the rail, alongside multiple conversations.

## Install

```bash
npm install
install -m 0755 bin/letta-continuity ~/bin/letta-continuity
```

`bin/letta-continuity` is the tracked reference copy; `~/bin/letta-continuity` is the deploy
artifact (untracked, like the launchd plists). It sources **no credentials** — those belong to
the App Server process, and duplicating them into a viewer would only widen the blast radius.

## Layout

| File | Role |
|------|------|
| `src/render.ts` | Pure event → text. No stdout handle, so it is testable without a TTY. |
| `src/session.ts` | The render loop, against a `SessionCore` seam a stub can implement. |
| `src/cli.ts` | Argument/env resolution. |
| `src/main.ts` | Wires the real `ContinuityCore` to readline and stdout. |

## Tests

```bash
npm run check   # typecheck + lint + tests
```

The suite drives the whole render loop against a stubbed core: own vs peer turn labelling,
attribution surviving the release of ownership at turn end, visible reconnect, queue-behind
indicators, subagent activity, and stream/line-break correctness.

Two behaviours here are regressions from bugs the live run caught, and the stub reproduces the
real server's shape so they stay caught:

- every delta chunk carries a **distinct** `delta.id`, so lines are keyed on run + message type
  (keying on message id printed `agent › HE` / `agent › LL` / `agent › O`);
- a turn's stream ends with control deltas (`usage_statistics`, `stop_reason`), and `stop_reason`
  carries **no** `delta.id`.
