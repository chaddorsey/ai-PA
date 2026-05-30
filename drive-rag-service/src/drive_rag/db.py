"""HTTP client for PostgREST/pgvector operations.

This module handles all database operations:
- Document state tracking (coordination catalog)
- Chunk storage with embeddings
- Vector similarity search
- Folder cache for hierarchy traversal
- Revision tracking for edit attribution
"""

from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

from drive_rag.models import (
    ChunkRecord,
    DocumentState,
    FolderCache,
    DocumentRevision,
    DocumentSnapshot,
    SearchResult,
)
from drive_rag.settings import get_settings

logger = structlog.get_logger()


def _serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO format string for database storage."""
    return dt.isoformat() if dt else None


def _deserialize_datetime(value: Any) -> Optional[datetime]:
    """Convert ISO format string from database to datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Handle ISO format with optional timezone
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class Database:
    """HTTP client for PostgREST RAG operations."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize database connection.

        Args:
            url: PostgREST URL (defaults to settings)
            key: Service key for authentication (defaults to settings)
        """
        settings = get_settings()
        self.base_url = (url or settings.supabase_url).rstrip("/")
        self.service_key = key or settings.supabase_service_key
        self.schema = "rag"

        self.client = httpx.Client(
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
                "Accept-Profile": self.schema,  # Use schema via header
                "Content-Profile": self.schema,  # For write operations
                "Prefer": "return=representation",
            },
            timeout=30.0,
        )

    def _url(self, table: str) -> str:
        """Build URL for a table (schema is set via header)."""
        return f"{self.base_url}/{table}"

    def _check_response(self, response: httpx.Response, operation: str) -> None:
        """Check response and raise on error."""
        if response.status_code >= 400:
            logger.error(
                "database_error",
                operation=operation,
                status=response.status_code,
                body=response.text,
            )
            response.raise_for_status()

    # =====================
    # Document State Operations
    # =====================

    def get_document_state(self, file_id: str) -> Optional[DocumentState]:
        """Get the current state of a document.

        Args:
            file_id: Google Drive file ID

        Returns:
            DocumentState if found, None otherwise
        """
        response = self.client.get(
            self._url("document_state"),
            params={"drive_file_id": f"eq.{file_id}", "select": "*"},
        )
        self._check_response(response, "get_document_state")

        data = response.json()
        if not data:
            return None

        row = data[0]
        return self._row_to_document_state(row)

    def _row_to_document_state(self, row: dict[str, Any]) -> DocumentState:
        """Convert a database row to a DocumentState object.

        Args:
            row: Database row dictionary

        Returns:
            DocumentState object with all fields populated
        """
        return DocumentState(
            drive_file_id=row["drive_file_id"],
            title=row["title"],
            mime_type=row.get("mime_type"),
            # Revision tracking
            last_seen_revision_id=row.get("last_seen_revision_id"),
            last_indexed_revision_id=row.get("last_indexed_revision_id"),
            last_indexed_at=_deserialize_datetime(row.get("last_indexed_at")),
            content_hash=row.get("content_hash"),
            # Timestamps from Drive API
            created_time=_deserialize_datetime(row.get("created_time")),
            modified_time=_deserialize_datetime(row.get("modified_time")),
            viewed_by_me_time=_deserialize_datetime(row.get("viewed_by_me_time")),
            shared_with_me_time=_deserialize_datetime(row.get("shared_with_me_time")),
            # Ownership/Users
            owner_email=row.get("owner_email"),
            owner_name=row.get("owner_name"),
            owner_permission_id=row.get("owner_permission_id"),
            last_modifier_email=row.get("last_modifier_email"),
            last_modifier_name=row.get("last_modifier_name"),
            sharing_user_email=row.get("sharing_user_email"),
            sharing_user_name=row.get("sharing_user_name"),
            # Folder hierarchy
            parent_folder_ids=row.get("parent_folder_ids") or [],
            folder_path=row.get("folder_path") or [],
            folder_path_ids=row.get("folder_path_ids") or [],
            # Sharing/Permissions
            shared=row.get("shared", False),
            sharing_domains=row.get("sharing_domains") or [],
            has_external_access=row.get("has_external_access", False),
            is_shared_drive=row.get("is_shared_drive", False),
            # Links
            web_view_link=row.get("web_view_link"),
            # File properties
            file_size_bytes=row.get("file_size_bytes"),
            description=row.get("description"),
            starred=row.get("starred", False),
            trashed=row.get("trashed", False),
            # Capabilities
            can_edit=row.get("can_edit", False),
            can_share=row.get("can_share", False),
            can_read_revisions=row.get("can_read_revisions", False),
            # Graphiti entity analysis
            collaborator_emails=row.get("collaborator_emails") or [],
            # Ingestion metadata
            first_indexed_at=_deserialize_datetime(row.get("first_indexed_at")),
            index_version=row.get("index_version", 1),
        )

    def upsert_document_state(self, state: DocumentState) -> None:
        """Insert or update document state.

        Args:
            state: Document state to upsert
        """
        data = {
            # Core identifiers
            "drive_file_id": state.drive_file_id,
            "title": state.title,
            "mime_type": state.mime_type,
            # Revision tracking
            "last_seen_revision_id": state.last_seen_revision_id,
            "last_indexed_revision_id": state.last_indexed_revision_id,
            "last_indexed_at": _serialize_datetime(state.last_indexed_at),
            "content_hash": state.content_hash,
            # Timestamps from Drive API
            "created_time": _serialize_datetime(state.created_time),
            "modified_time": _serialize_datetime(state.modified_time),
            "viewed_by_me_time": _serialize_datetime(state.viewed_by_me_time),
            "shared_with_me_time": _serialize_datetime(state.shared_with_me_time),
            # Ownership/Users
            "owner_email": state.owner_email,
            "owner_name": state.owner_name,
            "owner_permission_id": state.owner_permission_id,
            "last_modifier_email": state.last_modifier_email,
            "last_modifier_name": state.last_modifier_name,
            "sharing_user_email": state.sharing_user_email,
            "sharing_user_name": state.sharing_user_name,
            # Folder hierarchy
            "parent_folder_ids": state.parent_folder_ids if state.parent_folder_ids else None,
            "folder_path": state.folder_path if state.folder_path else None,
            "folder_path_ids": state.folder_path_ids if state.folder_path_ids else None,
            # Sharing/Permissions
            "shared": state.shared,
            "sharing_domains": state.sharing_domains if state.sharing_domains else None,
            "has_external_access": state.has_external_access,
            "is_shared_drive": state.is_shared_drive,
            # Links
            "web_view_link": state.web_view_link,
            # File properties
            "file_size_bytes": state.file_size_bytes,
            "description": state.description,
            "starred": state.starred,
            "trashed": state.trashed,
            # Capabilities
            "can_edit": state.can_edit,
            "can_share": state.can_share,
            "can_read_revisions": state.can_read_revisions,
            # Graphiti entity analysis
            "collaborator_emails": state.collaborator_emails if state.collaborator_emails else None,
            # Ingestion metadata
            "first_indexed_at": _serialize_datetime(state.first_indexed_at),
            "index_version": state.index_version,
            # System timestamp
            "updated_at": datetime.utcnow().isoformat(),
        }

        response = self.client.post(
            self._url("document_state"),
            json=data,
            headers={
                **self.client.headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        self._check_response(response, "upsert_document_state")

        logger.debug("upserted_document_state", file_id=state.drive_file_id)

    # =====================
    # Chunk Operations
    # =====================

    def get_chunks_by_file(self, file_id: str) -> list[dict[str, Any]]:
        """Get all chunks for a document.

        Args:
            file_id: Google Drive file ID

        Returns:
            List of chunk records (without embeddings to save bandwidth)
        """
        response = self.client.get(
            self._url("document_chunks"),
            params={
                "drive_file_id": f"eq.{file_id}",
                "select": "id,drive_file_id,revision_id,title,chunk_id,outline_path,"
                "block_start_id,block_end_id,char_start,char_end,chunk_hash",
            },
        )
        self._check_response(response, "get_chunks_by_file")

        return response.json() or []

    def upsert_chunks(
        self, chunks: list[ChunkRecord], embeddings: list[list[float]]
    ) -> None:
        """Insert or update chunks with embeddings.

        Args:
            chunks: List of chunk records
            embeddings: List of embedding vectors (same order as chunks)
        """
        if not chunks:
            return

        records = []
        for chunk, embedding in zip(chunks, embeddings):
            records.append(
                {
                    "drive_file_id": chunk.drive_file_id,
                    "revision_id": chunk.revision_id,
                    "title": chunk.title,
                    "chunk_id": chunk.chunk_id,
                    "outline_path": chunk.outline_path,
                    "block_start_id": chunk.block_start_id,
                    "block_end_id": chunk.block_end_id,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "chunk_text": chunk.chunk_text,
                    "chunk_hash": chunk.chunk_hash,
                    "embedding": embedding,
                    "indexed_at": datetime.utcnow().isoformat(),
                }
            )

        # Upsert in batches of 100.
        # PostgREST `resolution=merge-duplicates` defaults to the table's
        # primary key as the conflict target. Our uniqueness lives on the
        # `unique_chunk` constraint (drive_file_id, chunk_id) — NOT the PK
        # — so we must pass on_conflict explicitly. Without it, re-ingesting
        # a doc with unchanged chunks 409s on the unique constraint instead
        # of merging. Bug surfaced 2026-05-28 when MC tried snapshot-on-
        # command for an actively-edited proposal.
        for i in range(0, len(records), 100):
            batch = records[i : i + 100]
            response = self.client.post(
                self._url("document_chunks") + "?on_conflict=drive_file_id,chunk_id",
                json=batch,
                headers={
                    **self.client.headers,
                    "Prefer": "resolution=merge-duplicates,return=representation",
                },
            )
            self._check_response(response, "upsert_chunks")

        logger.info("upserted_chunks", count=len(chunks))

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunks by their IDs.

        Args:
            chunk_ids: List of chunk_id values to delete
        """
        if not chunk_ids:
            return

        # Delete in batches
        for i in range(0, len(chunk_ids), 100):
            batch = chunk_ids[i : i + 100]
            # PostgREST uses in.() for arrays
            ids_param = ",".join(f'"{cid}"' for cid in batch)
            response = self.client.delete(
                self._url("document_chunks"),
                params={"chunk_id": f"in.({ids_param})"},
            )
            self._check_response(response, "delete_chunks")

        logger.info("deleted_chunks", count=len(chunk_ids))

    def delete_chunks_by_file(self, file_id: str) -> int:
        """Delete all chunks for a document.

        Args:
            file_id: Google Drive file ID

        Returns:
            Number of chunks deleted
        """
        response = self.client.delete(
            self._url("document_chunks"),
            params={"drive_file_id": f"eq.{file_id}"},
            headers={
                **self.client.headers,
                "Prefer": "return=representation",
            },
        )
        self._check_response(response, "delete_chunks_by_file")

        data = response.json()
        count = len(data) if data else 0
        logger.info("deleted_file_chunks", file_id=file_id, count=count)
        return count

    # =====================
    # Search Operations
    # =====================

    def search_similar(
        self,
        query_embedding: list[float],
        limit: int = 10,
        file_ids: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search for similar chunks using vector similarity.

        Args:
            query_embedding: Query embedding vector
            limit: Maximum results to return
            file_ids: Optional list of file IDs to search within

        Returns:
            List of search results ordered by similarity
        """
        # Try using the search RPC function if available
        try:
            params = {
                "query_embedding": query_embedding,
                "match_count": limit,
            }
            if file_ids:
                params["filter_file_ids"] = file_ids

            response = self.client.post(
                f"{self.base_url}/rpc/search_document_chunks",
                json=params,
            )

            if response.status_code == 200:
                data = response.json()
                if data:
                    return [
                        SearchResult(
                            drive_file_id=row["drive_file_id"],
                            title=row["title"],
                            chunk_text=row["chunk_text"],
                            outline_path=row.get("outline_path", []),
                            similarity=row["similarity"],
                        )
                        for row in data
                    ]
                return []
        except Exception as e:
            logger.warning(
                "vector_search_rpc_failed",
                error=str(e),
                fallback="python_filtering",
            )

        # Fallback to Python-based filtering (slower but works)
        return self._search_similar_fallback(query_embedding, limit, file_ids)

    def _search_similar_fallback(
        self,
        query_embedding: list[float],
        limit: int = 10,
        file_ids: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Fallback search using Python (slower, for initial testing)."""
        import numpy as np

        # Fetch chunks with embeddings
        params = {"select": "drive_file_id,title,chunk_text,outline_path,embedding", "limit": "1000"}
        if file_ids:
            ids_param = ",".join(f'"{fid}"' for fid in file_ids)
            params["drive_file_id"] = f"in.({ids_param})"

        response = self.client.get(self._url("document_chunks"), params=params)
        self._check_response(response, "search_similar_fallback")

        data = response.json()
        if not data:
            return []

        # Calculate cosine similarities
        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)

        scored_results = []
        for row in data:
            if not row.get("embedding"):
                continue

            # Parse embedding - may be string (from PostgREST) or list
            embedding_data = row["embedding"]
            if isinstance(embedding_data, str):
                # Parse string representation "[0.1,0.2,...]"
                import json
                embedding_data = json.loads(embedding_data)

            chunk_vec = np.array(embedding_data)
            chunk_norm = np.linalg.norm(chunk_vec)

            if query_norm == 0 or chunk_norm == 0:
                similarity = 0.0
            else:
                similarity = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))

            scored_results.append(
                (
                    similarity,
                    SearchResult(
                        drive_file_id=row["drive_file_id"],
                        title=row["title"],
                        chunk_text=row["chunk_text"],
                        outline_path=row.get("outline_path", []),
                        similarity=similarity,
                    ),
                )
            )

        # Sort by similarity descending
        scored_results.sort(key=lambda x: x[0], reverse=True)

        return [r for _, r in scored_results[:limit]]

    def get_chunk_count(self, file_id: Optional[str] = None) -> int:
        """Get count of indexed chunks.

        Args:
            file_id: Optional file ID to count chunks for

        Returns:
            Number of chunks
        """
        params = {"select": "id", "limit": "0"}
        if file_id:
            params["drive_file_id"] = f"eq.{file_id}"

        # Use GET with Prefer: count=exact header (HEAD doesn't work with multi-schema)
        response = self.client.get(
            self._url("document_chunks"),
            params=params,
            headers={
                **self.client.headers,
                "Prefer": "count=exact",
            },
        )
        self._check_response(response, "get_chunk_count")

        # Count is in Content-Range header
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            try:
                return int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass
        return 0

    def get_document_count(self) -> int:
        """Get count of indexed documents.

        Returns:
            Number of documents in document_state
        """
        params = {"select": "drive_file_id", "limit": "0"}

        # Use GET with Prefer: count=exact header
        response = self.client.get(
            self._url("document_state"),
            params=params,
            headers={
                **self.client.headers,
                "Prefer": "count=exact",
            },
        )
        self._check_response(response, "get_document_count")

        # Count is in Content-Range header
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            try:
                return int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass
        return 0

    def get_indexed_documents(
        self, limit: int = 50, offset: int = 0
    ) -> list[DocumentState]:
        """Get list of indexed documents.

        Args:
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            List of document states
        """
        response = self.client.get(
            self._url("document_state"),
            params={
                "select": "*",
                "order": "last_indexed_at.desc",
                "limit": str(limit),
                "offset": str(offset),
            },
        )
        self._check_response(response, "get_indexed_documents")

        data = response.json()
        return [self._row_to_document_state(row) for row in (data or [])]

    # =====================
    # Folder Cache Operations
    # =====================

    def get_folder_cache(self, folder_id: str) -> Optional[FolderCache]:
        """Get cached folder metadata.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            FolderCache if found and not stale, None otherwise
        """
        response = self.client.get(
            self._url("folder_cache"),
            params={
                "folder_id": f"eq.{folder_id}",
                "select": "*",
                "stale_after": f"gte.{datetime.utcnow().isoformat()}",
            },
        )
        self._check_response(response, "get_folder_cache")

        data = response.json()
        if not data:
            return None

        row = data[0]
        return FolderCache(
            folder_id=row["folder_id"],
            name=row["name"],
            parent_folder_ids=row.get("parent_folder_ids") or [],
            folder_path=row.get("folder_path") or [],
            folder_path_ids=row.get("folder_path_ids") or [],
            depth=row.get("depth", 0),
            created_time=_deserialize_datetime(row.get("created_time")),
            modified_time=_deserialize_datetime(row.get("modified_time")),
            owner_email=row.get("owner_email"),
            owner_name=row.get("owner_name"),
            shared=row.get("shared", False),
            cached_at=_deserialize_datetime(row.get("cached_at")),
            stale_after=_deserialize_datetime(row.get("stale_after")),
        )

    def upsert_folder_cache(self, folder: FolderCache) -> None:
        """Insert or update folder cache entry.

        Args:
            folder: Folder cache data to upsert
        """
        data = {
            "folder_id": folder.folder_id,
            "name": folder.name,
            "parent_folder_ids": folder.parent_folder_ids if folder.parent_folder_ids else None,
            "folder_path": folder.folder_path if folder.folder_path else None,
            "folder_path_ids": folder.folder_path_ids if folder.folder_path_ids else None,
            "depth": folder.depth,
            "created_time": _serialize_datetime(folder.created_time),
            "modified_time": _serialize_datetime(folder.modified_time),
            "owner_email": folder.owner_email,
            "owner_name": folder.owner_name,
            "shared": folder.shared,
            "cached_at": datetime.utcnow().isoformat(),
            "stale_after": _serialize_datetime(folder.stale_after),
        }

        response = self.client.post(
            self._url("folder_cache"),
            json=data,
            headers={
                **self.client.headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        self._check_response(response, "upsert_folder_cache")

        logger.debug("upserted_folder_cache", folder_id=folder.folder_id)

    # =====================
    # Revision Tracking Operations
    # =====================

    def upsert_document_revision(self, revision: DocumentRevision) -> None:
        """Insert or update a document revision record.

        Args:
            revision: Revision data to upsert
        """
        data = {
            "drive_file_id": revision.drive_file_id,
            "revision_id": revision.revision_id,
            "modified_time": _serialize_datetime(revision.modified_time),
            "modifier_email": revision.modifier_email,
            "modifier_name": revision.modifier_name,
            "modifier_permission_id": revision.modifier_permission_id,
            "keep_forever": revision.keep_forever,
            "published": revision.published,
            "content_hash": revision.content_hash,
            "has_snapshot": revision.has_snapshot,
            "snapshot_uri": revision.snapshot_uri,
        }

        # PostgREST requires explicit on_conflict when the conflict target
        # is a UNIQUE constraint other than the PK. The PK here is `id`;
        # the actual uniqueness lives on `unique_file_revision`
        # (drive_file_id, revision_id). Same fix shape as upsert_chunks.
        response = self.client.post(
            self._url("document_revisions") + "?on_conflict=drive_file_id,revision_id",
            json=data,
            headers={
                **self.client.headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        self._check_response(response, "upsert_document_revision")

        logger.debug(
            "upserted_document_revision",
            file_id=revision.drive_file_id,
            revision_id=revision.revision_id,
        )

    def get_document_revisions(self, file_id: str) -> list[DocumentRevision]:
        """Get all revisions for a document.

        Args:
            file_id: Google Drive file ID

        Returns:
            List of revision records ordered by modified_time desc
        """
        response = self.client.get(
            self._url("document_revisions"),
            params={
                "drive_file_id": f"eq.{file_id}",
                "select": "*",
                "order": "modified_time.desc",
            },
        )
        self._check_response(response, "get_document_revisions")

        data = response.json()
        return [
            DocumentRevision(
                drive_file_id=row["drive_file_id"],
                revision_id=row["revision_id"],
                modified_time=_deserialize_datetime(row.get("modified_time")),
                modifier_email=row.get("modifier_email"),
                modifier_name=row.get("modifier_name"),
                modifier_permission_id=row.get("modifier_permission_id"),
                keep_forever=row.get("keep_forever", False),
                published=row.get("published", False),
                content_hash=row.get("content_hash"),
                has_snapshot=row.get("has_snapshot", False),
                snapshot_uri=row.get("snapshot_uri"),
            )
            for row in (data or [])
        ]

    # =====================
    # Snapshot Operations
    # =====================

    def upsert_snapshot_metadata(self, snapshot: DocumentSnapshot) -> None:
        """Insert or update snapshot metadata.

        Args:
            snapshot: Snapshot metadata to upsert
        """
        data = {
            "drive_file_id": snapshot.drive_file_id,
            "revision_id": snapshot.revision_id,
            "content_hash": snapshot.content_hash,
            "normalized_text_length": snapshot.normalized_text_length,
            "blocks_count": snapshot.blocks_count,
            "compressed_size_bytes": snapshot.compressed_size_bytes,
            "snapshot_path": snapshot.snapshot_path,
            "modifier_email": snapshot.modifier_email,
            "modifier_name": snapshot.modifier_name,
            "modified_time": _serialize_datetime(snapshot.modified_time),
        }

        # Same on_conflict fix as upsert_chunks / upsert_document_revision —
        # the uniqueness target is unique_file_revision_snapshot, not the PK.
        response = self.client.post(
            self._url("document_snapshots") + "?on_conflict=drive_file_id,revision_id",
            json=data,
            headers={
                **self.client.headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        self._check_response(response, "upsert_snapshot_metadata")

        logger.debug(
            "upserted_snapshot_metadata",
            file_id=snapshot.drive_file_id,
            revision_id=snapshot.revision_id,
        )

    def get_snapshot_metadata(
        self, file_id: str, revision_id: str
    ) -> Optional[DocumentSnapshot]:
        """Get snapshot metadata for a specific revision.

        Args:
            file_id: Google Drive file ID
            revision_id: Document revision ID

        Returns:
            DocumentSnapshot if found, None otherwise
        """
        response = self.client.get(
            self._url("document_snapshots"),
            params={
                "drive_file_id": f"eq.{file_id}",
                "revision_id": f"eq.{revision_id}",
                "select": "*",
            },
        )
        self._check_response(response, "get_snapshot_metadata")

        data = response.json()
        if not data:
            return None

        row = data[0]
        return DocumentSnapshot(
            drive_file_id=row["drive_file_id"],
            revision_id=row["revision_id"],
            content_hash=row["content_hash"],
            normalized_text_length=row["normalized_text_length"],
            blocks_count=row["blocks_count"],
            compressed_size_bytes=row.get("compressed_size_bytes"),
            snapshot_path=row["snapshot_path"],
            modifier_email=row.get("modifier_email"),
            modifier_name=row.get("modifier_name"),
            modified_time=_deserialize_datetime(row.get("modified_time")),
            created_at=_deserialize_datetime(row.get("created_at")),
        )

    def get_snapshots_for_file(self, file_id: str) -> list[DocumentSnapshot]:
        """Get all snapshots for a document.

        Args:
            file_id: Google Drive file ID

        Returns:
            List of snapshot metadata ordered by modified_time desc
        """
        response = self.client.get(
            self._url("document_snapshots"),
            params={
                "drive_file_id": f"eq.{file_id}",
                "select": "*",
                "order": "modified_time.desc",
            },
        )
        self._check_response(response, "get_snapshots_for_file")

        data = response.json()
        return [
            DocumentSnapshot(
                drive_file_id=row["drive_file_id"],
                revision_id=row["revision_id"],
                content_hash=row["content_hash"],
                normalized_text_length=row["normalized_text_length"],
                blocks_count=row["blocks_count"],
                compressed_size_bytes=row.get("compressed_size_bytes"),
                snapshot_path=row["snapshot_path"],
                modifier_email=row.get("modifier_email"),
                modifier_name=row.get("modifier_name"),
                modified_time=_deserialize_datetime(row.get("modified_time")),
                created_at=_deserialize_datetime(row.get("created_at")),
            )
            for row in (data or [])
        ]

    def get_all_snapshots(self) -> list[DocumentSnapshot]:
        """Get all snapshot metadata for retention processing.

        Returns:
            List of all DocumentSnapshot records
        """
        response = self.client.get(
            self._url("document_snapshots"),
            params={
                "select": "*",
                "order": "modified_time.desc",
            },
        )
        self._check_response(response, "get_all_snapshots")

        data = response.json()
        return [
            DocumentSnapshot(
                drive_file_id=row["drive_file_id"],
                revision_id=row["revision_id"],
                content_hash=row["content_hash"],
                normalized_text_length=row["normalized_text_length"],
                blocks_count=row["blocks_count"],
                compressed_size_bytes=row.get("compressed_size_bytes"),
                snapshot_path=row["snapshot_path"],
                modifier_email=row.get("modifier_email"),
                modifier_name=row.get("modifier_name"),
                modified_time=_deserialize_datetime(row.get("modified_time")),
                created_at=_deserialize_datetime(row.get("created_at")),
            )
            for row in (data or [])
        ]

    def delete_snapshot_metadata(self, file_id: str, revision_id: str) -> None:
        """Delete snapshot metadata record.

        Args:
            file_id: Google Drive file ID
            revision_id: Document revision ID
        """
        response = self.client.delete(
            self._url("document_snapshots"),
            params={
                "drive_file_id": f"eq.{file_id}",
                "revision_id": f"eq.{revision_id}",
            },
        )
        self._check_response(response, "delete_snapshot_metadata")

        logger.debug(
            "deleted_snapshot_metadata",
            file_id=file_id,
            revision_id=revision_id,
        )

    # =========================================================================
    # Change Sync State (for Drive Changes API)
    # =========================================================================

    def get_sync_state(self, state_id: str = "default") -> Optional[dict]:
        """Get the current sync state for change tracking.

        Args:
            state_id: Identifier for the sync state (default: "default")

        Returns:
            Sync state dict or None if not initialized
        """
        response = self.client.get(
            self._url("change_sync_state"),
            params={
                "id": f"eq.{state_id}",
                "select": "*",
            },
        )
        self._check_response(response, "get_sync_state")

        data = response.json()
        if data:
            row = data[0]
            return {
                "id": row["id"],
                "page_token": row["page_token"],
                "last_sync_at": _deserialize_datetime(row.get("last_sync_at")),
                "total_changes_processed": row.get("total_changes_processed", 0),
                "new_files_count": row.get("new_files_count", 0),
                "modified_files_count": row.get("modified_files_count", 0),
                "deleted_files_count": row.get("deleted_files_count", 0),
                "last_error": row.get("last_error"),
                "created_at": _deserialize_datetime(row.get("created_at")),
                "updated_at": _deserialize_datetime(row.get("updated_at")),
            }
        return None

    def initialize_sync_state(self, page_token: str, state_id: str = "default") -> None:
        """Initialize sync state with a starting page token.

        Args:
            page_token: The initial page token from getStartPageToken
            state_id: Identifier for the sync state (default: "default")
        """
        response = self.client.post(
            self._url("change_sync_state"),
            json={
                "id": state_id,
                "page_token": page_token,
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._check_response(response, "initialize_sync_state")

        logger.info(
            "initialized_sync_state",
            state_id=state_id,
            token_prefix=page_token[:20] if page_token else "",
        )

    def update_sync_state(
        self,
        page_token: str,
        changes_processed: int = 0,
        new_files: int = 0,
        modified_files: int = 0,
        deleted_files: int = 0,
        error: Optional[str] = None,
        state_id: str = "default",
    ) -> None:
        """Update sync state after processing changes.

        Args:
            page_token: New page token for next sync
            changes_processed: Number of changes processed in this sync
            new_files: Number of new files discovered
            modified_files: Number of modified files
            deleted_files: Number of deleted/trashed files
            error: Error message if sync failed
            state_id: Identifier for the sync state (default: "default")
        """
        # First get current state to increment counters
        current = self.get_sync_state(state_id)
        if not current:
            # Initialize if not exists
            self.initialize_sync_state(page_token, state_id)
            current = {"total_changes_processed": 0, "new_files_count": 0,
                      "modified_files_count": 0, "deleted_files_count": 0}

        update_data = {
            "page_token": page_token,
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_changes_processed": current["total_changes_processed"] + changes_processed,
            "new_files_count": current["new_files_count"] + new_files,
            "modified_files_count": current["modified_files_count"] + modified_files,
            "deleted_files_count": current["deleted_files_count"] + deleted_files,
        }

        if error:
            update_data["last_error"] = error[:500]  # Truncate long errors
        else:
            update_data["last_error"] = None

        response = self.client.patch(
            self._url("change_sync_state"),
            params={"id": f"eq.{state_id}"},
            json=update_data,
        )
        self._check_response(response, "update_sync_state")

        logger.info(
            "updated_sync_state",
            state_id=state_id,
            changes_processed=changes_processed,
            new_files=new_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
        )

    def reset_sync_state(self, page_token: str, state_id: str = "default") -> None:
        """Reset sync state with a new page token.

        This clears the counters and sets a fresh token. Use when
        the token becomes invalid or for a fresh start.

        Args:
            page_token: New starting page token
            state_id: Identifier for the sync state (default: "default")
        """
        # Delete existing state if any
        self.client.delete(
            self._url("change_sync_state"),
            params={"id": f"eq.{state_id}"},
        )

        # Create fresh state
        self.initialize_sync_state(page_token, state_id)

        logger.info(
            "reset_sync_state",
            state_id=state_id,
        )

    def document_exists(self, file_id: str) -> bool:
        """Check if a document exists in our index.

        Args:
            file_id: Google Drive file ID

        Returns:
            True if document exists in document_state
        """
        response = self.client.get(
            self._url("document_state"),
            params={
                "drive_file_id": f"eq.{file_id}",
                "select": "drive_file_id",
            },
        )
        self._check_response(response, "document_exists")

        data = response.json()
        return len(data) > 0

    def mark_document_deleted(self, file_id: str) -> None:
        """Mark a document as deleted/removed.

        This doesn't delete the document from our index, but marks it
        so we know it's no longer available in Drive.

        Args:
            file_id: Google Drive file ID
        """
        # For now, we'll add a 'deleted_at' timestamp if we want soft delete
        # Or we could just delete the document state
        # Let's log for now and implement deletion strategy later
        logger.info(
            "document_marked_deleted",
            file_id=file_id,
        )

    # =========================================================================
    # Staleness Sweep Operations
    # =========================================================================

    def get_sweep_candidates(self, tier: str, limit: int = 500) -> list[dict[str, Any]]:
        """Get documents in a staleness tier, ordered by least-recently checked.

        Args:
            tier: Staleness tier (hot, warm, cool, cold)
            limit: Maximum number of candidates to return

        Returns:
            List of dicts with drive_file_id and modified_time
        """
        response = self.client.get(
            self._url("document_state"),
            params={
                "staleness_tier": f"eq.{tier}",
                "select": "drive_file_id,modified_time",
                "order": "last_checked_at.asc.nullsfirst",
                "limit": str(limit),
            },
        )
        self._check_response(response, "get_sweep_candidates")

        return response.json() or []

    def update_staleness_check(
        self,
        file_id: str,
        new_tier: str,
        check_count: int,
        last_activity_at: Optional[str] = None,
    ) -> None:
        """Update staleness tracking after checking a document.

        Args:
            file_id: Google Drive file ID
            new_tier: New staleness tier (hot, warm, cool, cold)
            check_count: Updated cumulative check count
            last_activity_at: ISO timestamp of last detected activity (optional)
        """
        data: dict[str, Any] = {
            "staleness_tier": new_tier,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
            "check_count": check_count,
        }
        if last_activity_at is not None:
            data["last_activity_at"] = last_activity_at

        response = self.client.patch(
            self._url("document_state"),
            params={"drive_file_id": f"eq.{file_id}"},
            json=data,
        )
        self._check_response(response, "update_staleness_check")

        logger.debug(
            "updated_staleness_check",
            file_id=file_id,
            new_tier=new_tier,
            check_count=check_count,
        )

    def get_staleness_stats(self) -> dict[str, Any]:
        """Get staleness tier distribution statistics.

        Returns:
            Dict with tiers (hot/warm/cool/cold counts), total, never_checked
        """
        tiers = {}
        total = 0
        tier_names = ["hot", "warm", "cool", "cold"]

        for tier in tier_names:
            response = self.client.get(
                self._url("document_state"),
                params={
                    "staleness_tier": f"eq.{tier}",
                    "select": "drive_file_id",
                    "limit": "0",
                },
                headers={
                    **self.client.headers,
                    "Prefer": "count=exact",
                },
            )
            self._check_response(response, f"get_staleness_stats_{tier}")

            content_range = response.headers.get("Content-Range", "")
            count = 0
            if "/" in content_range:
                try:
                    count = int(content_range.split("/")[1])
                except (ValueError, IndexError):
                    pass
            tiers[tier] = count
            total += count

        # Count documents never checked
        response = self.client.get(
            self._url("document_state"),
            params={
                "last_checked_at": "is.null",
                "select": "drive_file_id",
                "limit": "0",
            },
            headers={
                **self.client.headers,
                "Prefer": "count=exact",
            },
        )
        self._check_response(response, "get_staleness_stats_never_checked")

        never_checked = 0
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            try:
                never_checked = int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass

        return {
            "tiers": tiers,
            "total": total,
            "never_checked": never_checked,
        }

    def bulk_promote_tier(self, file_ids: list[str], tier: str) -> None:
        """Promote multiple documents to a staleness tier (e.g. after edits).

        Resets check_count to 0 and sets last_activity_at to now.
        Logs warnings for individual failures instead of raising.

        Args:
            file_ids: List of Google Drive file IDs to promote
            tier: Target staleness tier (typically "hot")
        """
        now = datetime.now(timezone.utc).isoformat()

        for file_id in file_ids:
            try:
                response = self.client.patch(
                    self._url("document_state"),
                    params={"drive_file_id": f"eq.{file_id}"},
                    json={
                        "staleness_tier": tier,
                        "last_activity_at": now,
                        "check_count": 0,
                    },
                )
                self._check_response(response, "bulk_promote_tier")
            except Exception as e:
                logger.warning(
                    "bulk_promote_tier_failed",
                    file_id=file_id,
                    tier=tier,
                    error=str(e),
                )

        logger.info(
            "bulk_promote_tier_complete",
            count=len(file_ids),
            tier=tier,
        )


# Module-level singleton
_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
