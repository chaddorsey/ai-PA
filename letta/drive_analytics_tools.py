#!/usr/bin/env python3
"""
Drive Analytics Tools for Letta

Custom tools to collect and analyze Google Drive activity data.
These can be registered with Letta agents to provide Drive analytics capabilities.

All Google API calls are delegated to the `gws` CLI (subprocess), which handles
OAuth credentials internally. No Google client libraries are imported.
"""

import os
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta


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


def collect_daily_mentions(
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: Optional[int] = None
) -> str:
    """
    Collect comments that mention you in Google Drive files.

    Queries Drive API for files you have access to, then fetches comments
    and parses for @mentions of your email address.

    Supports three modes:
    1. Single date: collect_daily_mentions(date="2026-01-07")
    2. Date range: collect_daily_mentions(start_date="2026-01-05", end_date="2026-01-07")
    3. Days lookback: collect_daily_mentions(days=7)  # Last 7 days

    Args:
        date: Single date in YYYY-MM-DD format. If provided alone, queries that date.
        start_date: Start of date range in YYYY-MM-DD format (inclusive).
        end_date: End of date range in YYYY-MM-DD format (inclusive). Defaults to today if start_date provided.
        days: Number of days to look back from today (e.g., 7 = last 7 days). Ignored if date or start_date provided.

    Returns:
        str: JSON string containing mentions with timestamps and document links.
             For date ranges, returns mentions grouped by date.
    """
    import subprocess
    import json
    import os
    from datetime import datetime, timedelta

    GWS_TIMEOUT = 30
    MY_EMAIL = os.getenv("MY_EMAIL", "cdorsey@concord.org")

    try:
        # Determine date range based on parameters
        today = datetime.now().date()

        if start_date:
            range_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            if end_date:
                range_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            else:
                range_end = today
            date_str = f"{start_date} to {range_end.strftime('%Y-%m-%d')}"
        elif date:
            range_start = datetime.strptime(date, "%Y-%m-%d").date()
            range_end = range_start
            date_str = date
        elif days:
            range_end = today
            range_start = today - timedelta(days=days - 1)
            date_str = f"last {days} days"
        else:
            # Default: last workday only (inline workday calculation)
            check_date = datetime.now()
            while check_date.weekday() >= 5:
                check_date = check_date - timedelta(days=1)
            range_start = check_date.date()
            range_end = range_start
            date_str = range_start.strftime("%Y-%m-%d")

        detected_at = datetime.now().isoformat() + "Z"

        # Query all files you can access that were recently modified
        cutoff_datetime = datetime.combine(range_start, datetime.min.time()) - timedelta(days=7)
        cutoff_date = cutoff_datetime.strftime("%Y-%m-%dT00:00:00Z")

        all_files_query = f"modifiedTime > '{cutoff_date}'"
        all_files = []
        page_token = None

        while True:
            _params = {
                "q": all_files_query,
                "pageSize": 100,
                "fields": "nextPageToken,files(id,name,webViewLink)",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
                "corpora": "allDrives",
            }
            if page_token:
                _params["pageToken"] = page_token

            _cmd = ["gws"] + "drive files list".split()
            _cmd.extend(["--params", json.dumps(_params)])
            _cmd.extend(["--format", "json"])
            _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
            if _r.returncode != 0:
                return json.dumps({
                    "type": "drive_analytics_mentions",
                    "date": date_str,
                    "mentions": [],
                    "error": f"Could not query files: {_r.stderr[:500] if _r.stderr else f'gws exit {_r.returncode}'}"
                })
            _data = json.loads(_r.stdout) if _r.stdout.strip() else {}
            all_files.extend(_data.get("files", []))
            page_token = _data.get("nextPageToken")
            if not page_token or len(all_files) >= 500:
                break

        file_info = {f.get("id"): f for f in all_files if f.get("id")}

        # Check comments on each file (limit to avoid timeout)
        mentions = []

        for file in all_files[:200]:
            file_id = file.get("id")
            if not file_id:
                continue

            # Fetch comments via gws
            comments = []
            comment_page_token = None
            while True:
                _comment_params = {
                    "fileId": file_id,
                    "pageSize": 100,
                    "fields": "nextPageToken,comments(id,content,author,createdTime,modifiedTime,resolved,mentionedEmailAddresses)",
                }
                if comment_page_token:
                    _comment_params["pageToken"] = comment_page_token

                _cmd = ["gws"] + "drive comments list".split()
                _cmd.extend(["--params", json.dumps(_comment_params)])
                _cmd.extend(["--format", "json"])
                _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
                if _r.returncode != 0:
                    break  # Some files may not have comments API access
                try:
                    _cdata = json.loads(_r.stdout) if _r.stdout.strip() else {}
                except Exception:
                    break
                comments.extend(_cdata.get("comments", []))
                comment_page_token = _cdata.get("nextPageToken")
                if not comment_page_token:
                    break

            for comment in comments:
                comment_content = comment.get("content", "")
                comment_created = comment.get("createdTime", "")
                comment_modified = comment.get("modifiedTime", "")

                mentioned_emails = comment.get("mentionedEmailAddresses", [])
                is_mentioned = any(
                    MY_EMAIL.lower() == email.lower() for email in mentioned_emails
                )

                if is_mentioned:
                    try:
                        comment_date = datetime.fromisoformat(comment_created.replace("Z", "+00:00"))
                        comment_date_only = comment_date.date()

                        if range_start <= comment_date_only <= range_end:
                            mentions.append({
                                "comment_id": comment.get("id"),
                                "file_id": file_id,
                                "file_title": file_info.get(file_id, {}).get("name", "(untitled)"),
                                "file_link": file_info.get(file_id, {}).get("webViewLink", ""),
                                "author": comment.get("author", {}).get("displayName", "(unknown)"),
                                "text": comment_content,
                                "created_time": comment_created,
                                "modified_time": comment_modified,
                                "date": comment_date_only.strftime("%Y-%m-%d"),
                                "detected_at": detected_at,
                                "is_new": True,
                                "mentioned_emails": mentioned_emails,
                            })
                    except (ValueError, AttributeError):
                        mentions.append({
                            "comment_id": comment.get("id"),
                            "file_id": file_id,
                            "file_title": file_info.get(file_id, {}).get("name", "(untitled)"),
                            "file_link": file_info.get(file_id, {}).get("webViewLink", ""),
                            "author": comment.get("author", {}).get("displayName", "(unknown)"),
                            "text": comment_content,
                            "created_time": comment_created,
                            "modified_time": comment_modified,
                            "detected_at": detected_at,
                            "is_new": True,
                            "mentioned_emails": mentioned_emails,
                        })

        mentions.sort(key=lambda x: x.get("created_time", ""), reverse=True)

        result = {
            "type": "drive_analytics_mentions",
            "date_range": date_str,
            "start_date": range_start.strftime("%Y-%m-%d"),
            "end_date": range_end.strftime("%Y-%m-%d"),
            "total_mentions": len(mentions),
            "mentions": mentions,
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Error collecting mentions: {str(e)}",
            "type": "error"
        })


