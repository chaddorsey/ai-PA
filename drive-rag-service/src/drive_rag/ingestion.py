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
    DocumentRevision,
    DocumentSnapshot,
    DocumentState,
    IngestionResult,
    IngestFolderResponse,
)
from drive_rag.snapshots import save_snapshot
from drive_rag.normalizer import (
    normalize_docs_document,
    normalize_plain_text_document,
    normalize_spreadsheet_csv,
    normalize_presentation_text,
    normalize_pdf_document,
)

logger = structlog.get_logger()

# MIME types for Google Workspace files
GOOGLE_DOCS_MIME_TYPE = "application/vnd.google-apps.document"
GOOGLE_SHEETS_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES_MIME_TYPE = "application/vnd.google-apps.presentation"

# MIME type for PDF files
PDF_MIME_TYPE = "application/pdf"

# All supported MIME types for ingestion
SUPPORTED_MIME_TYPES = [
    GOOGLE_DOCS_MIME_TYPE,
    GOOGLE_SHEETS_MIME_TYPE,
    GOOGLE_SLIDES_MIME_TYPE,
    PDF_MIME_TYPE,
]


def _parse_drive_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse a Drive API timestamp string to datetime.

    Args:
        value: ISO format timestamp string from Drive API

    Returns:
        datetime object or None if parsing fails
    """
    if not value:
        return None
    try:
        # Drive API returns RFC 3339 timestamps
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_document_state(
    file_id: str,
    title: str,
    mime_type: str,
    head_revision_id: str,
    content_hash: str,
    file_meta: dict,
    owner_email: Optional[str],
    owner_name: Optional[str],
    last_modifier_email: Optional[str],
    last_modifier_name: Optional[str],
    sharing_user_email: Optional[str],
    sharing_user_name: Optional[str],
    parent_folder_ids: list[str],
    folder_path: list[str],
    folder_path_ids: list[str],
    sharing_domains: list[str],
    has_external_access: bool,
    can_edit: bool,
    can_share: bool,
    can_read_revisions: bool,
    file_size_bytes: Optional[int],
    last_indexed_revision_id: Optional[str] = None,
    last_indexed_at: Optional[datetime] = None,
    first_indexed_at: Optional[datetime] = None,
) -> DocumentState:
    """Build a comprehensive DocumentState from file metadata.

    This helper constructs a DocumentState with all metadata fields
    extracted from the Drive API response.
    """
    return DocumentState(
        drive_file_id=file_id,
        title=title,
        mime_type=mime_type,
        # Revision tracking
        last_seen_revision_id=head_revision_id,
        last_indexed_revision_id=last_indexed_revision_id,
        last_indexed_at=last_indexed_at,
        content_hash=content_hash,
        # Timestamps from Drive API
        created_time=_parse_drive_timestamp(file_meta.get("createdTime")),
        modified_time=_parse_drive_timestamp(file_meta.get("modifiedTime")),
        viewed_by_me_time=_parse_drive_timestamp(file_meta.get("viewedByMeTime")),
        shared_with_me_time=_parse_drive_timestamp(file_meta.get("sharedWithMeTime")),
        # Ownership/Users
        owner_email=owner_email,
        owner_name=owner_name,
        owner_permission_id=None,  # Would require permissions.list call
        last_modifier_email=last_modifier_email,
        last_modifier_name=last_modifier_name,
        sharing_user_email=sharing_user_email,
        sharing_user_name=sharing_user_name,
        # Folder hierarchy
        parent_folder_ids=parent_folder_ids,
        folder_path=folder_path,
        folder_path_ids=folder_path_ids,
        # Sharing/Permissions
        shared=file_meta.get("shared", False),
        sharing_domains=sharing_domains,
        has_external_access=has_external_access,
        is_shared_drive=False,  # Would need to check driveId field
        # Links
        web_view_link=file_meta.get("webViewLink"),
        # File properties
        file_size_bytes=file_size_bytes,
        description=file_meta.get("description"),
        starred=file_meta.get("starred", False),
        trashed=file_meta.get("trashed", False),
        # Capabilities
        can_edit=can_edit,
        can_share=can_share,
        can_read_revisions=can_read_revisions,
        # Graphiti entity analysis (populated later during entity extraction)
        collaborator_emails=[],
        # Ingestion metadata
        first_indexed_at=first_indexed_at,
        index_version=1,
    )


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
        # 1. Fetch extended file metadata from Drive
        logger.info("fetching_metadata", file_id=file_id)
        file_meta = google.get_file_metadata_extended(file_id)

        title = file_meta.get("name", "Untitled")
        mime_type = file_meta.get("mimeType", "")
        head_revision_id = file_meta.get("headRevisionId", "")

        # Extract owner information
        owner_email = None
        owner_name = None
        if file_meta.get("owners"):
            owner = file_meta["owners"][0]
            owner_email = owner.get("emailAddress")
            owner_name = owner.get("displayName")

        # Extract last modifier information
        last_modifier_email = None
        last_modifier_name = None
        if file_meta.get("lastModifyingUser"):
            modifier = file_meta["lastModifyingUser"]
            last_modifier_email = modifier.get("emailAddress")
            last_modifier_name = modifier.get("displayName")

        # Extract sharing user information
        sharing_user_email = None
        sharing_user_name = None
        if file_meta.get("sharingUser"):
            sharer = file_meta["sharingUser"]
            sharing_user_email = sharer.get("emailAddress")
            sharing_user_name = sharer.get("displayName")

        # Extract capabilities
        capabilities = file_meta.get("capabilities", {})
        can_edit = capabilities.get("canEdit", False)
        can_share = capabilities.get("canShare", False)
        can_read_revisions = capabilities.get("canReadRevisions", False)

        # Build folder path
        parent_folder_ids = file_meta.get("parents", [])
        folder_path, folder_path_ids = [], []
        if parent_folder_ids:
            try:
                folder_path, folder_path_ids = google.build_folder_path(parent_folder_ids[0])
            except Exception as path_error:
                logger.warning("folder_path_build_failed", file_id=file_id, error=str(path_error))

        # Extract sharing domains
        sharing_domains, has_external_access = google.extract_sharing_domains(file_meta)

        # Parse file size (may be None for Google Workspace files)
        file_size_bytes = None
        if file_meta.get("size"):
            try:
                file_size_bytes = int(file_meta["size"])
            except (ValueError, TypeError):
                pass

        # Verify it's a supported file type
        if mime_type not in SUPPORTED_MIME_TYPES:
            return IngestionResult(
                status="skipped",
                drive_file_id=file_id,
                reason=f"Unsupported file type (mime: {mime_type})",
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

        # 3. Fetch and normalize content based on file type
        logger.info("fetching_content", file_id=file_id, title=title, mime_type=mime_type)

        if mime_type == GOOGLE_DOCS_MIME_TYPE:
            # Google Docs - try Docs API first, fall back to Drive export
            try:
                doc = google.get_document(file_id)
                snapshot = normalize_docs_document(file_id, head_revision_id, doc)
            except Exception as docs_error:
                logger.warning(
                    "docs_api_failed_using_fallback",
                    file_id=file_id,
                    error=str(docs_error),
                )
                plain_text = google.export_document_as_text(file_id)
                snapshot = normalize_plain_text_document(file_id, head_revision_id, plain_text)

        elif mime_type == GOOGLE_SHEETS_MIME_TYPE:
            # Google Sheets - export as CSV
            csv_content = google.export_spreadsheet_as_csv(file_id)
            snapshot = normalize_spreadsheet_csv(file_id, head_revision_id, csv_content)

        elif mime_type == GOOGLE_SLIDES_MIME_TYPE:
            # Google Slides - export as plain text
            text_content = google.export_presentation_as_text(file_id)
            snapshot = normalize_presentation_text(file_id, head_revision_id, text_content)

        elif mime_type == PDF_MIME_TYPE:
            # PDF files - download and extract text
            pdf_content = google.download_file_content(file_id)
            snapshot = normalize_pdf_document(file_id, head_revision_id, pdf_content)

        # Check content hash for deeper comparison
        if not force and existing_state:
            if existing_state.content_hash == snapshot.normalized_hash:
                # Update revision tracking but skip re-indexing
                database.upsert_document_state(
                    _build_document_state(
                        file_id=file_id,
                        title=title,
                        mime_type=mime_type,
                        head_revision_id=head_revision_id,
                        content_hash=snapshot.normalized_hash,
                        file_meta=file_meta,
                        owner_email=owner_email,
                        owner_name=owner_name,
                        last_modifier_email=last_modifier_email,
                        last_modifier_name=last_modifier_name,
                        sharing_user_email=sharing_user_email,
                        sharing_user_name=sharing_user_name,
                        parent_folder_ids=parent_folder_ids,
                        folder_path=folder_path,
                        folder_path_ids=folder_path_ids,
                        sharing_domains=sharing_domains,
                        has_external_access=has_external_access,
                        can_edit=can_edit,
                        can_share=can_share,
                        can_read_revisions=can_read_revisions,
                        file_size_bytes=file_size_bytes,
                        # Preserve existing indexed times
                        last_indexed_revision_id=existing_state.last_indexed_revision_id,
                        last_indexed_at=existing_state.last_indexed_at,
                        first_indexed_at=existing_state.first_indexed_at,
                    )
                )

                return IngestionResult(
                    status="skipped",
                    drive_file_id=file_id,
                    revision_id=head_revision_id,
                    reason="Content hash unchanged",
                )

        # 4. Save snapshot for edit tracking (Phase 2)
        try:
            # Check if we already have a snapshot for this revision
            existing_snapshot = database.get_snapshot_metadata(file_id, head_revision_id)
            if not existing_snapshot:
                snapshot_meta = save_snapshot(
                    file_id=file_id,
                    revision_id=head_revision_id,
                    snapshot=snapshot,
                    modifier_email=last_modifier_email,
                    modifier_name=last_modifier_name,
                    modified_time=_parse_drive_timestamp(file_meta.get("modifiedTime")),
                )

                # Store snapshot metadata in database
                database.upsert_snapshot_metadata(
                    DocumentSnapshot(
                        drive_file_id=file_id,
                        revision_id=head_revision_id,
                        content_hash=snapshot_meta["content_hash"],
                        normalized_text_length=snapshot_meta["normalized_text_length"],
                        blocks_count=snapshot_meta["blocks_count"],
                        compressed_size_bytes=snapshot_meta["compressed_size_bytes"],
                        snapshot_path=snapshot_meta["snapshot_path"],
                        modifier_email=snapshot_meta["modifier_email"],
                        modifier_name=snapshot_meta["modifier_name"],
                        modified_time=snapshot_meta["modified_time"],
                    )
                )

                logger.info(
                    "snapshot_saved",
                    file_id=file_id,
                    revision_id=head_revision_id[:16] if head_revision_id else "",
                    path=snapshot_meta["snapshot_path"],
                )
        except Exception as snapshot_error:
            # Don't fail ingestion if snapshot saving fails
            logger.warning(
                "snapshot_save_failed",
                file_id=file_id,
                error=str(snapshot_error),
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

        # Update document state with full metadata
        now = datetime.utcnow()
        first_indexed_at = existing_state.first_indexed_at if existing_state else now

        database.upsert_document_state(
            _build_document_state(
                file_id=file_id,
                title=title,
                mime_type=mime_type,
                head_revision_id=head_revision_id,
                content_hash=snapshot.normalized_hash,
                file_meta=file_meta,
                owner_email=owner_email,
                owner_name=owner_name,
                last_modifier_email=last_modifier_email,
                last_modifier_name=last_modifier_name,
                sharing_user_email=sharing_user_email,
                sharing_user_name=sharing_user_name,
                parent_folder_ids=parent_folder_ids,
                folder_path=folder_path,
                folder_path_ids=folder_path_ids,
                sharing_domains=sharing_domains,
                has_external_access=has_external_access,
                can_edit=can_edit,
                can_share=can_share,
                can_read_revisions=can_read_revisions,
                file_size_bytes=file_size_bytes,
                last_indexed_revision_id=head_revision_id,
                last_indexed_at=now,
                first_indexed_at=first_indexed_at,
            )
        )

        # 9. Store revision history (if we can read revisions)
        if can_read_revisions:
            try:
                revisions = google.list_revisions(file_id)
                for rev in revisions:
                    rev_modifier = rev.get("lastModifyingUser", {})
                    database.upsert_document_revision(
                        DocumentRevision(
                            drive_file_id=file_id,
                            revision_id=rev.get("id", ""),
                            modified_time=_parse_drive_timestamp(rev.get("modifiedTime")),
                            modifier_email=rev_modifier.get("emailAddress"),
                            modifier_name=rev_modifier.get("displayName"),
                            # Check if we have a snapshot for this revision
                            has_snapshot=database.get_snapshot_metadata(
                                file_id, rev.get("id", "")
                            ) is not None,
                        )
                    )
                logger.info(
                    "revisions_stored",
                    file_id=file_id,
                    count=len(revisions),
                )
            except Exception as rev_error:
                # Don't fail ingestion if revision tracking fails
                logger.warning(
                    "revision_tracking_failed",
                    file_id=file_id,
                    error=str(rev_error),
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

    # List all supported file types in folder
    all_files = []
    for mime_type in SUPPORTED_MIME_TYPES:
        files = google.list_files_in_folder(folder_id, mime_type=mime_type)
        all_files.extend(files)

    logger.info("found_documents", folder_id=folder_id, count=len(all_files))

    results: list[IngestionResult] = []
    processed = 0
    skipped = 0
    failed = 0

    for file in all_files:
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
