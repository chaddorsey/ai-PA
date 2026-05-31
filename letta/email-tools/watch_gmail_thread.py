import os
from typing import Optional, Dict, Any

def watch_gmail_thread(
    thread_id: str,
    subject: Optional[str] = None,
    recipients: Optional[str] = None,
    followup_interval: Optional[str] = None,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Start monitoring a Gmail thread for replies. Use this after sending an
    important email that needs follow-up tracking. The watch service will
    notify you when a reply is received on this thread.

    Args:
        thread_id: Gmail thread ID to monitor (required)
        subject: Thread subject line for display purposes
        recipients: Original recipients as comma-separated string
        followup_interval: Follow-up reminder interval like '3d' (3 days), '12h' (12 hours), '1w' (1 week). Default: 3 days if omitted.
        context: Additional context about why this thread is being watched

    Returns:
        Dictionary with status and watch details.
    """
    import json
    import traceback
    import urllib.request

    try:
        url = os.environ.get("GMAIL_WATCH_SERVICE_URL", "http://gmail-watch-service:8000/mcp")
        arguments = {"thread_id": thread_id}
        if subject is not None:
            arguments["subject"] = subject
        if recipients is not None:
            arguments["recipients"] = recipients
        if followup_interval is not None:
            arguments["followup_interval"] = followup_interval
        if context is not None:
            arguments["context"] = context

        payload = json.dumps({"name": "watch_thread", "arguments": arguments}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        content = result.get("content", [{}])
        if content:
            return json.loads(content[0].get("text", "{}"))
        return {"status": "error", "error_message": "Empty response from watch service"}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