# Placeholder for calculate_running_averages - will need Letta API access
def calculate_running_averages() -> str:
    """
    Calculate running averages for Drive analytics.

    Reads historical daily logs from memory blocks (via Letta API) and
    calculates 3-day, 10-day, and 50-day averages.

    Returns:
        str: JSON string with running averages
    """
    # This tool will need to access Letta API to read memory blocks
    # For now, return a stub
    return json.dumps({
        "error": "This tool requires Letta API access to read memory blocks. Not yet implemented.",
        "type": "error"
    })


def get_drive_analytics_summary(period: str = "yesterday", scope: str = "workspace", date: Optional[str] = None) -> str:
    """
    Get summary of Drive activity for a period or specific date from memory blocks.

    Reads from stored memory blocks to provide a summary of Drive activity.
    The agent should read from the consolidated memory blocks:
    - drive_analytics_workspace (for workspace data)
    - drive_analytics_personal (for personal data)

    Args:
        period: Time period - "today", "yesterday", "last_7_workdays", "last_10_workdays" (ignored if date is provided)
        scope: Scope of data - "workspace" or "personal"
        date: Optional specific date in YYYY-MM-DD format. If provided, overrides period.

    Returns:
        str: JSON string with instructions for the agent
    """
    block_name = "drive_analytics_workspace" if scope == "workspace" else "drive_analytics_personal"

    if date:
        date_instruction = (
            f"Look for the specific date '{date}' (YYYY-MM-DD format) in the block. "
            f"If that date is not found, inform the user that no data is available for {date} "
            f"and offer to collect it using collect_daily_workspace_activity('{date}') "
            f"or collect_daily_personal_activity('{date}'). "
        )
    else:
        date_instruction = (
            f"If the user specified a date in their request, parse it to YYYY-MM-DD format "
            f"and look for that specific date. Otherwise, interpret the period '{period}' "
            f"(e.g., 'yesterday' = most recent workday, 'today' = today if it's a workday). "
            f"If a specific date is requested but not found, inform the user and offer to collect it. "
        )

    return json.dumps({
        "message": (
            f"To get Drive analytics summary for {period if not date else date} ({scope}), "
            f"read the '{block_name}' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_workspace_activity() or collect_daily_personal_activity(). "
            "Do NOT make up or assume data exists. "
            f"{date_instruction}"
            "If data exists for the requested date/period, extract it and provide a summary."
        ),
        "block_name": block_name,
        "period": period,
        "scope": scope,
        "date": date,
    })


def get_drive_trends(metric: str = "document", comparison_period: str = "10_day") -> str:
    """
    Compare current activity to historical averages.

    Reads from memory blocks and compares current period to running averages.

    Args:
        metric: What to analyze - "activity_type", "document", or "user"
        comparison_period: Period for comparison - "3_day", "10_day", or "50_day"

    Returns:
        str: JSON string with trends (or instruction to read from memory)
    """
    return json.dumps({
        "message": (
            f"To get Drive trends for {metric} compared to {comparison_period} average, "
            "read from drive_analytics_averages memory block and compare with recent daily logs. "
            "Use memory blocks to access stored data."
        ),
        "metric": metric,
        "comparison_period": comparison_period,
    })


