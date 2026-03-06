"""
Smart Meeting Search Tool for Letta

This tool provides intelligent meeting search with:
- Relative date parsing ("last week", "yesterday", "this month")
- Project/context mapping (e.g., "DST meeting" → participant tags)
- Multi-filter combinations (participants + date + type)
- Semantic search with structured filtering

Designed to work with meetings imported to archival memory via granola_mcp_to_archival.py
"""

from typing import Dict, Any, Optional


# Project/context mappings - maps shorthand to participant tags
# Update this based on your common meeting patterns
PROJECT_CONTEXT_MAP = {
    # Projects
    "dst": ["participant:leslie", "participant:william", "participant:kirk"],
    "codap": ["participant:william", "participant:leslie", "participant:kirk"],
    "grapher": ["participant:leslie", "participant:andeerubin"],
    "itsi": ["participant:amy", "participant:leslie"],

    # Teams
    "leadership": ["internal", "type:team"],
    "research": ["org:concord.org", "type:small-group"],
    "external-partners": ["external"],
}


def search_meetings_smart(
    query: Optional[str] = None,
    participants: Optional[str] = None,
    date_range: Optional[str] = None,
    project: Optional[str] = None,
    meeting_type: Optional[str] = None,
    scope: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search meeting transcripts with intelligent filtering and natural language date parsing.

    This tool translates natural queries into structured archival memory searches.
    Use it to find meetings by combining semantic queries with filters.

    Args:
        query: Natural language description of what you're looking for
               (e.g., "budget discussions", "next steps from planning session")
        participants: Comma-separated list of participant first names
                     (e.g., "leslie,william,amy")
        date_range: Relative or absolute date range. Supports:
                   - Relative: "today", "yesterday", "last-week", "this-week",
                     "last-month", "this-month", "last-7-days", "last-30-days"
                   - Absolute: "2025-05" (month), "2025-05-15" (day)
        project: Project or context shorthand that maps to known participants/orgs.
                Supported: "dst", "codap", "grapher", "itsi", "leadership",
                "research", "external-partners"
        meeting_type: Type of meeting. Options: "1on1", "small-group", "team"
        scope: Meeting scope. Options: "internal", "external"
        limit: Maximum number of results (default 10, max 50)

    Returns:
        Dictionary with status, results, and search metadata.
        Example: {
            "status": "ok",
            "count": 5,
            "query_used": "budget planning discussions",
            "tags_used": ["participant:leslie", "date:2025-05"],
            "results": [
                {"title": "CODAP Budget Review", "date": "2025-05-15",
                 "participants": ["Leslie", "William"], "snippet": "..."}
            ]
        }
    """
    # IMPORTS INSIDE FUNCTION (required for Letta tools)
    import os
    import json
    import traceback
    from datetime import datetime, timedelta
    import re

    try:
        # Validate and cap limit
        if limit is None:
            limit = 10
        limit = min(max(1, limit), 50)

        # Build tags list
        tags = []

        # Parse date_range to tags
        start_datetime = None
        end_datetime = None

        if date_range:
            date_range = date_range.lower().strip()
            now = datetime.now()

            if date_range == "today":
                start_datetime = now.strftime("%Y-%m-%d")
                end_datetime = now.strftime("%Y-%m-%d")
            elif date_range == "yesterday":
                yesterday = now - timedelta(days=1)
                start_datetime = yesterday.strftime("%Y-%m-%d")
                end_datetime = yesterday.strftime("%Y-%m-%d")
            elif date_range in ["last-week", "last week"]:
                start = now - timedelta(days=7)
                tags.append(f"date:{start.strftime('%Y-%m')}")
            elif date_range in ["this-week", "this week"]:
                start = now - timedelta(days=now.weekday())
                start_datetime = start.strftime("%Y-%m-%d")
                end_datetime = now.strftime("%Y-%m-%d")
            elif date_range in ["last-month", "last month"]:
                first_of_month = now.replace(day=1)
                last_month = first_of_month - timedelta(days=1)
                tags.append(f"date:{last_month.strftime('%Y-%m')}")
            elif date_range in ["this-month", "this month"]:
                tags.append(f"date:{now.strftime('%Y-%m')}")
            elif date_range.startswith("last-") and date_range.endswith("-days"):
                days_match = re.match(r"last-(\d+)-days", date_range)
                if days_match:
                    days = int(days_match.group(1))
                    start = now - timedelta(days=days)
                    start_datetime = start.strftime("%Y-%m-%d")
                    end_datetime = now.strftime("%Y-%m-%d")
            elif re.match(r"^\d{4}-\d{2}$", date_range):
                # Absolute month: 2025-05
                tags.append(f"date:{date_range}")
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", date_range):
                # Absolute day: 2025-05-15
                start_datetime = date_range
                end_datetime = date_range

        # Parse participants
        if participants:
            for p in participants.split(","):
                p = p.strip().lower()
                if p:
                    tags.append(f"participant:{p}")

        # Map project to tags
        if project:
            project_key = project.lower().strip()
            if project_key in PROJECT_CONTEXT_MAP:
                tags.extend(PROJECT_CONTEXT_MAP[project_key])
            else:
                # Treat as a search term if not a known project
                query = f"{project} {query or ''}".strip()

        # Add meeting type
        if meeting_type:
            mt = meeting_type.lower().strip()
            if mt in ["1on1", "1-on-1", "one-on-one"]:
                tags.append("type:1on1")
            elif mt in ["small-group", "small group", "smallgroup"]:
                tags.append("type:small-group")
            elif mt in ["team", "group"]:
                tags.append("type:team")

        # Add scope
        if scope:
            s = scope.lower().strip()
            if s in ["internal", "external"]:
                tags.append(s)

        # Remove duplicates
        tags = list(set(tags))

        # Construct search query for archival memory
        letta_base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        agent_id = os.environ.get("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")

        # Build API request
        import requests

        # Construct query params - scan ALL passages to find unique meetings
        # We need to scan all passages because each meeting has multiple chunks,
        # the API doesn't support tag filtering, and recent meetings may be at the end
        scan_limit = 2000  # Scan all passages (typically 1500-2000)
        params = {"limit": scan_limit}

        if query:
            params["text"] = query

        # Make request to archival memory API
        url = f"{letta_base_url}/v1/agents/{agent_id}/archival-memory"

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        passages = response.json()

        # Filter by tags locally (API might not support all tag combinations)
        filtered_results = []
        for passage in passages:
            passage_tags = set(passage.get("tags", []))

            # Check if all required tags are present
            if tags:
                # Use "any" match by default for flexibility
                if not any(t in passage_tags for t in tags):
                    continue

            # Extract meeting info from passage text
            text = passage.get("text", "")

            # Check date range against the actual meeting date (from passage text),
            # NOT created_at (which is the archival ingestion timestamp)
            if start_datetime or end_datetime:
                date_check = re.search(r"\*\*Date:\*\* (\d{4}-\d{2}-\d{2})", text)
                passage_date = date_check.group(1) if date_check else ""
                if not passage_date:
                    continue
                if start_datetime and passage_date < start_datetime:
                    continue
                if end_datetime and passage_date > end_datetime:
                    continue

            # Parse title
            title_match = re.search(r"## Meeting: (.+?)(\n|$)", text)
            title = title_match.group(1) if title_match else "Untitled"

            # Parse date
            date_match = re.search(r"\*\*Date:\*\* (\d{4}-\d{2}-\d{2})", text)
            meeting_date = date_match.group(1) if date_match else ""

            # Parse participants
            participants_match = re.search(r"\*\*Participants:\*\* (.+?)(\n|$)", text)
            participant_list = participants_match.group(1).split(", ") if participants_match else []

            # Extract snippet (first 200 chars of transcript or summary)
            snippet = ""
            if "### Summary" in text:
                summary_start = text.find("### Summary")
                summary_end = text.find("### Transcript", summary_start)
                if summary_end == -1:
                    summary_end = len(text)
                snippet = text[summary_start + 12:summary_start + 212].strip()
            elif "### Transcript" in text:
                transcript_start = text.find("### Transcript")
                snippet = text[transcript_start + 15:transcript_start + 215].strip()

            # Get meeting ID from tags
            meeting_id = ""
            for t in passage.get("tags", []):
                if t.startswith("id:"):
                    meeting_id = t[3:]
                    break

            # Skip if no meeting ID (shouldn't happen but be safe)
            if not meeting_id:
                continue

            # Check if we already have this meeting - prefer summary chunks
            is_summary = "chunk:summary" in passage_tags

            # If we don't have this meeting yet, or this is a summary (better), add/replace it
            existing_idx = next((i for i, r in enumerate(filtered_results) if r["meeting_id"] == meeting_id), None)

            meeting_entry = {
                "title": title,
                "date": meeting_date,
                "participants": participant_list,
                "meeting_id": meeting_id,
                "snippet": snippet[:200] + "..." if len(snippet) > 200 else snippet,
                "is_summary": is_summary,
                "tags": list(passage_tags)[:10]  # Limit tags in response
            }

            if existing_idx is None:
                filtered_results.append(meeting_entry)
            elif is_summary and not filtered_results[existing_idx].get("is_summary"):
                # Replace with summary version (has better metadata)
                filtered_results[existing_idx] = meeting_entry

        # Sort by date descending
        filtered_results.sort(key=lambda x: x.get("date", ""), reverse=True)

        # Remove is_summary flag from output and limit results
        for r in filtered_results:
            r.pop("is_summary", None)
        filtered_results = filtered_results[:limit]

        return {
            "status": "ok",
            "count": len(filtered_results),
            "total_scanned": len(passages),
            "query_used": query,
            "tags_used": tags,
            "date_filter": {
                "start": start_datetime,
                "end": end_datetime
            } if start_datetime or end_datetime else None,
            "results": filtered_results
        }

    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error_message": f"API request failed: {str(e)}",
            "results": []
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Search failed: {str(e)}\n{traceback.format_exc()}",
            "results": []
        }


def get_meeting_details(
    meeting_id: str
) -> Dict[str, Any]:
    """
    Get full details for a specific meeting by its ID.

    Use this after search_meetings_smart to retrieve the complete transcript
    and notes for a specific meeting.

    Args:
        meeting_id: The Granola meeting UUID (e.g., "f2d5b455-8f1b-4c4b-843b-8ec4958fec7b")

    Returns:
        Dictionary with full meeting content including transcript and notes.
    """
    import os
    import requests
    import traceback

    try:
        letta_base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        agent_id = os.environ.get("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")

        # Search for passages with this meeting ID
        # Use high limit to scan all passages (meetings may be stored at any position)
        url = f"{letta_base_url}/v1/agents/{agent_id}/archival-memory"
        response = requests.get(url, params={"limit": 2000}, timeout=30)
        response.raise_for_status()

        passages = response.json()

        # Find all passages for this meeting
        meeting_passages = []
        for passage in passages:
            passage_tags = passage.get("tags", [])
            if f"id:{meeting_id}" in passage_tags:
                meeting_passages.append(passage)

        if not meeting_passages:
            return {
                "status": "not_found",
                "error_message": f"No meeting found with ID: {meeting_id}",
                "meeting_id": meeting_id
            }

        # Combine passage texts (may be chunked)
        # Sort by chunk tag if present
        meeting_passages.sort(key=lambda x: (
            "chunk:summary" not in x.get("tags", []),
            next((t for t in x.get("tags", []) if t.startswith("chunk:transcript-")), "zzz")
        ))

        full_text = "\n\n---\n\n".join(p.get("text", "") for p in meeting_passages)

        # Extract metadata from first (summary) chunk
        first_text = meeting_passages[0].get("text", "")
        import re

        title_match = re.search(r"## Meeting: (.+?)(\n|$)", first_text)
        title = title_match.group(1) if title_match else "Untitled"

        date_match = re.search(r"\*\*Date:\*\* (.+?)(\n|$)", first_text)
        meeting_date = date_match.group(1) if date_match else ""

        participants_match = re.search(r"\*\*Participants:\*\* (.+?)(\n|$)", first_text)
        participants = participants_match.group(1).split(", ") if participants_match else []

        return {
            "status": "ok",
            "meeting_id": meeting_id,
            "title": title,
            "date": meeting_date,
            "participants": participants,
            "chunk_count": len(meeting_passages),
            "full_text": full_text,
            "tags": list(set(t for p in meeting_passages for t in p.get("tags", [])))
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Failed to get meeting details: {str(e)}\n{traceback.format_exc()}",
            "meeting_id": meeting_id
        }


def list_participants() -> Dict[str, Any]:
    """
    List all known participants from meeting transcripts.

    Use this to discover available participant names for filtering.
    Returns a list of participant tags sorted by frequency.

    Args:
        None

    Returns:
        Dictionary with list of participants and their meeting counts.
    """
    import os
    import requests
    import traceback
    from collections import Counter

    try:
        letta_base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        agent_id = os.environ.get("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")

        url = f"{letta_base_url}/v1/agents/{agent_id}/archival-memory"
        response = requests.get(url, params={"limit": 500}, timeout=30)
        response.raise_for_status()

        passages = response.json()

        participant_counts = Counter()
        org_counts = Counter()
        date_counts = Counter()

        for passage in passages:
            for tag in passage.get("tags", []):
                if tag.startswith("participant:"):
                    participant_counts[tag] += 1
                elif tag.startswith("org:"):
                    org_counts[tag] += 1
                elif tag.startswith("date:"):
                    date_counts[tag] += 1

        return {
            "status": "ok",
            "participants": [
                {"name": p.replace("participant:", ""), "count": c}
                for p, c in participant_counts.most_common(50)
            ],
            "organizations": [
                {"name": o.replace("org:", ""), "count": c}
                for o, c in org_counts.most_common(20)
            ],
            "date_months": [
                {"month": d.replace("date:", ""), "count": c}
                for d, c in sorted(date_counts.items(), reverse=True)
            ]
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Failed to list participants: {str(e)}\n{traceback.format_exc()}"
        }
