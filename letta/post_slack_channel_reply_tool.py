"""
Post Slack Channel Reply Tool for Letta

Posts a threaded reply in a Slack channel using the user's own token (xoxp),
so the reply appears as the user — matching the Google Drive comment reply
pattern where replies are posted under the user's identity.

Tool: post_slack_channel_reply
"""

from typing import Dict, Any


def post_slack_channel_reply(
    channel: str,
    thread_ts: str,
    reply_text: str,
) -> Dict[str, Any]:
    """
    Post a threaded reply to a Slack channel message.

    Uses the SLACK_MCP_XOXP_TOKEN (user token) so the reply appears as
    the user, not the bot. This is the Slack equivalent of
    reply_to_document_comment for Google Docs.

    Args:
        channel: The Slack channel ID to post in (e.g., "C0123456789").
        thread_ts: The thread timestamp to reply to. For standalone messages,
            this is the message's own ts (creates a new thread). For threaded
            messages, this is the parent thread's ts (continues the thread).
        reply_text: The text of the reply to post. Supports Slack mrkdwn
            formatting.

    Returns:
        Dictionary with keys:
        - status: "ok" or "error"
        - ts: The timestamp of the posted reply (if successful)
        - channel: The channel ID where the reply was posted
        - error_message: Error details if status is "error"
    """
    import json
    import os
    import traceback
    import urllib.request
    import urllib.error

    try:
        SLACK_TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")

        if not SLACK_TOKEN:
            return {
                "status": "error",
                "ts": "",
                "channel": channel,
                "error_message": "SLACK_MCP_XOXP_TOKEN not set in environment",
            }

        if not channel or not channel.strip():
            return {
                "status": "error",
                "ts": "",
                "channel": "",
                "error_message": "channel is required",
            }

        if not thread_ts or not thread_ts.strip():
            return {
                "status": "error",
                "ts": "",
                "channel": channel,
                "error_message": "thread_ts is required",
            }

        if not reply_text or not reply_text.strip():
            return {
                "status": "error",
                "ts": "",
                "channel": channel,
                "error_message": "reply_text is required",
            }

        payload = json.dumps({
            "channel": channel.strip(),
            "thread_ts": thread_ts.strip(),
            "text": reply_text.strip(),
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {SLACK_TOKEN}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if result.get("ok"):
            return {
                "status": "ok",
                "ts": result.get("ts", ""),
                "channel": result.get("channel", channel),
                "error_message": "",
            }
        else:
            return {
                "status": "error",
                "ts": "",
                "channel": channel,
                "error_message": f"Slack API error: {result.get('error', 'unknown')}",
            }

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            pass
        return {
            "status": "error",
            "ts": "",
            "channel": channel,
            "error_message": f"HTTP {e.code}: {body}",
        }
    except Exception as e:
        return {
            "status": "error",
            "ts": "",
            "channel": channel,
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
