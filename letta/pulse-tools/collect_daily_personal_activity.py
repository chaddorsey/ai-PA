def collect_daily_personal_activity(date: Optional[str] = None) -> str:
    """
    Collect your personal Drive activity for a specific date.

    Queries Drive API for files you own or have access to, then queries
    Drive Activity API for activity on those files. Detects activity patterns.

    Args:
        date: Date in YYYY-MM-DD format. If provided, queries exactly that date
              (including weekends). If not provided, defaults to last workday.

    Returns:
        str: JSON string containing your personal activity data with patterns
    """
    import subprocess
    import json
    import time
    import os
    from datetime import datetime, timedelta

    GWS_TIMEOUT = 60
    MY_EMAIL = os.getenv("MY_EMAIL", "cdorsey@concord.org")

    try:
        # Determine target date
        if date:
            # User provided a specific date - use it exactly as requested
            target_date = datetime.strptime(date, "%Y-%m-%d")
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            # No date provided - default to last workday (inline)
            target_date = datetime.now() - timedelta(days=1)
            while target_date.weekday() >= 5:
                target_date -= timedelta(days=1)
            date_str = target_date.strftime("%Y-%m-%d")

        # Use Admin Reports API filtered by your email - much faster than querying all files
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"

        # Query Admin Reports API via gws CLI with pagination
        all_activities = []
        next_page_token = None

        while True:
            _params = {
                "userKey": MY_EMAIL,
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
                return json.dumps({
                    "error": f"Admin Reports API error: {_r.stderr[:500] if _r.stderr else f'gws exit {_r.returncode}'}",
                    "type": "error"
                })
            _data = json.loads(_r.stdout) if _r.stdout.strip() else {}
            all_activities.extend(_data.get("items", []))
            next_page_token = _data.get("nextPageToken")
            if not next_page_token:
                break
            time.sleep(0.1)

        activities = all_activities

        # Analyze your activity
        my_documents = {}
        total_edits = 0
        total_views = 0
        doc_ids_to_fetch = set()

        for activity in activities:
            for event in activity.get("events", []):
                event_name = event.get("name", "unknown")

                doc_id = None
                doc_title = "(untitled)"
                owner = None

                for param in event.get("parameters", []):
                    param_name = param.get("name")
                    param_value = param.get("value")

                    if param_name == "doc_id":
                        doc_id = param_value
                    elif param_name == "doc_title":
                        doc_title = param_value
                    elif param_name == "owner":
                        owner = param_value

                if doc_id:
                    if doc_id not in my_documents:
                        my_documents[doc_id] = {
                            "doc_id": doc_id,
                            "title": doc_title,
                            "owner": owner,
                            "link": "",
                            "edit_count": 0,
                            "view_count": 0,
                            "total_engagement": 0,
                        }
                        doc_ids_to_fetch.add(doc_id)

                    if event_name == "edit":
                        my_documents[doc_id]["edit_count"] += 1
                        total_edits += 1
                    elif event_name == "view":
                        my_documents[doc_id]["view_count"] += 1
                        total_views += 1

                    my_documents[doc_id]["total_engagement"] = (
                        my_documents[doc_id]["edit_count"] + my_documents[doc_id]["view_count"]
                    )

        # Only fetch links for top 50 documents
        top_doc_ids = sorted(
            doc_ids_to_fetch,
            key=lambda x: my_documents[x]["total_engagement"],
            reverse=True
        )[:50]

        # Fetch links and check accessibility via gws
        for doc_id in top_doc_ids:
            _cmd = ["gws"] + "drive files get".split()
            _cmd.extend(["--params", json.dumps({
                "fileId": doc_id,
                "fields": "id,name,webViewLink,shared,capabilities",
                "supportsAllDrives": True,
            })])
            _cmd.extend(["--format", "json"])
            _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=15)
            if _r.returncode != 0:
                _err = _r.stderr or ""
                if "404" in _err or "notFound" in _err:
                    my_documents[doc_id]["is_accessible"] = False
                    my_documents[doc_id]["link"] = ""
                    my_documents[doc_id]["access_error"] = "deleted"
                elif "403" in _err or "forbidden" in _err.lower():
                    my_documents[doc_id]["is_accessible"] = False
                    my_documents[doc_id]["link"] = ""
                    my_documents[doc_id]["access_error"] = "no_access"
                else:
                    my_documents[doc_id]["is_accessible"] = False
                    my_documents[doc_id]["link"] = ""
                continue
            try:
                file = json.loads(_r.stdout) if _r.stdout.strip() else {}
            except Exception:
                my_documents[doc_id]["is_accessible"] = False
                my_documents[doc_id]["link"] = ""
                continue
            if file:
                my_documents[doc_id]["link"] = file.get("webViewLink", "")
                my_documents[doc_id]["is_accessible"] = True
                my_documents[doc_id]["is_shared"] = file.get("shared", False)
                if file.get("name") and not my_documents[doc_id]["title"]:
                    my_documents[doc_id]["title"] = file.get("name")

        # Sort by engagement and format titles
        top_documents = sorted(
            my_documents.values(),
            key=lambda x: x["total_engagement"],
            reverse=True
        )[:20]

        # Format display titles based on accessibility
        for doc in top_documents:
            title = doc.get("title", "(untitled)")
            is_accessible = doc.get("is_accessible", False)
            access_error = doc.get("access_error", "")

            if not is_accessible:
                if access_error == "deleted":
                    doc["display_title"] = f"{title} - Deleted"
                elif access_error == "no_access":
                    doc["display_title"] = f"{title} - Not shared"
                else:
                    doc["display_title"] = f"{title} - Not accessible"
            else:
                doc["display_title"] = title

        result = {
            "type": "drive_analytics_personal",
            "date": date_str,
            "is_workday": True,
            "my_activity": {
                "total_activities": len(activities),
                "total_edits": total_edits,
                "total_views": total_views,
                "documents_engaged": len(my_documents),
                "top_documents": top_documents,
                "activity_patterns": {
                    "viewed_then_stopped": [],
                    "began_editing_recently": [],
                    "started_editing_then_stopped": [],
                    "view_most_regularly": [],
                    "multiple_views_per_day": [],
                },
            },
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Error collecting personal activity: {str(e)}",
            "type": "error"
        })
