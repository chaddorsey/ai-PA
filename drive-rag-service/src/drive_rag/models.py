"""Pydantic models for Drive RAG service."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class StructureBlock(BaseModel):
    """A structural block from a Google Doc (paragraph, heading, list item, etc.)."""

    block_id: str
    type: str  # heading, paragraph, list_item, table_row, unknown
    outline_path: list[str] = Field(default_factory=list)
    heading_level: Optional[int] = None
    list_level: Optional[int] = None
    text_hash: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    text: str = ""


class NormalizedSnapshot(BaseModel):
    """Result of normalizing a Google Doc."""

    normalized_text: str
    normalized_hash: str
    blocks: list[StructureBlock]


class ChunkRecord(BaseModel):
    """A chunk of text from a document, ready for embedding."""

    drive_file_id: str
    revision_id: str
    title: str
    chunk_id: str
    outline_path: list[str] = Field(default_factory=list)
    block_start_id: str
    block_end_id: str
    char_start: int
    char_end: int
    chunk_text: str
    chunk_hash: str


class DocumentState(BaseModel):
    """Tracking state for a document in the coordination catalog.

    This expanded model captures comprehensive metadata for:
    - Document discovery and tracking
    - Folder hierarchy traversal
    - User/ownership attribution
    - Sharing and permissions analysis
    - Graphiti/Neo4j entity-relationship building
    """

    drive_file_id: str
    title: str
    mime_type: Optional[str] = None

    # Revision tracking
    last_seen_revision_id: Optional[str] = None
    last_indexed_revision_id: Optional[str] = None
    last_indexed_at: Optional[datetime] = None
    content_hash: Optional[str] = None

    # Timestamps from Drive API
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None
    viewed_by_me_time: Optional[datetime] = None
    shared_with_me_time: Optional[datetime] = None

    # Ownership/Users
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None
    owner_permission_id: Optional[str] = None
    last_modifier_email: Optional[str] = None
    last_modifier_name: Optional[str] = None
    sharing_user_email: Optional[str] = None
    sharing_user_name: Optional[str] = None

    # Folder hierarchy
    parent_folder_ids: list[str] = Field(default_factory=list)
    folder_path: list[str] = Field(default_factory=list)
    folder_path_ids: list[str] = Field(default_factory=list)

    # Sharing/Permissions
    shared: bool = False
    sharing_domains: list[str] = Field(default_factory=list)
    has_external_access: bool = False
    is_shared_drive: bool = False

    # Links
    web_view_link: Optional[str] = None

    # File properties
    file_size_bytes: Optional[int] = None
    description: Optional[str] = None
    starred: bool = False
    trashed: bool = False

    # Capabilities
    can_edit: bool = False
    can_share: bool = False
    can_read_revisions: bool = False

    # For Graphiti entity analysis
    collaborator_emails: list[str] = Field(default_factory=list)

    # Ingestion metadata
    first_indexed_at: Optional[datetime] = None
    index_version: int = 1


class FolderCache(BaseModel):
    """Cached folder metadata for efficient hierarchy lookups."""

    folder_id: str
    name: str

    # Hierarchy
    parent_folder_ids: list[str] = Field(default_factory=list)
    folder_path: list[str] = Field(default_factory=list)
    folder_path_ids: list[str] = Field(default_factory=list)
    depth: int = 0

    # Timestamps
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None

    # Ownership
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None

    # Sharing
    shared: bool = False

    # Cache management
    cached_at: Optional[datetime] = None
    stale_after: Optional[datetime] = None


class DocumentRevision(BaseModel):
    """Revision metadata for edit tracking (Phase 2)."""

    drive_file_id: str
    revision_id: str

    # Revision metadata
    modified_time: Optional[datetime] = None
    modifier_email: Optional[str] = None
    modifier_name: Optional[str] = None
    modifier_permission_id: Optional[str] = None

    # Properties
    keep_forever: bool = False
    published: bool = False

    # For diff tracking
    content_hash: Optional[str] = None
    has_snapshot: bool = False
    snapshot_uri: Optional[str] = None


class DocumentSnapshot(BaseModel):
    """Metadata for a stored document snapshot (Phase 2).

    The actual content is stored on filesystem; this model tracks metadata.
    """

    drive_file_id: str
    revision_id: str

    # Content metadata
    content_hash: str
    normalized_text_length: int
    blocks_count: int
    compressed_size_bytes: Optional[int] = None

    # Filesystem location (relative path from base)
    snapshot_path: str

    # Attribution
    modifier_email: Optional[str] = None
    modifier_name: Optional[str] = None
    modified_time: Optional[datetime] = None

    # Tracking
    created_at: Optional[datetime] = None


class IngestionResult(BaseModel):
    """Result of ingesting a document."""

    status: str  # indexed, skipped, error
    drive_file_id: str
    revision_id: Optional[str] = None
    reason: Optional[str] = None
    chunks_added: int = 0
    chunks_updated: int = 0
    chunks_deleted: int = 0


class SearchRequest(BaseModel):
    """Request for semantic search."""

    query: str
    limit: int = Field(default=10, ge=1, le=50)
    file_ids: Optional[list[str]] = None


class SearchResult(BaseModel):
    """A single search result."""

    drive_file_id: str
    title: str
    chunk_text: str
    outline_path: list[str]
    similarity: float


class SearchResponse(BaseModel):
    """Response from semantic search."""

    query: str
    results: list[SearchResult]
    total_results: int


class IngestFolderRequest(BaseModel):
    """Request to ingest all docs in a folder."""

    folder_id: str
    recursive: bool = False


class IngestFolderResponse(BaseModel):
    """Response from folder ingestion."""

    folder_id: str
    documents_processed: int
    documents_skipped: int
    documents_failed: int
    results: list[IngestionResult]


class DocumentStatusResponse(BaseModel):
    """Status of a document's indexing."""

    drive_file_id: str
    indexed: bool
    title: Optional[str] = None
    revision_id: Optional[str] = None
    chunk_count: int = 0
    last_indexed_at: Optional[datetime] = None
    owner_email: Optional[str] = None


