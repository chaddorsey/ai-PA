from typing import Dict, Any, Optional, List

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
