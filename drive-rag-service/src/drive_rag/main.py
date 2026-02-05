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
    ChangedDocumentRecord,
    ChangedDocumentsResponse,
    ChangesSyncResponse,
    DocumentDiffResponse,
    DocumentEditsResponse,
    DocumentStatusResponse,
    EditRecord,
    IngestFolderRequest,
    IngestFolderResponse,
    IngestionResult,
    RetentionResponse,
    ScanChangesResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SyncStatusResponse,
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


@app.post("/v1/ingest/{file_id:path}", response_model=IngestionResult)
async def ingest_single_document(
    file_id: str,
    force: bool = Query(False, description="Force re-indexing even if unchanged"),
    extract_entities: Optional[bool] = Query(None, description="Extract entities to knowledge graph"),
):
    """Ingest a single Google Doc into the RAG system.

    Args:
        file_id: Google Drive file ID or URL (e.g., https://docs.google.com/document/d/FILE_ID/edit)
        force: Force re-indexing even if document hasn't changed
        extract_entities: Extract entities to knowledge graph (defaults to ENABLE_ENTITY_EXTRACTION env var)

    Returns:
        IngestionResult with status and statistics
    """
    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)
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


@app.get("/v1/status/{file_id:path}", response_model=DocumentStatusResponse)
async def get_document_status(file_id: str):
    """Get indexing status for a document.

    Args:
        file_id: Google Drive file ID or URL

    Returns:
        DocumentStatusResponse with indexing status and metadata
    """
    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)
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


@app.delete("/v1/documents/{file_id:path}")
async def delete_document(file_id: str):
    """Delete a document and all its chunks from the index.

    Args:
        file_id: Google Drive file ID or URL

    Returns:
        Deletion status
    """
    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)
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


@app.get("/v1/edits/{file_id:path}", response_model=DocumentEditsResponse)
async def get_document_edits(
    file_id: str,
    since: Optional[str] = Query(None, description="Filter edits since date (ISO format or relative like 'yesterday')"),
    by_user: Optional[str] = Query(None, description="Filter edits by user email"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
):
    """Get edit history for a document.

    Args:
        file_id: Google Drive file ID or URL
        since: Optional time filter (ISO date or relative like "yesterday", "last-week")
        by_user: Optional filter by user email
        limit: Maximum number of edits to return

    Returns:
        DocumentEditsResponse with edit history
    """
    from datetime import datetime, timedelta

    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)
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


@app.get("/v1/diff/{file_id:path}", response_model=DocumentDiffResponse)
async def get_document_diff(
    file_id: str,
    from_revision: Optional[str] = Query(None, description="Base revision ID (defaults to oldest snapshot)"),
    to_revision: Optional[str] = Query(None, description="Target revision ID (defaults to latest snapshot)"),
):
    """Get diff between two document versions.

    Args:
        file_id: Google Drive file ID or URL
        from_revision: Base revision ID (optional, defaults to oldest)
        to_revision: Target revision ID (optional, defaults to latest)

    Returns:
        DocumentDiffResponse with block-level changes
    """
    from drive_rag.differ import diff_snapshots, ChangeType
    from drive_rag.snapshots import load_snapshot_from_path

    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)
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


@app.post("/v1/entities/extract/{file_id:path}")
async def extract_document_entities(
    file_id: str,
):
    """Extract entities from a document and add to knowledge graph.

    This triggers entity extraction using Graphiti, which identifies
    people, organizations, projects, and relationships mentioned
    in the document.

    Args:
        file_id: Google Drive file ID or URL

    Returns:
        Extraction result with episode UUID
    """
    from drive_rag.auth import get_google_client
    from drive_rag.entities import extract_entities_from_document

    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)

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


@app.get("/v1/entities/document/{file_id:path}")
async def get_entities_for_document(file_id: str):
    """Get all entities extracted from a specific document.

    Args:
        file_id: Google Drive file ID or URL

    Returns:
        Entities and relationships from the document
    """
    from drive_rag.entities import get_document_entities

    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)

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


# =====================
# Change Monitoring Endpoints
# =====================


