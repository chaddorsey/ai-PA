# Continuity conversation — approval preconditions

Owner: multi-surface continuity (M1)
Related: `docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md` (Unit 2),
`docs/plans/2026-08-13-approval-contract-findings.md`

## Why this exists

On a shared conversation, a turn that stops to ask for approval blocks **every** attached surface,
because the App Server runs one turn at a time per `{agent, conversation}`. The parent milestone's
policy had two legs:

1. **Prevent** approval-requiring work from being selected on the shared conversation.
2. **Backstop**: a client answers any approval that does happen, so the turn resolves.

Leg 2 was the only one implemented, and it was implemented against a protocol that does not exist
(see the contract findings). Leg 1 is cheaper, has no protocol dependency, and is what this document
covers.

## There are two distinct approval sources

| Source | Trigger | Who controls it |
|---|---|---|
| **Interactive-input tools** — `INTERACTIVE_USER_INPUT_TOOL_NAMES`, currently `["AskUserQuestion"]` | The agent selects a tool whose whole purpose is to block on a human answer | **The client**, per turn |
| **Permission-gated tool use** — `control_request` / `request.subtype: "can_use_tool"` | The permission engine requires approval for a tool call (Bash, Write, …) | The **runtime's permission mode**, not the client |

They need different mitigations, and conflating them is what made the original policy look complete.

## Leg 1a — interactive tools: handled in code, no action required

Every `input` the continuity client sends carries `exclude_interactive_tools: true`
(`protocol.ts::buildInput`). The server then drops `INTERACTIVE_USER_INPUT_TOOL_NAMES` from that
turn's tool context, so an `AskUserQuestion`-class tool cannot be selected at all.

This is enforced per turn by the client rather than by configuration somebody has to remember, and
it follows the server's own precedent: the headless `/v1/responses` path (which enrichment uses)
sets exactly this flag. The contract test asserts the flag is present on every built `input`, so
removing it fails the suite.

**No operational step. Nothing to check.**

## Leg 1b — permission mode: verify, because the client cannot control it

The permission mode belongs to the runtime, and it is reported to every client on
`update_device_status` as `device_status.current_permission_mode`.

Observed on the live App Server (2026-08-13): **`unrestricted`** — under which permission-gated
`can_use_tool` approvals do not fire.

**Check it whenever the App Server's launch configuration changes**, and specifically before
`M1 Unit 8` cutover. If the mode is ever something other than `unrestricted`:

- Permission-gated approvals become possible on the shared conversation.
- The client's approval responder (Unit 5) becomes load-bearing rather than a backstop.
- Confirm the responder is deployed before making the change, or the first gated tool call will
  block every surface.

The opt-in live gate asserts the observed mode, so a change shows up as a failing check rather than
as a hung conversation:

```
LETTA_LIVE_WS=1 npx vitest run test/live.contract.test.ts
```

## What is deliberately NOT claimed here

- This does not guarantee approvals never happen — only that the client-controllable class is
  excluded and the other class is observed. The Unit 5 responder remains the backstop.
- The agent's full attached tool set is resolved at runtime by letta-code (toolset mode, base
  tools, MCP servers) and is not recorded in the agent's stored record, so it cannot be asserted
  from the backend files. `exclude_interactive_tools` is the enforceable equivalent.
