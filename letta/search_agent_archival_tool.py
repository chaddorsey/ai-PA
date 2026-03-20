from typing import Dict, Any, Optional


def search_agent_archival(target_agent_id: str, query: str, search_mode: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Search another agent's archival memory. Returns passages matching the query.

    Use this to access knowledge stored in other agents' archives. Key archives:
      - docs-and-transcripts agent (agent-398b4f6c-6afa-493f-8063-897c6b171a0d): Meeting notes and transcripts. Passages tagged with date:YYYY-MM, participant:name, type:1on1/small-group/team, id:meeting-uuid.
      - tasks agent (agent-dd15479e-6543-400e-8463-b2a48b13cd4a): Extracted task source references.
      - pulse agent (agent-2ed14ef4-6289-453a-ae27-290b6ed196b8): Slack monitoring observations.

    Args:
        target_agent_id: The agent whose archival memory to search. Use the full agent ID.
        query: Search query. Use "schema" to get the archive's self-description with tag vocabulary, passage format, and example queries. For semantic mode use natural language like "budget discussion". For text mode use exact substrings or tag patterns like "date:2025-04" or "id:f2d5b455" or "participant:leslie".
        search_mode: How to search. "semantic" for meaning match. "text" for exact substring (good for dates, IDs, names, tags). "auto" tries semantic first then text fallback. Default "auto".
        limit: Max results to return. Default 10, max 100.

    Returns:
        Dictionary with matching passages including text, tags, and metadata.
    """
    import json
    import os
    import traceback
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")

        if not target_agent_id or not query:
            return {"status": "error", "error_message": "target_agent_id and query are required"}

        mode = (search_mode or "auto").lower()
        if mode not in ("semantic", "text", "auto"):
            return {"status": "error", "error_message": "search_mode must be semantic, text, or auto"}

        search_limit = min(limit or 10, 100)
        base_url = f"{LETTA_BASE}/v1/agents/{target_agent_id}/archival-memory"

        # Schema query — return the archive's self-description
        if query.strip().lower() == "schema":
            mode = "text"
            query = "ARCHIVE SCHEMA:"
            search_limit = 1

        quoted = urllib.request.quote(query)

        # Build URL based on mode
        if mode == "text":
            urls_to_try = [f"{base_url}?search={quoted}&limit={search_limit}"]
        elif mode == "semantic":
            urls_to_try = [f"{base_url}?query={quoted}&limit={search_limit}"]
        else:
            urls_to_try = [
                f"{base_url}?query={quoted}&limit={search_limit}",
                f"{base_url}?search={quoted}&limit={search_limit}",
            ]

        passages = []
        used_mode = mode

        for url_idx, fetch_url in enumerate(urls_to_try):
            for attempt in range(3):
                req = urllib.request.Request(fetch_url, method="GET")
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    break
                except urllib.error.HTTPError as he:
                    if he.code in (301, 302, 307, 308):
                        fetch_url = he.headers.get("Location", "")
                        continue
                    raise
            else:
                data = []

            if isinstance(data, list):
                for p in data:
                    passages.append({
                        "text": p.get("text", "")[:2000],
                        "tags": p.get("tags", []),
                        "archive_id": p.get("archive_id", ""),
                        "id": p.get("id", ""),
                    })

            if passages:
                used_mode = "semantic" if url_idx == 0 and mode == "auto" else mode
                break
            elif mode == "auto" and url_idx == 0:
                used_mode = "text_fallback"

        return {
            "status": "ok",
            "count": len(passages),
            "search_mode": used_mode,
            "target_agent_id": target_agent_id,
            "query": query,
            "passages": passages,
        }

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