@app.post("/v1/scan/changes", response_model=ScanChangesResponse)
async def scan_for_document_changes(
    priority: str = Query("high", description="Priority tier: high, medium, low, all"),
    batch_size: int = Query(100, ge=10, le=500, description="Maximum documents to scan"),
    dry_run: bool = Query(False, description="Preview what would change without re-indexing"),
):
    """Scan for documents that have changed in Google Drive.

    This endpoint checks indexed documents against Google Drive to detect
    changes, and triggers re-ingestion for documents that have been modified.

    Priority tiers:
    - high: Documents modified in last 24 hours (check frequently)
    - medium: Documents modified 1-7 days ago
    - low: Older documents (daily rotating sample)
    - all: All documents (for full daily scan)

    Args:
        priority: Priority tier to scan
        batch_size: Maximum documents to check in this scan
        dry_run: If True, report changes but don't re-index

    Returns:
        ScanChangesResponse with scan statistics
    """
    from drive_rag.change_monitor import scan_for_changes, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_ALL

    valid_priorities = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_ALL]
    if priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority '{priority}'. Must be one of: {valid_priorities}",
        )

    logger.info(
        "scan_changes_request",
        priority=priority,
        batch_size=batch_size,
        dry_run=dry_run,
    )

    try:
        result = await scan_for_changes(
            priority=priority,
            batch_size=batch_size,
            dry_run=dry_run,
        )
        return ScanChangesResponse(**result.to_dict())

    except Exception as e:
        logger.exception("scan_changes_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/documents/changed", response_model=ChangedDocumentsResponse)
