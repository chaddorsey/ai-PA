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
    """Tracking state for a document in the coordination catalog."""

    drive_file_id: str
    title: str
    mime_type: Optional[str] = None
    last_seen_revision_id: Optional[str] = None
    last_indexed_revision_id: Optional[str] = None
    last_indexed_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    owner_email: Optional[str] = None


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
    total_chunks_searched: int


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
