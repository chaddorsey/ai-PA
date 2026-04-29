---
date: 2026-04-28
status: review-needed
---

# Follow-ups: Memory-Block Layer + Rescheduling Input Handling

Two related concerns surfaced during the Chad/Amy reschedule debugging
on 2026-04-28. Both deserve a closer look in a future session.

---

## (1) Block-layer status across migrated agents

### Current state — observed 2026-04-28

Both **MC** and **calendar-agent_copy** have memory blocks that mirror
their memfs files. For calendar-agent_copy specifically:

```
calendar-agent_copy blocks: 12
  [memfs-sync] system/response_formatting_guidelines       833  chars
  [memfs-sync] system/orchestrate_scheduling_tool_use_guidelines  6716 chars
  [memfs-sync] system/agent_info                           128  chars
  [memfs-sync] system/persona                             3246  chars
  [memfs-sync] system/preferences_identity-4b355b96…        83  chars
  [memfs-sync] system/calendar_preferences                1364  chars
  [memfs-sync] system/user_preferences                      76  chars
  [memfs-sync] system/preferences_U0AB18G54ET              315  chars
  [memfs-sync] system/scheduling_context                   446  chars
  [memfs-sync] system/preferences_identity-42c594bb…        83  chars
  [memfs-sync] system/user_calendar_context                108  chars
  [memfs-sync] system/preferences_U02V91KU8                273  chars
```

All 12 mirror corresponding files at `~/.letta/agents/<aid>/memory/system/*.md`.

### Why both layers exist (post-migration)

The memfs-sync patches (`PATCH-MEMFS-GIT` etc.) mirror each `system/*`
memfs file into a same-labeled core memory block. Memfs is the disk
source-of-truth (Gitea-backed, survives container rebuilds, supports
edit-as-file); blocks are the prompt-cache snapshot the LLM actually
reads in its system prompt. Edits flow memfs → blocks automatically
via the sync patches.

This is the **intended cycle-1 architecture** — both layers serving
distinct purposes. Not a legacy artifact.

### What still warrants review

Even granting the dual-storage design, several items deserve a closer
look:

1. **Drift detection.** If memfs and the block content ever diverge
   (sync patch fails silently, manual block edit via API bypasses
   memfs), the agent reads stale content from blocks while the disk
   source-of-truth says something else. **Add a steward check**:
   diff each agent's memfs `system/*.md` against its block of the
   same label; emit `signals/<date>/<agent>-block-drift.md` on
   mismatch.

2. **Redundancy at scope.** Some calendar-agent blocks look like they
   COULD live elsewhere:
   - `system/preferences_identity-<uuid>` (3 of them, ~83 chars each)
     — these are per-identity preference snapshots. Could potentially
     be lazy-loaded per-conversation rather than always-pinned.
   - `system/preferences_U02V91KU8` and `system/preferences_U0AB18G54ET`
     — Slack-user-keyed prefs. Same: lazy-load when those users come
     up rather than always in prompt.
   The `orchestrate_scheduling_tool_use_guidelines` is 6716 chars —
   real instructional content; pinned is fine.

3. **Are tools also using block reads?** Specifically:
   - Does `orchestrate_scheduling` itself read memory blocks at runtime?
     (Answer: appears no — the tool is now an HTTP wrapper that doesn't
     touch blocks. Confirmed 2026-04-28 when I rewrote it.)
   - Do calendar-agent's other tools read blocks? Worth grepping the
     attached tool source for `core-memory/blocks` or block ID patterns.
     If yes, that's another contract surface (block label/format) that
     can drift.

4. **Block size budget.** Calendar-agent's pinned content totals ~13.6KB
   across 12 blocks. Combined with system prompt + other context, this
   is the per-turn cache cost. With Ezra's #1775 (ENAMETOOLONG) caveat,
   it's worth measuring: if any agent's pinned blocks approach the
   limits, prune or move to lazy-load paths (`digest/`, `briefing/`,
   etc., outside `system/`).

### Suggested action (when we tackle this)

- Write `scripts/audit-agent-block-vs-memfs.py` — diffs blocks against
  memfs files for each migrated agent, reports drift and size totals.
- Build a steward task that runs that audit daily and emits a
  Layer-5 `signals/<date>/<source>-block-drift.md` signal on
  mismatch.
- Identify the `preferences_*` blocks that could move outside `system/`
  to a lazy-load path. Document the migration path in
  `docs/runbooks/agent-memfs-conventions.md`.

---

## (2) Rescheduling input handling — known weak point

### Observed problems on 2026-04-28

The Chad/Amy reschedule attempt produced a chain of friction even with
all the orchestrator-path fixes in place:

1. **First attempt** with utterance "Reschedule the meeting with Amy
   that was earlier today" → orchestrator `bad_input`: "Could not
   identify the meeting to reschedule." User_id was provided. The
   utterance was clear enough for a human but the orchestrator
   couldn't extract.

