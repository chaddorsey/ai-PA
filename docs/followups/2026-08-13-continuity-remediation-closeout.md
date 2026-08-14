# Closeout: continuity remediation — final review + reopening/closing M1 Unit 5

Date: 2026-08-13
Branch: `feat/msc-app-server-sole-owner`
Status: **remediation complete and committed; two things remain, both below**

This is a resume-from-cold handoff. It assumes no memory of the session that produced the work.
Read it top to bottom before touching anything.

---

## Where things stand

| | |
|---|---|
| Original M1 Unit 5 work | `36951978`, `34a2fc75`, `e5079323` |
| Reviewed by | 9 persona agents + 3 plan-level agents (a `/code-review` and a `ce:plan` deepening) |
| Remediation plan | `docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md` (`status: completed`, 12/12 units) |
| Remediation commits | `bf46d004` … `0182e732` (11 commits) |
| Key protocol findings | `docs/plans/2026-08-13-approval-contract-findings.md` |
| Parent milestone plan | `docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md` |
| **M1 Unit 5 checkbox** | **deliberately left `[ ]` (reopened)** — see part (b) |

Packages: `clients/letta-continuity-core` (raw-WS client-core), `clients/letta-terminal`
(terminal surface). Nothing here is deployed; App Server cutover is M1 Unit 8.

---

## (a) Running the final code review

### Command

```
/ce:review base:e5079323 plan:docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md
```

`ce:review` is the one that accepts `base:<sha>`, which matters here — `e5079323` is the last
pre-remediation commit, so this scopes the review to the 11 remediation commits only. The three
original commits were reviewed already; that review is what *produced* this work, and re-reviewing
them will resurface findings that are now fixed.

The built-in `/code-review` does not take a `base:` argument. If you use it instead, state the
scope in the prompt: *"review the commits from `bf46d004` to `HEAD`, paths `clients/` only."*

Either way, the scope answer is: **`clients/letta-continuity-core` and `clients/letta-terminal`
only.** Other modified paths in the working tree (`letta/mc-tools`, `litellm/`, `scripts/`,
`smaug-data/`) are pre-existing uncommitted dirt, unrelated to this work.

Passing `plan:` lets the reviewer check the work against the plan's own requirements trace
(L1–L10) rather than only reading the diff.

### Before you start: run the suites, so findings are measured against a green baseline

```bash
cd clients/letta-continuity-core && npm run check    # expect: 134 passed | 4 skipped
cd ../letta-terminal            && npm run check    # expect: 51 passed
```

The opt-in live gate needs the App Server up on `:4577`:

```bash
cd clients/letta-continuity-core
LETTA_LIVE_WS=1 LETTA_LIVE_WS_EXPECT_VERSION=0.30.19 npm run check:live   # expect: 4 passed
```

`LETTA_LIVE_WS_EXPECT_VERSION` must match the **running** server, which may differ from the
on-disk binary (that gap is the whole reason `test/version-pin.test.ts` exists). Check with:

```bash
node -e "console.log(require('/opt/homebrew/lib/node_modules/@letta-ai/letta-code/package.json').version)"   # on-disk
```

### Settled by evidence — do NOT re-litigate these

A reviewer reasoning from the code alone will "discover" several of these and get them backwards.
Each was established by reading the letta-code 0.30.20 bundle and/or a live probe:

1. **Approvals are answered unconditionally, not gated on run ownership.** The server broadcasts
   each approval to *every* subscriber and settles the race itself (`settled` guard in
   `requestApprovalOverWS`; the loser is answered "Approval request is no longer pending"). A
   duplicate response is harmless; nobody answering hangs every surface. Gating on attribution
   would risk exactly that. This reverses the parent plan's stated decision, which is marked
   FACTUALLY WRONG in place.
2. **The approval request is a top-level `control_request` frame**, not the
   `approval_request_message` delta (that delta is only a transcript projection). `approval_send`
   is not a server command at all.
3. **`input_accepted` is unicast**, so a peer cannot replay our ack. Queue frames *are* broadcast,
   which is why claim transitions are single-shot.
4. **The dequeue-before-run ordering is what the real server does** (captured). The mock used to
   emit the inverted order; `src/ownership.ts` now hardens against it defensively rather than
   restructuring around a hazard that does not occur live.
5. **Attribution is inferred from stream position and cannot be made exact.** No frame carries both
   our `client_message_id` and a `run_id`; `conversation_messages_list` echoes the id as `otid` but
   carries no `run_id`. This is an accepted, documented risk — its consequence is a mislabelled
   turn, not a hung conversation.
6. **`exclude_interactive_tools: true` on every input is deliberate** and mirrors what the server's
   own headless `/v1/responses` path does.

### Known-open — real, already tracked, not new findings

