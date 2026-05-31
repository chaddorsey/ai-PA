import os
from typing import Dict, Any

def get_gmail_watch_status(thread_id: str) -> Dict[str, Any]:
    """
    Get detailed status of a specific watched Gmail thread, including
    whether a reply has been received and follow-up deadline info.

    Args:
        thread_id: Gmail thread ID to check status for (required)

    Returns:
        Dictionary with detailed thread watch status.
    """
    import json
    import traceback
    import urllib.request

    try:
        url = os.environ.get("GMAIL_WATCH_SERVICE_URL", "http://gmail-watch-service:8000/mcp")
        payload = json.dumps({"name": "get_watch_status", "arguments": {"thread_id": thread_id}}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        content = result.get("content", [{}])
        if content:
            return json.loads(content[0].get("text", "{}"))
        return {"status": "error", "error_message": "Empty response from watch service"}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
