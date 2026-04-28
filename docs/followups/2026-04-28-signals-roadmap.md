---
date: 2026-04-28
status: near-term — address very soon
implements_already: Phase 1.1, 1.2, Phase 2 row 1 (pipeline-health)
---

# Signals Roadmap — Near-Term Build Order

This doc captures the still-to-build items from the signal-extension plan
discussed 2026-04-28 after the analytics-pipeline restoration. Phases 1.1,
1.2, and Phase 2 row 1 are already implemented; everything below is
near-term, in priority order.

## Already in place

- `emit_canonical_signal` Letta primitive — write API for any agent.
- `read_recent_signals` Letta primitive — read API (attached to MC).
- MC `system/signals_protocol.md` — when to refresh, what to project, how to act.
- MC `system/recent_signals_digest.md` — Layer-3 working digest stub.
- MC `system/assistant_role_playbook.md` — pointer to the protocol.
- Cron prompts updated for Slack Vibe Check, Quant Snapshot, T+2 Recollect, CSV Export, Compose Briefing — all five now emit `pulse-monitor-pipeline-health.md` plus their primary signals.

First end-to-end production firing: **2026-04-29 morning ET cron run** (06:00 UTC CSV-export → 10:00 UTC compose-briefing).

## Phase 1.3 — Heartbeat refresh (next)

**Goal**: MC's `recent_signals_digest.md` is fresh by the time the user shows up each morning, without depending on the user typing first.

**Implementation:**
- Add a new scheduler-service cron job: `MC Signals Heartbeat`
  - Cron: `0 7 * * 1-5` ET (= 11:00 UTC weekday)
  - agent_id: MC (`agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef`)
  - Message: *"Signals heartbeat: refresh `system/recent_signals_digest.md` per `system/signals_protocol.md`. Call `read_recent_signals(days_back=2, attention_level_min='routine', max_signals=12, body_excerpt_chars=400)`, rewrite the digest file in the format the protocol specifies, and emit a one-line confirmation. Do not address the user — this is a background refresh."*
- Set after the 10:00 UTC analytics-morning emission so the digest catches the latest day's signals.
- Reuse the `analytics_pipeline` category or create `mc_heartbeat`.

**Cost**: 5 minutes. Low risk — same pattern as the existing pulse-monitor crons.

## Phase 2 — Remaining signal types (one cron-prompt edit each)

Priority order based on actionability for MC's executive view.

### 2.2 — `tasks-agent-extracted-summary`

