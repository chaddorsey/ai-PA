-- gmail-watch-service/scripts/init_schema.sql
-- Schema for Gmail Watch Service
-- This file must be kept in sync with src/gmail_watch/models.py

CREATE SCHEMA IF NOT EXISTS gmail_watch;

-- Watched threads registry
-- Tracks Gmail threads being monitored for replies
CREATE TABLE IF NOT EXISTS gmail_watch.watched_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id VARCHAR(255) NOT NULL UNIQUE,
    subject TEXT,
    original_recipients TEXT[],
    watch_type VARCHAR(50) DEFAULT 'standard',

    -- Follow-up timing
    followup_seconds INTEGER,
    source VARCHAR(50) DEFAULT 'manual',
    bcc_address VARCHAR(255),
    followup_due_at TIMESTAMPTZ,
    followup_notified BOOLEAN DEFAULT FALSE,

    -- Reply tracking
    reply_received BOOLEAN DEFAULT FALSE,
    reply_received_at TIMESTAMPTZ,
    reply_message_id VARCHAR(255),

    -- Timestamps and activity
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 1,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,

    -- Extensible metadata
    extra_data JSONB
);

-- History sync state (singleton pattern - always id=1)
-- Tracks Gmail API sync state for incremental history pulls
CREATE TABLE IF NOT EXISTS gmail_watch.sync_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    history_id BIGINT NOT NULL,
    watch_expiration TIMESTAMPTZ,
    watch_resource_id VARCHAR(255),
    last_pull_at TIMESTAMPTZ,
    last_notification_at TIMESTAMPTZ,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMPTZ
);

-- Notification log (audit trail)
-- Records all notifications sent to the Letta agent
CREATE TABLE IF NOT EXISTS gmail_watch.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255),
    notification_type VARCHAR(50) NOT NULL,
    notified_at TIMESTAMPTZ DEFAULT NOW(),
    agent_id VARCHAR(255),
    message_sent TEXT,
    extra_data JSONB
);

-- Indexes for watched_threads
CREATE INDEX IF NOT EXISTS idx_watched_threads_active
    ON gmail_watch.watched_threads(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_watched_threads_thread_id
    ON gmail_watch.watched_threads(thread_id);
CREATE INDEX IF NOT EXISTS idx_watched_threads_followup
    ON gmail_watch.watched_threads(followup_due_at)
    WHERE is_active = TRUE AND followup_seconds IS NOT NULL AND NOT followup_notified;

-- Indexes for notifications
CREATE INDEX IF NOT EXISTS idx_notifications_thread
    ON gmail_watch.notifications(thread_id);
CREATE INDEX IF NOT EXISTS idx_notifications_notified_at
    ON gmail_watch.notifications(notified_at);
