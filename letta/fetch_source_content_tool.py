"""
Fetch Source Content Tool for Letta

Fetches the full content for a source reference, using the appropriate
API based on source type. Used by Phase A-discover to scan full emails,
meeting transcripts, and comment threads for additional tasks.

Tool: fetch_source_content
"""

from typing import Dict, Any, Optional


def fetch_source_content(
    source_type: str,
    fetch_hint: str,
    source_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch full content for a source, using fetch_hint to determine how.

    Used by Phase A-discover to load the complete email, meeting transcript,
    or comment thread for scanning beyond what Phase 0 captured.

    Args:
        source_type: One of "email", "meeting", "slack", "google-docs-comment".
        fetch_hint: Retrieval instruction from the spark record.
            Format: "gmail:MESSAGE_ID" for email, "granola:MEETING_ID" for meetings.
            For slack/docs-comment, pass the reference_id instead.
        source_ref: Optional reference_id for additional context lookup.

    Returns:
        Dictionary with status, content text, and metadata.
    """
    import json
    import os
    import subprocess
    import traceback
    import urllib.request

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.environ.get("LETTA_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")

        if not fetch_hint and not source_ref:
            return {"status": "error", "error_message": "fetch_hint or source_ref required"}

        content = ""
        metadata = {}

        if source_type == "email" and fetch_hint and fetch_hint.startswith("gmail:"):
            # Fetch full email via gws CLI
            message_id = fetch_hint.split(":", 1)[1]
            try:
                result = subprocess.run(
                    ["gws", "gmail", "users", "messages", "get",
                     "--params", json.dumps({"userId": "me", "id": message_id, "format": "full"}),
                     "--format", "json"],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    # Skip keyring line
                    raw = "\n".join(l for l in result.stdout.split("\n") if not l.startswith("Using keyring"))
                    msg = json.loads(raw)

                    # Extract headers
                    headers = {}
                    for h in msg.get("payload", {}).get("headers", []):
                        headers[h["name"]] = h["value"]
                    metadata = {
                        "subject": headers.get("Subject", ""),
                        "from": headers.get("From", ""),
                        "to": headers.get("To", ""),
                        "date": headers.get("Date", ""),
                        "thread_id": msg.get("threadId", ""),
                    }

                    # Extract body text
                    import base64

                    # Extract text body from MIME parts
                    payload = msg.get("payload", {})
                    body_data = None

                    # Walk MIME tree to find text/plain
                    parts_to_check = [payload]
                    while parts_to_check:
                        part = parts_to_check.pop(0)
                        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                            body_data = part["body"]["data"]
                            break
                        parts_to_check.extend(part.get("parts", []))

                    if body_data:
                        content = base64.urlsafe_b64decode(body_data).decode("utf-8", "replace")
                    else:
                        content = msg.get("snippet", "")
                else:
                    content = f"(gws error: {result.stderr[:200]})"
            except FileNotFoundError:
                # gws not available in this container — try via archival
                content = "(gws CLI not available — use archival search instead)"
            except Exception as e:
                content = f"(fetch error: {str(e)[:200]})"

        elif source_type == "meeting" and fetch_hint and fetch_hint.startswith("granola:"):
            # Fetch meeting from archival
            meeting_id = fetch_hint.split(":", 1)[1]
            try:
                search_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={meeting_id}&limit=3"
                req = urllib.request.Request(search_url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    passages = json.loads(resp.read().decode("utf-8"))

                if isinstance(passages, list):
                    # Find the meeting passage (longest one with meeting content)
                    best = max(passages, key=lambda p: len(p.get("text", "")) if isinstance(p, dict) else 0)
                    if isinstance(best, dict):
                        content = best.get("text", "")
                        metadata = {"meeting_id": meeting_id}
            except Exception as e:
                content = f"(archival search error: {str(e)[:200]})"

        elif source_type == "slack":
            # For Slack, content was already inline in the spark
            # Discovery would need thread context — use run_slack
            content = "(Slack thread fetch requires run_slack — call run_slack directly for thread context)"
            metadata = {"hint": "Use run_slack to fetch thread replies for discovery"}

        elif source_type == "google-docs-comment":
            # Comment content was already enriched by DriveEnricher
            # Discovery would scan comment replies — use run_gws
            content = "(Docs comment replies require run_gws — call run_gws directly)"
            metadata = {"hint": "Use run_gws to fetch comment reply chain for discovery"}

        else:
            return {"status": "error", "error_message": f"Unsupported source_type: {source_type}"}

        # Truncate very long content
        if len(content) > 5000:
            content = content[:5000] + "\n\n(truncated at 5000 chars)"

        return {
            "status": "ok",
            "source_type": source_type,
            "content": content,
            "metadata": metadata,
            "content_length": len(content),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
