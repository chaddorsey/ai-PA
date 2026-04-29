---
title: letta-code empty-approvals subprocess crash (and our fix)
date: 2026-04-29
status: workaround landed; upstream report pending
versions_affected: 0.23.x, 0.24.x (verified through 0.24.10)
patch: letta-memfs-patches/patches/apply_letta_code_empty_approvals_fix.py
related_code:
  - pa-web-ui/approval_responder.py
  - pa-web-ui/tests/test_approval_responder.py
  - pa-web-ui/subprocess_pool.py
---

# letta-code 0.23.8 / 0.24.10 — empty-approvals subprocess crash

## TL;DR

When the Letta server emits `stop_reason: "requires_approval"` but the
streaming response's `approvals` array is empty, letta-code's headless
mode panics and **kills the subprocess with exit code 1**. The Letta
server is left holding a dangling `approval_request_message` that nothing
ever resolves; the run sits `completed` with `stop_reason="requires_approval"`;
the agent appears stalled to the user. Our patched bundle replaces the
fatal exit with a 3-second wait + outer-loop continue, allowing an external
resolver (our `approval_responder.py`) to POST an `ApprovalCreate` and
unblock the run.

## Reproduction

Any flow where:
1. A user sends a message to a self-hosted Letta agent.
2. The agent issues a tool call that the server marks `requires_approval`.
3. The streaming response reaches headless letta-code with `approvals: []`
   instead of a populated array.

Tools we've reproduced this on: `Skill`, `Task`, `Bash`. The empirical
trigger isn't the tool name — it's a race in how the Letta server populates
the streaming response's `approvals` field at the moment of the
`requires_approval` stop. Sometimes the array is empty; sometimes it's
populated; on self-hosted Letta 0.16.7 the empty case is common enough that
real users hit it routinely.

Affected versions confirmed by reading the bundled `letta.js`:

```
$ grep -c headless_requires_approval_empty letta.js
1   # in 0.23.8 (pa-web-ui's pinned version)
1   # in 0.24.10 (current latest as of 2026-04-29)
```

The same anchor block ships in both — the fix is version-tolerant within
this range.

## The bug code

Inside the headless run loop (function name varies; the sentinel is the
console.error string and the exitHeadless call):

```js
if (stopReason === "requires_approval") {
  if (approvals.length === 0) {
    console.error("Unexpected empty approvals array");
    await exitHeadless(1, "headless_requires_approval_empty");
  }
  const { autoAllowed, autoDenied, needsUserInput } =
    await classifyApprovals(approvals, {
      alwaysRequiresUserInput: isInteractiveApprovalTool,
      ...
    });
  ...
}
```

The empty-array branch is fatal. There's no recovery path; the subprocess
exits cleanly from the user's perspective and dirty from the run-state
perspective.

## Why this is hard to catch from outside

A naive client (pa-web-ui's `approval_responder.py` initially, before the
2026-04-29 refinements) sees:
1. The stream ends.
2. The Letta server's run state is `completed` with `stop_reason="requires_approval"`.
3. POSTing an `ApprovalCreate` returns 400 *"No tool call is currently
   awaiting approval"* — because the server cleaned up the dangling
   approval state when the streaming subprocess disconnected.

That 400 looks identical to a healthy "letta-code already handled the
approval, your POST raced and lost" case. Discriminating between the two
requires looking at the run state — and even then, status=running can
mean the run is healthy mid-flight OR about to die from this bug.

## Our fix (this patch)

Replace the fatal `exitHeadless(1, ...)` with:

1. **Wait 3 seconds** — gives the external resolver time to POST an
   `ApprovalCreate` to `/v1/agents/{id}/messages`.
2. **`continue` the outer loop** — the next iteration calls
   `drainStreamWithResume` again, which can resume the run by ID. By then
   the server has applied the external approval and has fresh stream
   chunks to send. The subprocess consumes them and continues normally.
3. **Cap retries at 5** — if the resolver never POSTs, after 5 attempts
   we `break` cleanly (instead of crashing). The user sees a normal
   stopped-turn state rather than a subprocess crash.

A counter on `globalThis.__pa_empty_approvals_attempts` tracks attempts
across iterations; it resets on any successful (non-empty) approval cycle.

## Verification

After patch applied:

```
$ grep -c '\[PATCH-EMPTY-APPROVALS\]' letta.js
2 (or higher; multi-line comment + console.error string)
```

Smoke test: invoke a tool flow on the patched container that previously
hit the bug (Skill, Task, Bash on a triggering input). The subprocess
should NOT exit; the responder's POST should succeed; the user-visible
flow should complete normally without a "stranded" error event.

## Upstream-friendly fix (suggestion to Letta devs)

The cleanest upstream fix would be: when the streaming response includes
`stop_reason="requires_approval"` but `approvals` is empty, the headless
client should treat the empty-array as a *transient* condition and either:

- Fetch the run state from the API to derive the pending approvals from
  recent `approval_request_message` events, OR
- Wait briefly (similar to our 3s) and re-stream from the run's last
  known `seq_id`, in case the streaming chunk that should have carried
  the approvals is delayed.

Either treatment preserves the streaming semantics for the common case
while avoiding the fatal client-side exit when the server's chunking
happens to drop the approvals list.

The current behavior — `console.error` followed by `exitHeadless(1, ...)`
— makes the headless mode brittle whenever the server's streaming
chunking deviates from the expected shape, and there is no client-side
recovery or escalation path other than process death.

## Related infrastructure on our side

| File | Role |
|---|---|
| `pa-web-ui/approval_responder.py` | Detects `approval_request_message` in the stream, POSTs `ApprovalCreate` to the Letta API to auto-approve. Includes race-loss vs subprocess-crashed disambiguation. |
| `pa-web-ui/tests/test_approval_responder.py` | 17 unit tests covering policy classification, dedup, race-loss outcomes, synthetic error emission. |
| `pa-web-ui/subprocess_pool.py` | Wires the responder into the `_emit` event-fanout path with --yolo policy (allow all non-interactive tools). |
| `letta-memfs-patches/patches/apply_letta_code_empty_approvals_fix.py` | This patch — applied at Docker build time alongside the existing #3205 self-hosted-handle-fix. |
| `pa-web-ui/Dockerfile` | Applies both patches; verifies marker counts. |

## Why we patch the bundle instead of waiting for an upstream fix

- Self-hosted Letta 0.16.x users hit this regularly.
- Skill, Task, and Bash all reproduce it.
- Our pa-web-ui is the primary user-facing surface to MC; every minute
  of dead-air in that flow is user-visible.
- The patch is ~30 lines of bundle string-replace — same proven pattern
  as our existing #3205 patch. Risk is bounded; verification is one grep.
- We log markers (`[PATCH-EMPTY-APPROVALS]`) so post-incident inspection
  can immediately tell whether the patch is in play.

When the upstream-fixed version of letta-code ships, our patch becomes a
no-op (the `OLD_BLOCK` anchor will no longer match) and we can remove it
in a clean Dockerfile cleanup pass.
