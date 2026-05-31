from typing import Dict, Any, Optional, List

def get_document_events(doc_ids: List[str], days: int = 7) -> Dict[str, Any]:
    """
    Get individual events (timeline) for specific documents.

    Returns a detailed timeline of who did what and when on specific documents.
    Use this for audit trails or understanding the sequence of activity.
    For aggregated counts, use search_drive_activity instead.

    Args:
        doc_ids: List of document IDs to query
        days: Number of days to look back (default: 7)

    Returns:
        Dict with events list (time, actor, action) and summary counts per document

    Example:
        # Get timeline for a specific document
        get_document_events(doc_ids=["1abc...xyz"])
        # Returns: {"status": "ok", "data": {"documents": [{"doc_id": "...", "events": [...]}]}}
    """
    # Imports inside function (Letta compliance)
    import subprocess
    import json
    import time
    from datetime import datetime, timedelta

    GWS_TIMEOUT = 60

    try:
        # Calculate date range
        end_date = datetime.now()
        start_date_dt = end_date - timedelta(days=days)

        start_time = start_date_dt.strftime("%Y-%m-%dT00:00:00Z")
        end_time = end_date.strftime("%Y-%m-%dT23:59:59Z")

        # Query Admin Reports API via gws CLI with pagination
        activities = []
        next_page_token = None
        MAX_PAGES = 15
        pages_fetched = 0

        while pages_fetched < MAX_PAGES:
            _params = {
                "userKey": "all",
                "applicationName": "drive",
                "startTime": start_time,
                "endTime": end_time,
                "maxResults": 1000,
            }
            if next_page_token:
                _params["pageToken"] = next_page_token

            _cmd = ["gws"] + "admin-reports activities list".split()
            _cmd.extend(["--params", json.dumps(_params)])
            _cmd.extend(["--format", "json"])
            _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
            if _r.returncode != 0:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Admin Reports API error: {_r.stderr[:500] if _r.stderr else f'gws exit {_r.returncode}'}"
                }
            _data = json.loads(_r.stdout) if _r.stdout.strip() else {}
            activities.extend(_data.get("items", []))
            pages_fetched += 1
            next_page_token = _data.get("nextPageToken")
            if not next_page_token:
                break
            time.sleep(0.1)

        # Filter activities for specified documents
        doc_activities = {}
        doc_id_set = set(doc_ids)

        for doc_id in doc_ids:
            doc_activities[doc_id] = {
                "doc_id": doc_id,
                "events": [],
                "summary": {
                    "edit_count": 0,
                    "view_count": 0,
                    "share_count": 0,
                    "comment_count": 0,
                },
            }

        for activity in activities:
            for event in activity.get("events", []):
                for param in event.get("parameters", []):
                    if param.get("name") == "doc_id":
                        doc_id = param.get("value")
                        if doc_id in doc_id_set:
                            event_name = event.get("name", "unknown")
                            doc_activities[doc_id]["events"].append({
                                "time": activity.get("id", {}).get("time"),
                                "actor": activity.get("actor", {}).get("email", "(unknown)"),
                                "action": event_name,
                            })

                            if event_name == "edit":
                                doc_activities[doc_id]["summary"]["edit_count"] += 1
                            elif event_name == "view":
                                doc_activities[doc_id]["summary"]["view_count"] += 1
                            elif event_name in ["change_user_access", "change_acl_editors"]:
                                doc_activities[doc_id]["summary"]["share_count"] += 1
                            elif event_name in ["create_comment", "resolve_comment"]:
                                doc_activities[doc_id]["summary"]["comment_count"] += 1

        # Sort events by time for each document
        for doc in doc_activities.values():
            doc["events"].sort(key=lambda x: x["time"] or "", reverse=True)

        return {
            "status": "ok",
            "data": {
                "documents": list(doc_activities.values()),
                "period_days": days,
                "truncated": pages_fetched >= MAX_PAGES,
            }
        }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error getting document events: {str(e)}\n{traceback.format_exc()}"
        }
