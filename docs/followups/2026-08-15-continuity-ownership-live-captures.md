---
status: complete
parent: docs/plans/2026-08-15-002-continuity-round4-review-findings.md
purpose: input to the root-cause-A (ownership/attribution) design conversation
branch: feat/msc-app-server-sole-owner
server: letta-code 0.30.19 running on ws://127.0.0.1:4577/ws (permission mode `unrestricted`)
agent: disposable scratch agent, minted and deleted (clients/tools/scratch-agent.mjs)
harness: clients/tools/capture-ownership.mjs
raw: docs/followups/captures/*.jsonl
date: 2026-08-15
---

# Live captures for the ownership/attribution design conversation

The round-4 review named three questions, each "promotable-or-killable by one capture." All three
were run against the live App Server on a disposable agent. Two are answered, one is **not
observable in the M1 configuration** — and the run turned up a fourth thing nobody asked about
that is more serious than any of them.

Raw frames are in `docs/followups/captures/`; the harness that produced them is
`clients/tools/capture-ownership.mjs`.

## Environment note, found on the way in

The **running** App Server reports `letta_code_version: 0.30.19`. The **installed** package on
disk is `0.30.20`. That is real server/on-disk drift, live right now: the package was upgraded and
the constant-on server was never restarted, so it is still executing the older build.

`version-pin.test.ts` does **not** catch this, and cannot as written — it compares the *installed*
version against `VALIDATED_SERVER_VERSIONS`, and both 0.30.19 and 0.30.20 are in that list. The
gate answers "is what is on disk contract-verified", not "is what is RUNNING what we think is
running". Those are different questions and only the second one predicts behaviour.

Consequence for the round-4 record: **0.30.20 has still never been live-validated**, because it
has never run. `PINNED_SERVER_VERSION` is 0.30.20, so `check:live` with default settings would
fail against this server — correctly. Everything below, and the 4/4 gate pass, is **0.30.19**.

## Q1 — does the runtime report `WAITING_ON_INPUT` while a turn is parked on an approval?

**NOT OBSERVABLE in the M1 configuration, and that is a real answer.**

The probe asked the agent to run a Bash command and deliberately did not answer any approval. No
`control_request` ever arrived. The runtime went straight through
`EXECUTING_CLIENT_SIDE_TOOL` → `client_tool_start` → `tool_return_message` → `client_tool_end`
and finished the turn.

The cause is documented and asserted: the runtime's permission mode is `unrestricted`, and
`live.contract.test.ts` **pins that** ("under `unrestricted` no permission-gated `can_use_tool`
approval fires on the shared conversation"). So on M1 as configured, a permission-gated approval
cannot occur.

**What this does to the findings:** A1 and A6 — the approval-park attribution defects — are
**unreachable in the shipping configuration**, not wrong. They become live the moment the
permission mode changes, which is exactly the event the existing contract test exists to catch.
The design conversation should treat them as *conditional* findings gated on permission mode
rather than as things to fix now. It should NOT treat them as disproven.

I did not change the permission mode to force an approval: that is an operational change to a
constant-on runtime and a documented precondition, not mine to flip.

## Q2 — can two `input` frames on one socket both be acked `started`/`submitting`?

**YES — both were acked `started`, and neither was ever queued.**

```
   27ms -> input (rpc-in-1)
   27ms -> input (rpc-in-2)
  128ms <- input_accepted  req=rpc-in-1  accepted=true  disposition=started
 2260ms <- turn_finished   run=local-run-572
 2289ms <- input_accepted  req=rpc-in-2  accepted=true  disposition=started
```

The server serialises by **deferring the second ack** until the first turn is over — not by
queueing. `update_queue` was never involved. So on a single socket the "queued → dequeued → armed"
chain that `ownership.ts` is largely built around **is never exercised at all**.

Two further things fall out of the same capture, and both bear directly on the design:

- **`active_run_ids` is almost always empty.** Across 34 frames only one carried a populated
  `active_run_ids`. Any inference resting on `soleActiveTurn()` is reading a field the server
  mostly leaves blank.
- **The runtime reports `WAITING_ON_INPUT` while an accepted input has not yet produced its run.**
  Between rpc-in-2's `started` ack (2289ms) and its first delta (3073ms) there were **four**
  `WAITING_ON_INPUT` frames. Idle does not mean "your turn is over"; it means "nothing is running
  this instant." That is the same shape as A6/A7 reached without any approval involved, and it is
  the assumption the one-shot's idle-based termination rests on.

## Q3 — does the server re-broadcast `update_queue` removals after a reconnect?

**NO.** And the reason is worse than the question.

Queueing does happen — but only **between peers**, not within one socket. With peer A running a
long turn and peer B injecting behind it:

```
  160ms <- ACK req=rpc-in-1  accepted=true  disposition=started      (peer A)
  864ms <- ACK req=rpc-in-b  accepted=true  disposition=queued       (peer B)
  864ms <- update_queue  queue=["cm-b"]  removed=[]
  866ms    (peer B's socket terminated)
  869ms <- update_queue  queue=[]  removed=[{client_message_id:"cm-b", disposition:"cancelled"}]
 1443ms <- turn_finished  run=local-run-576  stop=end_turn           (peer A's turn — the only one)
 2089ms    (peer B reconnects)  update_queue  queue=[]  removed=[]
```

**A controlled comparison confirms the cause.** Identical scenario with B's socket left connected:
`cm-b` was `dequeued` and ran normally. So the `cancelled` above is caused by **the submitting
socket going away**, not by queueing.

### The finding this promotes

> **A queued message is CANCELLED when its submitting socket drops, and the cancellation notice is
> sent only to the socket that is dying. The client that reconnects is never told.**

Trace it from the client's side: submit, receive `queued`, arm a claim, lose the socket (a
watchdog restart drops every attached surface at once — the ordinary case, not an edge). The
server cancels the message. The cancellation goes to the dead socket. On reconnect the client
sees `queue=[] removed=[]` — a clean slate with no record that anything was cancelled. Its message
will never run, no reply will ever come, and **nothing on the wire will ever say so**. It waits
until its own timeout, or until the 15-minute reaper.

`ownership.ts` already handles `disposition: "cancelled"` by dropping the claim. That code is
correct and unreachable on this path, because the frame never arrives.

### What this does to A8

**A8 as written is killed.** It supposed that a *replayed* `update_queue` removal after a
reconnect re-arms a demoted claim and then binds a peer's run. There is no replay: after a
reconnect the queue view is empty and carries no removals. The hazard is the opposite one — not a
removal arriving twice, but the only removal that mattered arriving never.

## What the design conversation should take from this

1. **The wire cannot tell a client its queued turn was cancelled across a reconnect.** Any
   ownership model that keeps a claim across a seam has to answer this, and it cannot answer it by
   inference — the information is not merely ambiguous, it is absent. This is the strongest
   evidence yet for the review's question *"can attribution be carried on the frames themselves?"*
   and it points at a **server-side** requirement: either the queue view on reattach must include
   recently-cancelled entries, or a resubmit-on-reconnect policy has to be a client decision made
   explicitly rather than a claim quietly waiting.
2. **Idle is not turn completion**, confirmed without approvals in the picture (Q2). Terminating a
   turn on a shared `WAITING_ON_INPUT` is unsound on the happy path too, not only when a turn is
   parked.
3. **The single-socket queue path does not exist** (Q2), so the `queued → dequeued → armed` chain
   only ever runs between peers. A bridge that multiplexes N consumers onto ONE core (the Unit 6
   shape) will therefore see deferred acks, not queue frames — which is *not* the shape
   `ownership.ts` is written against, and not the shape its tests drive.
4. **A1/A6 are conditional on permission mode**, currently `unrestricted` and pinned by a test.
   Not disproven, not currently reachable.

## Reproducing

```bash
AGENT=$(node clients/tools/scratch-agent.mjs)
node clients/tools/capture-ownership.mjs two-inputs     "$AGENT"
node clients/tools/capture-ownership.mjs queue-replay2  "$AGENT"   # the drop run
node clients/tools/capture-ownership.mjs queue-control  "$AGENT"   # the control
node clients/tools/capture-ownership.mjs approval-park  "$AGENT"
node clients/tools/scratch-agent.mjs delete "$AGENT"
```

Set `CAPTURE_OUT=<file>.jsonl` to keep raw frames. The harness is a pure WS client — it never
opens the backend, and every scenario targets a disposable agent.
