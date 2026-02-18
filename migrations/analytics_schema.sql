-- Daily Analytics Briefing schema
-- Stores ephemeral metrics (Drive Admin Reports, Email Admin Reports, Slack CSVs)
-- that cannot be reconstructed after their retention windows expire.

CREATE SCHEMA IF NOT EXISTS analytics;

-- Main snapshot table: one row per date
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
  email_user_count           INT,

  -- Slack (CSV export — point-in-time, non-recoverable)
  slack_covers_date          DATE,
  slack_total_messages       INT,
  slack_channels_active      INT,
  slack_members_active       INT,

  -- Full detail for ad-hoc queries and future metrics
  raw_snapshot               JSONB NOT NULL,

  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Top-N items per day (normalized for querying)
CREATE TABLE analytics.daily_top_items (
  id             SERIAL PRIMARY KEY,
  snapshot_date  DATE NOT NULL REFERENCES analytics.daily_snapshots(snapshot_date),
  domain         TEXT NOT NULL,
  category       TEXT NOT NULL,
  rank           INT NOT NULL,
  item_title     TEXT,
  item_id        TEXT,
  item_owner     TEXT,
  count          INT NOT NULL,
  metadata       JSONB
);

CREATE INDEX idx_daily_top_domain ON analytics.daily_top_items(domain, category, snapshot_date);

-- Grant PostgREST access
GRANT USAGE ON SCHEMA analytics TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analytics TO service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO anon, authenticated;
