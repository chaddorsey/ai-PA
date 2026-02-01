"""HTTP client for PostgREST/pgvector operations.

This module handles all database operations:
- Document state tracking (coordination catalog)
- Chunk storage with embeddings
- Vector similarity search
- Folder cache for hierarchy traversal
- Revision tracking for edit attribution
"""

from datetime import datetime
from typing import Any, Optional

import httpx
import structlog

from drive_rag.models import ChunkRecord, DocumentState, FolderCache, DocumentRevision, SearchResult
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

        # Upsert in batches of 100
        for i in range(0, len(records), 100):
            batch = records[i : i + 100]
            response = self.client.post(
                self._url("document_chunks"),
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

        response = self.client.post(
            self._url("document_revisions"),
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


# Module-level singleton
_db: Optional[Database] = None


def get_db() -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db
