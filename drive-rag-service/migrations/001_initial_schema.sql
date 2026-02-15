-- Migration 001: Initial rag schema
--
-- Creates the complete rag schema for the Drive RAG service.
-- Generated from live database after restore from pg_cluster backup.
--
-- Prerequisites: pgvector extension must be available.

-- Enable pgvector extension (required for vector(1536) columns)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the rag schema
CREATE SCHEMA IF NOT EXISTS rag;

SET default_tablespace = '';
SET default_table_access_method = heap;

--
-- Tables
--

CREATE TABLE rag.document_activity (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    drive_file_id text NOT NULL,
    activity_type text NOT NULL,
    actor_email text,
    actor_name text,
    activity_time timestamp with time zone NOT NULL,
    target_user_email text,
    comment_content text,
    discovered_at timestamp with time zone DEFAULT now()
);

CREATE TABLE rag.document_chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    drive_file_id text NOT NULL,
    revision_id text NOT NULL,
    title text NOT NULL,
    chunk_id text NOT NULL,
    outline_path text[],
    block_start_id text,
    block_end_id text,
    char_start integer,
    char_end integer,
    chunk_text text NOT NULL,
    chunk_hash text NOT NULL,
    embedding public.vector(1536),
    indexed_at timestamp with time zone DEFAULT now()
);

CREATE TABLE rag.document_entities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    drive_file_id text NOT NULL,
    entity_type text NOT NULL,
    entity_name text NOT NULL,
    entity_normalized text,
    mention_count integer DEFAULT 1,
    first_seen_chunk_id text,
    confidence double precision,
    co_occurring_entities text[],
    extracted_at timestamp with time zone DEFAULT now(),
    extraction_version integer DEFAULT 1
);

CREATE TABLE rag.document_revisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    drive_file_id text NOT NULL,
    revision_id text NOT NULL,
    modified_time timestamp with time zone,
    modifier_email text,
    modifier_name text,
    modifier_permission_id text,
    keep_forever boolean DEFAULT false,
    published boolean DEFAULT false,
    content_hash text,
    has_snapshot boolean DEFAULT false,
    snapshot_uri text,
    discovered_at timestamp with time zone DEFAULT now()
);

CREATE TABLE rag.document_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    drive_file_id text NOT NULL,
    revision_id text NOT NULL,
    content_hash text NOT NULL,
    normalized_text_length integer NOT NULL,
    blocks_count integer NOT NULL,
    compressed_size_bytes integer,
    snapshot_path text NOT NULL,
    modifier_email text,
    modifier_name text,
    modified_time timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

COMMENT ON TABLE rag.document_snapshots IS 'Metadata for document content snapshots stored on filesystem';
COMMENT ON COLUMN rag.document_snapshots.content_hash IS 'SHA-256 hash of normalized text for change detection';
COMMENT ON COLUMN rag.document_snapshots.snapshot_path IS 'Relative path from SNAPSHOT_BASE_PATH to the gzipped JSON file';

CREATE TABLE rag.document_state (
    drive_file_id text NOT NULL,
    title text NOT NULL,
    mime_type text,
    last_seen_revision_id text,
    last_indexed_revision_id text,
    last_indexed_at timestamp with time zone,
    content_hash text,
    owner_email text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_time timestamp with time zone,
    modified_time timestamp with time zone,
    viewed_by_me_time timestamp with time zone,
    shared_with_me_time timestamp with time zone,
    owner_name text,
    owner_permission_id text,
    last_modifier_email text,
    last_modifier_name text,
    sharing_user_email text,
    sharing_user_name text,
    parent_folder_ids text[],
    folder_path text[],
    folder_path_ids text[],
    shared boolean DEFAULT false,
    sharing_domains text[],
    has_external_access boolean DEFAULT false,
    is_shared_drive boolean DEFAULT false,
    web_view_link text,
    web_content_link text,
    file_size_bytes bigint,
    description text,
    starred boolean DEFAULT false,
    trashed boolean DEFAULT false,
    labels jsonb,
    can_edit boolean DEFAULT false,
    can_share boolean DEFAULT false,
    can_read_revisions boolean DEFAULT false,
    collaborator_emails text[],
    related_file_ids text[],
    first_indexed_at timestamp with time zone,
    index_version integer DEFAULT 1
);

CREATE TABLE rag.folder_cache (
    folder_id text NOT NULL,
    name text NOT NULL,
    parent_folder_ids text[],
    folder_path text[],
    folder_path_ids text[],
    depth integer DEFAULT 0,
    created_time timestamp with time zone,
    modified_time timestamp with time zone,
    owner_email text,
    owner_name text,
    shared boolean DEFAULT false,
    cached_at timestamp with time zone DEFAULT now(),
    stale_after timestamp with time zone DEFAULT (now() + '1 day'::interval)
);

--
-- Primary keys
--

ALTER TABLE ONLY rag.document_activity
    ADD CONSTRAINT document_activity_pkey PRIMARY KEY (id);

ALTER TABLE ONLY rag.document_chunks
    ADD CONSTRAINT document_chunks_pkey PRIMARY KEY (id);

ALTER TABLE ONLY rag.document_entities
    ADD CONSTRAINT document_entities_pkey PRIMARY KEY (id);

