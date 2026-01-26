-- Migration: Create user_conversations table for Letta Conversations tracking
-- Date: 2026-01-26
-- Purpose: Maps users to their Letta conversation IDs for multi-user agent access
--
-- Architecture Note (from Task 0 verification):
-- Letta 0.16.3 uses isolated_block_labels for per-conversation block isolation.
-- This table tracks which conversation belongs to which user, enabling:
-- - Conversation lookup on subsequent messages
-- - Activity tracking for TTL/cleanup
-- - User-source-agent tuple uniqueness

CREATE TABLE IF NOT EXISTS user_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,              -- Slack user ID, email, etc.
    user_source TEXT NOT NULL,          -- 'slack', 'email', 'web'
    agent_id TEXT NOT NULL,             -- Letta agent ID
    conversation_id TEXT NOT NULL,      -- Letta conversation ID
    identity_id TEXT,                   -- Letta identity ID (optional)
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, user_source, agent_id)
);

-- Index for fast lookup by user_id + agent_id (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_user_conversations_lookup
    ON user_conversations(user_id, agent_id);

-- Index for cleanup of inactive conversations
CREATE INDEX IF NOT EXISTS idx_user_conversations_last_active
    ON user_conversations(last_active_at);

-- Documentation
COMMENT ON TABLE user_conversations IS 'Maps users to their Letta conversation IDs for multi-user agent access';
COMMENT ON COLUMN user_conversations.user_id IS 'External user identifier (Slack ID, email)';
COMMENT ON COLUMN user_conversations.user_source IS 'Source platform: slack, email, web';
COMMENT ON COLUMN user_conversations.agent_id IS 'Letta agent ID this conversation belongs to';
COMMENT ON COLUMN user_conversations.conversation_id IS 'Letta Conversations API conversation_id';
COMMENT ON COLUMN user_conversations.identity_id IS 'Optional Letta identity ID for future identity linking';
COMMENT ON COLUMN user_conversations.last_active_at IS 'Timestamp of last message, used for TTL cleanup';
