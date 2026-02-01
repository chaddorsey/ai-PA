"""Document ingestion worker.

This module orchestrates the document ingestion pipeline:
1. Fetch document metadata from Drive
2. Check if document has changed (revision/hash comparison)
3. Fetch document content from Docs API
4. Normalize to stable text with structure blocks
5. Chunk the normalized text
6. Embed new/changed chunks
7. Store in Supabase with pgvector
"""

from datetime import datetime
from typing import Optional

import structlog

from drive_rag.auth import get_google_client, GoogleClient
from drive_rag.chunker import chunk_from_normalized, diff_chunks
from drive_rag.db import get_db, Database
from drive_rag.embedder import get_embedder, Embedder
from drive_rag.models import (
    ChunkRecord,
    DocumentState,
    IngestionResult,
    IngestFolderResponse,
)
from drive_rag.normalizer import normalize_docs_document

logger = structlog.get_logger()

# MIME type for Google Docs
GOOGLE_DOCS_MIME_TYPE = "application/vnd.google-apps.document"


async def ingest_document(
    file_id: str,
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
    embedder: Optional[Embedder] = None,
    force: bool = False,
) -> IngestionResult:
    """Ingest a single Google Doc into the RAG system.

    Args:
        file_id: Google Drive file ID
        google_client: Google API client (defaults to global)
        db: Database client (defaults to global)
        embedder: Embedding client (defaults to global)
        force: Force re-indexing even if unchanged

    Returns:
        IngestionResult with status and statistics
    """
    google = google_client or get_google_client()
    database = db or get_db()
    embed = embedder or get_embedder()

    try:
        # 1. Fetch file metadata from Drive
        logger.info("fetching_metadata", file_id=file_id)
        file_meta = google.get_file_metadata(file_id)

        title = file_meta.get("name", "Untitled")
        mime_type = file_meta.get("mimeType", "")
        head_revision_id = file_meta.get("headRevisionId", "")
        owner_email = None
        if file_meta.get("owners"):
            owner_email = file_meta["owners"][0].get("emailAddress")

        # Verify it's a Google Doc
        if mime_type != GOOGLE_DOCS_MIME_TYPE:
            return IngestionResult(
                status="skipped",
                drive_file_id=file_id,
                reason=f"Not a Google Doc (mime: {mime_type})",
            )

        # 2. Check if changed
        existing_state = database.get_document_state(file_id)

        if not force and existing_state:
            if existing_state.last_seen_revision_id == head_revision_id:
                logger.info(
                    "document_unchanged",
                    file_id=file_id,
                    revision_id=head_revision_id,
                )
                return IngestionResult(
                    status="skipped",
                    drive_file_id=file_id,
                    revision_id=head_revision_id,
                    reason="Revision unchanged",
                )

        # 3. Fetch document content from Docs API
        logger.info("fetching_content", file_id=file_id, title=title)
        doc = google.get_document(file_id)

        # 4. Normalize to stable text with structure
        snapshot = normalize_docs_document(file_id, head_revision_id, doc)

        # Check content hash for deeper comparison
        if not force and existing_state:
            if existing_state.content_hash == snapshot.normalized_hash:
                # Update revision tracking but skip re-indexing
                database.upsert_document_state(
                    DocumentState(
                        drive_file_id=file_id,
                        title=title,
                        mime_type=mime_type,
                        last_seen_revision_id=head_revision_id,
                        last_indexed_revision_id=existing_state.last_indexed_revision_id,
                        last_indexed_at=existing_state.last_indexed_at,
                        content_hash=snapshot.normalized_hash,
                        owner_email=owner_email,
                    )
                )

                return IngestionResult(
                    status="skipped",
                    drive_file_id=file_id,
                    revision_id=head_revision_id,
                    reason="Content hash unchanged",
                )

        # 5. Chunk the normalized text
        new_chunks = chunk_from_normalized(
            file_id=file_id,
            revision_id=head_revision_id,
            title=title,
            normalized_text=snapshot.normalized_text,
            blocks=snapshot.blocks,
        )

        # 6. Diff against existing chunks for incremental update
        existing_chunk_data = database.get_chunks_by_file(file_id)
        existing_chunks = [
            ChunkRecord(
                drive_file_id=row["drive_file_id"],
                revision_id=row["revision_id"],
                title=row["title"],
                chunk_id=row["chunk_id"],
                outline_path=row.get("outline_path", []),
                block_start_id=row.get("block_start_id", ""),
                block_end_id=row.get("block_end_id", ""),
                char_start=row.get("char_start", 0),
                char_end=row.get("char_end", 0),
                chunk_text="",  # Not fetched to save bandwidth
                chunk_hash=row["chunk_hash"],
            )
            for row in existing_chunk_data
        ]

        to_add, to_update, to_delete = diff_chunks(existing_chunks, new_chunks)

        # Combine chunks that need embedding
        chunks_to_embed = to_add + to_update

        # 7. Embed new/changed chunks
        if chunks_to_embed:
            logger.info("embedding_chunks", count=len(chunks_to_embed))
            texts = [c.chunk_text for c in chunks_to_embed]
            embeddings = await embed.embed(texts)

            # 8. Store in database
            database.upsert_chunks(chunks_to_embed, embeddings)

        # Delete removed chunks
        if to_delete:
            database.delete_chunks([c.chunk_id for c in to_delete])

        # Update document state
        database.upsert_document_state(
            DocumentState(
                drive_file_id=file_id,
                title=title,
                mime_type=mime_type,
                last_seen_revision_id=head_revision_id,
                last_indexed_revision_id=head_revision_id,
                last_indexed_at=datetime.utcnow(),
                content_hash=snapshot.normalized_hash,
                owner_email=owner_email,
            )
        )

        logger.info(
            "ingestion_complete",
            file_id=file_id,
            title=title,
            chunks_added=len(to_add),
            chunks_updated=len(to_update),
            chunks_deleted=len(to_delete),
        )

        return IngestionResult(
            status="indexed",
            drive_file_id=file_id,
            revision_id=head_revision_id,
            chunks_added=len(to_add),
            chunks_updated=len(to_update),
            chunks_deleted=len(to_delete),
        )

    except Exception as e:
        logger.exception("ingestion_failed", file_id=file_id, error=str(e))
        return IngestionResult(
            status="error",
            drive_file_id=file_id,
            reason=str(e),
        )


