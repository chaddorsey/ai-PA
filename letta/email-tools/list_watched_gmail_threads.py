import os
from typing import Optional, Dict, Any, List

def list_watched_gmail_threads(
    include_inactive: Optional[str] = None,
    include_replied: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List all Gmail threads currently being monitored for replies.
    Returns thread IDs, subjects, reply status, and follow-up deadlines.

    Args:
        include_inactive: Set to "true" to include manually deactivated watches
        include_replied: Set to "true" to include threads that already received replies

    Returns:
        Dictionary with count and list of watched threads.
    """
    import json
    import traceback
    import urllib.request

    try:
        url = os.environ.get("GMAIL_WATCH_SERVICE_URL", "http://gmail-watch-service:8000/mcp")
        arguments = {}
        if include_inactive is not None and include_inactive.lower() == "true":
            arguments["include_inactive"] = True
        if include_replied is not None and include_replied.lower() == "true":
            arguments["include_replied"] = True

        payload = json.dumps({"name": "list_watched_threads", "arguments": arguments}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        content = result.get("content", [{}])
        if content:
            return json.loads(content[0].get("text", "{}"))
        return {"status": "error", "error_message": "Empty response from watch service"}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