2. **Second attempt** with explicit `event_id` → `bad_input`: "user_id
   is required for rescheduling." Calendar-agent had to retry with
   an explicit user_id field even though it had the email in
   utterance + participants.

3. **Third attempt** with `event_id` + `user_id` + `participant_ids` →
   succeeded. Returned 3 ranked 45-min options including
   Wed 11:15-12:00 EDT.

4. **Fourth attempt** ("apply this slot to the meeting") → orchestrator
   silently degraded to a generic 15-min free-window view because it
   has no apply mode. MC interpreted this as "the chosen slot has a
   conflict" — wrong; the slot was valid in the original proposal,
   the user's calendar was open.

### Root causes

- **Natural-language event identification is brittle.** "The meeting
  with Amy that was earlier today" should resolve to one event when
  a recent calendar lookup is available; orchestrator currently can't
  cross-reference the requester's recent events without explicit
  date+title.
- **Ambiguous required-field semantics.** `user_id` is ostensibly
  optional but is required for reschedule mode. The error path made
  calendar-agent retry rather than the orchestrator inferring from
  `participant_ids`.
- **No apply path.** Orchestrator is propose-only; calendar-agent and
  MC have no clean "execute the chosen proposal" tool. Re-calling
  orchestrate_scheduling with an "apply" utterance gets a fallback
  that misrepresents available slots.
- **Soft-degradation semantics.** When the orchestrator can't form a
  constrained query (e.g., unknown duration, can't identify event),
  it returns 15-min free windows instead of `status: bad_input`.
  This silent fallback misled MC + user.

### Suggested directions

#### A. Better event identification (reschedule resolution)

When utterance describes "the meeting with X earlier today" / "the
Carnegie sync next Tuesday" / etc., the orchestrator could:

- Pull the requester's recent calendar (last 7 days + next 14)
- Fuzzy-match attendee name + relative date phrasing → candidate
  event(s)
- If 1 match: proceed
- If >1 match: return `status: clarify`, list candidates with brief
  IDs. Calendar-agent surfaces candidates to MC, which asks user
  one disambiguating question.

This belongs **inside the orchestrator**, not as agent-side logic —
otherwise every consumer (slackbot, MC via calendar-agent, future
voice channels) reimplements it.

#### B. Add an "apply" tool / endpoint

Either:
- A new `apply_calendar_proposal(proposal_id)` tool that takes an
  orchestrator proposal_id and the original event_id, then calls the
  calendar API to move the event. Idempotent: re-running with the
  same proposal_id is a no-op. Shared across MC and calendar-agent.
- Or extend `orchestrate_scheduling` with an `apply: true` param +
  `chosen_proposal_id`. Same primitive expanded.

Either way, the user-confirms-then-apply step shouldn't go back
through propose mode.

#### C. Strict mode for ambiguous requests

When orchestrator can't form a constrained query, return:
```
{
  status: "bad_input",
  explanation: "Couldn't determine duration / event ID / target slot",
  candidates: [list of ambiguous interpretations],
  proposals: []
}
```
Don't return a generic 15-min free-window fallback that looks like
proposals but isn't.

#### D. Provide normalized inputs from calendar-agent

Calendar-agent could pre-process MC's delegation utterance:
- Resolve attendee names → emails via Letta identities
- Resolve relative dates (today, tomorrow, "earlier today") → ISO dates
- Look up event_id from a description if possible
- Pass the orchestrator a fully-structured request

This is valuable IF calendar-agent's persona makes this its job, AND
the orchestrator accepts structured input cleanly. Currently the
contract is hybrid (utterance + structured fields, with utterance
preferred for extraction).

#### E. Error-path reporting

Each orchestrator failure should surface a categorical reason that
calendar-agent can pass to MC verbatim:
- `event_not_found` (with candidates if any)
- `participants_unresolved`
- `no_zero_conflict_proposals` (with override candidates)
- `duration_unknown`
- `timeframe_too_narrow`

Right now calendar-agent's "I can't reschedule because [generic]"
messages mask which problem is which.

### Where to start

The single highest-leverage fix is **(B) the apply path** — it
unblocks the daily "user picks slot, MC moves event" flow. Without
it, every successful reschedule has a 50/50 chance of trip-ending
in the degraded-fallback bug.

Second priority: **(C) strict mode** — eliminates the silent-fallback
class of bug that produced today's "false conflict" report.

(A), (D), (E) are quality-of-life improvements that compound but
aren't blockers.

### Caveat

The orchestrator code lives at `letta/scheduling_orchestrator/` in
this repo (the FastAPI service + the underlying `orchestrate_scheduling`
function). Changes there affect both the slackbot path and the
Letta-tool wrapper. Worth a deliberate review session rather than
piecemeal patches — and worth coordinating with whoever wrote the
orchestrator originally if that's not us.