- Producer: tasks-agent
- When: after each `consume_queue` batch (tasks-agent's existing daily/triggered runs)
- Body: count by source, headline of the top 3 newly-extracted tasks, any quarantine flags
- Why MC needs it: surface fresh task-pool additions without polling Postgres
- Implementation: edit tasks-agent's relevant cron prompt(s) to append an `emit_canonical_signal(slug='extracted-summary', source='tasks-agent', ...)` call

### 2.3 — `email-agent-mentions`

- Producer: email-agent
- When: daily morning (matches existing email-collection cron)
- Body: list of direct/named mentions in the last 24h that aren't autoreplies; flag "letter request" / "@nsf.gov" priorities per MC's monitoring rules
- Attention: `elevated` if any letter request or @nsf.gov sender; otherwise `routine`
- Why MC needs it: surface actionable email items distinct from quant analytics

### 2.4 — `calendar-agent-anomalies`

- Producer: calendar-agent_copy
- When: when a non-routine condition is detected (after-hours meeting, conflict, deep-work block invasion, troop-meeting overlap)
- Routine days: emit nothing — silence is fine for this one
- Body: short description of the anomaly + suggested resolution
- Why MC needs it: protect the 9–11 AM block, surface conflicts before they hurt

### 2.5 — `docs-and-transcripts-agent-meeting-followup`

- Producer: docs-and-transcripts-agent
- When: after each Granola import that adds new meetings
- Body: per-meeting list of (a) commitments Chad made, (b) decisions reached, (c) open questions worth surfacing
- Why MC needs it: meeting-followup is the highest-leverage post-meeting moment; signal makes it visible without MC doing its own meeting scan

### 2.6 — `mc-day-summary`

- Producer: MC itself
- When: end of working day (cron at 18:00 ET)
- Body: terse closing digest — what got done, what slipped, what's queued for tomorrow
- Why: closes the loop. Tomorrow morning's signals digest will pick this up; gives Chad a "yesterday in one paragraph" anchor.

## Phase 3 — Better querying

### 3.1 — Filter extensions on `read_recent_signals`

- New params: `mentioned_entity` (substring match in mentioned_entities array), `body_search` (substring in body)
- Backwards compatible.

### 3.2 — `query_signals` primitive

- Full-text-style search across `agents-canonical/signals/*/*.md` returning ranked hits
- Implementation: small primitive Letta tool; backed by Gitea search API or a periodic-rebuilt sqlite FTS index
- Decide implementation only when there's a real consumer asking for it

### 3.3 — MC skill `/recent-signals`

- One-keystroke skill that does the read + dedup + render in a single Bash call (no per-tool approval round-trips)
- Consumes the digest if fresh, else refreshes via the read tool

## Phase 4 — Cycle-2 territory (don't build yet)

### 4.1 — Cross-agent signal consumption

- Attach `read_recent_signals` to worker agents
- Concrete first wire: tasks-agent reads `email-agent-mentions` to consider whether email-derived items should become tasks
- Requires care: don't create N×N coupling. Establish "which agents consume which sources" as a contract per agent.

### 4.2 — Steward agent

- Standalone persistent agent (Fimeg's "conscience" pattern), NOT a reflection subagent — confirmed by Ezra's deprecation note
- Mechanism: invoked via `Task(agent_id=<fixed>, conversation_id=<fixed>, prompt=...)` so identity persists across invocations
- Owned memfs with its own identity files
- Daily duties:
  - Aggregate `*-pipeline-health` signals across all sources → `signals/<date>/steward-system-health.md`
  - Diff each migrated agent's `system/required_tools.md` against `/v1/agents/<id>/tools` → emit `signals/<date>/<source>-tool-drift.md` on disagreement
  - Watch for `attention_level=urgent` signals; promote to user touchpoint
  - Process worker-agent reflection-inbox tags ([self]/[canonical]/[system])

## Naming-drift cleanup (cosmetic, when convenient)

Two existing signals predate the `<source>-<slug>.md` convention:

| Current path | Should be |
|---|---|
| `signals/<date>/schedule.md` | `signals/<date>/calendar-agent-schedule.md` |
| `signals/<date>/analytics-morning.md` | `signals/<date>/pulse-monitor-analytics-morning.md` |

Implementation: edit `generate_daily_briefing.py` and `compose_daily_briefing.py` to use the conventional path; leave the old files in place (or rename in a one-shot script). `read_recent_signals` is naming-agnostic, so this is purely consistency work — not blocking anything.

## Constraints from Ezra's reflection-subagent note

These are constraints to bake into the items above (not separate work):

- **Keep `system/recent_signals_digest.md` strictly bounded** (target ≤4KB, hard cap ~16KB) so it doesn't contribute to bug #1775 (ENAMETOOLONG) when MC eventually triggers reflection. The protocol already enforces "trim aggressively" in prose; a future check could measure file size on each refresh.
- **Phase 1.3 heartbeat uses scheduler-service cron, NOT letta-code reflection trigger**. Decoupled from the reflection bug surface.
- **Phase 4.2 steward built as standalone persistent agent**, not as a reflection subagent — for cognitive-separation use cases that ephemeral subagents can't satisfy.
- **MC's introspective memory hygiene is a separate workstream** from this signals work. Will use built-in `/doctor` skill or tight `.letta/settings.json` reflection config when introduced. Out of scope here.

## Verification gate

Before declaring "first pass at signals up and running": confirm tomorrow morning's run produces at minimum:

- ✓ `signals/2026-04-29/schedule.md` (existing)
- ✓ `signals/2026-04-29/pulse-monitor-slack-vibe.md` (new)
- ✓ `signals/2026-04-29/pulse-monitor-analytics-snapshot.md` (new)
- ✓ `signals/2026-04-29/pulse-monitor-pipeline-health.md` (new)
- ✓ `signals/2026-04-29/analytics-morning.md` OR `signals/2026-04-29/pulse-monitor-analytics-morning.md` (existing, possibly renamed)

If any of these are missing 2026-04-29 morning, debug before continuing to Phase 1.3.
