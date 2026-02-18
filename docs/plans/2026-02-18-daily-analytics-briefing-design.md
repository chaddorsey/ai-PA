# Daily Analytics Briefing — Design Document

**Date:** 2026-02-18
**Status:** Draft

## Goal

Produce a regularized daily "vibe check" analytics snapshot across Drive, Email, and Slack that:
1. Captures ephemeral metrics that can't be reconstructed later
2. Stores snapshots in a backed-up database for trend comparison
3. Identifies standout stats vs. running averages
4. Respects data availability constraints (Slack delay, weekend gaps, privacy)

## Existing Infrastructure

The system already has substantial analytics tooling. This design composes it rather than rebuilding.

### What Already Exists

| Domain | Tool | What It Provides | Ephemeral? |
|--------|------|-----------------|------------|
| **Drive** | `collect_daily_workspace_activity()` | Admin Reports API: total activities, unique users, unique documents, top-5 edited/shared/commented/viewed/active-users | **YES** — Admin Reports API retains 180 days, then gone forever |
| **Drive** | `collect_daily_personal_activity()` | Personal file interactions, mentions, comments | **YES** — same 180-day window |
| **Drive** | `collect_daily_mentions()` | @-mentions in Drive comments | **YES** — same window |
| **Drive** | `/v1/stats`, `/v1/staleness/status` | Document count, chunk count, staleness tier distribution | No — reconstructible anytime |
| **Drive** | `/v1/documents/changed?since=` | List of recently modified documents with authors | Partially — file metadata persists but Activity API events expire |
| **Email** | `get_email_analytics(mode="org")` | Org-wide sent/received/ratio | **YES** — Admin Reports API, 180-day window |
| **Email** | `get_email_analytics(mode="quartile")` | User groups by activity quartile | **YES** — same window |
| **Slack quant** | `trigger_slack_analytics_export` + `analyze_slack_analytics` | Channel/member CSV exports: messages posted, active members, viewers | **YES** — point-in-time snapshots, non-recoverable |
| **Slack qual** | Pulse Monitor agent workflow | Channel-by-channel vibe summaries, sentiment, key posters, @-mentions | No — messages persist on paid plan; summaries can be regenerated |

### Critical "Capture or Lose" Data

These metrics **cannot be regenerated** if not captured daily:

1. **Drive Admin Reports** (180-day rolling window):
   - Total activities (edits, views, shares, comments) by day
   - Unique active users by day
   - Unique documents touched by day
   - Top-5 most edited/shared/commented/viewed documents
   - Top-5 most active users
   - Activity type breakdown (edit, view, create, share, comment, rename, move, delete)

2. **Email Admin Reports** (180-day rolling window):
   - Org-wide emails sent and received
   - Send/receive ratio
   - Quartile distribution

3. **Slack Analytics CSVs** (point-in-time, non-recoverable):
   - Messages posted per channel
   - Members who posted per channel
   - Members who viewed per channel
   - Total active members

### Data That's Safe to Skip Daily

- Drive file metadata (modifiedTime, owner) — always queryable via Drive API
- Slack message content — persists indefinitely on paid Concord plan
- Gmail Watch thread data — already captured in real-time to database
- Drive staleness tiers — reconstructible from current file metadata

## Architecture: Hybrid Approach

### Component 1: `collect_analytics_snapshot` Tool (Deterministic)

A new Letta tool that gathers quantitative metrics from all three domains, **persists the snapshot to the database as a side effect**, and returns structured JSON. This is the "capture" layer — runs daily, stores results durably before returning anything to the agent.

**Inputs:**
- `date` (optional, defaults to last workday) — YYYY-MM-DD
- `include_slack_qualitative` (default: false) — whether to trigger Slack pulse summary

**Data Collection Flow:**

