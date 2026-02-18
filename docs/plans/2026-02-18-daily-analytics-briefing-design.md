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

A new Letta tool that gathers quantitative metrics from all three domains and returns structured JSON. This is the "capture" layer — runs daily, stores results.

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
  └── Returns: structured JSON snapshot
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

### Component 4: Agent Instructions (Pulse Monitor / Daily Briefing Agent)

The agent receives the snapshot JSON and comparison data, then:
1. Formats a concise briefing highlighting standouts
2. Optionally adds qualitative Slack vibe summary (using existing Pulse Monitor workflow)
3. Writes to a memory block or sends via Slack DM

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
| `collect_analytics_snapshot` | `0 8 * * 1-5` (8 AM ET, Mon-Fri) | Capture previous workday's metrics |
| `collect_analytics_snapshot` (weekend) | `0 8 * * 1` (8 AM Monday) | Also capture Sat+Sun if any activity |
| Slack CSV export trigger | `0 7 * * 1-5` (7 AM ET) | Trigger export for 3 days ago (Slack delay) |

The 8 AM collection time ensures the previous day's data has fully propagated through Google's Admin Reports pipeline (which can have a few hours of lag).

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

### Phase 1: MVP (This Design)
- New `collect_analytics_snapshot` Letta tool combining existing APIs
- `daily_snapshots` + `daily_top_items` tables in Supabase
- Scheduler cron job for daily collection
- Basic trend comparison (7-day and 30-day averages)
- Agent instructions for formatting the briefing

### Phase 2: Backfill + Enrichment
- Historical backfill script (180 days of Drive + Email)
- Standout detection with standard deviation flagging
- Slack qualitative integration (Pulse Monitor vibe summary)

### Phase 3: Dashboard (Future)
- Web UI for browsing historical snapshots
- Trend charts (drive activity over time, email volume, etc.)
- Alerting for anomalies

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `letta/daily_analytics_snapshot.py` | Create | New Letta tool: `collect_analytics_snapshot()` |
| `letta/register_daily_analytics.py` | Create | Registration script for the tool |
| `migrations/analytics_schema.sql` | Create | Database schema for snapshots |
| Agent memory block | Update | Add briefing format instructions |
| Scheduler job | Create | Daily 8 AM cron via scheduler-service API |

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

## Open Questions

1. **Which agent runs this?** Options: extend the daily briefing agent, extend the Pulse Monitor, or create a dedicated analytics agent. Recommendation: extend the daily briefing agent since it already runs on schedule and could incorporate this into the existing calendar briefing.

2. **Slack qualitative frequency?** The Pulse Monitor's vibe-check workflow is LLM-intensive. Daily may be excessive. Could be workday-only or on-demand.

3. **Alerting channel?** Should standout stats be pushed to a Slack DM, or just stored for the next time the user asks for a briefing?
