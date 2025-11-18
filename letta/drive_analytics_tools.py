#!/usr/bin/env python3
"""
Drive Analytics Tools for Letta

Custom tools to collect and analyze Google Drive activity data.
These can be registered with Letta agents to provide Drive analytics capabilities.
"""

import os
import json
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
OAUTH_KEY_FILE = os.getenv(
    "GMAIL_OAUTH_PATH",
    str(Path.home() / ".gmail-mcp" / "gcp-oauth.admin-reports.desktop.json")
)
TOKEN_PATH = os.getenv(
    "GMAIL_CREDENTIALS_PATH",
    str(Path.home() / ".gmail-mcp" / "admin-reports.credentials.json")
)
MY_EMAIL = os.getenv("MY_EMAIL", "cdorsey@concord.org")

# Scopes required
SCOPES = [
    "https://www.googleapis.com/auth/admin.reports.audit.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.activity.readonly",
]

# Constants
MAX_RESULTS_PER_PAGE = 1000
MIN_ABSOLUTE_CHANGE = 10
MIN_PERCENTAGE_CHANGE = 25
MIN_BASE_ACTIVITY = 5


def _load_credentials():
    """Load OAuth credentials from file."""
    creds = None
    
    # Load existing token if available
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            print(f"Warning: Failed to load credentials: {e}")
    
    # If no valid credentials, need to authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Warning: Failed to refresh credentials: {e}")
                creds = None
        
        if not creds:
            if not os.path.exists(OAUTH_KEY_FILE):
                raise FileNotFoundError(
                    f"OAuth key file not found at {OAUTH_KEY_FILE}. "
                    "Set GMAIL_OAUTH_PATH environment variable or place file at default location."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next time
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    
    return creds


def _is_workday(date: datetime) -> bool:
    """Check if a date is a workday (Monday-Friday)."""
    return date.weekday() < 5  # 0-4 = Monday-Friday


def _get_last_workday(target_date: Optional[datetime] = None) -> datetime:
    """Get the last workday before the target date (or yesterday)."""
    if target_date is None:
        target_date = datetime.now()
    
    # Go back until we find a workday
    date = target_date - timedelta(days=1)
    while not _is_workday(date):
        date -= timedelta(days=1)
    
    return date


def _query_admin_reports_api(start_time: str, end_time: str, user_key: str = "all") -> List[Dict]:
    """Query Admin Reports API for Drive activity."""
    creds = _load_credentials()
    service = build("admin", "reports_v1", credentials=creds)
    
    all_activities = []
    next_page_token = None
    
    params = {
        "userKey": user_key,
        "applicationName": "drive",
        "startTime": start_time,
        "endTime": end_time,
        "maxResults": MAX_RESULTS_PER_PAGE,
    }
    
    while True:
        if next_page_token:
            params["pageToken"] = next_page_token
        
        try:
            response = service.activities().list(**params).execute()
            activities = response.get("items", [])
            all_activities.extend(activities)
            
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
            
            # Small delay to respect rate limits
            time.sleep(0.1)
            
        except HttpError as e:
            return json.dumps({
                "error": f"Admin Reports API error: {str(e)}",
                "error_details": e.error_details if hasattr(e, "error_details") else None
            })
    
    return all_activities


def _query_drive_api(creds: Credentials, query: str = None) -> List[Dict]:
    """Query Drive API for files."""
    try:
        service = build("drive", "v3", credentials=creds)
        
        files = []
        page_token = None
        
        params = {
            "pageSize": 1000,
            "fields": "nextPageToken, files(id, name, owners, shared, webViewLink, permissions)",
            "supportsAllDrives": True,  # Required for Shared Drives
            "includeItemsFromAllDrives": True,  # Include Shared Drive files
        }
        
        if query:
            params["q"] = query
        
        while True:
            if page_token:
                params["pageToken"] = page_token
            
            response = service.files().list(**params).execute()
            files.extend(response.get("files", []))
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        
        return files
    except HttpError as e:
        # Return empty list on error rather than error string
        print(f"Warning: Drive API error: {str(e)}")
        return []


def _query_drive_activity_api(creds: Credentials, item_name: str = None, ancestor_name: str = None) -> List[Dict]:
    """Query Drive Activity API for file activity."""
    try:
        service = build("driveactivity", "v2", credentials=creds)
        
        activities = []
        page_token = None
        
        request_body = {
            "pageSize": 1000,
        }
        
        if item_name:
            request_body["itemName"] = item_name
        elif ancestor_name:
            request_body["ancestorName"] = ancestor_name
        
        while True:
            if page_token:
                request_body["pageToken"] = page_token
            
            response = service.activity().query(body=request_body).execute()
            activities.extend(response.get("activities", []))
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        
        return activities
    except HttpError as e:
        # Return empty list on error rather than error string
        print(f"Warning: Drive Activity API error: {str(e)}")
        return []


def _get_file_comments(creds: Credentials, file_id: str) -> List[Dict]:
    """Get comments for a specific file."""
    service = build("drive", "v3", credentials=creds)
    
    comments = []
    page_token = None
    
    while True:
        params = {
            "fileId": file_id,
            "pageSize": 100,
            "fields": "nextPageToken, comments(id, content, author, createdTime, modifiedTime, resolved)",
        }
        
        if page_token:
            params["pageToken"] = page_token
        
        try:
            response = service.comments().list(**params).execute()
            comments.extend(response.get("comments", []))
            
            page_token = response.get("nextPageToken")
            if not page_token:
                break
                
        except HttpError as e:
            # Some files may not have comments API access
            break
    
    return comments


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
            # No date provided - default to last workday
            target_date = _get_last_workday()
            date_str = target_date.strftime("%Y-%m-%d")
        
        # Note: We query the exact date requested, even if it's a weekend
        # The API will return whatever data exists for that date
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"
        
        # Query Admin Reports API
        activities = _query_admin_reports_api(start_time, end_time, "all")
        
        if isinstance(activities, str):  # Error response
            return activities
        
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
        
        # Check accessibility and fetch links for top documents
        creds = _load_credentials()
        if creds:
            try:
                service = build("drive", "v3", credentials=creds)
                for doc_id in top_doc_ids:
                    try:
                        file = service.files().get(
                            fileId=doc_id,
                            fields="id, name, webViewLink, shared, capabilities",
                            supportsAllDrives=True  # Required for files in Shared Drives
                        ).execute()
                        if file:
                            documents[doc_id]["link"] = file.get("webViewLink", "")
                            documents[doc_id]["is_accessible"] = True
                            documents[doc_id]["is_shared"] = file.get("shared", False)
                            # Update title if we got a better one from Drive API
                            if file.get("name") and not documents[doc_id].get("title"):
                                documents[doc_id]["title"] = file.get("name")
                    except HttpError as e:
                        if e.resp.status == 404:
                            # File doesn't exist (deleted)
                            documents[doc_id]["is_accessible"] = False
                            documents[doc_id]["link"] = ""
                            documents[doc_id]["access_error"] = "deleted"
                        elif e.resp.status == 403:
                            # File exists but user doesn't have access
                            documents[doc_id]["is_accessible"] = False
                            documents[doc_id]["link"] = ""
                            documents[doc_id]["access_error"] = "no_access"
                        else:
                            # Other error - assume not accessible
                            documents[doc_id]["is_accessible"] = False
                            documents[doc_id]["link"] = ""
                    except Exception:
                        # Any other error - assume not accessible
                        documents[doc_id]["is_accessible"] = False
                        documents[doc_id]["link"] = ""
            except Exception as e:
                # If credential loading fails, continue without links
                print(f"Warning: Could not check file accessibility: {e}")
        
        # Generate top-five lists
        def get_top_five(counts_dict, documents_dict, category_name):
            """Get top 5 items from counts, enriched with document info."""
            sorted_items = sorted(counts_dict.items(), key=lambda x: x[1], reverse=True)[:5]
            result = []
            for doc_id, count in sorted_items:
                doc_info = documents_dict.get(doc_id, {})
                title = doc_info.get("title", "(untitled)")
                link = doc_info.get("link", "")
                is_accessible = doc_info.get("is_accessible", False)
                access_error = doc_info.get("access_error", "")
                
                # Format title based on accessibility
                if not is_accessible:
                    if access_error == "deleted":
                        display_title = f"{title} - Deleted"
                    elif access_error == "no_access":
                        display_title = f"{title} - Not shared"
                    else:
                        display_title = f"{title} - Not accessible"
                else:
                    display_title = title
                
                result.append({
                    "doc_id": doc_id,
                    "title": title,
                    "display_title": display_title,  # Title with accessibility status
                    "owner": doc_info.get("owner", "(unknown)"),
                    "count": count,
                    "link": link if is_accessible else "",  # Only include link if accessible
                    "is_accessible": is_accessible,
                    "is_shared": doc_info.get("is_shared", False),
                })
            return result
        
        top_edited = get_top_five(edit_counts, documents, "most_edited")
        top_shared = get_top_five(share_counts, documents, "most_shared")
        top_commented = get_top_five(comment_counts, documents, "most_commented")
        top_viewed = get_top_five(view_counts, documents, "most_viewed")
        
        # Top active users
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_active_users = [{"email": email, "activity_count": count} for email, count in top_users]
        
        result = {
            "type": "drive_analytics_daily",
            "date": date_str,
            "is_workday": _is_workday(target_date),
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
    try:
        creds = _load_credentials()
        
        # Determine target date
        if date:
            # User provided a specific date - use it exactly as requested
            target_date = datetime.strptime(date, "%Y-%m-%d")
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            # No date provided - default to last workday
            target_date = _get_last_workday()
            date_str = target_date.strftime("%Y-%m-%d")
        
        # Note: We query the exact date requested, even if it's a weekend
        # The API will return whatever data exists for that date
        
        # Use Admin Reports API filtered by your email - much faster than querying all files
        start_time = f"{date_str}T00:00:00Z"
        end_time = f"{date_str}T23:59:59Z"
        
        activities = _query_admin_reports_api(start_time, end_time, MY_EMAIL)
        
        if isinstance(activities, str):  # Error response
            return activities
        
        # Analyze your activity first
        my_documents = {}
        total_edits = 0
        total_views = 0
        doc_ids_to_fetch = set()  # Only fetch links for documents with activity
        
        for activity in activities:
            for event in activity.get("events", []):
                event_name = event.get("name", "unknown")
                
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
                    if doc_id not in my_documents:
                        my_documents[doc_id] = {
                            "doc_id": doc_id,
                            "title": doc_title,
                            "owner": owner,
                            "link": "",  # Will fetch link later if needed
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
        
        # Only fetch links for documents that have activity (much faster)
        # Limit to top 50 documents to avoid too many API calls
        top_doc_ids = sorted(
            doc_ids_to_fetch,
            key=lambda x: my_documents[x]["total_engagement"],
            reverse=True
        )[:50]
        
        # Fetch links and check accessibility for top documents
        if top_doc_ids:
            try:
                service = build("drive", "v3", credentials=creds)
                for doc_id in top_doc_ids:
                    try:
                        file = service.files().get(
                            fileId=doc_id,
                            fields="id, name, webViewLink, shared, capabilities",
                            supportsAllDrives=True  # Required for files in Shared Drives
                        ).execute()
                        if file:
                            my_documents[doc_id]["link"] = file.get("webViewLink", "")
                            my_documents[doc_id]["is_accessible"] = True
                            my_documents[doc_id]["is_shared"] = file.get("shared", False)
                            if file.get("name") and not my_documents[doc_id]["title"]:
                                my_documents[doc_id]["title"] = file.get("name")
                    except HttpError as e:
                        if e.resp.status == 404:
                            # File doesn't exist (deleted)
                            my_documents[doc_id]["is_accessible"] = False
                            my_documents[doc_id]["link"] = ""
                            my_documents[doc_id]["access_error"] = "deleted"
                        elif e.resp.status == 403:
                            # File exists but user doesn't have access
                            my_documents[doc_id]["is_accessible"] = False
                            my_documents[doc_id]["link"] = ""
                            my_documents[doc_id]["access_error"] = "no_access"
                        else:
                            # Other error - assume not accessible
                            my_documents[doc_id]["is_accessible"] = False
                            my_documents[doc_id]["link"] = ""
                    except Exception:
                        # Any other error - assume not accessible
                        my_documents[doc_id]["is_accessible"] = False
                        my_documents[doc_id]["link"] = ""
            except Exception as e:
                # If link fetching fails, continue without links
                print(f"Warning: Could not fetch some document links: {e}")
        
        # Sort by engagement and format titles
        top_documents = sorted(
            my_documents.values(),
            key=lambda x: x["total_engagement"],
            reverse=True
        )[:20]  # Top 20 for personal activity
        
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
        
        # Activity patterns would require historical data, so we'll return basic structure
        # The agent can compare with previous days to detect patterns
        
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
                    # Patterns require historical comparison - agent will calculate
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


def collect_daily_mentions(date: Optional[str] = None) -> str:
    """
    Collect comments that mention you in Google Drive files.
    
    Queries Drive API for files you have access to, then fetches comments
    and parses for @mentions of your email address.
    
    Args:
        date: Date in YYYY-MM-DD format. If provided, queries exactly that date
              (including weekends). If not provided, defaults to last workday.
    
    Returns:
        str: JSON string containing mentions with timestamps and document links
    """
    try:
        creds = _load_credentials()
        
        # Determine target date
        if date:
            # User provided a specific date - use it exactly as requested
            target_date = datetime.strptime(date, "%Y-%m-%d")
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            # No date provided - default to last workday
            target_date = _get_last_workday()
            date_str = target_date.strftime("%Y-%m-%d")
        
        # Note: We query the exact date requested, even if it's a weekend
        # The API will return whatever data exists for that date
        detected_at = datetime.now().isoformat() + "Z"
        
        # Use a more efficient approach: query files that were recently modified
        # This is much faster than querying all files
        try:
            service = build("drive", "v3", credentials=creds)
            
            # Query files modified in the last 7 days (to catch recent comments)
            # This is much more efficient than querying all files
            cutoff_date = (target_date - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
            
            # Get files you own that were recently modified
            owned_query = f"'{MY_EMAIL}' in owners and modifiedTime > '{cutoff_date}'"
            owned_files = []
            page_token = None
            
            while True:
                params = {
                    "q": owned_query,
                    "pageSize": 100,
                    "fields": "nextPageToken, files(id, name, webViewLink)",
                    "supportsAllDrives": True,  # Required for Shared Drives
                    "includeItemsFromAllDrives": True,  # Include Shared Drive files
                }
                if page_token:
                    params["pageToken"] = page_token
                
                response = service.files().list(**params).execute()
                owned_files.extend(response.get("files", []))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            
            # Get files shared with you that were recently modified
            shared_query = f"sharedWithMe=true and modifiedTime > '{cutoff_date}'"
            shared_files = []
            page_token = None
            
            while True:
                params = {
                    "q": shared_query,
                    "pageSize": 100,
                    "fields": "nextPageToken, files(id, name, webViewLink)",
                    "supportsAllDrives": True,  # Required for Shared Drives
                    "includeItemsFromAllDrives": True,  # Include Shared Drive files
                }
                if page_token:
                    params["pageToken"] = page_token
                
                response = service.files().list(**params).execute()
                shared_files.extend(response.get("files", []))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            
            all_files = owned_files + shared_files
            file_info = {f.get("id"): f for f in all_files if f.get("id")}
            
        except Exception as e:
            print(f"Warning: Could not query files efficiently: {e}")
            # Fallback: return empty mentions rather than hanging
            return json.dumps({
                "type": "drive_analytics_mentions",
                "date": date_str,
                "mentions": [],
                "error": f"Could not query files: {str(e)}"
            })
        
        # Check comments on each file (limit to avoid timeout)
        mentions = []
        
        for file in all_files[:200]:  # Limit to 200 most recent files
            file_id = file.get("id")
            if not file_id:
                continue
            
            comments = _get_file_comments(creds, file_id)
            
            for comment in comments:
                comment_content = comment.get("content", "")
                comment_created = comment.get("createdTime", "")
                comment_modified = comment.get("modifiedTime", "")
                
                # Check if comment mentions your email
                # Google Drive mentions may appear as @cdorsey@concord.org or just the email
                if MY_EMAIL.lower() in comment_content.lower():
                    # Parse comment date to check if it's in our target date range
                    try:
                        comment_date = datetime.fromisoformat(comment_created.replace("Z", "+00:00"))
                        if comment_date.date() == target_date.date():
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
                                "is_new": True,  # Would need to compare with previous checks
                            })
                    except (ValueError, AttributeError):
                        # If date parsing fails, include it anyway
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
                        })
        
        result = {
            "type": "drive_analytics_mentions",
            "date": date_str,
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


def get_document_activity(doc_ids: List[str], days: int = 7) -> str:
    """
    Get activity for specific documents.
    
    Queries Admin Reports API for activity on specific documents.
    
    Args:
        doc_ids: List of document IDs to query
        days: Number of days to look back (default: 7)
    
    Returns:
        str: JSON string with activity details for each document
    """
    try:
        creds = _load_credentials()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        start_time = start_date.strftime("%Y-%m-%dT00:00:00Z")
        end_time = end_date.strftime("%Y-%m-%dT23:59:59Z")
        
        # Query activities
        activities = _query_admin_reports_api(start_time, end_time, "all")
        
        if isinstance(activities, str):  # Error response
            return activities
        
        # Filter activities for specified documents
        doc_activities = {}
        
        for doc_id in doc_ids:
            doc_activities[doc_id] = {
                "doc_id": doc_id,
                "activities": [],
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
                        if doc_id in doc_activities:
                            event_name = event.get("name", "unknown")
                            doc_activities[doc_id]["activities"].append({
                                "time": activity.get("id", {}).get("time"),
                                "actor": activity.get("actor", {}).get("email", "(unknown)"),
                                "event": event_name,
                            })
                            
                            # Update summary
                            if event_name == "edit":
                                doc_activities[doc_id]["summary"]["edit_count"] += 1
                            elif event_name == "view":
                                doc_activities[doc_id]["summary"]["view_count"] += 1
                            elif event_name in ["change_user_access", "change_acl_editors"]:
                                doc_activities[doc_id]["summary"]["share_count"] += 1
                            elif event_name in ["create_comment", "resolve_comment"]:
                                doc_activities[doc_id]["summary"]["comment_count"] += 1
        
        return json.dumps({
            "documents": list(doc_activities.values()),
            "period_days": days,
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Error getting document activity: {str(e)}",
            "type": "error"
        })


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


def initialize_drive_analytics_memory() -> str:
    """
    Initialize Drive analytics memory blocks if they don't exist.
    
    Creates the consolidated memory blocks with empty JSON objects.
    The agent should call this once to set up the memory structure.
    
    Returns:
        str: JSON string with instructions for the agent
    """
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
                "my_email": MY_EMAIL,
                "max_days": 50
            }, indent=2)
        }
    })


if __name__ == "__main__":
    # Test the tools
    print("Testing collect_daily_workspace_activity()...")
    result = collect_daily_workspace_activity()
    print(result[:500] + "..." if len(result) > 500 else result)