```
collect_analytics_snapshot(date="2026-02-17")
  │
  ├── Drive: collect_daily_workspace_activity(date)
  │   └── Admin Reports API → activities, users, documents, top-5s
  │
  ├── Email: get_email_analytics(start=date 00:00, end=date 23:59, mode="org")
  │   └── Admin Reports API → sent, received, ratio
  │
  ├── Slack quantitative: analyze most recent CSV export
  │   └── analyze_slack_analytics(file_url) → channel stats
  │   └── NOTE: CSV covers 2-3 days ago due to Slack delay
  │
  ├── PERSIST: write snapshot to analytics.daily_snapshots via PostgREST
  │   └── Side effect — data is durable even if agent drops context
  │
  └── Returns: structured JSON snapshot (+ confirmation of DB write)
```

**Output Schema:**

```json
{
  "snapshot_date": "2026-02-17",
  "collected_at": "2026-02-18T08:15:00Z",
  "is_workday": true,
  "drive": {
    "total_activities": 342,
    "unique_users": 18,
    "unique_documents": 87,
    "activity_breakdown": {
      "edit": 156, "view": 98, "create": 23,
      "share": 15, "comment": 31, "other": 19
    },
    "top_edited": [{"title": "...", "count": 12, "owner": "..."}],
    "top_shared": [...],
    "top_commented": [...],
    "top_viewed": [...],
    "top_active_users": [{"email": "...", "activity_count": 45}]
  },
  "email": {
    "total_sent": 234,
    "total_received": 567,
    "ratio": 0.41,
    "total_activity": 801,
    "covers_date": "2026-02-17"
  },
  "slack": {
    "covers_date": "2026-02-14",
    "total_messages_posted": 189,
    "channels_active": 24,
    "members_active": 31,
    "top_channels": [{"channel": "#general", "messages": 42, "posters": 15}]
  }
}
```

### Component 2: `daily_analytics_snapshots` Database Table

Stores each day's snapshot for trend comparison. Lives in the Supabase PostgreSQL `scheduler` schema (or a new `analytics` schema).

```sql
CREATE TABLE analytics.daily_snapshots (
  snapshot_date  DATE PRIMARY KEY,
  is_workday     BOOLEAN NOT NULL,
  collected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Drive (Admin Reports API — ephemeral, 180-day window)
  drive_total_activities     INT,
  drive_unique_users         INT,
  drive_unique_documents     INT,
  drive_edits                INT,
  drive_views                INT,
  drive_creates              INT,
  drive_shares               INT,
  drive_comments             INT,
  drive_other_activities     INT,

  -- Email (Admin Reports API — ephemeral, 180-day window)
  email_total_sent           INT,
  email_total_received       INT,
  email_ratio                FLOAT,
  email_total_activity       INT,

  -- Slack (CSV export — point-in-time, non-recoverable)
  slack_covers_date          DATE,  -- actual date the Slack data covers (2-3 days behind)
  slack_total_messages       INT,
  slack_channels_active      INT,
  slack_members_active       INT,

  -- Full detail for ad-hoc queries and future metrics
  raw_snapshot               JSONB NOT NULL,

  -- Backup metadata
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Separate table for top-N lists (normalized for querying)
CREATE TABLE analytics.daily_top_items (
  id             SERIAL PRIMARY KEY,
  snapshot_date  DATE NOT NULL REFERENCES analytics.daily_snapshots(snapshot_date),
  domain         TEXT NOT NULL,  -- 'drive', 'slack'
  category       TEXT NOT NULL,  -- 'most_edited', 'most_shared', 'top_channels', etc.
  rank           INT NOT NULL,   -- 1-5
  item_title     TEXT,
  item_id        TEXT,           -- doc_id, channel_id
  item_owner     TEXT,           -- owner email, channel name
  count          INT NOT NULL,
  metadata       JSONB           -- extra fields (link, is_accessible, etc.)
);

CREATE INDEX idx_daily_top_domain ON analytics.daily_top_items(domain, category, snapshot_date);
```

### Component 3: Trend Comparison Logic

When generating the briefing, compare today's snapshot to running averages:

- **7-day workday average** — recent trend baseline
- **30-day workday average** — stable baseline
- **Flag standouts** — any metric >1 standard deviation from 30-day mean

Weekends are stored but excluded from workday averages. The briefing can note "Weekend activity was X% of typical workday" when relevant.

### Component 4: `compose_daily_briefing` Tool + Agent Instructions