def get_my_drive_activity(days: int = 7, include_links: bool = True, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    Get your personal Drive activity with document links for a date range or lookback period.

    Reads from the drive_analytics_personal memory block to get documents you've engaged with.

    Args:
        days: Number of workdays to look back (default: 7, ignored if start_date/end_date provided)
        include_links: Whether to include Drive document links (default: True)
        start_date: Optional start date in YYYY-MM-DD format (overrides days)
        end_date: Optional end date in YYYY-MM-DD format (defaults to today if start_date provided)

    Returns:
        str: JSON string with instructions for the agent
    """
    if start_date:
        date_instruction = (
            f"Extract entries from '{start_date}' to '{end_date or start_date}' (inclusive). "
            f"If any dates in this range are missing, inform the user which dates are missing "
            f"and offer to collect them using collect_daily_personal_activity() with the specific dates. "
        )
    else:
        date_instruction = (
            f"If the user specified a date range in their request, parse the dates to YYYY-MM-DD format "
            f"and extract entries for that range. Otherwise, extract entries for the past {days} workdays. "
            f"If specific dates are requested but not found, inform the user and offer to collect them. "
        )

    return json.dumps({
        "message": (
            f"To get your Drive activity, read the 'drive_analytics_personal' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_personal_activity(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"Aggregate the top_documents from each day in the range. "
            f"For each document, use the 'display_title' field if available (it shows accessibility status), "
            f"otherwise use 'title'. "
            f"Only include links for documents where 'is_accessible' is true. "
            f"Format shared documents as: '[Title](link)'. "
            f"Format non-shared documents as: 'Title - Not shared' (no link)."
        ),
        "block_name": "drive_analytics_personal",
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "include_links": include_links,
    })


def get_drive_mentions(days: int = 7, unread_only: bool = False, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    Get comments that mention you from memory for a date range or lookback period.

    Reads from the drive_analytics_mentions memory block to get comments mentioning you.

    Args:
        days: Number of days to look back (default: 7, ignored if start_date/end_date provided)
        unread_only: Filter to only unread mentions (default: False)
        start_date: Optional start date in YYYY-MM-DD format (overrides days)
        end_date: Optional end date in YYYY-MM-DD format (defaults to today if start_date provided)

    Returns:
        str: JSON string with instructions for the agent
    """
    if start_date:
        date_instruction = (
            f"Extract entries from '{start_date}' to '{end_date or start_date}' (inclusive). "
            f"If any dates in this range are missing, inform the user which dates are missing "
            f"and offer to collect them using collect_daily_mentions() with the specific dates. "
        )
    else:
        date_instruction = (
            f"If the user specified a date range in their request, parse the dates to YYYY-MM-DD format "
            f"and extract entries for that range. Otherwise, extract entries for the past {days} days. "
            f"If specific dates are requested but not found, inform the user and offer to collect them. "
        )

    return json.dumps({
        "message": (
            f"To get Drive mentions, read the 'drive_analytics_mentions' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no mentions data is available yet and explicitly offer "
            "to collect it using collect_daily_mentions(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"Filter by is_new if unread_only is True ({unread_only}). "
            "For each mention, only include document links if the file is accessible. "
            "If a file is not accessible, note it in the response (e.g., 'File not accessible'). "
            "Provide a list with document links (when accessible), comment text, and timestamps."
        ),
        "block_name": "drive_analytics_mentions",
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "unread_only": unread_only,
    })


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


def get_top_documents(category: str = "edited", count: int = 5, include_links: bool = True, date: Optional[str] = None) -> str:
    """
    Get top documents by category with links for a specific date or most recent.

    Reads from the drive_analytics_workspace memory block to get top documents.

    Args:
        category: Category - "edited", "shared", "commented", or "viewed" (default: "edited")
        count: Number of documents to return (default: 5)
        include_links: Whether to include Drive document links (default: True)
        date: Optional date in YYYY-MM-DD format. If not provided, uses most recent entry.

    Returns:
        str: JSON string with instructions for the agent
    """
    date_instruction = ""
    if date:
        date_instruction = (
            f"Look for the specific date '{date}' (YYYY-MM-DD format) in the block. "
            f"If that date is not found, inform the user that no data is available for {date} "
            f"and offer to collect it using collect_daily_workspace_activity(date='{date}'). "
            f"CRITICAL: You must pass the date parameter explicitly: date='{date}', not just '{date}'. "
        )
    else:
        date_instruction = (
            "If the user specified a date in their request (e.g., 'Thursday, November 13' or 'November 10, 2025'), "
            "parse it to YYYY-MM-DD format (e.g., '2025-11-13' or '2025-11-10') and look for that specific date. "
            "If the user didn't specify a date, use the most recent entry (latest date key). "
            "If a specific date is requested but not found, inform the user and offer to collect it. "
            "IMPORTANT: When calling collect_daily_workspace_activity() to collect data, you MUST pass the date parameter. "
            "For example, if the user asks for November 10, 2025, you must call: collect_daily_workspace_activity(date='2025-11-10'). "
            "Do NOT call collect_daily_workspace_activity() without the date parameter, as it will default to the last workday "
            "and may not match what the user requested. "
        )

    return json.dumps({
        "message": (
            f"To get top {count} {category} documents, "
            "read the 'drive_analytics_workspace' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_workspace_activity(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"If data exists for the requested date, extract the top_five.most_{category} list "
            f"and return the top {count} items. "
            f"For each document, use the 'display_title' field if available (it shows accessibility status like 'Not shared' or 'Deleted'), "
            f"otherwise use 'title'. "
            f"Only include links for documents where 'is_accessible' is true. "
            f"Format shared documents as: '[Title](link)'. "
            f"Format non-shared documents as: 'Title - Not shared' (no link). "
            f"Format deleted documents as: 'Title - Deleted' (no link)."
        ),
        "block_name": "drive_analytics_workspace",
        "category": category,
        "count": count,
        "include_links": include_links,
        "date": date,
    })


def get_recent_my_activity(activity_type: str = "all", days: int = 3, include_links: bool = True, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    Get documents you've viewed or edited recently with links for a date range or lookback period.

    Reads from the drive_analytics_personal memory block to get your recent activity.
    Useful for quick access to active documents.

    Args:
        activity_type: Type of activity - "edit", "view", or "all" (default: "all")
        days: Number of workdays to look back (default: 3, ignored if start_date/end_date provided)
        include_links: Whether to include Drive document links (default: True)
        start_date: Optional start date in YYYY-MM-DD format (overrides days)
        end_date: Optional end date in YYYY-MM-DD format (defaults to today if start_date provided)

    Returns:
        str: JSON string with instructions for the agent
    """
    if start_date:
        date_instruction = (
            f"Extract entries from '{start_date}' to '{end_date or start_date}' (inclusive). "
            f"If any dates in this range are missing, inform the user which dates are missing "
            f"and offer to collect them using collect_daily_personal_activity() with the specific dates. "
        )
    else:
        date_instruction = (
            f"If the user specified a date range in their request, parse the dates to YYYY-MM-DD format "
            f"and extract entries for that range. Otherwise, extract entries for the past {days} workdays. "
            f"If specific dates are requested but not found, inform the user and offer to collect them. "
        )

    return json.dumps({
        "message": (
            f"To get your recent {activity_type} activity, read the 'drive_analytics_personal' memory block using memory_read. "
            "Parse the JSON. "
            "CRITICAL: If the block is empty ({{}}) or the parsed JSON has no date keys, "
            "you MUST inform the user that no analytics data is available yet and explicitly offer "
            "to collect it using collect_daily_personal_activity(). Do NOT make up or assume data exists. "
            f"{date_instruction}"
            f"Aggregate top_documents from the date range, filter by activity_type if specified ({activity_type}). "
            f"For each document, use the 'display_title' field if available (it shows accessibility status), "
            f"otherwise use 'title'. "
            f"Only include links for documents where 'is_accessible' is true. "
            f"Format shared documents as: '[Title](link)'. "
            f"Format non-shared documents as: 'Title - Not shared' (no link)."
        ),
        "block_name": "drive_analytics_personal",
        "activity_type": activity_type,
        "days": days,
        "start_date": start_date,
        "end_date": end_date,
        "include_links": include_links,
    })


def get_drive_file_info(drive_url: str) -> str:
    """
    Get document or folder title and metadata from a Google Drive URL.

    Extracts the file ID from a Google Drive URL and retrieves file/folder information
    including title, owner, creation date, modification date, sharing status, etc.
    Works for both files and folders.

    Args:
        drive_url: Google Drive URL in any format:
                   - https://docs.google.com/document/d/FILE_ID/edit
                   - https://drive.google.com/file/d/FILE_ID/view
                   - https://drive.google.com/drive/folders/FILE_ID
                   - https://drive.google.com/open?id=FILE_ID
                   - etc.

    Returns:
        str: JSON string with file/folder metadata or error message

    Example:
        get_drive_file_info("https://docs.google.com/document/d/1abc123xyz/edit")
        # Returns: {"title": "Document Name", "owner": "user@example.com", ...}

        get_drive_file_info("https://drive.google.com/drive/folders/1abc123xyz")
        # Returns: {"title": "Folder Name", "mime_type": "application/vnd.google-apps.folder", ...}
    """
    import re
    import subprocess
    import json
    from datetime import datetime

    try:
        # Extract file ID from various Google Drive URL formats
        file_id = None

        # Pattern 1: /folders/FILE_ID (for folder URLs)
        match = re.search(r'/folders/([a-zA-Z0-9_-]+)', drive_url)
        if match:
            file_id = match.group(1)

        # Pattern 2: /d/FILE_ID/ or /file/d/FILE_ID/ (for file/document URLs)
        if not file_id:
            match = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
            if match:
                file_id = match.group(1)

        # Pattern 3: ?id=FILE_ID
        if not file_id:
            match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', drive_url)
            if match:
                file_id = match.group(1)

        # Pattern 4: FILE_ID directly (if URL is just the ID)
        if not file_id:
            if re.match(r'^[a-zA-Z0-9_-]+$', drive_url):
                file_id = drive_url

        if not file_id:
            return json.dumps({
                "error": "Could not extract file ID from URL",
                "url": drive_url,
                "message": "Please provide a valid Google Drive URL (e.g., https://docs.google.com/document/d/FILE_ID/edit)"
            }, indent=2)

        # Query Drive API via gws CLI
        _cmd = ["gws"] + "drive files get".split()
        _cmd.extend(["--params", json.dumps({
            "fileId": file_id,
            "fields": "id,name,mimeType,createdTime,modifiedTime,owners,shared,webViewLink,webContentLink,size,permissions,capabilities,description,starred,trashed",
            "supportsAllDrives": True,
        })])
        _cmd.extend(["--format", "json"])
        _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=15)

        if _r.returncode != 0:
            _err = _r.stderr or ""
            if "404" in _err or "notFound" in _err:
                return json.dumps({
                    "error": "File not found",
                    "file_id": file_id,
                    "message": "The file does not exist or has been deleted. You may not have access to this file."
                }, indent=2)
            elif "403" in _err or "forbidden" in _err.lower():
                return json.dumps({
                    "error": "Access denied",
                    "file_id": file_id,
                    "message": "You do not have permission to access this file. The file may not be shared with you."
                }, indent=2)
            else:
                return json.dumps({
                    "error": f"Drive API error",
                    "file_id": file_id,
                    "message": _err[:500] if _err else f"gws exit {_r.returncode}"
                }, indent=2)

        file = json.loads(_r.stdout) if _r.stdout.strip() else {}

        # Format response
        owners = file.get("owners", [])
        owner_emails = [owner.get("emailAddress", "unknown") for owner in owners]
        owner_names = [owner.get("displayName", "unknown") for owner in owners]

        mime_type = file.get("mimeType", "unknown")
        is_folder = mime_type == "application/vnd.google-apps.folder"

        result = {
            "success": True,
            "file_id": file.get("id"),
            "title": file.get("name", "(untitled)"),
            "mime_type": mime_type,
            "is_folder": is_folder,
            "created_time": file.get("createdTime"),
            "modified_time": file.get("modifiedTime"),
            "owners": owner_emails,
            "owner_names": owner_names,
            "shared": file.get("shared", False),
            "web_view_link": file.get("webViewLink", ""),
            "web_content_link": file.get("webContentLink", ""),
            "size_bytes": file.get("size"),
            "description": file.get("description", ""),
            "starred": file.get("starred", False),
            "trashed": file.get("trashed", False),
            "capabilities": file.get("capabilities", {}),
        }

        # Format dates for readability
        if result["created_time"]:
            try:
                created_dt = datetime.fromisoformat(result["created_time"].replace('Z', '+00:00'))
                result["created_date"] = created_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        if result["modified_time"]:
            try:
                modified_dt = datetime.fromisoformat(result["modified_time"].replace('Z', '+00:00'))
                result["modified_date"] = modified_dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        # Format size
        if result["size_bytes"]:
            size = int(result["size_bytes"])
            if size < 1024:
                result["size"] = f"{size} bytes"
            elif size < 1024 * 1024:
                result["size"] = f"{size / 1024:.1f} KB"
            else:
                result["size"] = f"{size / (1024 * 1024):.1f} MB"

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"Error processing URL: {str(e)}",
            "url": drive_url
        }, indent=2)


def initialize_drive_analytics_memory() -> str:
    """
    Initialize Drive analytics memory blocks if they don't exist.

    Creates the consolidated memory blocks with empty JSON objects.
    The agent should call this once to set up the memory structure.

    Returns:
        str: JSON string with instructions for the agent
    """
    _my_email = os.getenv("MY_EMAIL", "cdorsey@concord.org")
    return json.dumps({
        "message": (
            "Initialize Drive analytics memory blocks. For each block name below, "
            "check if it exists using memory_read. If it doesn't exist, create it using "
            "memory_create with an empty JSON object {} as the initial content. "
            "Blocks to create: drive_analytics_workspace, drive_analytics_personal, "
            "drive_analytics_mentions, drive_analytics_averages, drive_analytics_config. "
            "For the config block, you can initialize it with: "
            '{"my_email": "cdorsey@concord.org", "max_days": 50}.'
        ),
        "blocks_to_create": [
            "drive_analytics_workspace",
            "drive_analytics_personal",
            "drive_analytics_mentions",
            "drive_analytics_averages",
            "drive_analytics_config"
        ],
        "initial_content": {
            "drive_analytics_workspace": "{}",
            "drive_analytics_personal": "{}",
            "drive_analytics_mentions": "{}",
            "drive_analytics_averages": "{}",
            "drive_analytics_config": json.dumps({
                "my_email": _my_email,
                "max_days": 50
            }, indent=2)
        }
    })


def search_drive_activity(
    user: Optional[str] = None,
    owner: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    activity_type: Optional[str] = None,
    folder: Optional[str] = None,
    count: Optional[int] = 50,
    sort_by: Optional[str] = "recent"
) -> Dict[str, Any]:
    """
    Search Google Drive activity with flexible filtering.

    Unified activity search supporting user, owner, date range, and activity type filters.
    Returns documents with activity counts and links.

    Args:
        user: Filter by actor (who did the action). Single email or comma-separated list.
              Example: "jie@company.com" or "jie@company.com,rebecca@company.com"
        owner: Filter by document owner. Single email or comma-separated list.
               Example: "leslie@company.com"
        start_date: Start date in YYYY-MM-DD format. Default: 7 days ago.
        end_date: End date in YYYY-MM-DD format. Default: today.
        activity_type: Filter by type: "edit", "view", "share", "comment", or "all". Default: "all".
        folder: Optional folder ID to scope search.
        count: Maximum documents to return. Default: 50, max: 200.
        sort_by: Sort results by "recent", "edit_count", "view_count", "view_actor_count",
                 "edit_actor_count", "name". Default: "recent".

    Returns:
        Dict with status, data (documents with activity counts and actor details).
        Each document includes:
        - view_count, edit_count, share_count, comment_count (activity counts)
        - view_actors, edit_actors, share_actors, comment_actors (who did each action)
        - view_actor_count, edit_actor_count, etc. (unique people per action type)

    Examples:
        # What did Jie and Rebecca work on Monday?
        search_drive_activity(user="jie@,rebecca@", start_date="2024-12-23", end_date="2024-12-23")

        # What did Cynthia edit most last week?
        search_drive_activity(user="cynthia@", activity_type="edit", start_date="2024-12-16", end_date="2024-12-20", sort_by="edit_count")

        # Documents owned by Leslie viewed last month
        search_drive_activity(owner="leslie@", activity_type="view", start_date="2024-11-01", end_date="2024-11-30")
    """
    # Imports inside function (Letta compliance)
    import subprocess
    import json
    import time
    from datetime import datetime, timedelta

    GWS_TIMEOUT = 60

    # Wrap in try-except (Letta compliance)
    try:
        # Parse user list
        user_list = []
        if user:
            user_list = [u.strip() for u in user.split(',') if u.strip()]

        # Parse owner list
        owner_list = []
        if owner:
            owner_list = [o.strip() for o in owner.split(',') if o.strip()]

        # Set date defaults
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        # Validate dates
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            return {
                "status": "error",
                "data": {},
                "error_message": f"Invalid date format. Use YYYY-MM-DD. Error: {str(e)}"
            }

        # Build time range for API
        start_time = f"{start_date}T00:00:00Z"
        end_time = f"{end_date}T23:59:59Z"

        # Set defaults
        if count is None or count < 1:
            count = 50
        if count > 200:
            count = 200
        if activity_type is None:
            activity_type = "all"
        if sort_by is None:
            sort_by = "recent"

        # Query Admin Reports API via gws CLI
        # Use userKey filter only if single user with full email
        use_api_filter = False
        if len(user_list) == 1:
            single_user = user_list[0]
            if '@' in single_user and not single_user.endswith('@'):
                user_key = single_user
                use_api_filter = True
            else:
                user_key = "all"
        else:
            user_key = "all"

        activities = []
        next_page_token = None
        MAX_RESULTS_PER_PAGE = 1000

        # Determine MAX_PAGES based on query type and date range
        date_range_days = (end_dt - start_dt).days + 1
        is_org_wide = not owner_list and not user_list
        needs_more_pages = (owner_list) or (is_org_wide and date_range_days > 7)
        MAX_PAGES = 50 if needs_more_pages else 15

        pages_fetched = 0
        hit_page_limit = False

        while pages_fetched < MAX_PAGES:
            _params = {
                "userKey": user_key,
                "applicationName": "drive",
                "startTime": start_time,
                "endTime": end_time,
                "maxResults": MAX_RESULTS_PER_PAGE,
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

        if next_page_token:
            hit_page_limit = True

        # Process activities into document-centric view
        documents = {}

        for activity in activities:
            actor_email = activity.get("actor", {}).get("email", "")
            activity_time = activity.get("id", {}).get("time", "")

            # Filter by user list if we didn't use API filter or have multiple users
            if user_list and not use_api_filter:
                if not any(actor_email.lower().startswith(u.lower().rstrip('@')) for u in user_list):
                    continue

            for event in activity.get("events", []):
                event_name = event.get("name", "unknown")

                # Filter by activity type
                if activity_type != "all":
                    if activity_type == "edit" and event_name != "edit":
                        continue
                    elif activity_type == "view" and event_name != "view":
                        continue
                    elif activity_type == "share" and event_name not in ["change_user_access", "change_acl_editors", "change_document_visibility"]:
                        continue
                    elif activity_type == "comment" and event_name not in ["create_comment", "resolve_comment", "edit_comment", "delete_comment"]:
                        continue

                # Extract document info
                doc_id = None
                doc_title = "(untitled)"
                doc_owner = None

                for param in event.get("parameters", []):
                    param_name = param.get("name")
                    param_value = param.get("value")

                    if param_name == "doc_id":
                        doc_id = param_value
                    elif param_name == "doc_title":
                        doc_title = param_value
                    elif param_name == "owner":
                        doc_owner = param_value

                if not doc_id:
                    continue

                # Filter by owner if specified
                if owner_list:
                    if not doc_owner:
                        continue
                    if not any(doc_owner.lower().startswith(o.lower().rstrip('@')) for o in owner_list):
                        continue

                # Initialize document entry
                if doc_id not in documents:
                    documents[doc_id] = {
                        "doc_id": doc_id,
                        "title": doc_title,
                        "owner": doc_owner,
                        "edit_count": 0,
                        "view_count": 0,
                        "share_count": 0,
                        "comment_count": 0,
                        "total_activity": 0,
                        "actors": set(),
                        "view_actors": set(),
                        "edit_actors": set(),
                        "share_actors": set(),
                        "comment_actors": set(),
                        "last_activity": "",
                        "link": "",
                        "is_accessible": False,
                    }

                # Update counts and track actors by activity type
                if event_name == "edit":
                    documents[doc_id]["edit_count"] += 1
                    documents[doc_id]["edit_actors"].add(actor_email)
                elif event_name == "view":
                    documents[doc_id]["view_count"] += 1
                    documents[doc_id]["view_actors"].add(actor_email)
                elif event_name in ["change_user_access", "change_acl_editors", "change_document_visibility"]:
                    documents[doc_id]["share_count"] += 1
                    documents[doc_id]["share_actors"].add(actor_email)
                elif event_name in ["create_comment", "resolve_comment", "edit_comment", "delete_comment"]:
                    documents[doc_id]["comment_count"] += 1
                    documents[doc_id]["comment_actors"].add(actor_email)

                documents[doc_id]["total_activity"] += 1
                documents[doc_id]["actors"].add(actor_email)

                if activity_time > documents[doc_id]["last_activity"]:
                    documents[doc_id]["last_activity"] = activity_time

        # Convert sets to lists for JSON serialization
        for doc in documents.values():
            doc["actors"] = list(doc["actors"])
            doc["actor_count"] = len(doc["actors"])
            doc["view_actors"] = list(doc["view_actors"])
            doc["view_actor_count"] = len(doc["view_actors"])
            doc["edit_actors"] = list(doc["edit_actors"])
            doc["edit_actor_count"] = len(doc["edit_actors"])
            doc["share_actors"] = list(doc["share_actors"])
            doc["share_actor_count"] = len(doc["share_actors"])
            doc["comment_actors"] = list(doc["comment_actors"])
            doc["comment_actor_count"] = len(doc["comment_actors"])

        # Sort documents
        doc_list = list(documents.values())
        if sort_by == "edit_count":
            doc_list.sort(key=lambda x: x["edit_count"], reverse=True)
        elif sort_by == "view_count":
            doc_list.sort(key=lambda x: x["view_count"], reverse=True)
        elif sort_by == "view_actor_count":
            doc_list.sort(key=lambda x: x["view_actor_count"], reverse=True)
        elif sort_by == "edit_actor_count":
            doc_list.sort(key=lambda x: x["edit_actor_count"], reverse=True)
        elif sort_by == "name":
            doc_list.sort(key=lambda x: x["title"].lower())
        else:  # recent
            doc_list.sort(key=lambda x: x["last_activity"], reverse=True)

        # Limit results
        doc_list = doc_list[:count]

        # Fetch links for top documents via gws
        for doc in doc_list[:25]:
            _cmd = ["gws"] + "drive files get".split()
            _cmd.extend(["--params", json.dumps({
                "fileId": doc["doc_id"],
                "fields": "id,name,webViewLink,shared",
                "supportsAllDrives": True,
            })])
            _cmd.extend(["--format", "json"])
            _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=15)
            if _r.returncode != 0:
                _err = _r.stderr or ""
                if "404" in _err or "notFound" in _err:
                    doc["access_error"] = "deleted"
                elif "403" in _err or "forbidden" in _err.lower():
                    doc["access_error"] = "no_access"
                doc["is_accessible"] = False
                continue
            try:
                file = json.loads(_r.stdout) if _r.stdout.strip() else {}
            except Exception:
                doc["is_accessible"] = False
                continue
            doc["link"] = file.get("webViewLink", "")
            doc["is_accessible"] = True
            if file.get("name"):
                doc["title"] = file.get("name")

        return {
            "status": "ok",
            "data": {
                "query": {
                    "user": user,
                    "owner": owner,
                    "start_date": start_date,
                    "end_date": end_date,
                    "activity_type": activity_type,
                    "sort_by": sort_by,
                },
                "total_documents": len(doc_list),
                "total_activities": sum(d["total_activity"] for d in doc_list),
                "documents": doc_list,
                "truncated": hit_page_limit,
                "warning": "Results may be incomplete. For better results, use a shorter date range (1-2 weeks recommended)." if hit_page_limit else None,
            }
        }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error searching Drive activity: {str(e)}\n{traceback.format_exc()}"
        }


def get_drive_documents(
    owner: Optional[str] = None,
    name: Optional[str] = None,
    file_type: Optional[str] = None,
    folder: Optional[str] = None,
    modified_after: Optional[str] = None,
    shared_only: Optional[bool] = False,
    count: Optional[int] = 50,
    include_trashed: Optional[bool] = False
) -> Dict[str, Any]:
    """
    Search and list Google Drive documents with flexible filtering.

    Finds documents by owner, name, type, folder, or modification date.
    Returns document metadata with links.

    Args:
        owner: Filter by document owner. REQUIRES full email address (Drive API limitation).
               Single email or comma-separated list. Partial emails will not match.
               Example: "leslie@company.com" or "leslie@company.com,john@company.com"
        name: Search by document name (partial match).
              Example: "budget" matches "Q4 Budget Report"
        file_type: Filter by type: "document", "spreadsheet", "presentation",
                   "pdf", "folder", "image", or "all". Default: "all".
        folder: Folder ID to scope search to specific folder.
        modified_after: Only return files modified after this date (YYYY-MM-DD).
        shared_only: If True, only return shared documents. Default: False.
        count: Maximum documents to return. Default: 50, max: 200.
        include_trashed: Include trashed files. Default: False.

    Returns:
        Dict with status, data (documents with metadata), and error_message if applicable.

    Examples:
        # Find documents owned by Leslie
        get_drive_documents(owner="leslie@company.com")

        # Find spreadsheets with "budget" in the name
        get_drive_documents(name="budget", file_type="spreadsheet")

        # Find recently modified documents
        get_drive_documents(modified_after="2024-12-01")
    """
    # Imports inside function (Letta compliance)
    import subprocess
    import json
    from datetime import datetime

    GWS_TIMEOUT = 30

    try:
        # Build query parts
        query_parts = []

        # Owner filter
        if owner:
            owner_list = [o.strip() for o in owner.split(',') if o.strip()]
            owner_queries = []
            for o in owner_list:
                if not o.endswith('@') and '@' not in o:
                    o = f"{o}@"
                owner_queries.append(f"'{o}' in owners")
            if owner_queries:
                if len(owner_queries) == 1:
                    query_parts.append(owner_queries[0])
                else:
                    query_parts.append(f"({' or '.join(owner_queries)})")

        # Name search
        if name:
            query_parts.append(f"name contains '{name}'")

        # File type filter
        mime_type_map = {
            "document": "application/vnd.google-apps.document",
            "spreadsheet": "application/vnd.google-apps.spreadsheet",
            "presentation": "application/vnd.google-apps.presentation",
            "pdf": "application/pdf",
            "folder": "application/vnd.google-apps.folder",
            "image": "image/",
        }

        if file_type and file_type != "all":
            mime_type = mime_type_map.get(file_type)
            if mime_type:
                if file_type == "image":
                    query_parts.append(f"mimeType contains 'image/'")
                else:
                    query_parts.append(f"mimeType = '{mime_type}'")

        # Folder filter
        if folder:
            query_parts.append(f"'{folder}' in parents")

        # Modified after filter
        if modified_after:
            try:
                datetime.strptime(modified_after, "%Y-%m-%d")
                query_parts.append(f"modifiedTime > '{modified_after}T00:00:00'")
            except ValueError:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Invalid date format for modified_after: {modified_after}. Use YYYY-MM-DD."
                }

        # Trashed filter
        if not include_trashed:
            query_parts.append("trashed = false")

        # Build final query
        query = " and ".join(query_parts) if query_parts else None

        # Set defaults
        if count is None or count < 1:
            count = 50
        if count > 200:
            count = 200

        # Execute query via gws CLI with pagination
        documents = []
        page_token = None

        fields = "nextPageToken,files(id,name,mimeType,webViewLink,owners,modifiedTime,shared,size,createdTime)"

        while len(documents) < count:
            _params = {
                "pageSize": min(100, count - len(documents)),
                "fields": fields,
                "orderBy": "modifiedTime desc",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if query:
                _params["q"] = query
            if page_token:
                _params["pageToken"] = page_token

            _cmd = ["gws"] + "drive files list".split()
            _cmd.extend(["--params", json.dumps(_params)])
            _cmd.extend(["--format", "json"])
            _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
            if _r.returncode != 0:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Drive API error: {_r.stderr[:500] if _r.stderr else f'gws exit {_r.returncode}'}"
                }
            _data = json.loads(_r.stdout) if _r.stdout.strip() else {}
            files = _data.get("files", [])

            for f in files:
                # Filter shared_only if needed
                if shared_only and not f.get("shared", False):
                    continue

                doc = {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "type": f.get("mimeType", "").replace("application/vnd.google-apps.", ""),
                    "link": f.get("webViewLink", ""),
                    "owner": f.get("owners", [{}])[0].get("emailAddress", "") if f.get("owners") else "",
                    "modified": f.get("modifiedTime", ""),
                    "created": f.get("createdTime", ""),
                    "shared": f.get("shared", False),
                    "size": f.get("size", ""),
                }
                documents.append(doc)

                if len(documents) >= count:
                    break

            page_token = _data.get("nextPageToken")
            if not page_token:
                break

        return {
            "status": "ok",
            "data": {
                "query": {
                    "owner": owner,
                    "name": name,
                    "file_type": file_type,
                    "folder": folder,
                    "modified_after": modified_after,
                    "shared_only": shared_only,
                },
                "total_documents": len(documents),
                "documents": documents,
            }
        }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error getting Drive documents: {str(e)}\n{traceback.format_exc()}"
        }
