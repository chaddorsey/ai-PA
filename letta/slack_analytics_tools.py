#!/usr/bin/env python3
"""
Slack Analytics Tools for Letta

Custom tools to trigger and retrieve Slack analytics data.
These can be registered with Letta agents to provide analytics capabilities.
"""

import os
import subprocess
import time
import json
import csv
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import requests


# Configuration
SLACK_TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
PLAYWRIGHT_SCRIPT_PATH = "/Users/dorseyhomeserver/ai-PA/scripts/slack_analytics_trigger_export.py"
AUTH_STATE_PATH = "/Users/dorseyhomeserver/ai-PA/slack_auth_state.json"


def trigger_slack_analytics_export(analytics_type: str = "channels") -> str:
    """
    Trigger a Slack analytics CSV export using browser automation.
    
    This function clicks the "Export CSV" button in Slack's analytics dashboard.
    The CSV file will be generated and available in Slack's Files section.
    
    Args:
        analytics_type: Type of analytics to export. Options: "channels", "members", "overview", "all"
    
    Returns:
        str: Success message with instructions on how to retrieve the file
    
    Example:
        result = trigger_slack_analytics_export("channels")
        # Returns: "✓ Triggered channels analytics export. Check Slack Files in 1-2 minutes."
    """
    
    if analytics_type not in ["channels", "members", "overview", "all"]:
        return f"❌ Invalid analytics_type: {analytics_type}. Must be: channels, members, overview, or all"
    
    try:
        # Run the Playwright script
        result = subprocess.run(
            [
                "python3",
                PLAYWRIGHT_SCRIPT_PATH,
                "--type", analytics_type,
                "--headless",
                "--auth-file", AUTH_STATE_PATH
            ],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            if analytics_type == "all":
                return (
                    "✓ Triggered exports for channels, members, and overview analytics.\n"
                    "The CSV files will be generated and available in Slack Files in 1-2 minutes.\n"
                    "Use list_recent_slack_files() or get_slack_analytics_files() to retrieve them."
                )
            else:
                return (
                    f"✓ Triggered {analytics_type} analytics export.\n"
                    f"The CSV file will be generated and available in Slack Files in 1-2 minutes.\n"
                    "Use list_recent_slack_files() or get_slack_analytics_files() to retrieve them."
                )
        else:
            return f"❌ Failed to trigger export:\n{result.stderr}"
            
    except subprocess.TimeoutExpired:
        return "❌ Timeout: Export trigger took too long (>60s)"
    except Exception as e:
        return f"❌ Error triggering export: {str(e)}"


def list_recent_slack_files(
    types: str = "csv",
    count: int = 10,
    user: Optional[str] = None
) -> str:
    """
    List recent files uploaded to Slack workspace.
    
    Args:
        types: File types to filter (e.g., "csv", "pdf", "all")
        count: Number of files to return (max 100)
        user: Filter by specific user ID (optional)
    
    Returns:
        str: JSON string with list of recent files including name, URL, timestamp
    
    Example:
        files = list_recent_slack_files(types="csv", count=5)
        # Returns JSON with recent CSV files
    """
    
    if not SLACK_TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set in environment"
    
    try:
        params = {
            "count": min(count, 100),
        }
        
        if types != "all":
            params["types"] = types
        
        if user:
            params["user"] = user
        
        response = requests.get(
            "https://slack.com/api/files.list",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
            params=params,
            timeout=10
        )
        
        data = response.json()
        
        if not data.get("ok"):
            return f"❌ Slack API error: {data.get('error', 'Unknown error')}"
        
        files = data.get("files", [])
        
        # Format for readability
        formatted_files = []
        for f in files:
            formatted_files.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "title": f.get("title"),
                "filetype": f.get("filetype"),
                "size": f.get("size"),
                "created": datetime.fromtimestamp(f.get("created", 0)).isoformat(),
                "url_private_download": f.get("url_private_download"),
                "user": f.get("user")
            })
        
        return json.dumps({
            "count": len(formatted_files),
            "files": formatted_files
        }, indent=2)
        
    except Exception as e:
        return f"❌ Error listing files: {str(e)}"