The compose step is a **Letta tool** (`compose_daily_briefing`) that reads from durable stores, not conversation memory. The agent calls this tool, which:
1. Reads the quantitative snapshot from `analytics.daily_snapshots` (PostgREST)
2. Reads the Slack vibe-check summaries from archival memory (tagged `daily_vibe_check` + date)
3. Computes trend comparisons (7-day, 30-day workday averages)
4. Formats a concise briefing highlighting standouts
5. Writes to the `daily_analytics_briefing` memory block (Letta API)
6. Writes to `analytics/briefings/YYYY-MM-DD.md` (filesystem)
7. Returns the briefing text to the agent

**Example Briefing Output:**

```
**Daily Analytics — Monday, Feb 17** (vs. 30-day avg)

**Drive Activity**
- 342 activities across 87 documents by 18 users
- Edits: 156 (▲ 23% above avg) — standout
- Most edited: "Q1 Budget Forecast" (12 edits, owned by phorwitz@)
- Most active: kswenson@ (45 activities), emcelroy@ (38)

**Email**
- 234 sent / 567 received (ratio: 0.41) — typical
- Total activity: 801 (within normal range)

**Slack** (covering Feb 14)
- 189 messages across 24 channels by 31 members
- Top: #dev-general (42 msgs), #random (28), #project-alpha (19)
- Members active: 31 (▼ 12% below avg) — low day

**Notable:** Drive edits spiked — likely Q1 planning push.
```

## Scheduling

| Job | Cron | Purpose |
|-----|------|---------|
| Slack CSV export trigger | `0 2 * * 1-5` (2 AM ET) | Trigger export for 3 days ago (Slack delay) |
| `collect_analytics_snapshot` | `30 2 * * 1-5` (2:30 AM ET, Mon-Fri) | Capture previous workday's quantitative metrics |
| `collect_analytics_snapshot` (weekend) | `30 2 * * 1` (2:30 AM Monday) | Also capture Sat+Sun if any activity |
| Slack vibe-check heartbeat | `0 3 * * 1-5` (3 AM ET) | Send Pulse Monitor the "generate vibe check" message |
| Compose briefing | `0 6 * * 1-5` (6 AM ET) | Pulse Monitor calls `compose_daily_briefing()` — reads from DB + archival memory, writes block + markdown |

**Sequence rationale:** Slack CSV export triggers first (2 AM), then quantitative snapshot captures at 2:30 AM (after CSV has ~30 min to generate). Slack vibe check starts at 3 AM (LLM-intensive, has up to 3 hours to complete piecemeal). By 6 AM, all components are ready and the final briefing is composed and written to memory block + markdown archive. Ready before the user's day starts.

## Weekend Handling

- **Collection**: Snapshots are collected Mon-Fri only. Monday's run also captures Saturday and Sunday.
- **Averages**: Weekend days are stored with `is_workday=false` and excluded from workday running averages.
- **Briefing**: Weekend stats are mentioned as a note ("Weekend: 23 Drive activities, 45 emails — 15% of typical workday") but not compared against workday baselines.

## Slack Data Delay

Slack analytics CSVs have a 2-3 day reporting delay. The snapshot records:
- `slack_covers_date`: the actual date the Slack data covers
- This may be 2-3 days behind `snapshot_date`
- The briefing clearly labels which date the Slack stats cover
- Over time, the 30-day average absorbs this delay naturally

## Backfill Strategy

Since both Admin Reports APIs retain 180 days of data, we can backfill approximately 6 months of historical Drive and Email snapshots on initial deployment. Slack data cannot be backfilled (CSVs are point-in-time).

**Backfill script**: Query Admin Reports API for each workday in the past 180 days, store in `daily_snapshots`. This provides an immediate baseline for trend comparison.

## Privacy Considerations

- **Email**: Org-level totals only (sent/received/ratio). No individual identification. The existing `get_email_analytics` tool's privacy model (hashed user IDs) is respected but not needed — we only use `mode="org"`.
- **Drive**: Individual activity is visible (who edited what) since this is inherent to Drive sharing. The design focuses on workspace-wide patterns, but top-5 active users are identified by email. This matches existing Drive audit visibility.
- **Slack**: Channel-level aggregates only. No message content in the quantitative snapshot. Qualitative summaries (optional Pulse Monitor layer) summarize themes, not reproduce messages.

