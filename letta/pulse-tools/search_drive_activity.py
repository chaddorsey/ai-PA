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
            "error_message": f"Error searching Drive activity: {str(e)}
{traceback.format_exc()}"
        }
