-- Migration 005: Change sync state table for Drive Changes API
--
-- This table stores the page token for the Drive Changes API,
-- allowing incremental change detection instead of polling all documents.
--
-- Key benefits:
-- - Single API call returns all changes since last sync
-- - Automatically detects new files, modifications, and deletions
-- - Much more efficient than per-document revision checks

-- Table to persist change tracking state
CREATE TABLE IF NOT EXISTS rag.change_sync_state (
    id TEXT PRIMARY KEY DEFAULT 'default',
    page_token TEXT NOT NULL,
    last_sync_at TIMESTAMPTZ,
    total_changes_processed BIGINT DEFAULT 0,
    new_files_count BIGINT DEFAULT 0,
    modified_files_count BIGINT DEFAULT 0,
    deleted_files_count BIGINT DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comment for documentation
COMMENT ON TABLE rag.change_sync_state IS 'Stores Drive Changes API page token for incremental change detection';
COMMENT ON COLUMN rag.change_sync_state.page_token IS 'The nextPageToken or newStartPageToken from Drive Changes API';
COMMENT ON COLUMN rag.change_sync_state.last_sync_at IS 'When the last successful sync completed';
COMMENT ON COLUMN rag.change_sync_state.total_changes_processed IS 'Cumulative count of all changes processed';