## Implementation Phases

### Phase 1: MVP
- Database schema (`daily_snapshots`, `daily_top_items`)
- `collect_analytics_snapshot` Letta tool (quantitative: Drive + Email + Slack CSV)
- Scheduler jobs for the 4-step pipeline (CSV trigger → snapshot → vibe check → compose)
- Pulse Monitor memory block with briefing format instructions
- Markdown archive output (`analytics/briefings/YYYY-MM-DD.md`)
- Basic trend comparison (7-day and 30-day workday averages)

### Phase 2: Backfill + Baselines
- Historical backfill script (180 days of Drive + Email Admin Reports data)
- Standout detection with standard deviation flagging
- Tune vibe-check channel selection (top-N from analytics vs. curated list)

### Phase 3: Dashboard (Future)
- Web UI for browsing historical snapshots and trend charts
- Anomaly alerting via Slack DM

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `letta/daily_analytics_snapshot.py` | Create | New Letta tool: `collect_analytics_snapshot()` (persists to DB as side effect) |
| `letta/compose_daily_briefing.py` | Create | New Letta tool: `compose_daily_briefing()` (reads from DB + archival, writes block + markdown) |
| `letta/register_daily_analytics.py` | Create | Registration script for both tools |
| `migrations/analytics_schema.sql` | Create | Database schema for snapshots |
| `analytics/briefings/` | Create dir | Markdown archive for rendered briefings |
| Pulse Monitor memory blocks | Update | Add `daily_analytics_briefing` block + briefing format instructions |
| Scheduler jobs (x4) | Create | Slack CSV trigger, snapshot, vibe-check heartbeat, compose briefing |
| `scripts/backfill_analytics.py` | Create | Backfill 180 days of Drive + Email historical data |

## Existing Tools Reused (Not Modified)

- `collect_daily_workspace_activity()` from `drive_analytics_tools.py`
- `get_email_analytics()` from `email_analytics_tools.py`
- `analyze_slack_analytics()` from Slack analytics tools
- `trigger_slack_analytics_export()` from Slack analytics tools
- Pulse Monitor's `slack_pulse_reporting_process` for qualitative layer

## Dependencies

- Google Admin Reports API credentials (already configured: `admin-reports.credentials.json`)
- Slack analytics browser auth state (already configured)
- Supabase PostgreSQL (already running)
- Scheduler-service (already running, cron jobs now properly loading)

## Design Decisions

### Owning Agent: Pulse Monitor

The Pulse Monitor agent owns this capability. It already has Slack search/summary tools, the `slack_pulse_reporting_process` workflow, and organizational awareness as its core mission. The daily briefing agent remains focused on calendar/schedule.

### Slack Qualitative: Off-Hours, Piecemeal

The Slack vibe-check runs daily during off-hours (late night or early morning). Since the Pulse Monitor summarizes channels sequentially (each requiring tool calls), this may span multiple tool invocations. The workflow needs:

- A **scheduler heartbeat** that sends the Pulse Monitor a message like: *"Generate the daily Slack vibe check for yesterday across the top channels. After summarizing each channel, write the summary to archival memory tagged `daily_vibe_check` with date `YYYY-MM-DD`. When all channels are done, write a combined summary to archival memory with the same tag. Do NOT rely on conversation context to preserve these — the compose step will read them from archival memory."*
- The agent's `slack_pulse_reporting_process` memory block already documents this workflow
- If the workflow is interrupted (agent timeout, error), the scheduler can retry on the next heartbeat
- Off-hours timing (`0 3 * * 1-5` — 3 AM ET weekdays) avoids competing with user interactions and gives up to 3 hours to complete before the 6 AM briefing assembly

### Output: Memory Block + Markdown Archive

Briefings are written to **two locations**:

1. **Active memory block** (`daily_analytics_briefing`) — contains the most recent briefing only, so the agent can reference it conversationally. This keeps context load bounded: each briefing replaces the previous one. (~500-800 tokens typical.)