async def get_changed_documents(
    since: Optional[str] = Query(None, description="ISO date or relative: yesterday, last-week, last-month"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    owner_email: Optional[str] = Query(None, description="Filter by document owner email"),
):
    """Get documents that have changed since a given time.

    This endpoint queries the database for documents that were modified
    after the specified time. Useful for agents to ask "what documents
    changed in the last 24 hours?"

    Args:
        since: Time filter - ISO date (2026-01-15) or relative (yesterday, last-week, last-month)
        limit: Maximum documents to return
        owner_email: Optional filter by owner

    Returns:
        ChangedDocumentsResponse with list of changed documents
    """
    from datetime import timedelta

    db = get_db()

    # Parse the 'since' parameter
    since_datetime = None
    now = datetime.utcnow()

    if since:
        since_lower = since.lower()
        if since_lower == "yesterday":
            since_datetime = now - timedelta(days=1)
        elif since_lower == "last-week":
            since_datetime = now - timedelta(weeks=1)
        elif since_lower == "last-month":
            since_datetime = now - timedelta(days=30)
        else:
            # Try to parse as ISO date
            try:
                since_datetime = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid 'since' value: {since}. Use ISO date or: yesterday, last-week, last-month",
                )
    else:
        # Default to last 24 hours
        since_datetime = now - timedelta(days=1)

    logger.info(
        "get_changed_documents_request",
        since=since_datetime.isoformat() if since_datetime else None,
        limit=limit,
        owner_email=owner_email,
    )

    try:
        # Query documents modified after since_datetime
        params = {
            "select": "drive_file_id,title,modified_time,last_modifier_email,last_modifier_name",
            "order": "modified_time.desc",
            "limit": str(limit),
            "modified_time": f"gte.{since_datetime.isoformat()}",
        }

        if owner_email:
            params["owner_email"] = f"eq.{owner_email}"

        response = db.client.get(db._url("document_state"), params=params)
        db._check_response(response, "get_changed_documents")

        data = response.json() or []

        # Check which documents have snapshots
        documents = []
        for row in data:
            file_id = row["drive_file_id"]
            # Check for snapshot (simplified - just check if any snapshot exists)
            has_snapshot = bool(db.get_snapshots_for_file(file_id))

            documents.append(
                ChangedDocumentRecord(
                    drive_file_id=file_id,
                    title=row.get("title", ""),
                    modified_time=datetime.fromisoformat(row["modified_time"].replace("Z", "+00:00"))
                    if row.get("modified_time")
                    else None,
                    modifier_email=row.get("last_modifier_email"),
                    modifier_name=row.get("last_modifier_name"),
                    has_snapshot=has_snapshot,
                )
            )

        return ChangedDocumentsResponse(
            total_changed=len(documents),
            since=since_datetime,
            documents=documents,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_changed_documents_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Admin Endpoints
# =====================


@app.post("/v1/admin/cleanup/snapshots", response_model=RetentionResponse)
async def cleanup_old_snapshots(
    dry_run: bool = Query(True, description="Preview what would be deleted without actually deleting"),
    tier1_days: int = Query(7, ge=1, le=30, description="Days to keep ALL snapshots (full retention)"),
    tier2_days: int = Query(90, ge=7, le=365, description="Days to keep DAILY snapshots"),
):
    """Apply retention policy to snapshot storage.

    This endpoint cleans up old snapshots based on tiered retention:
    - Tier 1 (0 to tier1_days): Keep ALL snapshots
    - Tier 2 (tier1_days to tier2_days): Keep ONE snapshot per day per document
    - Tier 3 (older than tier2_days): Keep ONE snapshot per document total

    IMPORTANT: No snapshots are deleted entirely - we always keep at least
    one persistent copy per document.

    Args:
        dry_run: If True (default), preview what would be deleted without deleting
        tier1_days: Days for full retention (default 7)
        tier2_days: Days for daily retention (default 90)

    Returns:
        RetentionResponse with cleanup statistics
    """
    from drive_rag.retention import apply_retention_policy

    logger.info(
        "cleanup_snapshots_request",
        dry_run=dry_run,
        tier1_days=tier1_days,
        tier2_days=tier2_days,
    )

    try:
        result = apply_retention_policy(
            dry_run=dry_run,
            tier1_days=tier1_days,
            tier2_days=tier2_days,
        )

        result_dict = result.to_dict()

        return RetentionResponse(
            snapshots_analyzed=result_dict["snapshots_analyzed"],
            snapshots_kept=result_dict["snapshots_kept"],
            snapshots_deleted=result_dict["snapshots_deleted"],
            space_freed_bytes=result_dict["space_freed_bytes"],
            space_freed_mb=result_dict["space_freed_mb"],
            dry_run=result_dict["dry_run"],
            error_count=result_dict["error_count"],
            errors=result_dict["errors"],
            breakdown=result_dict.get("breakdown"),
        )

    except Exception as e:
        logger.exception("cleanup_snapshots_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Drive Changes API Sync
# =====================


@app.post("/v1/sync/changes", response_model=ChangesSyncResponse)
async def sync_changes(
    dry_run: bool = Query(False, description="Preview what would be processed without actually ingesting"),
    reset_token: bool = Query(False, description="Reset the sync token and start fresh"),
    max_changes: int = Query(10000, ge=100, le=100000, description="Maximum changes to process"),
):
    """Sync changes using the Drive Changes API.

    This is the preferred method for detecting document changes. Instead of
    polling each document individually, it uses Google Drive's Changes API
    to efficiently get all changes since the last sync.

    Benefits:
    - Detects NEW files automatically (not just modifications)
    - Detects deleted/trashed files
    - Much more efficient than per-document polling
    - Single API call returns all changes

    On first call (or after reset_token=True), initializes the sync token
    and returns immediately. Subsequent calls will process actual changes.

    Args:
        dry_run: If True, report what would happen without actually ingesting
        reset_token: If True, reset the sync token (useful if token becomes invalid)
        max_changes: Maximum changes to process in one sync (default 10000)

    Returns:
        ChangesSyncResponse with sync statistics
    """
    from drive_rag.change_monitor import sync_changes_api

    logger.info(
        "sync_changes_request",
        dry_run=dry_run,
        reset_token=reset_token,
        max_changes=max_changes,
    )

    try:
        result = await sync_changes_api(
            dry_run=dry_run,
            reset_token=reset_token,
            max_changes=max_changes,
        )

        result_dict = result.to_dict()

        return ChangesSyncResponse(
            changes_processed=result_dict["changes_processed"],
            new_files=result_dict["new_files"],
            modified_files=result_dict["modified_files"],
            deleted_files=result_dict["deleted_files"],
            skipped_unsupported=result_dict["skipped_unsupported"],
            skipped_folders=result_dict["skipped_folders"],
            ingested=result_dict["ingested"],
            error_count=result_dict["error_count"],
            errors=result_dict["errors"],
            sync_duration_seconds=result_dict["sync_duration_seconds"],
            dry_run=result_dict["dry_run"],
            token_initialized=result_dict["token_initialized"],
        )

    except Exception as e:
        logger.exception("sync_changes_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/sync/status", response_model=SyncStatusResponse)
async def get_sync_status():
    """Get the current status of change sync.

    Returns information about the sync state including:
    - Whether sync is initialized
    - When the last sync occurred
    - Cumulative counts of changes processed

    Use this to monitor sync health and verify it's running.
    """
    from drive_rag.change_monitor import get_sync_status as get_status

    try:
        status = await get_status()
        return SyncStatusResponse(**status)
    except Exception as e:
        logger.exception("get_sync_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
