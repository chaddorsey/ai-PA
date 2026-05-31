import os
from typing import Dict, Any

def unwatch_gmail_thread(thread_id: str) -> Dict[str, Any]:
    """
    Stop monitoring a Gmail thread. Use when a thread no longer needs
    reply tracking, such as after you've received and handled the reply.

    Args:
        thread_id: Gmail thread ID to stop watching (required)

    Returns:
        Dictionary with status confirming the thread is no longer watched.
    """
    import json
    import traceback
    import urllib.request

    try:
        url = os.environ.get("GMAIL_WATCH_SERVICE_URL", "http://gmail-watch-service:8000/mcp")
        payload = json.dumps({"name": "unwatch_thread", "arguments": {"thread_id": thread_id}}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        content = result.get("content", [{}])
        if content:
            return json.loads(content[0].get("text", "{}"))
        return {"status": "error", "error_message": "Empty response from watch service"}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