2. **Markdown file archive** — written to `analytics/briefings/YYYY-MM-DD.md` for permanent reference. These accumulate as a time series and are included in the regular backup. The agent can read historical files on demand (e.g., "compare today to last Monday").

The **database** (`daily_snapshots` table) stores the raw structured data for programmatic trend comparison. The markdown files are the human-readable rendered version.

### Intermediate Output Persistence (Critical)

**Problem:** The pipeline runs as 4 separate scheduler heartbeats, each sending an independent message to the Pulse Monitor agent. There is no guarantee the agent retains raw outputs from earlier steps when composing the final briefing. Conversation context may be summarized, truncated, or simply not referenced.

**Principle:** Every pipeline step must persist its output to a durable store as a **side effect inside the tool itself**. The compose step reads exclusively from these stores — never from conversation memory.

**Per-Step Persistence:**

| Step | Tool / Action | Persists To | How |
|------|---------------|-------------|-----|
| 1. Slack CSV trigger | `trigger_slack_analytics_export` | Slack servers (external) | Existing behavior; CSV is generated server-side |
| 2. Quantitative snapshot | `collect_analytics_snapshot` | `analytics.daily_snapshots` table (PostgREST) | Tool writes to DB as side effect before returning |
| 3. Slack vibe check | Pulse Monitor workflow | Agent archival memory (tagged `daily_vibe_check`, `YYYY-MM-DD`) | Agent instructed to `archival_memory_insert` each channel summary with date tag |
| 4. Compose briefing | `compose_daily_briefing` (new tool) | Memory block (`daily_analytics_briefing`) + Markdown file | Tool reads from DB + archival memory, writes both outputs |

**Step 2 detail — `collect_analytics_snapshot` writes to DB:**
The tool itself calls PostgREST to INSERT/UPSERT the snapshot row into `analytics.daily_snapshots` and top-N items into `analytics.daily_top_items`. This happens inside the tool body before the return statement. If the DB write fails, the tool returns an error — the agent doesn't need to handle persistence.

**Step 3 detail — Slack vibe check writes to archival memory:**
The Pulse Monitor's instructions for the vibe-check heartbeat must include: *"After summarizing each channel, write the summary to archival memory with the tag `daily_vibe_check` and the date `YYYY-MM-DD`. When all channels are done, write a final combined summary with the same tag."* This ensures the qualitative data survives independently of conversation context.

**Step 4 detail — `compose_daily_briefing` reads from durable stores:**
A new Letta tool that:
1. Queries `analytics.daily_snapshots` for the target date (PostgREST GET)
2. Queries the agent's archival memory for entries tagged `daily_vibe_check` + target date
3. Queries the last 7 and 30 workday snapshots for trend comparison
4. Computes deltas and flags standouts (>1 stddev from 30-day mean)
5. Formats the briefing text
6. Writes to the `daily_analytics_briefing` memory block (via Letta API)
7. Writes to `analytics/briefings/YYYY-MM-DD.md` (via filesystem or API)
8. Returns the briefing text to the agent for conversational reference

**Why not bypass the agent entirely?** The quantitative snapshot (step 2) could theoretically run as a direct HTTP scheduler action to a dedicated analytics endpoint, skipping the agent. However, keeping it as an agent tool provides:
- Unified error reporting (agent can surface failures conversationally)
- The ability for the agent to retry or adjust parameters
- A natural place to log "snapshot collected for date X" in the agent's message history for auditability
The compose step (step 4) benefits from agent involvement for the same reasons, plus the agent can add ad-hoc commentary or context the tool can't.

**Failure modes and recovery:**
- If step 2 fails (DB write error): Agent receives error, can retry or alert user. No partial data in DB.
- If step 3 fails mid-channel: Archival memory contains whatever channels completed. Compose step notes "Slack vibe check: partial (N of M channels)."
- If step 4 fails (can't read DB): Agent receives error. Snapshot data is safe in DB for manual or retry compose.
- If steps run out of order or overlap: `snapshot_date` is the primary key — UPSERT semantics prevent duplicates.
