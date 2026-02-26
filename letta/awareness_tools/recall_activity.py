"""
Recall cross-interface activity from archival memory.

This tool enables the main agent to search its own archival memory for
summaries of interactions that happened across different interfaces
(Slack DMs, pa-web sub-agents).

Architecture Note (2026-02):
- Archival passages are written by:
  - pa-routing-handler (Pattern 3): pa-web sub-agent interactions
  - slackbot: Slack DM interactions
- All passages are tagged with 'memory:session' and 'session:YYYY-MM-DD'
- Text substring search (?search=) is reliable; semantic search (?query=) is not
"""

from typing import Dict, Any, Optional


def recall_activity(
    query: str,
    days_back: int = 1,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search archival memory for cross-interface activity summaries.

    Use this tool to recall what happened in recent conversations across
    Slack DMs and pa-web. Passages are written automatically after each
    interaction and tagged by date, source, and agent.

    Args:
        query: Search term to find in activity passages. Use specific keywords
               like a person's name, topic, or action. Use 'memory:session' to
               get all session passages, or a date like '2026-02-25' for a
               specific day.
        days_back: Number of days to search back (default 1 = today only).
                   Maximum 30. Used to filter by session:YYYY-MM-DD tags.
        source: Filter by source interface. Options: 'slack', 'pa-web', or
                None for all sources.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - passages: List of activity summaries found
        - count: Number of passages returned
        - search_params: The search parameters used (for debugging)
        - error_message: Error message if status is "error"
    """
    import os
    import traceback
    import urllib.request
    import urllib.parse
    import json
    from datetime import datetime, timedelta, timezone

    try:
        if days_back is None:
            days_back = 1
        if days_back < 1:
            days_back = 1
        if days_back > 30:
            days_back = 30

        letta_base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
        # Always search the MAIN agent's archival memory, regardless of
        # which agent is calling this tool. LETTA_AGENT_ID is set by
        # the sandbox to the calling agent's ID, so we cannot use it here.
        MAIN_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"
        agent_id = MAIN_AGENT_ID

        # Session passages have known text prefixes. When the query is a
        # tag-like value (memory:session, source:slack, etc.) search for
        # text patterns that actually appear in passage content instead,
        # because Letta's ?search= only matches passage text, not tags.
        text_search_terms = []
        tag_query = query.lower().strip()
        if tag_query in ("memory:session", "session", "cross-interface", "activity"):
            # Session passages start with "[Slack DM]" or "User asked"
            text_search_terms = ["[Slack DM]", "User asked"]
        elif tag_query.startswith("source:"):
            src = tag_query.split(":", 1)[1]
            if src == "slack":
                text_search_terms = ["[Slack DM]"]
            elif src == "pa-web":
                text_search_terms = ["User asked"]
            else:
                text_search_terms = [query]
        else:
            text_search_terms = [query]

        # Search for each text pattern and merge results (dedup by id)
        all_passages = []
        seen_ids = set()
        for term in text_search_terms:
            encoded = urllib.parse.quote(term, safe="")
            url = (
                f"{letta_base_url}/v1/agents/{agent_id}"
                f"/archival-memory?search={encoded}&limit=50"
            )
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                results = json.loads(resp.read().decode("utf-8"))
            if not isinstance(results, list):
                results = results.get(
                    "passages", results.get("results", [])
                )
            for p in results:
                pid = p.get("id", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_passages.append(p)

        # Build valid date set for filtering
        now_utc = datetime.now(timezone.utc)
        valid_dates = set()
        for i in range(days_back):
            day = now_utc - timedelta(days=i)
            valid_dates.add(day.strftime("%Y-%m-%d"))

        filtered = []
        for passage in all_passages:
            tags = passage.get("tags", []) or []

            # Must have memory:session tag
            if "memory:session" not in tags:
                continue

            # Check date range via session:YYYY-MM-DD tag
            passage_date = None
            for tag in tags:
                if tag.startswith("session:"):
                    passage_date = tag.split(":", 1)[1]
                    break

            if passage_date and passage_date not in valid_dates:
                continue

            # Filter by source if specified
            if source:
                source_tag = f"source:{source}"
                if source_tag not in tags:
                    continue

            text = passage.get("text", passage.get("content", ""))
            filtered.append({
                "text": text,
                "tags": tags,
                "date": passage_date or "",
                "id": passage.get("id", ""),
            })

        return {
            "status": "ok",
            "passages": filtered,
            "count": len(filtered),
            "search_params": {
                "query": query,
                "days_back": days_back,
                "source": source,
                "dates_checked": sorted(valid_dates),
            },
            "error_message": "",
        }

    except Exception as e:
        return {
            "status": "error",
            "passages": [],
            "count": 0,
            "search_params": {
                "query": query if query else "",
                "days_back": days_back if days_back else 1,
                "source": source,
            },
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