def get_slack_analytics_files(hours_back: int = 2) -> str:
    """
    Get recently created Slack analytics CSV files.
    
    Looks for CSV files that were created within the specified time window.
    This is useful after triggering an export to find the generated file.
    
    Args:
        hours_back: How many hours back to search for files (default: 2)
    
    Returns:
        str: JSON string with analytics CSV files found
    
    Example:
        # After triggering export, wait a bit then:
        files = get_slack_analytics_files(hours_back=1)
        # Returns JSON with recently created analytics CSVs
    """
    
    if not SLACK_TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set in environment"
    
    try:
        # Get recent CSV files
        response = requests.get(
            "https://slack.com/api/files.list",
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
            params={
                "types": "csv",
                "count": 50
            },
            timeout=10
        )
        
        data = response.json()
        
        if not data.get("ok"):
            return f"❌ Slack API error: {data.get('error', 'Unknown error')}"
        
        # Filter for analytics files created within time window
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        cutoff_timestamp = cutoff_time.timestamp()
        
        analytics_keywords = ["analytics", "channel", "member", "stats", "workspace"]
        analytics_files = []
        
        for f in data.get("files", []):
            file_created = f.get("created", 0)
            file_name = f.get("name", "").lower()
            file_title = f.get("title", "").lower()
            
            # Check if created recently and looks like analytics
            if file_created > cutoff_timestamp:
                if any(keyword in file_name or keyword in file_title for keyword in analytics_keywords):
                    analytics_files.append({
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "title": f.get("title"),
                        "size": f.get("size"),
                        "created": datetime.fromtimestamp(file_created).isoformat(),
                        "url_private_download": f.get("url_private_download"),
                        "age_minutes": int((time.time() - file_created) / 60)
                    })
        
        return json.dumps({
            "search_window_hours": hours_back,
            "found_count": len(analytics_files),
            "files": analytics_files
        }, indent=2)
        
    except Exception as e:
        return f"❌ Error getting analytics files: {str(e)}"


