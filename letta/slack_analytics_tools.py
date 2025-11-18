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


