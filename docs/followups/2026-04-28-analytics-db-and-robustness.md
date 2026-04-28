---
date: 2026-04-28
status: outline
---

# Follow-ups: Analytics DB Strategy + System Robustness Patterns

Outlines for the two secondary questions raised after Layer-5 emission cleanup.
Both are deferred from the primary fix; this doc captures thinking to plan from.

---

## (b) Analytics database — what should be in it, and why

### Current state

- **`analytics.daily_snapshots`** (one row per source × date):
  - Drive: activities count, top documents, by-user breakdown
  - Email: sent/received per user, ratios, quartile distribution
  - Slack: message totals, channels active, top channels (when CSV present)
  - Schema is wide JSON-per-source rather than normalized.
- Written by `collect_analytics_snapshot`, upserted by date + recollected at T+2.
- Read by `compose_daily_briefing` to compute trends.
- No other consumers today.

### What's right about it

- Numerical / aggregable / time-series — DB is the correct substrate.
- Upsert by date handles late-arriving data cleanly.
- Single table per concept (snapshot of a day) is simple to query.

### What's missing or wrong

1. **No raw-data preservation.** When `analyze_slack_analytics` runs, the per-row
   CSV detail is summarized into the snapshot and discarded. If we later want
   to re-analyze (different aggregation, drill into a specific user, build a
   dashboard), we cannot — Slack's file retention is finite. Same for Drive
   activity events: the API returns granular events; we keep aggregates.
2. **No per-channel time-series for Slack.** `top_channels` is captured as a
   point-in-time list, not a per-channel daily time-series. "Has #engineering
   been quieter than usual?" requires a row per (channel, date), not a list
   inside a daily snapshot.
