"""Custom Letta tools for Gmail Watch Service.

These tools allow Letta agents to manage Gmail thread watches
via the gmail-watch-service HTTP API.
"""

from typing import Dict, Any, Optional


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
        url = "http://gmail-watch-service:8000/mcp"
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
        url = "http://gmail-watch-service:8000/mcp"
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
        url = "http://gmail-watch-service:8000/mcp"
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
        url = "http://gmail-watch-service:8000/mcp"
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
