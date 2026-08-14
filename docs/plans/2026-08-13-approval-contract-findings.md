# Approval & attribution contract — findings

Date: 2026-08-13
Unit: 1 of `docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md`
Source: `@letta-ai/letta-code` 0.30.20 bundle (authoritative), plus live captures against `:4577`
Status: **RESOLVED — verdict 2 (a WS client can answer), with a major simplification**

## Verdict

**Outcome 2 of the four enumerated in the plan: approvals can fire, and a WS client can answer them.**

But the contract is materially different from what both the shipped code *and* the remediation plan's
first draft assumed, and the difference **removes** complexity rather than adding it.

## The real contract

### Request — a top-level `control_request` frame, broadcast to every subscriber

```json
{
  "type": "control_request",
  "request_id": "perm-<toolCallId>",
  "request": {
    "subtype": "can_use_tool",
    "tool_name": "Bash",
    "input": { "...parsed tool arguments..." },
    "tool_call_id": "<toolCallId>",
    "permission_suggestions": [],
    "blocked_path": null,
    "diffs": []
  },
  "agent_id": "...",
  "conversation_id": "..."
}
```

- `request_id` is **derivable**: `perm-${toolCallId}`.
- From `requestApprovalOverWS`: recipients are `getSubscribedListenerConnections(...)` — i.e. **all
  subscribed connections**, not just the turn's initiator.

### Response — an `input` with `kind: "approval_response"`

```json
{
  "type": "input",
  "request_id": "<our own correlation id>",
  "runtime": { "agent_id": "...", "conversation_id": "..." },
  "payload": {
    "kind": "approval_response",
    "request_id": "perm-<toolCallId>",
    "decision": { "behavior": "deny", "message": "<required for deny>" }
  }
}
```

- Server-side validator `isValidApprovalResponseBody` requires `payload.request_id: string` and
  either `payload.error: string` or a `decision` object. For `behavior: "deny"`, `message` is
  **required**. For `allow`, `message`/`updated_input`/`selected_permission_suggestion_ids` are
  optional.
- The listener acknowledges with the normal `input_accepted`, and reports
  `"Approval request is no longer pending"` when the request has already been settled.

### The `stream_delta` is a projection, not the actionable request

`projectToolCallContent` builds a message with `message_type: "approval_request_message"` and
`delta.tool_call`. That is the **transcript projection** — what a client renders. The actionable
request is the `control_request` frame above. A client that only watches deltas can *display* an
approval but can never *answer* one.

## The simplification: the server already enforces at-most-once

`requestApprovalOverWS` creates one `pending` object per approval, offered to every subscribed
connection, whose `resolve`/`reject` are both guarded:

```js
resolve: (response) => { if (settled) return; settled = true; ... }
```

`resolvePendingApprovalResolver` then `removePendingApproval`s it, so a second response finds no
pending entry and is answered with *"Approval request is no longer pending"*.

**Consequences — this overturns the M1 policy's central premise:**

1. A duplicate response is **harmless**. The server discards the loser of the race.
2. Therefore *"observers must not respond, to avoid duplicate responses"* — the parent plan's stated
   reason for tying approvals to run ownership — **solves a problem that does not exist**.
3. The only dangerous failure mode is the one the policy was really about: **nobody answers**.
4. So the correct M1 policy is strictly simpler *and* strictly safer than the designed one:
   **any client holding an unresolved approval may answer; answer promptly; let the server settle
   the race.**

This decouples approval correctness from run attribution entirely. Attribution remains necessary for
the terminal's own-vs-peer origin labels, but it is **no longer load-bearing for safety** — which
removes the plan's most delicate coupling.

The server also models approval ownership itself: `pendingApprovalResolvers` is keyed by
`(connectionId, requestId)`, with an explicit `__unowned_approval__` sentinel and
`addPendingApprovalConnection` / `keepPendingApprovalUnowned` transitions. Client-side ownership
inference is redundant with a mechanism the server already has.

## Answers to Unit 1's required questions

| Question | Answer |
|---|---|
| Which frame carries the request? | Top-level `control_request` (broadcast). The `approval_request_message` delta is a transcript projection only. |
| Which identifier correlates it? | `request_id = "perm-" + tool_call_id`. |
| Which command answers it? | `input` with `payload.kind = "approval_response"`. |
| What if nobody answers? | The pending promise is settled only by a response, an abort, or the turn lease being cancelled — see Residual Unknowns for the timeout question. |
| Is `input_accepted` unicast or broadcast? | **Unicast.** `acknowledgeInput` uses `safeSocketSend(socket, …)`, and the live two-peer capture shows each client saw only its own ack. A peer therefore cannot replay our ack to drop our claim. |
| Queued-turn frame order? | **Dequeue-then-run** (safe order), captured live: `update_queue removed:[{dequeued}]` precedes the next run's announcement. The project's mock emits the inverted order. |
| Do snapshot ids and live delta ids share a namespace? | **No.** `letta-msg-*` (live) vs `ui-msg-*` (snapshot); zero overlap over a full turn. |
| Can attribution be exact via `otid`? | **No.** Snapshot user messages carry our `client_message_id` as `otid`, but no `run_id`. |

## Residual unknowns (deferred, with impact named)

- **Timeout when nobody answers.** Not established from the bundle; the pending appears to rely on
  the turn lease/abort rather than a timer. *Impact:* only affects how loudly an unanswered approval
  must be surfaced — it no longer affects correctness, because any client may answer.
- **What a deny does to the turn** (error / retry / continue). *Impact:* informs UX copy, not the
  protocol. Worth capturing opportunistically if an approval is ever provoked.
- **Whether interactive approvals can fire at all** under `permission_mode: "unrestricted"`.
  *Impact:* if they cannot, the whole path is dormant and Unit 2's tool-set precondition is the only
  live mitigation. Does not change the implementation.
- **Whether delegated/subagent turns mint their own `run_id`.** *Impact:* attribution/labelling only
  now that approvals no longer depend on it. Downgraded from blocking to a known limitation.

## Impact on the plan

- **Unit 5 (approval path)** — implement `control_request` / `approval_response`, not the delta path.
  `request_id` is derivable, so the "never emit an empty identifier" hazard largely evaporates. Keep
  deny-only enforced by type. Drop the one-responder machinery.
- **Unit 6 (attribution)** — no longer gated on approvals for *safety*. It still needs the
  correctness fixes for origin labelling and for bounded state, but `attribute()` stops being a
  safety-critical API and the fail-closed policy simplifies to "answer if we hold an unresolved
  approval."
- **Unit 8 (fixtures)** — fixtures are derivable from the bundle shapes above; a live approval
  capture is no longer a prerequisite.
- **The parent M1 plan's Key Decision on approvals is factually wrong** and should be corrected: the
  duplicate-response concern it is built on does not exist.
