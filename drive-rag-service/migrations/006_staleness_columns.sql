-- Migration 006: Add staleness tracking columns to document_state
--
-- These columns support the staleness-sweep system which prioritizes
-- re-indexing based on how likely a document is to have changed.
--
-- Tiers (cold -> warm -> hot) indicate expected change frequency.
-- The sweep process checks documents in tier order, promoting/demoting
-- based on observed activity.

-- Add staleness tracking columns
ALTER TABLE rag.document_state
    ADD COLUMN IF NOT EXISTS staleness_tier TEXT NOT NULL DEFAULT 'cold',
    ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS check_count INTEGER NOT NULL DEFAULT 0;

-- Composite index for sweep queries: find documents by tier,
-- ordered by least-recently-checked first (NULLs = never checked = highest priority)
CREATE INDEX IF NOT EXISTS idx_doc_state_staleness_tier
    ON rag.document_state (staleness_tier, last_checked_at ASC NULLS FIRST);

-- Documentation
COMMENT ON COLUMN rag.document_state.staleness_tier IS 'Expected change frequency: cold (rarely), warm (sometimes), hot (frequently)';
COMMENT ON COLUMN rag.document_state.last_checked_at IS 'When the staleness sweep last inspected this document';
COMMENT ON COLUMN rag.document_state.last_activity_at IS 'When activity was last detected (edit, view, share, etc.)';
COMMENT ON COLUMN rag.document_state.check_count IS 'Total number of times this document has been checked by the sweep';