3. **No dashboard surface.** Briefings render trend prose, but there's no
   queryable view for spot-checks ("show me sent-email volume by week
   over Q1") without writing custom SQL each time.
4. **No backfill strategy.** Today's gap (4 weeks of `slack_collected: False`)
   shows the existing schema can't distinguish "we collected and there was
   nothing" from "we couldn't collect" without inspecting the `errors` array.
   Should be a first-class column.

### Suggested direction (sketch — not for build yet)

Layer the DB along Layer-1/Layer-2 lines:

- **Layer-1 raw retention** in a `analytics_raw` schema:
  - `slack_csv_archive(date_range_start, date_range_end, csv_type, file_bytes BYTEA, fetched_at)` — store the actual CSV files keyed by date range. Cheap (small files), durable, survives Slack's retention.
  - `drive_activity_events(date, doc_id, actor, action, ts)` — granular row per event (or store as JSONL parquet on disk, indexed by date). Decide based on cardinality.
  - Same for email-activity-events when warranted.
- **Layer-1 derived facts** (current `analytics.daily_snapshots`, evolved):
  - Add `slack_channel_daily(channel_id, channel_name, date, message_count, member_count, ...)` for per-channel time-series.
  - Add `collection_status(date, source, status, error_message, collected_at)` so "did the pipeline run successfully" is queryable as a first-class fact, not derived from a JSON `errors` field.
- **Layer-2 operational state** (already in scheduler-service Postgres) is fine where it is.
- **Dashboarding**: thin Postgres views over Layer-1 tables; Metabase/Superset or Grafana once views stabilize. No new substrate needed.

### Suggested first steps (low-cost, high-value)

1. **Add `collection_status` table** (small, additive). Update
   `collect_analytics_snapshot` to write a status row per source per run.
   Immediate value: a Layer-5 `signals/<date>/pipeline-health.md` can be
   generated from this trivially.
2. **Archive the CSVs** durably. `trigger_slack_analytics_export` already
   knows the date range; once the CSV lands in Slack, also persist the
   bytes to either `analytics_raw.slack_csv_archive` (Postgres bytea) or
   `agents-canonical/slack-csv/<date_range>/` (Gitea). This is the
   biggest robustness improvement for backfill.
3. **Per-channel daily Slack table** when there's a real consumer asking
   for it (don't build until needed).
4. **Per-channel daily series** is the natural input for vibe-check
   anomaly detection — currently the agent has to eyeball CSVs each day.

### What does NOT belong in the DB

- The vibe-check narrative summaries (those are Layer-5 prose; canonical signals are correct).
- The morning-briefing markdown (same).
- Per-agent identity (memfs).

---

## (c) System robustness patterns

The 4-week silent breakage of CSV downloads exposed a class of failure modes:

1. **Cron "succeeded" doesn't mean useful work happened** — scheduler-service treats agent-message dispatch as the success boundary. If the agent improvises around a missing tool and produces empty output, that still counts as success.
2. **Tool drift** — the cron payload references a tool name; if that tool isn't attached to the agent, the agent silently substitutes something else.
3. **External contract drift** — the Slack CLI lost an `analytics` subcommand at some point; agents still try to use it because nobody told them otherwise.
4. **Layer-5 absence as a signal** — the analytics-morning emission was missing for 4/27, 4/28; nothing alerted on this.

### Patterns to develop

#### Pattern 1 — Health-signal emission

Every periodic agent-driven workflow should emit a Layer-5 health signal at the end of its run:

```
signals/<date>/<source>-health.md
  status: ok | partial | failed
  inputs_seen: [list of expected upstream artifacts that were present]
  inputs_missing: [list of expected upstream artifacts that were absent]
  outputs_produced: [list of artifacts written]
  notes: [free text]
```

A daily steward (or MC at heartbeat) reads `signals/<today>/*-health.md`. Any `failed` or `partial` for >24h triggers a notification. Concrete first instance: `pulse-monitor-pipeline-health.md` covering the 5-cron analytics flow.

#### Pattern 2 — Declarative tool requirements + reconciliation

`system/required_tools.md` per agent (introduced in this session for pulse-monitor) is the declarative source. A reconciliation task — runs daily, or on agent-rebuild — diffs declared vs. actual and emits a `signals/<date>/<source>-tool-drift.md` signal when they disagree. First version can be a 30-line CLI script invoked by a steward skill; doesn't need to be a Letta tool.

#### Pattern 3 — Known-breakage register

`system/known_external_breakages.md` per agent (also introduced this session) holds facts the agent should consult before improvising around a CLI/API failure. The agent's persona/system instructions should include a one-line "before retrying with a different invocation, check known_external_breakages.md."

#### Pattern 4 — "Work happened" not "message dispatched" cron success

Scheduler-service should optionally accept a callback URL or a Layer-5 path it expects to see appear after a job runs. If the artifact isn't present within a window, mark the execution as `degraded` rather than `succeeded`. This is a scheduler-service feature change; propose as a separate plan.

For now, the substitute: Pattern 1 (health-signal emission) gives us most of the value without scheduler changes.

#### Pattern 5 — Cron prompts versioned + reviewable

The agent-instruction text inside `actions[].config.message` is operationally critical content stored in a DB JSON column with no review history. Either:
- Store cron prompts as files in the repo (e.g. `letta/cron-prompts/<job-slug>.md`) and have a sync script that pushes them to scheduler-service, OR
- Add a `prompt_version` field and audit-log changes.

Either makes drift between "what the prompt says to do" and "what the agent can do" visible during code review.

### Suggested first steps (low-cost, sequence)

1. **Implement Pattern 1 first** — add a final action to each daily-analytics cron prompt: "emit pipeline-health signal." Already doable with `emit_canonical_signal`; no new code.
2. **Build the steward reconciliation script for Pattern 2** — small Python CLI that reads `system/required_tools.md` from a list of agent IDs, compares to `/v1/agents/<id>/tools`, emits Layer-5 signals on drift. Run from a daily cron.
3. **Bake Pattern 3 into agent personas** — one-line addition to each migrated agent's persona pointing at `system/known_external_breakages.md`. Steward skill can refresh this section.
4. **Pattern 4 (scheduler change)** — propose as a separate plan; not blocking.
5. **Pattern 5 (cron prompts in repo)** — propose alongside Pattern 4.

### What this catches that today's setup misses

- 4-week CSV gap → would have been caught by Pattern 1 within 24h (health signal would say `slack_collected: False` every day).
- Tool drift on agent rebuild → Pattern 2 catches at next reconciliation tick.
- Slack CLI subcommand removal → Pattern 3 documents the workaround so the agent doesn't keep retrying the broken path.
- Cron prompt referring to a tool the agent doesn't have → Pattern 2 surfaces it; Pattern 5 prevents it from being merged in the first place.
