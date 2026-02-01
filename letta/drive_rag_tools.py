"""Custom Letta tools for Drive RAG document search.

These tools allow Letta agents to search and retrieve content from
indexed Google Drive documents via the drive-rag-service API.
"""

from typing import Dict, Any, Optional


def search_documents(
    query: str,
    limit: Optional[int] = None,
    file_ids: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search indexed Google Docs using semantic similarity.

    This tool searches through all indexed Google Drive documents
    and returns the most relevant text chunks based on semantic
    similarity to the query. Use this for questions about document
    content, finding specific information, or exploring topics
    across your document library.

    Args:
        query: Natural language search query describing what you're looking for.
               Be specific for better results.
        limit: Maximum number of results to return (default 10, max 50).
        file_ids: Optional comma-separated list of Google Drive file IDs
                  to search within. If not provided, searches all documents.

    Returns:
        Dictionary with search results including file titles,
        matching text snippets, similarity scores, and file IDs.
    """
    import os
    import traceback
    import requests

    try:
        # Default values
        if limit is None:
            limit = 10
        if limit > 50:
            limit = 50

        # Parse file_ids if provided
        file_id_list = None
        if file_ids:
            file_id_list = [fid.strip() for fid in file_ids.split(",") if fid.strip()]

        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # Build request payload
        payload = {
            "query": query,
            "limit": limit,
        }
        if file_id_list:
            payload["file_ids"] = file_id_list

        # Make request to drive-rag-service
        response = requests.post(
            f"{base_url}/v1/search",
            json=payload,
            timeout=30,
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Search failed with status {response.status_code}: {response.text}",
            }

        data = response.json()

        # Format results for readability
        results = []
        for r in data.get("results", []):
            results.append({
                "file_id": r.get("drive_file_id"),
                "title": r.get("title"),
                "text": r.get("chunk_text"),
                "section": " > ".join(r.get("outline_path", [])) if r.get("outline_path") else None,
                "similarity": round(r.get("similarity", 0), 4),
            })

        return {
            "status": "ok",
            "query": query,
            "result_count": len(results),
            "results": results,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }


def get_document_content(
    file_id: str,
    sections: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get full content or specific sections from an indexed Google Doc.

    Use this tool when you need to retrieve the complete text of a
    document or specific sections within it. The sections parameter
    can filter to specific headings/sections within the document.

    Args:
        file_id: Google Drive file ID of the document to retrieve.
        sections: Optional comma-separated list of section headings
                  to retrieve (e.g., "Summary,Conclusion"). If not
                  provided, returns all chunks from the document.

    Returns:
        Dictionary with document title, content chunks, and metadata.
    """
    import os
    import traceback
    import requests

    try:
        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # First get document status to verify it exists and get metadata
        status_response = requests.get(
            f"{base_url}/v1/status/{file_id}",
            timeout=30,
        )

        if status_response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to get document status: {status_response.text}",
            }

        status_data = status_response.json()

        if not status_data.get("indexed"):
            return {
                "status": "error",
                "error_message": f"Document {file_id} is not indexed",
            }

        # Parse sections filter
        section_filter = None
        if sections:
            section_filter = [s.strip().lower() for s in sections.split(",") if s.strip()]

        # Search for all chunks in this document
        search_payload = {
            "query": status_data.get("title", "document content"),
            "limit": 100,  # Get all chunks
            "file_ids": [file_id],
        }

        search_response = requests.post(
            f"{base_url}/v1/search",
            json=search_payload,
            timeout=30,
        )

        if search_response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to retrieve content: {search_response.text}",
            }

        search_data = search_response.json()
        results = search_data.get("results", [])

        # Filter by sections if specified
        if section_filter:
            filtered_results = []
            for r in results:
                outline = r.get("outline_path", [])
                outline_lower = [o.lower() for o in outline]
                # Check if any section matches
                if any(sf in " ".join(outline_lower) for sf in section_filter):
                    filtered_results.append(r)
            results = filtered_results

        # Build content output
        content_chunks = []
        for r in results:
            content_chunks.append({
                "section": " > ".join(r.get("outline_path", [])) if r.get("outline_path") else "Document",
                "text": r.get("chunk_text"),
            })

        return {
            "status": "ok",
            "file_id": file_id,
            "title": status_data.get("title"),
            "chunk_count": len(content_chunks),
            "content": content_chunks,
            "last_indexed": status_data.get("last_indexed_at"),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }


def list_indexed_documents(
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    List all indexed Google Docs with their status.

    Use this tool to see which documents are available for searching,
    check when documents were last indexed, or get an overview of
    the document library.

    Args:
        limit: Maximum number of documents to return (default 50).

    Returns:
        List of indexed documents with titles, IDs, chunk counts,
        and indexing dates.
    """
    import os
    import traceback
    import requests

    try:
        # Default values
        if limit is None:
            limit = 50

        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # Get documents list
        response = requests.get(
            f"{base_url}/v1/documents",
            params={"limit": limit},
            timeout=30,
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to list documents: {response.text}",
            }

        documents = response.json()

        # Format output
        doc_list = []
        for doc in documents:
            doc_list.append({
                "file_id": doc.get("drive_file_id"),
                "title": doc.get("title"),
                "chunk_count": doc.get("chunk_count"),
                "last_indexed": doc.get("last_indexed_at"),
                "owner": doc.get("owner_email"),
            })

        return {
            "status": "ok",
            "document_count": len(doc_list),
            "documents": doc_list,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }


def ingest_document(
    file_id: str,
    force: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Ingest a Google Doc into the RAG system.

    Use this tool to add a new document to the search index or
    re-index an existing document after it has been updated.
    The tool will skip documents that haven't changed unless
    force=True is specified.

    Args:
        file_id: Google Drive file ID of the document to ingest.
        force: Force re-indexing even if the document hasn't changed
               (default False).

    Returns:
        Dictionary with ingestion status, chunks added/updated/deleted,
        and any error messages.
    """
    import os
    import traceback
    import requests

    try:
        # Default values
        if force is None:
            force = False

        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # Make ingestion request
        response = requests.post(
            f"{base_url}/v1/ingest/{file_id}",
            params={"force": force},
            timeout=120,  # Longer timeout for ingestion
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Ingestion failed: {response.text}",
            }

        data = response.json()

        return {
            "status": data.get("status"),
            "file_id": data.get("drive_file_id"),
            "revision_id": data.get("revision_id"),
            "chunks_added": data.get("chunks_added", 0),
            "chunks_updated": data.get("chunks_updated", 0),
            "chunks_deleted": data.get("chunks_deleted", 0),
            "reason": data.get("reason"),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }


def get_index_stats() -> Dict[str, Any]:
    """
    Get statistics about the document index.

    Use this tool to check the overall status of the RAG system,
    including how many documents and chunks are indexed.

    Returns:
        Dictionary with total documents, total chunks, and average
        chunks per document.
    """
    import os
    import traceback
    import requests

    try:
        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # Get stats
        response = requests.get(
            f"{base_url}/v1/stats",
            timeout=30,
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to get stats: {response.text}",
            }

        data = response.json()

        return {
            "status": "ok",
            "total_documents": data.get("total_documents", 0),
            "total_chunks": data.get("total_chunks", 0),
            "avg_chunks_per_document": round(data.get("avg_chunks_per_document", 0), 1),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