- **Reconnect catch-up dedup does not work against a real server.** Live delta ids (`letta-msg-*`)
  and snapshot ids (`ui-msg-*`) are disjoint namespaces, zero overlap. Proven, asserted in the live
  gate, and stated in the core README's "Known gap". **The fix belongs to M1 Unit 7**, not here.
  Tracked in `docs/followups/2026-08-13-continuity-core-approval-correlation.md` finding #2.
- **Approval frames have no live capture.** They are bundle-derived, because the deployment runs
  `permission_mode: unrestricted`, under which interactive approvals do not fire. The live gate
  asserts that mode so a change is noticed.
- **The version gate proves version, not identity.** Nothing verifies the peer is the sole-owner
  App Server rather than any local process that bound `:4577` first. Accepted M1 residual;
  loopback is the trust boundary.
- **M1 Unit 6 (web) constraints** are recorded, not implemented: approval policy must not diverge
  per surface, and the correlation nonce must be per-send for a one-core/N-browser bridge.

### Where the risk actually is — look hardest here

- `src/ownership.ts` — the most-rewritten logic. `attribute()`'s three-way result, the observable
  definition of `positivelyForeign` (first seen while holding zero claims *and* zero owned runs),
  the reconnect demotion of armed claims, and inactivity-keyed expiry.
- `src/index.ts::routeFrame` — ordering matters: correlation bookkeeping → approval → dedup →
  attribution → assembler.
- `clients/letta-terminal/src/sanitize.ts` — security boundary. Allowlist completeness, and whether
  anything server-derived still reaches a stream without passing through it.
- `src/ws.ts::assertIdentity` — the three discriminated failure classes.

### One process note worth carrying forward

Several tests in this work were verified to **catch their own regression** by temporarily
reverting the fix and confirming the test fails for the stated reason. Two of them passed against
both fixed and broken code on the first attempt, for subtle reasons (a Promise executor
auto-rejects; `stop()` nulls the socket before the path under test). If the review proposes a new
test for a fix, that check is worth repeating — a green test is not evidence until it has been
seen to fail.

---

## (b) Closing out M1 Unit 5

### Why it is open

`M1 Unit 5` in the parent plan is `[ ]` with a **REOPENED 2026-08-13** note. The terminal client is
built, live-verified, and rendering correctly — but the review found the safety property that unit
advertised was *absent*, not merely fragile (the approval path targeted frames the server never
sends). It was reopened rather than left ticked because a green checkbox would have asserted
something untrue.

**Re-closing it is a judgement call for Chad, not an automatic consequence of the tests passing.**
The remediation is complete and verified; whether that satisfies the unit's intent is the part a
person decides.

### What to confirm before closing

1. Both suites green, plus the live gate (commands above).
2. The final code review from part (a) has run, and anything it raised is either fixed or
   deliberately accepted with a written reason.
3. A live end-to-end check still passes:
   ```bash
   cd clients/letta-terminal
   { echo "Reply with exactly: OK. No tools."; sleep 25; } | \
     ./node_modules/.bin/tsx src/main.ts --pointer <a pointer file> --no-color
   ```
   Expect `agent › OK`. Any `{agent, conversation}` works; use the low-stakes **docs** agent, never
   MC. Create a scratch conversation via the `conversation_create` WS RPC if you need one.
4. Accept, explicitly, that reconnect dedup is non-functional and deferred to M1 Unit 7. This is
   the one substantive gap remaining inside Unit 5's own subject matter.

### The edits to make when closing

In `docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md`:

- Flip Unit 5's `- [ ]` back to `- [x]`.
- Replace the `REOPENED 2026-08-13` paragraph with a closing note: what the remediation changed,
  that M1 Unit 5 is complete, and that dedup is carried into M1 Unit 7. Keep the reopening in the
  history — it is the honest record, and deleting it makes the plan look like it never went wrong.
- Leave the `⚠️ CORRECTED 2026-08-13` block on the approval Key Decision alone. It stays wrong
  forever; the correction is what makes it safe to read.

Then commit with a message that says what was verified, not just that it was closed.

### If instead the decision is "not yet"

Say what is missing in the Unit 5 note itself, so the next person does not have to reconstruct the
reasoning. The most likely candidates: wanting dedup fixed inside Unit 5 rather than deferred, or
wanting an approval path proven against a live approval (which needs a permission-mode change on
the App Server — see the runbook
`docs/runbooks/continuity-conversation-preconditions.md`).

---

## Fast orientation for a cold start

```bash
git -C /Volumes/main-drive/ai-PA log --oneline --reverse 4e8ea20b..HEAD   # the whole arc
```

Read in this order:
1. `docs/plans/2026-08-13-approval-contract-findings.md` — the protocol truth everything rests on
2. `docs/plans/2026-08-13-001-fix-continuity-core-review-remediation-plan.md` — what was done and why
3. `clients/letta-continuity-core/README.md` — current behaviour, including the Known gap
4. This file — what is left