class EditRecord(BaseModel):
    """A single edit/revision record."""

    revision_id: str
    modifier_email: Optional[str] = None
    modifier_name: Optional[str] = None
    modified_time: Optional[datetime] = None
    has_snapshot: bool = False


class DocumentEditsResponse(BaseModel):
    """Response containing document edit history."""

    drive_file_id: str
    title: Optional[str] = None
    edit_count: int
    editors: list[str] = Field(default_factory=list)
    edits: list[EditRecord] = Field(default_factory=list)


class BlockChangeRecord(BaseModel):
    """A single block-level change."""

    change_type: str  # added, deleted, modified, moved
    block_type: str
    text_preview: str
    section: Optional[str] = None


class DocumentDiffResponse(BaseModel):
    """Response containing diff between two document versions."""

    drive_file_id: str
    from_revision: Optional[str] = None
    to_revision: Optional[str] = None
    blocks_added: int = 0
    blocks_deleted: int = 0
    blocks_modified: int = 0
    blocks_moved: int = 0
    changes: list[BlockChangeRecord] = Field(default_factory=list)
    summary: Optional[str] = None


class ScanChangesResponse(BaseModel):
    """Response from change monitoring scan."""

    priority: str
    documents_scanned: int = 0
    documents_changed: int = 0
    documents_reindexed: int = 0
    documents_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    error_count: int = 0
    scan_duration_seconds: float = 0.0
    dry_run: bool = False


class ChangedDocumentRecord(BaseModel):
    """A document that was recently changed."""

    drive_file_id: str
    title: str
    modified_time: Optional[datetime] = None
    modifier_email: Optional[str] = None
    modifier_name: Optional[str] = None
    has_snapshot: bool = False


class ChangedDocumentsResponse(BaseModel):
    """Response containing list of recently changed documents."""

    total_changed: int
    since: Optional[datetime] = None
    documents: list[ChangedDocumentRecord] = Field(default_factory=list)


class RetentionBreakdownTier(BaseModel):
    """Breakdown for a single retention tier."""

    days: str
    kept: int
    deleted: Optional[int] = None


class RetentionBreakdown(BaseModel):
    """Breakdown of retention by tier."""

    tier1_full_retention: RetentionBreakdownTier
    tier2_daily_retention: RetentionBreakdownTier
    tier3_archive: RetentionBreakdownTier


class RetentionResponse(BaseModel):
    """Response from snapshot retention cleanup."""

    snapshots_analyzed: int = 0
    snapshots_kept: int = 0
    snapshots_deleted: int = 0
    space_freed_bytes: int = 0
    space_freed_mb: float = 0.0
    dry_run: bool = True
    error_count: int = 0
    errors: list[str] = Field(default_factory=list)
    breakdown: Optional[RetentionBreakdown] = None
