-- Migration 003: Document snapshots table for Phase 2 edit tracking
--
-- Snapshots are stored on filesystem at /Volumes/main-filestore/ai-PA-data/drive-rag-snapshots/
-- This table stores metadata and pointers to the files.
--
-- Directory structure:
--   {base_path}/{file_id_prefix}/{file_id}/{revision_id}.json.gz
--
-- Example:
--   /Volumes/main-filestore/ai-PA-data/drive-rag-snapshots/1K/1Kl-akJFpm.../abc123.json.gz

CREATE TABLE IF NOT EXISTS rag.document_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drive_file_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,

    -- Content metadata (actual content stored on filesystem)
    content_hash TEXT NOT NULL,
    normalized_text_length INTEGER NOT NULL,
    blocks_count INTEGER NOT NULL,
    compressed_size_bytes INTEGER,

    -- Filesystem location
    snapshot_path TEXT NOT NULL,  -- Relative path from base directory

    -- Attribution from Drive API
    modifier_email TEXT,
    modifier_name TEXT,
    modified_time TIMESTAMPTZ,

    -- Tracking
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_file_revision_snapshot UNIQUE (drive_file_id, revision_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_snapshots_file ON rag.document_snapshots(drive_file_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON rag.document_snapshots(modified_time DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_modifier ON rag.document_snapshots(modifier_email);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON rag.document_snapshots(created_at DESC);

-- Comments for documentation
COMMENT ON TABLE rag.document_snapshots IS 'Metadata for document content snapshots stored on filesystem';
COMMENT ON COLUMN rag.document_snapshots.snapshot_path IS 'Relative path from SNAPSHOT_BASE_PATH to the gzipped JSON file';
COMMENT ON COLUMN rag.document_snapshots.content_hash IS 'SHA-256 hash of normalized text for change detection';
