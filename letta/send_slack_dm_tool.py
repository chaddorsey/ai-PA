"""
Send Slack DM Tool for Letta

Sends a proactive notification to the user via Slack DM.
Posts interactive Block Kit messages (with Approve/Modify/Skip buttons)
through the slackbot's /api/notify endpoint.

Tool: send_slack_dm
"""

from typing import Dict, Any, Optional


def send_slack_dm(
    text: str,
    reply_context: Optional[str] = None,
    suggested_reply: Optional[str] = None,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a proactive Slack DM notification to the user with interactive buttons.

    Posts a Block Kit message through the slackbot's /api/notify endpoint.
    The message includes Approve/Modify/Skip action buttons. When the user
    clicks a button, their response is routed back to this agent automatically.

    Use this tool when you need to:
    - Present a completion feedback draft for user approval
    - Ask the user a question during a background task
    - Surface time-sensitive information that needs user action

    Args:
        text: The main notification text to display. Should explain what
            happened and what action the user can take. Supports basic
            markdown formatting.
        reply_context: Optional JSON string containing routing context for
            the user's response. For completion feedback, include:
            {"action": "completion_feedback", "ref_id": "...",
             "routing_tool": "reply_to_document_comment",
             "routing_args": {"file_id": "...", "comment_id": "..."},
             "resolve_tool": "resolve_document_comment",
             "resolve_args": {"file_id": "...", "comment_id": "..."}}
        suggested_reply: Optional suggested reply text that will be shown
            in the notification and pre-filled in the Modify modal. This
            is the text that will be sent if the user clicks "Send Reply".
        detail: Optional additional context text shown in a smaller font
            below the main text. Use for metadata like source, requester, etc.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - thread_ts: The Slack thread timestamp of the posted notification
        - channel_id: The Slack channel ID where the notification was posted
        - error_message: Error details if status is "error"
    """
    import json
    import os
    import traceback
    import urllib.request
    import urllib.error

    try:
        SLACKBOT_NOTIFY_URL = os.getenv(
            "SLACKBOT_NOTIFY_URL", "http://slackbot:8081/api/notify"
        )
        # Hard-coded: tasks-agent-sleeptime (the only agent using this tool)
        # The Letta sandbox doesn't inject the calling agent's ID, so we
        # set it explicitly. If other agents need this tool, register a
        # variant with their agent ID or add env-var injection.
        AGENT_ID = "agent-62edcfac-2cc7-41a5-a3c2-d417da393397"

        if not text or not text.strip():
            return {
                "status": "error",
                "thread_ts": "",
                "channel_id": "",
                "error_message": "text is required",
            }

        # Parse reply_context from JSON string if provided
        parsed_context = {}
        if reply_context:
            try:
                parsed_context = json.loads(reply_context)
            except json.JSONDecodeError:
                parsed_context = {"raw": reply_context}

        # Build notification payload
        payload = {
            "text": text.strip(),
            "originating_agent_id": AGENT_ID,
            "reply_context": parsed_context,
        }
        if suggested_reply:
            payload["suggested_reply"] = suggested_reply.strip()
        if detail:
            payload["detail"] = detail.strip()

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SLACKBOT_NOTIFY_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if result.get("ok"):
            return {
                "status": "ok",
                "thread_ts": result.get("thread_ts", ""),
                "channel_id": result.get("channel_id", ""),
                "error_message": "",
            }
        else:
            return {
                "status": "error",
                "thread_ts": "",
                "channel_id": "",
                "error_message": result.get("error", "Unknown error from notify endpoint"),
            }

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        return {
            "status": "error",
            "thread_ts": "",
            "channel_id": "",
            "error_message": f"HTTP {e.code}: {body}",
        }
    except Exception as e:
        return {
            "status": "error",
            "thread_ts": "",
            "channel_id": "",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
