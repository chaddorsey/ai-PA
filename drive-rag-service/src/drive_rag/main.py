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
    total_documents = db.get_document_count()

    return {
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "avg_chunks_per_document": (
            total_chunks / total_documents if total_documents else 0
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
            # Google Sheets — fetch all sheets via Sheets API
            try:
                all_sheets = google.get_all_sheets_as_csv(file_id)
                if len(all_sheets) == 1:
                    content = all_sheets[0]["csv"]
                else:
                    parts = []
                    for sheet in all_sheets:
                        parts.append(f"=== Sheet: {sheet['sheet_name']} ===")
                        parts.append(sheet["csv"])
                    content = "\n\n".join(parts)
            except Exception:
                # Fallback to single-sheet CSV export
                content = google.export_spreadsheet_as_csv(file_id)

        elif mime_type == "application/vnd.google-apps.presentation":
            # Google Slides
            content = google.export_presentation_as_text(file_id)

        elif mime_type == "application/pdf":
            # PDF - download bytes and extract text via pypdf
            from drive_rag.normalizer import normalize_pdf_document

            pdf_bytes = google.download_file_content(file_id)
            snapshot = normalize_pdf_document(file_id, "live", pdf_bytes)
            content = snapshot.normalized_text

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

        # Check if document is indexed for semantic search
        db = get_db()
        doc_state = db.get_document_state(file_id)
        indexed = doc_state is not None and doc_state.last_indexed_at is not None

        response = {
            "status": "ok",
            "file_id": file_id,
            "title": title,
            "mime_type": mime_type,
            "content": content,
            "content_length": len(content) if content else 0,
        }
        if not indexed:
            response["not_indexed"] = True
            response["index_note"] = (
                "This document is not indexed for semantic search. "
                "Use ingest_document to enable search."
            )
        return response

    except Exception as e:
        logger.exception("fetch_document_failed", file_id=file_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# Edit Tracking Endpoints
# =====================


@app.get("/v1/edits/{file_id:path}", response_model=DocumentEditsResponse)
async def get_document_edits(
    file_id: str,
    source: str = Query("live", description="Data source: 'live' (Drive API) or 'stored' (database)"),
    since: Optional[str] = Query(None, description="Filter edits since date (ISO format or relative like 'yesterday')"),
    by_user: Optional[str] = Query(None, description="Filter edits by user email"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
):
    """Get edit history for a document.

    Use source=live (default) to fetch revision history directly from the
    Google Drive API for up-to-date results. Use source=stored to query
    cached revisions from the database (faster but may miss recent edits).

    Args:
        file_id: Google Drive file ID or URL
        source: Data source - 'live' (Drive API, default) or 'stored' (database)
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

    if source == "live":
        # Fetch revisions directly from Google Drive API
        from drive_rag.auth import get_google_client

        try:
            google = get_google_client()
            metadata = google.get_file_metadata(file_id)
            title = metadata.get("name", "Untitled")

            revisions_data = google.list_revisions(file_id)

            edits = []
            editors = set()
            for rev in revisions_data:
                modifier = rev.get("lastModifyingUser", {})
                email = modifier.get("emailAddress")
                name = modifier.get("displayName")
                modified_time_str = rev.get("modifiedTime")

                modified_time = None
                if modified_time_str:
                    modified_time = datetime.fromisoformat(
                        modified_time_str.replace("Z", "+00:00")
                    )

                # Apply time filter
                if since_dt and modified_time:
                    if modified_time.replace(tzinfo=None) < since_dt:
                        continue

                # Apply user filter
                if by_user and email:
                    if by_user.lower() not in email.lower():
                        continue

                # Check if we have a stored snapshot for this revision
                has_snap = db.get_snapshot_metadata(file_id, rev.get("id", "")) is not None

                edits.append(
                    EditRecord(
                        revision_id=rev.get("id", ""),
                        modifier_email=email,
                        modifier_name=name,
                        modified_time=modified_time,
                        has_snapshot=has_snap,
                    )
                )
                if email:
                    editors.add(email)

            # Sort by time descending, apply limit
            edits.sort(
                key=lambda e: e.modified_time or datetime.min, reverse=True
            )
            edits = edits[:limit]

            return DocumentEditsResponse(
                drive_file_id=file_id,
                title=title,
                edit_count=len(edits),
                editors=sorted(list(editors)),
                edits=edits,
            )

        except Exception as e:
            # Fall back to stored data on failure
            logger.warning(
                "live_edits_fallback",
                file_id=file_id,
                error=str(e),
            )
            # Fall through to stored logic below

    # Stored source (database) — also used as fallback when live fails
    state = db.get_document_state(file_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Document {file_id} not found")

    revisions = db.get_document_revisions(file_id)

    filtered = []
    editors = set()
    for rev in revisions:
        if since_dt and rev.modified_time:
            if rev.modified_time.replace(tzinfo=None) < since_dt:
                continue
        if by_user and rev.modifier_email:
            if by_user.lower() not in rev.modifier_email.lower():
                continue
        filtered.append(rev)
        if rev.modifier_email:
            editors.add(rev.modifier_email)

    filtered = filtered[:limit]

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
    from_revision: Optional[str] = Query(
        None,
        description="Base revision ID, or 'latest' for most recent snapshot (defaults to oldest)",
    ),
    to_revision: Optional[str] = Query(
        None,
        description="Target revision ID, or 'live' for current document content (defaults to latest snapshot)",
    ),
):
    """Get diff between two document versions.

    Supports live comparison: use to_revision=live to compare against the
    current document content fetched directly from Google Drive.
    Use from_revision=latest to always use the most recent stored snapshot.

    Args:
        file_id: Google Drive file ID or URL
        from_revision: Base revision ID, 'latest', or None (defaults to oldest)
        to_revision: Target revision ID, 'live', or None (defaults to latest snapshot)

    Returns:
        DocumentDiffResponse with block-level changes
    """
    from drive_rag.differ import diff_snapshots
    from drive_rag.snapshots import load_snapshot_from_path

    # Parse URL to file ID if needed
    file_id = parse_drive_url(file_id)
    db = get_db()

    is_live = to_revision and to_revision.lower() == "live"
    is_from_latest = from_revision and from_revision.lower() == "latest"

    # Get snapshots for this file (needed for baseline)
    snapshots = db.get_snapshots_for_file(file_id)

    if not snapshots:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshots found for document {file_id}. Ingest the document first.",
        )

    # Sort by modified time (oldest first)
    snapshots.sort(key=lambda s: s.modified_time or datetime.min)

    # Resolve baseline (from) snapshot
    from_snapshot = None
    if is_from_latest:
        from_snapshot = snapshots[-1]  # Most recent
    elif from_revision:
        for s in snapshots:
            if s.revision_id == from_revision:
                from_snapshot = s
                break
        if not from_snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"Snapshot for revision {from_revision} not found",
            )
    else:
        from_snapshot = snapshots[0]  # Oldest

    # Load baseline snapshot
    try:
        from_data = load_snapshot_from_path(from_snapshot.snapshot_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load baseline snapshot: {str(e)}",
        )

    if from_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline snapshot file missing for revision {from_snapshot.revision_id}. The document needs to be re-ingested to regenerate snapshots.",
        )

    # Resolve target (to) data
    to_revision_id = None
    if is_live:
        # Fetch live content from Google Drive and normalize
        from drive_rag.auth import get_google_client
        from drive_rag.normalizer import (
            normalize_docs_document,
            normalize_plain_text_document,
            normalize_spreadsheet_csv,
            normalize_presentation_text,
        )

        try:
            google = get_google_client()
            metadata = google.get_file_metadata(file_id)
            mime_type = metadata.get("mimeType", "")

            if mime_type == "application/vnd.google-apps.document":
                try:
                    doc = google.get_document(file_id)
                    to_data = normalize_docs_document(file_id, "live", doc)
                except Exception:
                    text = google.export_document_as_text(file_id)
                    to_data = normalize_plain_text_document(file_id, "live", text)
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                csv_content = google.export_spreadsheet_as_csv(file_id)
                to_data = normalize_spreadsheet_csv(file_id, "live", csv_content)
            elif mime_type == "application/vnd.google-apps.presentation":
                text = google.export_presentation_as_text(file_id)
                to_data = normalize_presentation_text(file_id, "live", text)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Live diff not supported for MIME type: {mime_type}",
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch live content: {str(e)}",
            )

        to_revision_id = "live"
    else:
        # Load target from stored snapshot
        to_snapshot = None
        if to_revision:
            for s in snapshots:
                if s.revision_id == to_revision:
                    to_snapshot = s
                    break
            if not to_snapshot:
                raise HTTPException(
                    status_code=404,
                    detail=f"Snapshot for revision {to_revision} not found",
                )
        else:
            to_snapshot = snapshots[-1]  # Latest

        try:
            to_data = load_snapshot_from_path(to_snapshot.snapshot_path)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load target snapshot: {str(e)}",
            )

        if to_data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Target snapshot file missing for revision {to_snapshot.revision_id}. The document needs to be re-ingested to regenerate snapshots.",
            )

        to_revision_id = to_snapshot.revision_id

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
        to_revision=to_revision_id,
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
        elif mime_type == "application/pdf":
            from drive_rag.normalizer import normalize_pdf_document
            pdf_bytes = google.download_file_content(file_id)
            snapshot = normalize_pdf_document(file_id, "extract", pdf_bytes)
            content = snapshot.normalized_text
        elif mime_type in ("text/plain", "text/markdown"):
            content = google.download_file_content(file_id).decode("utf-8", errors="replace")
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


# =====================
# Change Monitoring Endpoints
# =====================


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


# =====================
# Staleness Sweep Endpoints
# =====================


@app.get("/v1/staleness/status")
async def get_staleness_status():
    """Get staleness sweep status and tier distribution.

    Returns tier counts, last check times, and sweep health metrics.
    """
    db = get_db()

    try:
        stats = db.get_staleness_stats()
        return {
            "status": "ok",
            **stats,
        }
    except Exception as e:
        logger.exception("staleness_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/staleness/poll")
async def trigger_activity_poll(
    since_minutes: int = Query(10, ge=1, le=60, description="Look-back window in minutes"),
):
    """Trigger an Activity API poll to detect recent changes.

    This is the fast path — polls Drive Activity API v2 for edits/creates
    across ALL files including shared-from-others.
    """
    from drive_rag.activity_client import poll_activity

    try:
        result = await poll_activity(since_minutes=since_minutes)
        return {
            "status": "ok",
            "activities_fetched": result.activities_fetched,
            "indexed_files_affected": result.indexed_files_affected,
            "files_promoted": result.files_promoted,
            "ingestion_triggered": result.ingestion_triggered,
            "new_files_discovered": result.new_files_discovered,
            "errors": result.errors,
            "poll_duration_seconds": round(result.poll_duration_seconds, 2),
        }
    except Exception as e:
        logger.exception("activity_poll_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/staleness/sweep/{tier}")
async def trigger_metadata_sweep(
    tier: str,
    limit: int = Query(500, ge=1, le=5000, description="Max documents to check"),
):
    """Trigger a metadata sweep for a specific tier.

    Batch-checks modifiedTime from Drive API against stored values.
    Re-ingests stale documents and manages tier transitions.
    """
    from drive_rag.staleness import run_sweep

    valid_tiers = ("hot", "warm", "cool", "cold")
    if tier not in valid_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier}'. Must be one of: {', '.join(valid_tiers)}",
        )

    try:
        result = await run_sweep(tier=tier, limit=limit)
        return {
            "status": "ok",
            "tier": result.tier,
            "candidates_checked": result.candidates_checked,
            "stale_found": result.stale_found,
            "ingestion_triggered": result.ingestion_triggered,
            "promotions": result.promotions,
            "demotions": result.demotions,
            "errors": result.errors,
            "sweep_duration_seconds": round(result.sweep_duration_seconds, 2),
        }
    except Exception as e:
        logger.exception("metadata_sweep_failed", tier=tier, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =====================
# File Discovery Endpoints
# =====================


@app.post("/v1/discovery/scan")
async def trigger_discovery_scan(
    since_hours: int = Query(24, ge=1, le=168, description="Look-back window in hours"),
):
    """Scan for newly-shared files not yet in the index.

    Queries Drive API for files recently shared with the authenticated user
    and ingests any supported file types not already indexed.
    """
    from drive_rag.discovery import discover_shared_files

    try:
        result = await discover_shared_files(since_hours=since_hours)
        return {
            "status": "ok",
            "files_found": result.files_found,
            "already_indexed": result.already_indexed,
            "new_files": result.new_files,
            "ingested": result.ingested,
            "errors": result.errors,
            "scan_duration_seconds": round(result.scan_duration_seconds, 2),
        }
    except Exception as e:
        logger.exception("discovery_scan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
