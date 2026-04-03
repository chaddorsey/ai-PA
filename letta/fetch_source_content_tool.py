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

                    # Also fetch thread context if this is part of a thread
                    thread_id = msg.get("threadId", "")
                    if thread_id and thread_id != message_id:
                        try:
                            thread_result = subprocess.run(
                                ["gws", "gmail", "users", "threads", "get",
                                 "--params", json.dumps({"userId": "me", "id": thread_id, "format": "metadata",
                                                          "metadataHeaders": ["Subject", "From", "Date"]}),
                                 "--format", "json"],
                                capture_output=True, text=True, timeout=15,
                            )
                            if thread_result.returncode == 0:
                                t_raw = "\n".join(l for l in thread_result.stdout.split("\n")
                                                  if not l.startswith("Using keyring"))
                                thread = json.loads(t_raw)
                                thread_msgs = thread.get("messages", [])
                                if len(thread_msgs) > 1:
                                    # Cap at last 10 messages to avoid context overflow
                                    recent_msgs = thread_msgs[-10:]
                                    thread_context = []
                                    for tm in recent_msgs:
                                        tm_headers = {h["name"]: h["value"]
                                                      for h in tm.get("payload", {}).get("headers", [])}
                                        thread_context.append(
                                            f"[{tm_headers.get('Date','')}] "
                                            f"From: {tm_headers.get('From','')} — "
                                            f"{tm.get('snippet','')[:150]}"
                                        )
                                    prefix = f"({len(thread_msgs)} messages in thread, showing last {len(recent_msgs)})\n" if len(thread_msgs) > 10 else ""
                                    content += f"\n\n--- THREAD CONTEXT ---\n{prefix}" + "\n".join(thread_context)
                                    metadata["thread_message_count"] = len(thread_msgs)
                        except Exception:
                            pass  # Thread fetch is best-effort
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
            # Parse channel + thread_ts from reference_id or fetch_hint
            # Format: slack-CHANNEL_ID-MESSAGE_TS or slack-CHANNEL_ID-MSG_TS-tTHREAD_TS
            ref = fetch_hint or source_ref or ""
            import re as _re
            slack_match = _re.match(r"slack-([A-Z0-9]+)-([\d.]+)(?:-t([\d.]+))?", ref)
            if slack_match:
                channel_id = slack_match.group(1)
                message_ts = slack_match.group(2)
                thread_ts = slack_match.group(3) or message_ts

                # Prefer user token (xoxp) for broader channel access
                slack_token = os.environ.get("SLACK_MCP_XOXP_TOKEN", "") or os.environ.get("SLACK_BOT_TOKEN", "")
                if not slack_token:
                    # Sandbox may not inherit env — try reading from .env
                    try:
                        for env_path in ["/app/.env", os.path.expanduser("~/.env")]:
                            if os.path.exists(env_path):
                                with open(env_path) as ef:
                                    for eline in ef:
                                        if eline.startswith("SLACK_MCP_XOXP_TOKEN="):
                                            slack_token = eline.split("=", 1)[1].strip()
                                            break
                                        if not slack_token and eline.startswith("SLACK_BOT_TOKEN="):
                                            slack_token = eline.split("=", 1)[1].strip()
                            if slack_token:
                                break
                    except Exception:
                        pass
                if slack_token:
                    try:
                        auth_header = {"Authorization": f"Bearer {slack_token}"}
                        thread_lines = []

                        # If message is in a thread, fetch thread replies
                        if thread_ts != message_ts:
                            thread_url = (
                                f"https://slack.com/api/conversations.replies"
                                f"?channel={channel_id}&ts={thread_ts}&limit=15"
                            )
                            treq = urllib.request.Request(thread_url, headers=auth_header)
                            with urllib.request.urlopen(treq, timeout=10) as tresp:
                                tdata = json.loads(tresp.read().decode("utf-8"))
                            if tdata.get("ok") and tdata.get("messages"):
                                for tm in tdata["messages"][-15:]:
                                    thread_lines.append(
                                        f"[{tm.get('ts','')}] <@{tm.get('user','')}>: "
                                        f"{tm.get('text','')[:200]}"
                                    )

                        # Also fetch surrounding channel messages (3 before, 3 after)
                        # Before
                        before_url = (
                            f"https://slack.com/api/conversations.history"
                            f"?channel={channel_id}&latest={message_ts}"
                            f"&limit=4&inclusive=false"
                        )
                        breq = urllib.request.Request(before_url, headers=auth_header)
                        with urllib.request.urlopen(breq, timeout=10) as bresp:
                            bdata = json.loads(bresp.read().decode("utf-8"))
                        before_msgs = list(reversed(bdata.get("messages", [])[:3]))

                        # After
                        after_url = (
                            f"https://slack.com/api/conversations.history"
                            f"?channel={channel_id}&oldest={message_ts}"
                            f"&limit=4&inclusive=false"
                        )
                        areq = urllib.request.Request(after_url, headers=auth_header)
                        with urllib.request.urlopen(areq, timeout=10) as aresp:
                            adata = json.loads(aresp.read().decode("utf-8"))
                        after_msgs = adata.get("messages", [])[:3]

                        context_lines = []
                        for cm in before_msgs:
                            context_lines.append(
                                f"[before] <@{cm.get('user','')}>: {cm.get('text','')[:200]}"
                            )
                        context_lines.append(f"[THIS MESSAGE] ts={message_ts}")
                        for cm in after_msgs:
                            context_lines.append(
                                f"[after] <@{cm.get('user','')}>: {cm.get('text','')[:200]}"
                            )

                        if thread_lines:
                            content = "--- THREAD ---\n" + "\n".join(thread_lines)
                            content += "\n\n--- CHANNEL CONTEXT ---\n" + "\n".join(context_lines)
                        else:
                            content = "--- CHANNEL CONTEXT ---\n" + "\n".join(context_lines)

                        metadata = {
                            "channel_id": channel_id,
                            "thread_ts": thread_ts,
                            "thread_count": len(thread_lines),
                            "context_before": len(before_msgs),
                            "context_after": len(after_msgs),
                        }
                    except Exception as e:
                        content = f"(Slack fetch error: {str(e)[:200]})"
                else:
                    content = "(No SLACK_BOT_TOKEN available)"
            else:
                content = f"(Could not parse Slack reference: {ref[:60]})"
            metadata = metadata if content and not content.startswith("(") else {"hint": "Parse failed"}

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