async def ingest_folder(
    folder_id: str,
    recursive: bool = False,
    google_client: Optional[GoogleClient] = None,
    db: Optional[Database] = None,
    embedder: Optional[Embedder] = None,
) -> IngestFolderResponse:
    """Ingest all Google Docs in a folder.

    Args:
        folder_id: Google Drive folder ID
        recursive: Whether to include subfolders (not yet implemented)
        google_client: Google API client
        db: Database client
        embedder: Embedding client

    Returns:
        IngestFolderResponse with results for each document
    """
    google = google_client or get_google_client()

    logger.info("listing_folder", folder_id=folder_id)

    # List Google Docs in folder
    files = google.list_files_in_folder(folder_id, mime_type=GOOGLE_DOCS_MIME_TYPE)

    logger.info("found_documents", folder_id=folder_id, count=len(files))

    results: list[IngestionResult] = []
    processed = 0
    skipped = 0
    failed = 0

    for file in files:
        file_id = file["id"]
        result = await ingest_document(
            file_id=file_id,
            google_client=google_client,
            db=db,
            embedder=embedder,
        )

        results.append(result)

        if result.status == "indexed":
            processed += 1
        elif result.status == "skipped":
            skipped += 1
        else:
            failed += 1

    return IngestFolderResponse(
        folder_id=folder_id,
        documents_processed=processed,
        documents_skipped=skipped,
        documents_failed=failed,
        results=results,
    )
