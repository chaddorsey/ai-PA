---
date: 2026-05-30
status: scoped, awaiting implementation session
priority: pre-full-pulse-migration
effort_estimate: ~8-12 hrs across 1-2 focused sessions
related:
  - docs/migrations/local-mode/pulse-monitor-agent.md (partial migration log)
  - docs/followups/2026-05-30-task-cli-refactor.md (Option-1 pattern)
---

# pulse-cli scoping

Pulse migration to local mode is currently shell-only because 20+
bespoke analytics tools have no CLI counterpart. This doc scopes
what `pulse-cli` needs to do for the rest of pulse migration to
become possible.

## Subcommands to ship

Grouped by workflow concern:

### Briefing composition (the 06:00 ET cron)

| Subcommand | Wraps | Notes |
|---|---|---|
| `pulse compose-briefing [--date YYYY-MM-DD]` | `compose_daily_briefing` | Reads `analytics.daily_snapshots` + summarizes vibe-check + Drive trends + emits canonical signal. Already mostly uses pg + PostgREST + canonical; minor archival-read for Slack vibe-check summaries needs replacing. |

### Slack analytics (02:00 + 03:00 + 04:00 crons)

| Subcommand | Wraps | Notes |
|---|---|---|
| `pulse slack-snapshot --date YYYY-MM-DD` | `collect_analytics_snapshot` | Per-day quantitative snapshot to `analytics.daily_snapshots` |
| `pulse slack-vibe-check [--date]` | (was Slack vibe check workflow) | Pulls slack-extract CSVs + summarizes channel/mention tone |
| (Slack CSV trigger/download already covered) | `slack-extract trigger`/`download` | Already shipped — pulse just shells out |

### Drive analytics (workspace/personal/mentions collectors)

| Subcommand | Wraps | Notes |
|---|---|---|
| `pulse drive-workspace --date` | `collect_daily_workspace_activity` | Admin Reports API → aggregate by type/doc/user |
| `pulse drive-personal --date` | `collect_daily_personal_activity` | User's own files via Drive Activity API |
| `pulse drive-mentions --date` | `collect_daily_mentions` | @mentions of Chad in Drive comments |
| `pulse drive-averages` | `calculate_running_averages` | 3/10/50-day running averages — needs new storage substrate |
| `pulse drive-summary [--date]` | `get_drive_analytics_summary` | Read summary from stored state |
| `pulse drive-mentions-read` | `get_drive_mentions` | Read mentions from stored state |

### Slack mentions intra-day (*/15 cron)

| Subcommand | Wraps | Notes |
|---|---|---|
| `pulse slack-mentions-refresh` | (was intra-day refresh workflow) | Pulls recent @mentions via slack CLI; updates short-term store |

### Misc

| Subcommand | Wraps | Notes |
|---|---|---|
| `pulse health` | — | pa_web + canonical + analytics.daily_snapshots connectivity probe |

## Storage substrate decisions needed

This is the work that gates the build:

### 1. drive_analytics_* memory blocks → ?

Docker pulse stores running stats in memory blocks. Options:

- **(A) New `analytics.drive_*` pa_web schema tables** — proper relational
  store. Best long-term. Migration cost: ~2 hrs schema design + DDL.
- **(B) Per-day rolled-up signal files in canonical** — write
  `agents-canonical/signals/<date>/drive-analytics-<scope>.md` each
  collection cycle. Read via Bash+curl. No schema work, slower reads
  for trend calc.
- **(C) Memfs JSON files in pulse's own memfs** — local-agent-only
  state. Doesn't survive across machines without git push. Fastest
  to ship but worst portability.

**Recommendation: (A)** — analytics.daily_snapshots already exists;
extend the analytics schema for the drive_* state.

### 2. Slack vibe-check archival passages → ?

compose_daily_briefing reads vibe-check summaries from archival.
Options:

- Read from canonical signals (where vibe-check OUTPUTS are emitted)
- Migrate the historical archival passages to canonical retroactively
- Build a small slack_vibe_check pa_web table

**Recommendation: read from canonical signals.** Vibe-check outputs
are already emitted as signals via emit_canonical_signal. Just
update compose-briefing to read from there instead of archival.

## Implementation plan

Same Option-1 pattern as task-cli:

1. Extract the Letta tool source_code for each pulse tool to standalone
   Python files at `letta/pulse-tools/` (mirroring `letta/tool-source/`).
2. Build `pulse-cli/` package with Click entrypoint wrapping each.
3. Refactor block-reads to pg/canonical reads per substrate decisions
   above (parallel migration step).
4. Test pulse-cli end-to-end against a real day's analytics.
5. Wire pulse-cli's substrate decisions into the agent's persona +
   recipes.
6. Resume migration: rename Docker agent, repoint 6 crons, soak.

## Time budget

| Phase | Hours |
|---|---|
| Extract tool source from Letta API to standalone Python | 1-2 |
| Build pulse-cli subcommands (wrap + Click) | 2-3 |
| Storage substrate decisions + DDL + migration | 2-3 |
| Refactor wrapped Python to use new substrates | 2-3 |
| End-to-end test against real data | 1 |
| Resume migration (Phase G + H + soak start) | 1 |
| **Total** | **9-13 hrs** |

## When to do this

After Tasks soak completes (target 2 weeks from 2026-05-30) so the
task-cli pattern is proven before applying it again. Or sooner if
pulse-cli build can be scheduled as a dedicated multi-hour session
that doesn't risk Tasks soak observation.

Do NOT do this in small chunks across many sessions — the analytics
state migration in particular benefits from being done in one focused
pass to avoid mixed-substrate runtime.