ALTER TABLE ONLY rag.document_revisions
    ADD CONSTRAINT document_revisions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY rag.document_snapshots
    ADD CONSTRAINT document_snapshots_pkey PRIMARY KEY (id);

ALTER TABLE ONLY rag.document_state
    ADD CONSTRAINT document_state_pkey PRIMARY KEY (drive_file_id);

ALTER TABLE ONLY rag.folder_cache
    ADD CONSTRAINT folder_cache_pkey PRIMARY KEY (folder_id);

--
-- Unique constraints
--

ALTER TABLE ONLY rag.document_chunks
    ADD CONSTRAINT unique_chunk UNIQUE (drive_file_id, chunk_id);

ALTER TABLE ONLY rag.document_entities
    ADD CONSTRAINT unique_file_entity UNIQUE (drive_file_id, entity_type, entity_normalized);

ALTER TABLE ONLY rag.document_revisions
    ADD CONSTRAINT unique_file_revision UNIQUE (drive_file_id, revision_id);

ALTER TABLE ONLY rag.document_snapshots
    ADD CONSTRAINT unique_file_revision_snapshot UNIQUE (drive_file_id, revision_id);

--
-- Indexes
--

CREATE INDEX idx_activity_actor ON rag.document_activity USING btree (actor_email);
CREATE INDEX idx_activity_file ON rag.document_activity USING btree (drive_file_id);
CREATE INDEX idx_activity_time ON rag.document_activity USING btree (activity_time);
CREATE INDEX idx_activity_type ON rag.document_activity USING btree (activity_type);

CREATE INDEX idx_chunks_embedding ON rag.document_chunks USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');
CREATE INDEX idx_chunks_file_id ON rag.document_chunks USING btree (drive_file_id);
CREATE INDEX idx_chunks_revision ON rag.document_chunks USING btree (drive_file_id, revision_id);

CREATE INDEX idx_doc_state_collaborators ON rag.document_state USING gin (collaborator_emails);
CREATE INDEX idx_doc_state_created ON rag.document_state USING btree (created_time);
CREATE INDEX idx_doc_state_domains ON rag.document_state USING gin (sharing_domains);
CREATE INDEX idx_doc_state_folder_path ON rag.document_state USING gin (folder_path);
CREATE INDEX idx_doc_state_indexed ON rag.document_state USING btree (last_indexed_at);
CREATE INDEX idx_doc_state_last_indexed ON rag.document_state USING btree (last_indexed_at DESC NULLS LAST);
COMMENT ON INDEX rag.idx_doc_state_last_indexed IS 'Optimizes queries for documents that need reindexing';
CREATE INDEX idx_doc_state_mime_type ON rag.document_state USING btree (mime_type);
CREATE INDEX idx_doc_state_modified ON rag.document_state USING btree (modified_time);
CREATE INDEX idx_doc_state_modified_indexed ON rag.document_state USING btree (modified_time DESC, last_indexed_at DESC NULLS LAST);
CREATE INDEX idx_doc_state_modified_time ON rag.document_state USING btree (modified_time DESC);
COMMENT ON INDEX rag.idx_doc_state_modified_time IS 'Optimizes priority-tier queries based on modification time';
CREATE INDEX idx_doc_state_owner ON rag.document_state USING btree (owner_email);
CREATE INDEX idx_doc_state_parent_folders ON rag.document_state USING gin (parent_folder_ids);

CREATE INDEX idx_entities_file ON rag.document_entities USING btree (drive_file_id);
CREATE INDEX idx_entities_name ON rag.document_entities USING btree (entity_normalized);
CREATE INDEX idx_entities_type ON rag.document_entities USING btree (entity_type);

CREATE INDEX idx_folder_cache_owner ON rag.folder_cache USING btree (owner_email);
CREATE INDEX idx_folder_cache_parent ON rag.folder_cache USING gin (parent_folder_ids);
CREATE INDEX idx_folder_cache_path ON rag.folder_cache USING gin (folder_path);
CREATE INDEX idx_folder_cache_stale ON rag.folder_cache USING btree (stale_after);

CREATE INDEX idx_revisions_file ON rag.document_revisions USING btree (drive_file_id);

--
-- Search function (in public schema, references rag tables)
--

CREATE OR REPLACE FUNCTION public.search_document_chunks(
    query_embedding vector,
    match_count integer DEFAULT 10,
    filter_file_ids text[] DEFAULT NULL::text[]
)
RETURNS TABLE(
    drive_file_id text,
    title text,
    chunk_text text,
    outline_path text[],
    similarity double precision
)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        dc.drive_file_id,
        dc.title,
        dc.chunk_text,
        dc.outline_path,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM rag.document_chunks dc
    WHERE
        dc.embedding IS NOT NULL
        AND (filter_file_ids IS NULL OR dc.drive_file_id = ANY(filter_file_ids))
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$function$;

--
-- Permissions (for PostgREST / Supabase roles)
--

GRANT USAGE ON SCHEMA rag TO anon, authenticated, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA rag TO anon, authenticated, service_role;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO service_role;
GRANT EXECUTE ON FUNCTION public.search_document_chunks TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT ALL ON TABLES TO service_role;