def list_files_from_channel(channel_id: str, limit: int = 100) -> str:
    """
    List files posted to a specific Slack channel (including MPDM channels).
    
    Retrieves messages from the channel using conversations.history, then extracts
    files from messages that contain file attachments. This is the recommended
    approach for getting files from specific channels, especially MPDMs.
    
    Args:
        channel_id: The Slack channel ID (e.g., "C1234567890", "mpdm-user1--user2-1", "G1234567890")
        limit: Maximum number of messages to retrieve (default: 100, max: 1000)
    
    Returns:
        str: JSON string with list of files found in the channel
    
    Example:
        files = list_files_from_channel("mpdm-cmcintyre--lstephens--cdorsey-1", limit=50)
        # Returns JSON with files posted in that MPDM channel
    """
    if not SLACK_TOKEN:
        return json.dumps({
            "error": "SLACK_MCP_XOXP_TOKEN not set in environment",
            "message": "Slack authentication token is required"
        }, indent=2)
    
    try:
        # Step 1: Get messages from the channel
        url = "https://slack.com/api/conversations.history"
        params = {
            "channel": channel_id,
            "limit": min(limit, 1000)  # Slack API max is 1000
        }
        headers = {
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("ok"):
            error = data.get("error", "Unknown error")
            return json.dumps({
                "error": f"Slack API error: {error}",
                "channel_id": channel_id,
                "message": f"Failed to retrieve messages from channel: {error}"
            }, indent=2)
        
        messages = data.get("messages", [])
        
        # Step 2: Extract files from messages
        files_found = []
        for message in messages:
            if "files" in message and message["files"]:
                for file_obj in message["files"]:
                    file_data = {
                        "file_id": file_obj.get("id"),
                        "name": file_obj.get("name"),
                        "title": file_obj.get("title"),
                        "mimetype": file_obj.get("mimetype"),
                        "filetype": file_obj.get("filetype"),
                        "pretty_type": file_obj.get("pretty_type"),
                        "size": file_obj.get("size"),
                        "url_private_download": file_obj.get("url_private_download"),
                        "created": file_obj.get("created"),
                        "created_iso": datetime.fromtimestamp(file_obj.get("created", 0)).isoformat() if file_obj.get("created") else None,
                        "user": file_obj.get("user"),
                        "message_ts": message.get("ts"),
                        "channel_id": channel_id
                    }
                    files_found.append(file_data)
        
        return json.dumps({
            "success": True,
            "channel_id": channel_id,
            "files_count": len(files_found),
            "messages_scanned": len(messages),
            "files": files_found,
            "message": f"Found {len(files_found)} file(s) in {len(messages)} message(s)"
        }, indent=2)
        
    except requests.exceptions.RequestException as e:
        return json.dumps({
            "error": f"Network error: {str(e)}",
            "channel_id": channel_id
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "channel_id": channel_id
        }, indent=2)


def download_slack_file(file_url: str, save_path: Optional[str] = None) -> str:
    """
    Download a file from Slack using its private download URL.
    
    Args:
        file_url: The url_private_download from a Slack file
        save_path: Optional path to save the file. If not provided, saves to /tmp/
    
    Returns:
        str: Path to downloaded file or error message
    
    Example:
        path = download_slack_file("https://files.slack.com/files-pri/...")
        # Returns: "/tmp/slack_file_xyz.csv"
    """
    
    if not SLACK_TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set in environment"
    
    if not file_url:
        return "❌ No file URL provided"
    
    try:
        # Download the file
        response = requests.get(
            file_url,
            headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
            timeout=30
        )
        
        if response.status_code != 200:
            return f"❌ Download failed: HTTP {response.status_code}"
        
        # Determine save path
        if not save_path:
            filename = file_url.split("/")[-1].split("?")[0]
            if not filename or filename == "":
                filename = f"slack_file_{int(time.time())}.csv"
            save_path = f"/tmp/{filename}"
        
        # Save the file
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        file_size = len(response.content)
        
        return json.dumps({
            "success": True,
            "file_path": save_path,
            "file_size_bytes": file_size,
            "message": f"✓ Downloaded {file_size} bytes to {save_path}"
        }, indent=2)
        
    except Exception as e:
        return f"❌ Error downloading file: {str(e)}"


def resolve_dm_channel_id(user_id: str) -> str:
    """
    Resolve a user ID to a DM channel ID using Slack's conversations.open API.
    
    When the MCP server returns channel information like "#U09C3N5LZ" (a user ID),
    this function converts it to the actual DM channel ID like "D09C3JMB9".
    
    Args:
        user_id: The Slack user ID (e.g., "U09C3N5LZ" or "#U09C3N5LZ")
    
    Returns:
        str: JSON string with DM channel ID or error message
    
    Example:
        resolve_dm_channel_id("U09C3N5LZ")
        # Returns: {"channel_id": "D09C3JMB9", "user_id": "U09C3N5LZ"}
    """
    if not SLACK_TOKEN:
        return json.dumps({
            "error": "SLACK_MCP_XOXP_TOKEN not set in environment",
            "message": "Slack authentication token is required"
        }, indent=2)
    
    # Remove # prefix if present
    clean_user_id = user_id.lstrip("#")
    
    # Validate user ID format (should start with U)
    if not clean_user_id.startswith("U"):
        return json.dumps({
            "error": f"Invalid user ID format: {user_id}",
            "message": "User ID should start with 'U' (e.g., 'U09C3N5LZ')"
        }, indent=2)
    
    try:
        # Call Slack API conversations.open to get/create DM channel
        url = "https://slack.com/api/conversations.open"
        params = {
            "users": clean_user_id
        }
        headers = {
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post(url, data=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("ok"):
            error = data.get("error", "Unknown error")
            return json.dumps({
                "error": f"Slack API error: {error}",
                "user_id": clean_user_id,
                "message": f"Failed to resolve DM channel: {error}"
            }, indent=2)
        
        channel = data.get("channel", {})
        channel_id = channel.get("id")
        
        if not channel_id:
            return json.dumps({
                "error": "No channel ID returned from Slack API",
                "user_id": clean_user_id
            }, indent=2)
        
        return json.dumps({
            "success": True,
            "channel_id": channel_id,
            "user_id": clean_user_id,
            "message": "DM channel ID resolved successfully"
        }, indent=2)
        
    except requests.exceptions.RequestException as e:
        return json.dumps({
            "error": f"Network error: {str(e)}",
            "user_id": clean_user_id
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "user_id": clean_user_id
        }, indent=2)


def get_slack_message_permalink(channel_id: str, message_ts: str) -> str:
    """
    Get a permalink URL for a specific Slack message.
    
    Uses Slack's chat.getPermalink API method to generate a permanent link
    to a message in a channel. For DM/MPDM channels where the API doesn't work,
    constructs the permalink manually using the standard format.
    
    Args:
        channel_id: The Slack channel ID (e.g., "C1234567890", "D1234567890", "mpdm-...")
        message_ts: The message timestamp (e.g., "1234567890.123456")
                   Can be in format "1234567890.123456" or "1234567890123456"
    
    Returns:
        str: JSON string with permalink URL or error message
    
    Example:
        get_slack_message_permalink("C1234567890", "1234567890.123456")
        # Returns: {"permalink": "https://concord-consortium.slack.com/archives/C1234567890/p1234567890123456"}
    """
    if not SLACK_TOKEN:
        return json.dumps({
            "error": "SLACK_MCP_XOXP_TOKEN not set in environment",
            "message": "Slack authentication token is required"
        }, indent=2)
    
    # Store original message_ts for permalink construction
    original_message_ts = message_ts
    
    # Normalize message_ts format (Slack API expects format like "1234567890.123456")
    # If provided as integer or without decimal, add decimal point
    try:
        if '.' not in message_ts:
            # If it's a long integer, insert decimal point 10 digits from the end
            if len(message_ts) > 10:
                message_ts = message_ts[:-6] + '.' + message_ts[-6:]
            else:
                message_ts = message_ts + '.000000'
    except Exception:
        pass  # Keep original format if parsing fails
    
    # Slack workspace URL
    SLACK_WORKSPACE_URL = "https://concord-consortium.slack.com"
    
    # Check if channel_id is actually a user ID (starts with #U or U)
    # This happens when MCP server returns "#U09C3N5LZ" instead of "D09C3JMB9"
    if channel_id.startswith("#U") or (channel_id.startswith("U") and not channel_id.startswith("D")):
        # Resolve user ID to DM channel ID
        user_id = channel_id.lstrip("#")
        resolve_result = resolve_dm_channel_id(user_id)
        try:
            resolve_data = json.loads(resolve_result)
            if resolve_data.get("success") and resolve_data.get("channel_id"):
                channel_id = resolve_data.get("channel_id")
            else:
                # If resolution fails, return error
                return json.dumps({
                    "error": f"Failed to resolve user ID to DM channel: {resolve_data.get('error', 'Unknown error')}",
                    "user_id": user_id,
                    "message_ts": message_ts,
                    "message": "Could not convert user ID to DM channel ID. Make sure the user ID is correct and the bot has access to DM with this user."
                }, indent=2)
        except json.JSONDecodeError:
            return json.dumps({
                "error": "Failed to parse DM channel resolution result",
                "user_id": user_id,
                "message_ts": message_ts
            }, indent=2)
    
    # Check if this looks like a DM/MPDM channel (starts with D or mpdm-)
    is_dm_or_mpdm = channel_id.startswith("D") or channel_id.startswith("mpdm-")
    
    try:
        # Try Slack API chat.getPermalink first (works for regular channels)
        url = "https://slack.com/api/chat.getPermalink"
        params = {
            "channel": channel_id,
            "message_ts": message_ts
        }
        headers = {
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post(url, data=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            permalink = data.get("permalink", "")
            if permalink:
                return json.dumps({
                    "success": True,
                    "permalink": permalink,
                    "channel_id": channel_id,
                    "message_ts": message_ts,
                    "message": "Permalink generated successfully via API"
                }, indent=2)
        
        # If API failed and this is a DM/MPDM channel, construct permalink manually
        error = data.get("error", "Unknown error")
        if (error == "channel_not_found" and is_dm_or_mpdm) or is_dm_or_mpdm:
            # Construct permalink manually for DM/MPDM channels
            # Format: https://workspace.slack.com/archives/CHANNEL_ID/pTIMESTAMP
            # Where TIMESTAMP is message_ts without the decimal point
            permalink_ts = original_message_ts.replace('.', '')
            permalink = f"{SLACK_WORKSPACE_URL}/archives/{channel_id}/p{permalink_ts}"
            
            return json.dumps({
                "success": True,
                "permalink": permalink,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "message": "Permalink constructed manually for DM/MPDM channel",
                "note": "DM/MPDM channels don't support chat.getPermalink API, so permalink was constructed using standard format"
            }, indent=2)
        
        # For other errors, return the error
        return json.dumps({
            "error": f"Slack API error: {error}",
            "channel_id": channel_id,
            "message_ts": message_ts,
            "message": f"Failed to get permalink: {error}"
        }, indent=2)
        
    except requests.exceptions.RequestException as e:
        # If network error and it's a DM/MPDM, try constructing manually anyway
        if is_dm_or_mpdm:
            permalink_ts = original_message_ts.replace('.', '')
            permalink = f"{SLACK_WORKSPACE_URL}/archives/{channel_id}/p{permalink_ts}"
            return json.dumps({
                "success": True,
                "permalink": permalink,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "message": "Permalink constructed manually (API unavailable)",
                "note": "Network error occurred, but permalink was constructed using standard format"
            }, indent=2)
        
        return json.dumps({
            "error": f"Network error: {str(e)}",
            "channel_id": channel_id,
            "message_ts": message_ts
        }, indent=2)
    except Exception as e:
        # If unexpected error and it's a DM/MPDM, try constructing manually anyway
        if is_dm_or_mpdm:
            permalink_ts = original_message_ts.replace('.', '')
            permalink = f"{SLACK_WORKSPACE_URL}/archives/{channel_id}/p{permalink_ts}"
            return json.dumps({
                "success": True,
                "permalink": permalink,
                "channel_id": channel_id,
                "message_ts": message_ts,
                "message": "Permalink constructed manually (fallback)",
                "note": "Unexpected error occurred, but permalink was constructed using standard format"
            }, indent=2)
        
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "channel_id": channel_id,
            "message_ts": message_ts
        }, indent=2)


def get_slack_analytics_data(
    analytics_type: str = "channels",
    wait_for_generation: bool = True,
    max_wait_minutes: int = 3
) -> str:
    """
    Complete workflow: Trigger export, wait, find file, download, and return data.
    
    This is the all-in-one function that:
    1. Triggers the Slack analytics CSV export
    2. Waits for the file to be generated
    3. Finds the file in Slack
    4. Downloads it
    5. Parses and returns the data
    
    Args:
        analytics_type: Type of analytics ("channels" or "members")
        wait_for_generation: Whether to wait for file generation (default: True)
        max_wait_minutes: Maximum minutes to wait for file (default: 3)
    
    Returns:
        str: JSON string with analytics data or error message
    
    Example:
        data = get_slack_analytics_data("channels")
        # Returns JSON with channel analytics data
    """
    
    if analytics_type not in ["channels", "members"]:
        return f"❌ Invalid analytics_type: {analytics_type}. Must be 'channels' or 'members'"
    
    # Step 1: Trigger export
    print(f"Step 1: Triggering {analytics_type} export...")
    trigger_result = trigger_slack_analytics_export(analytics_type)
    
    if "❌" in trigger_result:
        return trigger_result
    
    print(f"✓ Export triggered")
    
    if not wait_for_generation:
        return trigger_result
    
    # Step 2: Wait for file generation
    print(f"Step 2: Waiting for file generation (checking every 30s, max {max_wait_minutes} minutes)...")
    
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    check_interval = 30  # seconds
    
    analytics_file = None
    attempts = 0
    
    while time.time() - start_time < max_wait_seconds:
        attempts += 1
        print(f"  Attempt {attempts}: Checking for new files...")
        
        # Look for files created in last 10 minutes
        files_result = get_slack_analytics_files(hours_back=1)
        files_data = json.loads(files_result)
        
        # Find the most recent file matching our type
        for f in files_data.get("files", []):
            file_name = f.get("name", "").lower()
            file_title = f.get("title", "").lower()
            age_minutes = f.get("age_minutes", 999)
            
            # Look for recently created analytics file (< 5 minutes old)
            if age_minutes < 5:
                if analytics_type in file_name or analytics_type in file_title:
                    analytics_file = f
                    break
        
        if analytics_file:
            print(f"✓ Found analytics file: {analytics_file.get('name')}")
            break
        
        if time.time() - start_time < max_wait_seconds:
            print(f"  No file found yet, waiting {check_interval}s...")
            time.sleep(check_interval)
    
    if not analytics_file:
        return json.dumps({
            "status": "timeout",
            "message": f"⚠ Export triggered but file not found after {max_wait_minutes} minutes. Check Slack Files manually.",
            "trigger_result": trigger_result
        }, indent=2)
    
    # Step 3: Download the file
    print(f"Step 3: Downloading file...")
    download_url = analytics_file.get("url_private_download")
    download_result = download_slack_file(download_url)
    download_data = json.loads(download_result)
    
    if not download_data.get("success"):
        return download_result
    
    file_path = download_data.get("file_path")
    print(f"✓ Downloaded to {file_path}")
    
    # Step 4: Parse CSV and return data
    print(f"Step 4: Parsing CSV...")
    try:
        with open(file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
        
        return json.dumps({
            "status": "success",
            "analytics_type": analytics_type,
            "file_name": analytics_file.get("name"),
            "file_created": analytics_file.get("created"),
            "row_count": len(rows),
            "data": rows[:100],  # Return first 100 rows
            "note": f"Showing first 100 of {len(rows)} rows. Full file at: {file_path}"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"❌ Error parsing CSV: {str(e)}",
            "file_path": file_path
        }, indent=2)


# Letta tool registration helpers
def get_letta_tool_definitions() -> List[Dict[str, Any]]:
    """
    Get tool definitions in Letta format for registration.
    
    Returns:
        List of tool definitions that can be registered with Letta
    """
    
    return [
        {
            "name": "trigger_slack_analytics_export",
            "description": "Trigger a CSV export of Slack analytics data (channels, members, or overview). The CSV will be generated and available in Slack Files within 1-2 minutes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analytics_type": {
                        "type": "string",
                        "enum": ["channels", "members", "overview", "all"],
                        "description": "Type of analytics to export"
                    }
                },
                "required": ["analytics_type"]
            }
        },
        {
            "name": "list_recent_slack_files",
            "description": "List recent files uploaded to Slack workspace, useful for finding generated analytics CSVs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "types": {
                        "type": "string",
                        "description": "File types to filter (csv, pdf, all)",
                        "default": "csv"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of files to return (max 100)",
                        "default": 10
                    },
                    "user": {
                        "type": "string",
                        "description": "Filter by specific user ID (optional)"
                    }
                },
                "required": []
            }
        },
        {
            "name": "download_slack_file",
            "description": "Download a file from Slack using its private download URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_url": {
                        "type": "string",
                        "description": "The url_private_download from a Slack file"
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional path to save the file"
                    }
                },
                "required": ["file_url"]
            }
        },
        {
            "name": "get_slack_analytics_data",
            "description": "Complete workflow: trigger export, wait for generation, download, and return analytics data. This is the easiest way to get analytics data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analytics_type": {
                        "type": "string",
                        "enum": ["channels", "members"],
                        "description": "Type of analytics to get"
                    },
                    "wait_for_generation": {
                        "type": "boolean",
                        "description": "Whether to wait for file generation",
                        "default": True
                    },
                    "max_wait_minutes": {
                        "type": "integer",
                        "description": "Maximum minutes to wait for file",
                        "default": 3
                    }
                },
                "required": ["analytics_type"]
            }
        },
        {
            "name": "get_slack_analytics_files",
            "description": "Find recently created Slack analytics CSV files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "integer",
                        "description": "How many hours back to search",
                        "default": 2
                    }
                },
                "required": []
            }
        }
    ]


if __name__ == "__main__":
    # Test the tools
    print("Testing Slack Analytics Tools\n")
    
    print("="*60)
    print("Test 1: Trigger channels export")
    print("="*60)
    result = trigger_slack_analytics_export("channels")
    print(result)
    print()
    
    print("="*60)
    print("Test 2: List recent CSV files")
    print("="*60)
    result = list_recent_slack_files(types="csv", count=5)
    print(result)
    print()


