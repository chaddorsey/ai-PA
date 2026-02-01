"""Entity extraction and knowledge graph integration for Drive RAG.

This module handles:
- Extracting entities from document content using Graphiti
- Creating knowledge graph relationships between entities
- Querying documents by entity relationships
"""

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Graphiti MCP server endpoint
GRAPHITI_BASE_URL = os.environ.get("GRAPHITI_BASE_URL", "http://graphiti-mcp-server:8000")

# Group ID for Drive RAG documents in Graphiti
DRIVE_RAG_GROUP_ID = os.environ.get("DRIVE_RAG_GROUP_ID", "drive-rag-documents")

# UUID namespace for Drive RAG episodes (generated once, fixed)
DRIVE_RAG_UUID_NAMESPACE = uuid.UUID("9c8b5f3a-7d4e-4a2c-b1e9-6f8d0c3a5b7e")


class GraphitiClient:
    """Client for interacting with Graphiti knowledge graph."""

    def __init__(self, base_url: str = GRAPHITI_BASE_URL):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def add_episode(
        self,
        name: str,
        content: str,
        source_description: str,
        group_id: str = DRIVE_RAG_GROUP_ID,
        source_type: str = "text",
        uuid: Optional[str] = None,
    ) -> dict:
        """Add an episode to Graphiti for entity extraction.

        Args:
            name: Name/title of the episode (e.g., document title)
            content: Text content to extract entities from
            source_description: Description of the source (e.g., "Google Doc: Title")
            group_id: Graph partition ID (default: drive-rag-documents)
            source_type: Type of content: 'text', 'json', or 'message'
            uuid: Optional unique identifier for the episode

        Returns:
            Response from Graphiti API
        """
        client = await self._get_client()

        # Call the MCP tool endpoint
        payload = {
            "method": "tools/call",
            "params": {
                "name": "add_memory",
                "arguments": {
                    "name": name,
                    "episode_body": content,
                    "group_id": group_id,
                    "source": source_type,
                    "source_description": source_description,
                }
            }
        }

        if uuid:
            payload["params"]["arguments"]["uuid"] = uuid

        try:
            response = await client.post(
                f"{self.base_url}/mcp",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                "graphiti_episode_added",
                name=name,
                group_id=group_id,
                result=result,
            )
            return result
        except httpx.HTTPError as e:
            logger.error(
                "graphiti_add_episode_failed",
                name=name,
                error=str(e),
            )
            raise

    async def search_nodes(
        self,
        query: str,
        group_ids: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> dict:
        """Search for entities/nodes in the knowledge graph.

        Args:
            query: Natural language search query
            group_ids: Optional list of group IDs to filter by
            max_results: Maximum number of results to return

        Returns:
            Search results from Graphiti
        """
        client = await self._get_client()

        if group_ids is None:
            group_ids = [DRIVE_RAG_GROUP_ID]

        payload = {
            "method": "tools/call",
            "params": {
                "name": "search_memory_nodes",
                "arguments": {
                    "query": query,
                    "group_ids": group_ids,
                    "max_nodes": max_results,
                }
            }
        }

        try:
            response = await client.post(
                f"{self.base_url}/mcp",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(
                "graphiti_search_nodes_failed",
                query=query,
                error=str(e),
            )
            raise

    async def search_facts(
        self,
        query: str,
        group_ids: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> dict:
        """Search for facts/relationships in the knowledge graph.

        Args:
            query: Natural language search query
            group_ids: Optional list of group IDs to filter by
            max_results: Maximum number of results to return

        Returns:
            Search results from Graphiti
        """
        client = await self._get_client()

        if group_ids is None:
            group_ids = [DRIVE_RAG_GROUP_ID]

        payload = {
            "method": "tools/call",
            "params": {
                "name": "search_memory_facts",
                "arguments": {
                    "query": query,
                    "group_ids": group_ids,
                    "max_facts": max_results,
                }
            }
        }

        try:
            response = await client.post(
                f"{self.base_url}/mcp",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(
                "graphiti_search_facts_failed",
                query=query,
                error=str(e),
            )
            raise

    async def get_status(self) -> dict:
        """Get Graphiti service status."""
        client = await self._get_client()

        try:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error("graphiti_status_check_failed", error=str(e))
            return {"status": "error", "error": str(e)}


# Singleton client instance
_graphiti_client: Optional[GraphitiClient] = None


def get_graphiti_client() -> GraphitiClient:
    """Get the singleton Graphiti client."""
    global _graphiti_client
    if _graphiti_client is None:
        _graphiti_client = GraphitiClient()
    return _graphiti_client


async def extract_entities_from_document(
    file_id: str,
    title: str,
    content: str,
    mime_type: str = "application/vnd.google-apps.document",
    owner_email: Optional[str] = None,
    modified_time: Optional[datetime] = None,
) -> dict:
    """Extract entities from a document and add to knowledge graph.

    This creates a Graphiti episode from the document content, which
    triggers entity extraction and relationship building.

    Args:
        file_id: Google Drive file ID
        title: Document title
        content: Full text content of the document
        mime_type: MIME type of the document
        owner_email: Optional owner email
        modified_time: Optional modification time

    Returns:
        Result of the entity extraction
    """
    client = get_graphiti_client()

    # Generate a stable, valid UUID based on file_id and content hash
    # Using uuid5 ensures the same file+content always generates the same UUID
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    uuid_input = f"{file_id}-{content_hash}"
    episode_uuid = str(uuid.uuid5(DRIVE_RAG_UUID_NAMESPACE, uuid_input))

    # Build source description
    source_parts = [f"Google Drive document: {title}"]
    if owner_email:
        source_parts.append(f"Owner: {owner_email}")
    if modified_time:
        source_parts.append(f"Modified: {modified_time.isoformat()}")
    source_description = " | ".join(source_parts)

    # Add metadata prefix to content for better entity extraction
    metadata_lines = [
        f"Document Title: {title}",
        f"Document ID: {file_id}",
        f"Document Type: {mime_type}",
    ]
    if owner_email:
        metadata_lines.append(f"Owner: {owner_email}")

    enriched_content = "\n".join(metadata_lines) + "\n\n---\n\n" + content

    try:
        # Note: We don't pass a custom UUID because Graphiti expects any provided
        # UUID to reference an existing episode (for updates). Instead, we let
        # Graphiti generate its own UUID and track the file_id via source_description.
        result = await client.add_episode(
            name=title,
            content=enriched_content,
            source_description=source_description,
            group_id=DRIVE_RAG_GROUP_ID,
            source_type="text",
            # uuid parameter intentionally omitted - let Graphiti generate one
        )

        logger.info(
            "document_entities_extracted",
            file_id=file_id,
            title=title,
            # Note: episode_uuid is our reference ID, not the actual Graphiti UUID
            reference_id=episode_uuid,
        )

        return {
            "status": "ok",
            "file_id": file_id,
            "reference_id": episode_uuid,  # For our tracking, not Graphiti's UUID
            "result": result,
        }

    except Exception as e:
        logger.error(
            "document_entity_extraction_failed",
            file_id=file_id,
            error=str(e),
        )
        return {
            "status": "error",
            "file_id": file_id,
            "error": str(e),
        }


async def find_documents_by_entity(
    entity_query: str,
    max_results: int = 20,
) -> dict:
    """Find documents that mention a specific entity.

    Args:
        entity_query: Entity name or description to search for
        max_results: Maximum number of results

    Returns:
        Documents related to the entity
    """
    client = get_graphiti_client()

    try:
        # Search for nodes (entities) matching the query
        node_results = await client.search_nodes(
            query=entity_query,
            max_results=max_results,
        )

        # Search for facts (relationships) involving the entity
        fact_results = await client.search_facts(
            query=entity_query,
            max_results=max_results,
        )

        return {
            "status": "ok",
            "query": entity_query,
            "entities": node_results,
            "relationships": fact_results,
        }

    except Exception as e:
        logger.error(
            "find_documents_by_entity_failed",
            query=entity_query,
            error=str(e),
        )
        return {
            "status": "error",
            "query": entity_query,
            "error": str(e),
        }


async def get_document_entities(
    file_id: str,
) -> dict:
    """Get all entities extracted from a specific document.

    Args:
        file_id: Google Drive file ID

    Returns:
        Entities and relationships from the document
    """
    client = get_graphiti_client()

    # Search for the document by file ID
    query = f"document {file_id}"

    try:
        node_results = await client.search_nodes(
            query=query,
            max_results=50,
        )

        fact_results = await client.search_facts(
            query=query,
            max_results=50,
        )

        return {
            "status": "ok",
            "file_id": file_id,
            "entities": node_results,
            "relationships": fact_results,
        }

    except Exception as e:
        logger.error(
            "get_document_entities_failed",
            file_id=file_id,
            error=str(e),
        )
        return {
            "status": "error",
            "file_id": file_id,
            "error": str(e),
        }
