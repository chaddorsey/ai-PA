"""FastAPI application for Drive RAG service.

Provides HTTP endpoints for:
- Document ingestion (single file or folder)
- Semantic search across indexed documents
- Status queries for indexed documents
"""

from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from drive_rag.db import get_db
from drive_rag.embedder import get_embedder
from drive_rag.ingestion import ingest_document, ingest_folder
from drive_rag.models import (
    DocumentStatusResponse,
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
):
    """Ingest a single Google Doc into the RAG system.

    Args:
        file_id: Google Drive file ID
        force: Force re-indexing even if document hasn't changed

    Returns:
        IngestionResult with status and statistics
    """
    logger.info("ingest_request", file_id=file_id, force=force)

    try:
        result = await ingest_document(file_id=file_id, force=force)
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
