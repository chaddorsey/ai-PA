"""FastAPI application for Drive RAG service.

Provides HTTP endpoints for:
- Document ingestion (single file or folder)
- Semantic search across indexed documents
- Status queries for indexed documents
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from drive_rag.db import get_db
from drive_rag.embedder import get_embedder
from drive_rag.ingestion import ingest_document, ingest_folder
from drive_rag.models import (
    BlockChangeRecord,
    DocumentDiffResponse,
    DocumentEditsResponse,
    DocumentStatusResponse,
    EditRecord,
    IngestFolderRequest,
    IngestFolderResponse,
    IngestionResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - initialize and cleanup resources."""
    logger.info("starting_drive_rag_service")

    # Pre-initialize clients to validate configuration
    try:
        get_db()
        get_embedder()
        logger.info("clients_initialized")
    except Exception as e:
        logger.error("initialization_failed", error=str(e))
        raise

    yield

    logger.info("shutting_down_drive_rag_service")


app = FastAPI(
    title="Drive RAG Service",
    description="Document ingestion and semantic search for Google Drive documents",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "drive-rag-service"}


# =====================
# Ingestion Endpoints
# =====================


@app.post("/v1/ingest/{file_id}", response_model=IngestionResult)
async def ingest_single_document(
    file_id: str,
    force: bool = Query(False, description="Force re-indexing even if unchanged"),
    extract_entities: Optional[bool] = Query(None, description="Extract entities to knowledge graph"),
):
    """Ingest a single Google Doc into the RAG system.

    Args:
        file_id: Google Drive file ID
        force: Force re-indexing even if document hasn't changed
        extract_entities: Extract entities to knowledge graph (defaults to ENABLE_ENTITY_EXTRACTION env var)

    Returns:
        IngestionResult with status and statistics
    """
    logger.info("ingest_request", file_id=file_id, force=force, extract_entities=extract_entities)

    try:
        result = await ingest_document(file_id=file_id, force=force, extract_entities=extract_entities)
        return result
    except Exception as e:
        logger.exception("ingest_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/ingest/folder/{folder_id}", response_model=IngestFolderResponse)
