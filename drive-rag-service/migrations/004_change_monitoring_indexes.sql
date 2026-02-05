-- Migration 004: Indexes for efficient change monitoring queries
--
-- These indexes optimize the priority-based document scanning:
-- - High priority: documents modified in last 24 hours
-- - Medium priority: documents modified 1-7 days ago
-- - Low priority: older documents
--
-- The last_indexed_at index enables efficient queries for documents
-- that haven't been checked recently.

-- Index on modified_time for priority tier queries
CREATE INDEX IF NOT EXISTS idx_doc_state_modified_time
    ON rag.document_state(modified_time DESC);

-- Index on last_indexed_at for finding stale documents
CREATE INDEX IF NOT EXISTS idx_doc_state_last_indexed
    ON rag.document_state(last_indexed_at DESC NULLS LAST);

-- Composite index for common query pattern: modified but not recently indexed
CREATE INDEX IF NOT EXISTS idx_doc_state_modified_indexed
    ON rag.document_state(modified_time DESC, last_indexed_at DESC NULLS LAST);

-- Comments for documentation
COMMENT ON INDEX rag.idx_doc_state_modified_time IS 'Optimizes priority-tier queries based on modification time';
COMMENT ON INDEX rag.idx_doc_state_last_indexed IS 'Optimizes queries for documents that need reindexing';
