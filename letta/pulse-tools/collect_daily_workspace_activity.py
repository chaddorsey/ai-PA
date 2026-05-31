from typing import Dict, Any, Optional, List

def collect_daily_workspace_activity(date: Optional[str] = None) -> str:
    """
    Collect workspace-wide Drive activity for a specific date.

    Queries Admin Reports API for all Drive activity on the specified date,
    aggregates by activity type, document, and user, and returns top-five lists.

    IMPORTANT: Always pass the 'date' parameter when the user requests data for a specific date.
    For example, if the user asks for November 10, 2025, call this function with date='2025-11-10'.

    Args:
        date: Date in YYYY-MM-DD format (e.g., '2025-11-10'). REQUIRED when user requests a specific date.
              If provided, queries exactly that date (including weekends).
              If not provided, defaults to last workday (which may not be what the user wants).

    Returns:
        str: JSON string containing workspace activity data with top-five lists. The JSON includes
             a 'date' field showing which date was actually queried.
    """
    import subprocess
    import json
    import time
    import os
    from datetime import datetime, timedelta

    GWS_TIMEOUT = 60

    try:
        # Determine target date
        if date:
            # User provided a specific date - use it exactly as requested
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
                date_str = target_date.strftime("%Y-%m-%d")
            except ValueError as e:
                return json.dumps({
                    "error": f"Invalid date format: '{date}'. Expected YYYY-MM-DD format (e.g., '2025-11-10'). Error: {str(e)}",
                    "type": "error"
                })
        else:
            # No date provided - default to last workday (inline _get_last_workday)
            target_date = datetime.now() - timedelta(days=1)
            while target_date.weekday() >= 5:
                target_date -= timedelta(days=1)
            date_str = target_date.strftime("%Y-%m-%d")

        # Note: We query the exact date requested, even if it's a weekend
        # The API will return whatever data exists for that date
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"

        # Query Admin Reports API via gws CLI with pagination
        all_activities = []
        next_page_token = None

        while True:
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

        # Analyze activities
        activity_types = {}
        actors = set()
        documents = {}

        # Track by category for top-five lists
        edit_counts = {}
        share_counts = {}
        comment_counts = {}
        view_counts = {}
        user_counts = {}

        for activity in activities:
            actor_email = activity.get("actor", {}).get("email", "(unknown)")
            actors.add(actor_email)
            user_counts[actor_email] = user_counts.get(actor_email, 0) + 1

            for event in activity.get("events", []):
                event_name = event.get("name", "unknown")
                activity_types[event_name] = activity_types.get(event_name, 0) + 1

                # Extract document info
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
                    if doc_id not in documents:
                        documents[doc_id] = {
                            "doc_id": doc_id,
                            "title": doc_title,
                            "owner": owner,
                            "edit_count": 0,
                            "share_count": 0,
                            "comment_count": 0,
                            "view_count": 0,
                            "link": "",  # Will be populated if accessible
                            "is_accessible": False,  # Will be checked later
                            "is_shared": False,  # Will be checked later
                            "access_error": "",  # Will be set if not accessible
                        }

                    # Categorize by event type
                    if event_name == "edit":
                        documents[doc_id]["edit_count"] += 1
                        edit_counts[doc_id] = edit_counts.get(doc_id, 0) + 1
                    elif event_name in ["change_user_access", "change_acl_editors",
                                       "change_document_visibility", "change_document_access_scope"]:
                        documents[doc_id]["share_count"] += 1
                        share_counts[doc_id] = share_counts.get(doc_id, 0) + 1
                    elif event_name in ["create_comment", "resolve_comment", "delete_comment", "edit_comment"]:
                        documents[doc_id]["comment_count"] += 1
                        comment_counts[doc_id] = comment_counts.get(doc_id, 0) + 1
                    elif event_name == "view":
                        documents[doc_id]["view_count"] += 1
                        view_counts[doc_id] = view_counts.get(doc_id, 0) + 1

        # Fetch links and check accessibility for top documents
        # Only check top 25 documents to avoid too many API calls
        top_doc_ids = sorted(
            list(documents.keys()),
            key=lambda x: (
                documents[x].get("edit_count", 0) +
                documents[x].get("view_count", 0) +
                documents[x].get("share_count", 0) +
                documents[x].get("comment_count", 0)
            ),
            reverse=True
        )[:25]

        # Check accessibility and fetch links for top documents via gws
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
                    documents[doc_id]["is_accessible"] = False
                    documents[doc_id]["link"] = ""
                    documents[doc_id]["access_error"] = "deleted"
                elif "403" in _err or "forbidden" in _err.lower():
                    documents[doc_id]["is_accessible"] = False
                    documents[doc_id]["link"] = ""
                    documents[doc_id]["access_error"] = "no_access"
                else:
                    documents[doc_id]["is_accessible"] = False
                    documents[doc_id]["link"] = ""
                continue
            try:
                file = json.loads(_r.stdout) if _r.stdout.strip() else {}
            except Exception:
                documents[doc_id]["is_accessible"] = False
                documents[doc_id]["link"] = ""
                continue
            if file:
                documents[doc_id]["link"] = file.get("webViewLink", "")
                documents[doc_id]["is_accessible"] = True
                documents[doc_id]["is_shared"] = file.get("shared", False)
                if file.get("name") and not documents[doc_id].get("title"):
                    documents[doc_id]["title"] = file.get("name")

        # Generate top-five lists (inlined - no nested def for Letta compliance)
        top_edited = []
        for doc_id, cnt in sorted(edit_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            doc_info = documents.get(doc_id, {})
            title = doc_info.get("title", "(untitled)")
            is_accessible = doc_info.get("is_accessible", False)
            access_error = doc_info.get("access_error", "")
            if not is_accessible:
                if access_error == "deleted":
                    display_title = f"{title} - Deleted"
                elif access_error == "no_access":
                    display_title = f"{title} - Not shared"
                else:
                    display_title = f"{title} - Not accessible"
            else:
                display_title = title
            top_edited.append({
                "doc_id": doc_id, "title": title, "display_title": display_title,
                "owner": doc_info.get("owner", "(unknown)"), "count": cnt,
                "link": doc_info.get("link", "") if is_accessible else "",
                "is_accessible": is_accessible, "is_shared": doc_info.get("is_shared", False),
            })

        top_shared = []
        for doc_id, cnt in sorted(share_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            doc_info = documents.get(doc_id, {})
            title = doc_info.get("title", "(untitled)")
            is_accessible = doc_info.get("is_accessible", False)
            access_error = doc_info.get("access_error", "")
            if not is_accessible:
                if access_error == "deleted":
                    display_title = f"{title} - Deleted"
                elif access_error == "no_access":
                    display_title = f"{title} - Not shared"
                else:
                    display_title = f"{title} - Not accessible"
            else:
                display_title = title
            top_shared.append({
                "doc_id": doc_id, "title": title, "display_title": display_title,
                "owner": doc_info.get("owner", "(unknown)"), "count": cnt,
                "link": doc_info.get("link", "") if is_accessible else "",
                "is_accessible": is_accessible, "is_shared": doc_info.get("is_shared", False),
            })

        top_commented = []
        for doc_id, cnt in sorted(comment_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            doc_info = documents.get(doc_id, {})
            title = doc_info.get("title", "(untitled)")
            is_accessible = doc_info.get("is_accessible", False)
            access_error = doc_info.get("access_error", "")
            if not is_accessible:
                if access_error == "deleted":
                    display_title = f"{title} - Deleted"
                elif access_error == "no_access":
                    display_title = f"{title} - Not shared"
                else:
                    display_title = f"{title} - Not accessible"
            else:
                display_title = title
            top_commented.append({
                "doc_id": doc_id, "title": title, "display_title": display_title,
                "owner": doc_info.get("owner", "(unknown)"), "count": cnt,
                "link": doc_info.get("link", "") if is_accessible else "",
                "is_accessible": is_accessible, "is_shared": doc_info.get("is_shared", False),
            })

        top_viewed = []
        for doc_id, cnt in sorted(view_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            doc_info = documents.get(doc_id, {})
            title = doc_info.get("title", "(untitled)")
            is_accessible = doc_info.get("is_accessible", False)
            access_error = doc_info.get("access_error", "")
            if not is_accessible:
                if access_error == "deleted":
                    display_title = f"{title} - Deleted"
                elif access_error == "no_access":
                    display_title = f"{title} - Not shared"
                else:
                    display_title = f"{title} - Not accessible"
            else:
                display_title = title
            top_viewed.append({
                "doc_id": doc_id, "title": title, "display_title": display_title,
                "owner": doc_info.get("owner", "(unknown)"), "count": cnt,
                "link": doc_info.get("link", "") if is_accessible else "",
                "is_accessible": is_accessible, "is_shared": doc_info.get("is_shared", False),
            })

        # Top active users
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_active_users = [{"email": email, "activity_count": count} for email, count in top_users]

        result = {
            "type": "drive_analytics_daily",
            "date": date_str,
            "is_workday": target_date.weekday() < 5,
            "date_requested": date if date else None,  # Show what was requested vs what was used
            "summary": {
                "total_activities": len(activities),
                "unique_users": len(actors),
                "unique_documents": len(documents),
            },
            "top_activity_types": [
                {"type": k, "count": v}
                for k, v in sorted(activity_types.items(), key=lambda x: x[1], reverse=True)
            ],
            "top_five": {
                "most_edited": top_edited,
                "most_shared": top_shared,
                "most_commented": top_commented,
                "most_viewed": top_viewed,
                "most_active_users": top_active_users,
            },
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Error collecting workspace activity: {str(e)}",
            "type": "error"
        })