async def ingest_folder_documents(
    folder_id: str,
    recursive: bool = Query(False, description="Include subfolders (not yet implemented)"),
):
    """Ingest all Google Docs in a Drive folder.

    Args:
        folder_id: Google Drive folder ID
        recursive: Whether to include subfolders (not yet implemented)

    Returns:
        IngestFolderResponse with results for each document
    """
    logger.info("ingest_folder_request", folder_id=folder_id, recursive=recursive)

    try:
        result = await ingest_folder(folder_id=folder_id, recursive=recursive)
        return result
    except Exception as e:
        logger.exception("ingest_folder_failed", folder_id=folder_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Status Endpoints
# =====================


@app.get("/v1/status/{file_id}", response_model=DocumentStatusResponse)
async def get_document_status(file_id: str):
    """Get indexing status for a document.

    Args:
        file_id: Google Drive file ID

    Returns:
        DocumentStatusResponse with indexing status and metadata
    """
    db = get_db()

    state = db.get_document_state(file_id)

    if not state:
        return DocumentStatusResponse(
            drive_file_id=file_id,
            indexed=False,
            chunk_count=0,
        )

    chunk_count = db.get_chunk_count(file_id)

    return DocumentStatusResponse(
        drive_file_id=file_id,
        indexed=state.last_indexed_at is not None,
        title=state.title,
        revision_id=state.last_indexed_revision_id,
        chunk_count=chunk_count,
        last_indexed_at=state.last_indexed_at,
        owner_email=state.owner_email,
    )


@app.get("/v1/documents", response_model=list[DocumentStatusResponse])
async def list_indexed_documents(
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List all indexed documents.

    Args:
        limit: Maximum number of documents to return
        offset: Offset for pagination

    Returns:
        List of document status objects
    """
    db = get_db()

    documents = db.get_indexed_documents(limit=limit, offset=offset)

    results = []
    for doc in documents:
        chunk_count = db.get_chunk_count(doc.drive_file_id)
        results.append(
            DocumentStatusResponse(
                drive_file_id=doc.drive_file_id,
                indexed=doc.last_indexed_at is not None,
                title=doc.title,
                revision_id=doc.last_indexed_revision_id,
                chunk_count=chunk_count,
                last_indexed_at=doc.last_indexed_at,
                owner_email=doc.owner_email,
            )
        )

    return results


# =====================
# Search Endpoints
# =====================


@app.post("/v1/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """Search indexed documents using semantic similarity.

    Args:
        request: Search request with query and optional filters

    Returns:
        SearchResponse with ranked results
    """
    logger.info(
        "search_request",
        query=request.query,
        limit=request.limit,
        file_ids=request.file_ids,
    )

    db = get_db()
    embedder = get_embedder()

    try:
        # Embed the query
        query_embedding = await embedder.embed_single(request.query)

        # Search for similar chunks
        results = db.search_similar(
            query_embedding=query_embedding,
            limit=request.limit,
            file_ids=request.file_ids,
        )

        logger.info("search_complete", result_count=len(results))

        return SearchResponse(
            query=request.query,
            results=results,
            total_results=len(results),
        )
    except Exception as e:
        logger.exception("search_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Admin Endpoints
# =====================


@app.delete("/v1/documents/{file_id}")
async def delete_document(file_id: str):
    """Delete a document and all its chunks from the index.

    Args:
        file_id: Google Drive file ID

    Returns:
        Deletion status
    """
    db = get_db()

    # Check if document exists
    state = db.get_document_state(file_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Document {file_id} not found")

    # Delete chunks
    chunks_deleted = db.delete_chunks_by_file(file_id)

    # Delete document state
    db.client.table("rag.document_state").delete().eq(
        "drive_file_id", file_id
    ).execute()

    logger.info(
        "document_deleted",
        file_id=file_id,
        chunks_deleted=chunks_deleted,
    )

    return {
        "status": "deleted",
        "file_id": file_id,
        "chunks_deleted": chunks_deleted,
    }


@app.get("/v1/stats")
async def get_index_stats():
    """Get overall index statistics.

    Returns:
        Statistics about indexed documents and chunks
    """
    db = get_db()

    total_chunks = db.get_chunk_count()
    documents = db.get_indexed_documents(limit=1000)

    return {
        "total_documents": len(documents),
        "total_chunks": total_chunks,
        "avg_chunks_per_document": (
            total_chunks / len(documents) if documents else 0
        ),
    }


# =====================
# Direct Document Retrieval
# =====================


def parse_drive_url(url_or_id: str) -> str:
    """Extract file ID from a Google Drive/Docs URL or return as-is if already an ID.

    Supports formats:
    - https://docs.google.com/document/d/FILE_ID/...
    - https://drive.google.com/file/d/FILE_ID/...
    - https://drive.google.com/open?id=FILE_ID
    - Plain file ID
    """
    import re

    # Already a file ID (no slashes or query strings)
    if "/" not in url_or_id and "?" not in url_or_id:
        return url_or_id

    # Try /d/FILE_ID/ pattern (docs, sheets, slides, drive)
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)

    # Try ?id=FILE_ID pattern
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)

    # Return as-is, might be a valid ID
    return url_or_id


@app.get("/v1/fetch/{file_id_or_url:path}")
async def fetch_document_content(
    file_id_or_url: str,
    format: str = Query("text", description="Output format: text, json, or raw"),
):
    """Fetch live document content directly from Google Drive.

    Unlike get_document_content which returns indexed/chunked content,
    this fetches the current document directly from Google Drive API.

    Args:
        file_id_or_url: Google Drive file ID or full URL to the document
        format: Output format - 'text' for plain text, 'json' for structured,
                'raw' for unprocessed API response

    Returns:
        Document content with metadata
    """
    from drive_rag.auth import get_google_client

    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id_or_url)

    try:
        google = get_google_client()

        # Get file metadata first
        metadata = google.get_file_metadata(file_id)
        title = metadata.get("name", "Untitled")
        mime_type = metadata.get("mimeType", "")

        content = ""

        # Handle different file types
        if mime_type == "application/vnd.google-apps.document":
            # Google Docs
            if format == "json":
                doc = google.get_document(file_id)
                return {
                    "status": "ok",
                    "file_id": file_id,
                    "title": title,
                    "mime_type": mime_type,
                    "content": doc,
                }
            else:
                content = google.export_document_as_text(file_id)

        elif mime_type == "application/vnd.google-apps.spreadsheet":
            # Google Sheets
            content = google.export_spreadsheet_as_csv(file_id)

        elif mime_type == "application/vnd.google-apps.presentation":
            # Google Slides
            content = google.export_presentation_as_text(file_id)

        elif mime_type == "application/pdf":
            # PDF - can't export text easily, return metadata only
            return {
                "status": "ok",
                "file_id": file_id,
                "title": title,
                "mime_type": mime_type,
                "content": None,
                "note": "PDF files cannot be fetched as text. Use ingest_document to index them first.",
            }

        else:
            # Try generic text export for other types
            try:
                content = google.export_document_as_text(file_id)
            except Exception:
                return {
                    "status": "error",
                    "file_id": file_id,
                    "title": title,
                    "mime_type": mime_type,
                    "error": f"Unsupported file type: {mime_type}",
                }

        return {
            "status": "ok",
            "file_id": file_id,
            "title": title,
            "mime_type": mime_type,
            "content": content,
            "content_length": len(content) if content else 0,
        }

    except Exception as e:
        logger.exception("fetch_document_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Edit Tracking Endpoints
# =====================


@app.get("/v1/edits/{file_id}", response_model=DocumentEditsResponse)
async def get_document_edits(
    file_id: str,
    since: Optional[str] = Query(None, description="Filter edits since date (ISO format or relative like 'yesterday')"),
    by_user: Optional[str] = Query(None, description="Filter edits by user email"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
):
    """Get edit history for a document.

    Args:
        file_id: Google Drive file ID
        since: Optional time filter (ISO date or relative like "yesterday", "last-week")
        by_user: Optional filter by user email
        limit: Maximum number of edits to return

    Returns:
        DocumentEditsResponse with edit history
    """
    from datetime import datetime, timedelta

    db = get_db()

    # Get document state for title
    state = db.get_document_state(file_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Document {file_id} not found")

    # Get all revisions
    revisions = db.get_document_revisions(file_id)

    # Parse since filter
    since_dt = None
    if since:
        now = datetime.utcnow()
        since_lower = since.lower()
        if since_lower == "yesterday":
            since_dt = now - timedelta(days=1)
        elif since_lower == "last-week":
            since_dt = now - timedelta(weeks=1)
        elif since_lower == "last-month":
            since_dt = now - timedelta(days=30)
        else:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                pass

    # Filter revisions
    filtered = []
    editors = set()
    for rev in revisions:
        # Time filter
        if since_dt and rev.modified_time:
            if rev.modified_time.replace(tzinfo=None) < since_dt:
                continue

        # User filter
        if by_user and rev.modifier_email:
            if by_user.lower() not in rev.modifier_email.lower():
                continue

        filtered.append(rev)
        if rev.modifier_email:
            editors.add(rev.modifier_email)

    # Apply limit
    filtered = filtered[:limit]

    # Convert to response format
    edits = [
        EditRecord(
            revision_id=rev.revision_id,
            modifier_email=rev.modifier_email,
            modifier_name=rev.modifier_name,
            modified_time=rev.modified_time,
            has_snapshot=rev.has_snapshot,
        )
        for rev in filtered
    ]

    return DocumentEditsResponse(
        drive_file_id=file_id,
        title=state.title,
        edit_count=len(edits),
        editors=sorted(list(editors)),
        edits=edits,
    )


@app.get("/v1/diff/{file_id}", response_model=DocumentDiffResponse)
async def get_document_diff(
    file_id: str,
    from_revision: Optional[str] = Query(None, description="Base revision ID (defaults to oldest snapshot)"),
    to_revision: Optional[str] = Query(None, description="Target revision ID (defaults to latest snapshot)"),
):
    """Get diff between two document versions.

    Args:
        file_id: Google Drive file ID
        from_revision: Base revision ID (optional, defaults to oldest)
        to_revision: Target revision ID (optional, defaults to latest)

    Returns:
        DocumentDiffResponse with block-level changes
    """
    from drive_rag.differ import diff_snapshots, ChangeType
    from drive_rag.snapshots import load_snapshot_from_path

    db = get_db()

    # Get snapshots for this file
    snapshots = db.get_snapshots_for_file(file_id)

    if not snapshots:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshots found for document {file_id}"
        )

    # Sort by modified time (oldest first)
    snapshots.sort(key=lambda s: s.modified_time or datetime.min)

    # Find from/to snapshots
    from_snapshot = None
    to_snapshot = None

    if from_revision:
        for s in snapshots:
            if s.revision_id == from_revision:
                from_snapshot = s
                break
        if not from_snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Snapshot for revision {from_revision} not found"
            )
    else:
        from_snapshot = snapshots[0]  # Oldest

    if to_revision:
        for s in snapshots:
            if s.revision_id == to_revision:
                to_snapshot = s
                break
        if not to_snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Snapshot for revision {to_revision} not found"
            )
    else:
        to_snapshot = snapshots[-1]  # Latest

    # Load snapshot data
    try:
        from_data = load_snapshot_from_path(from_snapshot.snapshot_path)
        to_data = load_snapshot_from_path(to_snapshot.snapshot_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load snapshots: {str(e)}"
        )

    # Compute diff
    diff = diff_snapshots(from_data, to_data)

    # Convert to response format
    changes = []
    for change in diff.changes[:50]:  # Limit changes in response
        text_preview = change.text_preview
        if len(text_preview) > 200:
            text_preview = text_preview[:200] + "..."

        changes.append(
            BlockChangeRecord(
                change_type=change.change_type.value,
                block_type=change.block_type,
                text_preview=text_preview,
                section=change.section,
            )
        )

    return DocumentDiffResponse(
        drive_file_id=file_id,
        from_revision=from_snapshot.revision_id,
        to_revision=to_snapshot.revision_id,
        blocks_added=diff.blocks_added,
        blocks_deleted=diff.blocks_deleted,
        blocks_modified=diff.blocks_modified,
        blocks_moved=diff.blocks_moved,
        changes=changes,
        summary=diff.summary,
    )


# =====================
# Entity Extraction Endpoints (Knowledge Graph)
# =====================


@app.post("/v1/entities/extract/{file_id}")
async def extract_document_entities(
    file_id: str,
):
    """Extract entities from a document and add to knowledge graph.

    This triggers entity extraction using Graphiti, which identifies
    people, organizations, projects, and relationships mentioned
    in the document.

    Args:
        file_id: Google Drive file ID

    Returns:
        Extraction result with episode UUID
    """
    from drive_rag.auth import get_google_client
    from drive_rag.entities import extract_entities_from_document

    try:
        google = get_google_client()

        # Get file metadata
        metadata = google.get_file_metadata(file_id)
        title = metadata.get("name", "Untitled")
        mime_type = metadata.get("mimeType", "")
        owner = metadata.get("owners", [{}])[0]
        owner_email = owner.get("emailAddress")
        modified_time = metadata.get("modifiedTime")

        # Get document content
        if mime_type == "application/vnd.google-apps.document":
            content = google.export_document_as_text(file_id)
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            content = google.export_spreadsheet_as_csv(file_id)
        elif mime_type == "application/vnd.google-apps.presentation":
            content = google.export_presentation_as_text(file_id)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type for entity extraction: {mime_type}"
            )

        # Extract entities
        result = await extract_entities_from_document(
            file_id=file_id,
            title=title,
            content=content,
            mime_type=mime_type,
            owner_email=owner_email,
            modified_time=datetime.fromisoformat(modified_time.replace("Z", "+00:00")) if modified_time else None,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("entity_extraction_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/entities/search")
async def search_entities(
    query: str = Query(..., description="Entity or topic to search for"),
    max_results: int = Query(20, ge=1, le=100, description="Maximum results"),
):
    """Search for entities across all indexed documents.

    This searches the knowledge graph for entities (people, organizations,
    projects, etc.) and their relationships.

    Args:
        query: Natural language query for entities
        max_results: Maximum number of results

    Returns:
        Entities and relationships matching the query
    """
    from drive_rag.entities import find_documents_by_entity

    try:
        result = await find_documents_by_entity(
            entity_query=query,
            max_results=max_results,
        )
        return result

    except Exception as e:
        logger.exception("entity_search_failed", query=query, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/entities/document/{file_id}")
async def get_entities_for_document(file_id: str):
    """Get all entities extracted from a specific document.

    Args:
        file_id: Google Drive file ID

    Returns:
        Entities and relationships from the document
    """
    from drive_rag.entities import get_document_entities

    try:
        result = await get_document_entities(file_id)
        return result

    except Exception as e:
        logger.exception("get_document_entities_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/entities/consolidation")
async def analyze_entity_consolidation(
    similarity_threshold: float = Query(0.6, ge=0.0, le=1.0, description="Minimum similarity to flag as duplicate"),
    max_entities: int = Query(500, ge=10, le=2000, description="Maximum entities to analyze"),
):
    """Analyze entities for potential duplicates and consolidation opportunities.

    This scans the knowledge graph for similar entities that may need to be
    merged, such as:
    - "NSF" and "National Science Foundation"
    - "Nathan Kimball" and "N. Kimball"
    - "UIUC" and "University of Illinois"

    Args:
        similarity_threshold: Minimum similarity score (0-1) to flag as potential duplicate
        max_entities: Maximum number of entities to analyze

    Returns:
        Consolidation report with clusters, recommendations, and statistics
    """
    from drive_rag.consolidation import analyze_entity_clusters, format_consolidation_report

    try:
        report = await analyze_entity_clusters(
            similarity_threshold=similarity_threshold,
            max_entities=max_entities,
        )
        return format_consolidation_report(report)

    except Exception as e:
        logger.exception("entity_consolidation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
