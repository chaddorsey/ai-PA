---
date: 2026-04-26
status: deferred
trigger: post-cycle-1 (after MC soak completes; pair with Tier-2 planning)
related-plan: docs/plans/2026-04-26-001-feat-pa-organizational-memory-cycle1-plan.md
related-runbook: docs/runbooks/daily-schedule-falsification-audit.md
---

# Post-Cycle-1 Follow-up: Daily-Schedule Agent Migration

## Why this is deferred

`daily-schedule-agent-sleeptime` (`agent-a3f3940f-2dcb-4b73-a01c-132df63d5ae2`)
is misclassified: it's of `agent_type='sleeptime_agent'` but is being used
as a primary cron-invoked briefing producer (3 active cron jobs invoking
`generate_daily_briefing`). It has no parent agent.

Per Ezra (2026-04-26):

> `agent_type='sleeptime_agent'` is being deprecated (per "Our Next Phase,"
> Mar 2026). It was designed as a background companion to a parent agent —
> not as a standalone primary worker. The replacement is reflection subagents
> (client-side, ephemeral) for actual background-of-a-parent use cases, OR a
> regular `letta_v1_agent` for everything else.
>
> If it's "actually being used as a primary cron-invoked agent (no parent to
> inherit from)," it's misclassified. Don't try to keep the sleeptime
> classification — the platform is moving away from it.

So `/memfs enable` on this agent isn't the right operation. The path is to
**replace it with a `letta_v1_agent`**, transfer cron job targets to the
new agent_id, then memfs-enable normally.

## Decision space (still open)

Ezra's "do you need a Letta agent at all?" decision tree applies. Three options:

### A. Replace with a thin `letta_v1_agent` + memfs

- Create new agent with `letta_v1_agent` type, persona = "Execute
  generate_daily_briefing(target_date=...) on each scheduler invocation."
- Single tool: `generate_daily_briefing` only.
- Re-point the 3 cron jobs to the new agent_id.
- `/memfs enable` per the runbook; minimal `system/persona.md`,
  `reflections/inbox.md` for cycle-2 reflection capture.
- Decommission `agent-a3f3940f`.
- **Best when:** there is real state worth keeping (briefing-quality
  signals, prior outcomes informing future briefings, learning over time).

### B. Replace with a plain cron + script (no agent)

- Move `generate_daily_briefing` from a Letta tool into a standalone
  Python script callable directly.
- Schedule via systemd timer or scheduler-service `script` action type
  on the same cron expressions.
- Decommission `agent-a3f3940f`.
- **Best when:** the briefing is a pure function of inputs (Slack/calendar/
  task data) with no learning loop and no shared-memory output for other
  agents.

### C. Middle-ground: letta-code SDK headless + minimal agent (no memfs)

- Keep a small letta_v1_agent purely for the conversation-history audit
  trail; no memfs, no cross-agent state.
- Cron invokes `letta -p "<prompt>" --agent <id> --yolo --output-format json`.
- **Best when:** want the audit trail without the substrate weight.

## Per Ezra's read

> The fact that you're asking about memfs at all suggests there is state
> worth keeping — outcomes, history, refinement signals. If that's true,
> letta_v1_agent with memfs is fine, and the substrate question is
> "do durations/structured-eval-data go in memfs files vs Postgres?"
> (which we already covered). If there's truly no state, drop the agent.

For this specific agent: the briefings probably DO benefit from
cross-invocation context (yesterday's briefing → today's; user feedback
on prior briefings shaping tone/depth). So **option A is the most likely
right answer**, but the decision is deferred until we've actually seen
how the briefing flow benefits from cross-day context.

## Action items (post-MC-soak)

1. Decide A / B / C — confirm whether the briefing actually has
   cross-invocation state (look at `generate_daily_briefing` tool
   internals + recent briefing outputs).
2. If A:
   - Create new `letta_v1_agent` with thin persona + single tool.
   - Run the canary-pre-migration audit on the new agent (replaces
     `docs/runbooks/daily-schedule-agent-pre-migration-audit.md`).
   - Re-point 3 cron jobs (use scheduler-service PATCH or recreate).
   - `/memfs enable` per runbook.
   - Run a smoke-test cron tick; verify briefing produced.
   - Decommission `agent-a3f3940f` after a soak (1 week).
3. If B:
   - Port `generate_daily_briefing` to standalone Python.
   - Cron via systemd or scheduler-service `script` action.
   - Verify smoke + soak + decommission as above.
4. Either way: update memory entry + plan to reflect the new
   pulse-monitor / daily-schedule pattern (real agent_id + agent_type).

## Don't fix the existing agent — replace it

Keep cycle 1 honest: don't modify `agent-a3f3940f` in place. The cleanest
path per Ezra's guidance is decommission-and-replace, not in-place
upgrade. The original agent stays as a fallback target during transition.
