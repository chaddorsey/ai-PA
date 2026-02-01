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


def get_document_edits(
    file_id: str,
    since: Optional[str] = None,
    by_user: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get the edit history for a Google Doc.

    Use this tool to see who has edited a document and when. This is useful
    for understanding document collaboration, tracking changes, and seeing
    edit patterns over time.

    Args:
        file_id: Google Drive file ID of the document to check.
        since: Optional time filter. Use ISO date format (e.g., "2026-01-15") or
               relative values like "yesterday", "last-week", or "last-month".
               If not provided, returns all available edit history.
        by_user: Optional filter by user email. Returns only edits by users
                 whose email contains this string (case-insensitive).

    Returns:
        Dictionary with edit history including editor names, timestamps,
        and total edit count.
    """
    import os
    import traceback
    import requests

    try:
        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # Build query parameters
        params = {}
        if since:
            params["since"] = since
        if by_user:
            params["by_user"] = by_user

        # Make request
        response = requests.get(
            f"{base_url}/v1/edits/{file_id}",
            params=params,
            timeout=30,
        )

        if response.status_code == 404:
            return {
                "status": "error",
                "error_message": f"Document {file_id} not found or has no edit history",
            }

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to get edits: {response.text}",
            }

        data = response.json()

        # Format edits for readability
        edits = []
        for edit in data.get("edits", []):
            edit_entry = {
                "revision_id": edit.get("revision_id"),
                "editor": edit.get("modifier_name") or edit.get("modifier_email") or "Unknown",
                "email": edit.get("modifier_email"),
                "time": edit.get("modified_time"),
            }
            edits.append(edit_entry)

        return {
            "status": "ok",
            "file_id": file_id,
            "title": data.get("title"),
            "edit_count": data.get("edit_count", 0),
            "editors": data.get("editors", []),
            "edits": edits,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }


def fetch_document_from_drive(
    file_id_or_url: str,
) -> Dict[str, Any]:
    """
    Fetch the current content of a document directly from Google Drive.

    Unlike search_documents or get_document_content which return indexed/chunked
    content, this tool fetches the live, current version of a document directly
    from Google Drive. Use this when you need the complete, up-to-date content
    of a specific document.

    Args:
        file_id_or_url: Google Drive file ID or full URL to the document.
                        Accepts URLs like:
                        - https://docs.google.com/document/d/FILE_ID/edit
                        - https://drive.google.com/file/d/FILE_ID/view
                        - Or just the file ID directly

    Returns:
        Dictionary with document title, full content, and metadata.
        For Google Docs, Sheets, and Slides, returns the text content.
    """
    import os
    import traceback
    import requests

    try:
        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # URL encode the file_id_or_url for the path
        import urllib.parse
        encoded_path = urllib.parse.quote(file_id_or_url, safe="")

        # Make request
        response = requests.get(
            f"{base_url}/v1/fetch/{encoded_path}",
            timeout=60,
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to fetch document: {response.text}",
            }

        data = response.json()

        if data.get("status") == "error":
            return {
                "status": "error",
                "error_message": data.get("error", "Unknown error"),
            }

        # Format response
        content = data.get("content", "")
        if content and len(content) > 50000:
            # Truncate very long content with a note
            content = content[:50000] + "\n\n[Content truncated - document is very long]"

        return {
            "status": "ok",
            "file_id": data.get("file_id"),
            "title": data.get("title"),
            "mime_type": data.get("mime_type"),
            "content": content,
            "content_length": data.get("content_length", 0),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }


def get_document_changes(
    file_id: str,
    from_revision: Optional[str] = None,
    to_revision: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get a summary of changes between two versions of a document.

    Use this tool to see what content was added, deleted, or modified
    between document versions. This is useful for reviewing edits,
    understanding what changed, and tracking content evolution.

    Args:
        file_id: Google Drive file ID of the document to compare.
        from_revision: Optional base revision ID to compare from. If not
                       provided, uses the oldest available snapshot.
        to_revision: Optional target revision ID to compare to. If not
                     provided, uses the latest available snapshot.

    Returns:
        Dictionary with change summary including blocks added, deleted,
        modified, and detailed change descriptions.
    """
    import os
    import traceback
    import requests

    try:
        # Get service URL from environment or use default
        base_url = os.environ.get("DRIVE_RAG_SERVICE_URL", "http://drive-rag-service:8000")

        # Build query parameters
        params = {}
        if from_revision:
            params["from_revision"] = from_revision
        if to_revision:
            params["to_revision"] = to_revision

        # Make request
        response = requests.get(
            f"{base_url}/v1/diff/{file_id}",
            params=params,
            timeout=60,
        )

        if response.status_code == 404:
            return {
                "status": "error",
                "error_message": f"Document {file_id} not found or has no snapshots for comparison",
            }

        if response.status_code != 200:
            return {
                "status": "error",
                "error_message": f"Failed to get diff: {response.text}",
            }

        data = response.json()

        # Format changes for readability
        changes = []
        for change in data.get("changes", []):
            change_entry = {
                "type": change.get("change_type"),
                "block_type": change.get("block_type"),
                "section": change.get("section"),
                "preview": change.get("text_preview"),
            }
            changes.append(change_entry)

        return {
            "status": "ok",
            "file_id": file_id,
            "from_revision": data.get("from_revision"),
            "to_revision": data.get("to_revision"),
            "summary": {
                "blocks_added": data.get("blocks_added", 0),
                "blocks_deleted": data.get("blocks_deleted", 0),
                "blocks_modified": data.get("blocks_modified", 0),
                "blocks_moved": data.get("blocks_moved", 0),
            },
            "change_summary": data.get("summary"),
            "changes": changes,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
