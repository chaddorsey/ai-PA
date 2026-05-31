from typing import Dict, Any, Optional, List

import os
import json
import csv

def analyze_slack_analytics(file_url: str, top_n: int = 10) -> str:
    """Analyze a Slack analytics CSV file and generate summary.
    
    Args:
        file_url: The url_private_download from list_recent_slack_files()
        top_n: Number of top results to return (default 10)
    
    Returns:
        JSON with analysis results including top channels/members by various metrics
        
    Examples:
        # After listing files, analyze a channels file
        analyze_slack_analytics("https://files.slack.com/.../channels-2024-10-14.csv")
        
        # Analyze with custom top N
        analyze_slack_analytics("https://files.slack.com/.../members.csv", top_n=15)
    """
    import urllib.request
    import io
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return json.dumps({"error": "SLACK_MCP_XOXP_TOKEN not set"}, indent=2)
    
    if not file_url:
        return json.dumps({"error": "No file URL provided"}, indent=2)
    
    results = {
        "file_url": file_url,
        "file_type": None,
        "analysis": None,
        "errors": []
    }
    
    try:
        # Download the file
        req = urllib.request.Request(
            file_url,
            headers={"Authorization": f"Bearer {TOKEN}"}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8")
        
        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(content))
        rows = list(csv_reader)
        
        if not rows:
            results["errors"].append("Empty file")
            return json.dumps(results, indent=2)
        
        # Detect file type based on columns
        columns = set(rows[0].keys())
        
        # Channels file detection - look for channel-specific metrics
        has_channel_metrics = ("Members who posted" in columns or "Members posted" in columns) and                              ("Members who viewed" in columns or "Members viewed" in columns)
        
        # Channels file detection and analysis
        if has_channel_metrics or "Channel" in columns or "Channel name" in columns:
            results["file_type"] = "channels"
            
            # Find channel column (Slack exports use "Name" for channels)
            channel_col = None
            for name in ["Channel", "Channel name", "Name", "channel", "channel_name", "name"]:
                if name in rows[0]:
                    channel_col = name
                    break
            
            if not channel_col:
                results["errors"].append("Could not find channel name column")
                return json.dumps(results, indent=2)
            
            ch_analysis = {
                "total_channels": len(rows),
                "top_by_messages_posted": [],
                "top_by_members_posted": [],
                "top_by_members_viewed": []
            }
            
            # Messages posted
            msg_col = None
            for name in ["Messages posted", "messages_posted", "Messages", "Messages sent"]:
                if name in rows[0]:
                    msg_col = name
                    break
            if msg_col:
                sorted_msgs = sorted(
                    rows,
                    key=lambda r: int(r.get(msg_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                ch_analysis["top_by_messages_posted"] = [
                    {"channel": r[channel_col], "count": int(r[msg_col].replace(",", ""))}
                    for r in sorted_msgs
                ]
            
            # Members posted
            posted_col = None
            for name in ["Members who posted", "Members posted", "members_posted", "Posters"]:
                if name in rows[0]:
                    posted_col = name
                    break
            if posted_col:
                sorted_posted = sorted(
                    rows,
                    key=lambda r: int(r.get(posted_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                ch_analysis["top_by_members_posted"] = [
                    {"channel": r[channel_col], "count": int(r[posted_col].replace(",", ""))}
                    for r in sorted_posted
                ]
            
            # Members viewed
            viewed_col = None
            for name in ["Members who viewed", "Members viewed", "members_viewed", "Viewers"]:
                if name in rows[0]:
                    viewed_col = name
                    break
            if viewed_col:
                sorted_viewed = sorted(
                    rows,
                    key=lambda r: int(r.get(viewed_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                ch_analysis["top_by_members_viewed"] = [
                    {"channel": r[channel_col], "count": int(r[viewed_col].replace(",", ""))}
                    for r in sorted_viewed
                ]
            
            results["analysis"] = ch_analysis
        
        # Members file detection and analysis
        elif "Full name" in columns or "Display name" in columns or "Member" in columns:
            results["file_type"] = "members"
            
            # Find name column
            name_col = None
            for name in ["Full name", "Display name", "Member", "Name", "User"]:
                if name in rows[0]:
                    name_col = name
                    break
            
            if not name_col:
                results["errors"].append("Could not find member name column")
                return json.dumps(results, indent=2)
            
            mem_analysis = {
                "total_members": len(rows),
                "top_by_messages_posted": []
            }
            
            # Messages posted
            msg_col = None
            for col_name in ["Messages posted", "messages_posted", "Messages"]:
                if col_name in rows[0]:
                    msg_col = col_name
                    break
            if msg_col:
                sorted_msgs = sorted(
                    rows,
                    key=lambda r: int(r.get(msg_col, "0").replace(",", "")),
                    reverse=True
                )[:top_n]
                mem_analysis["top_by_messages_posted"] = [
                    {"member": r[name_col], "count": int(r[msg_col].replace(",", ""))}
                    for r in sorted_msgs
                ]
            
            results["analysis"] = mem_analysis
        
        else:
            results["errors"].append(f"Unknown file type (columns: {list(columns)[:5]})")
    
    except Exception as e:
        results["errors"].append(f"Error processing file: {str(e)}")
    
    return json.dumps(results, indent=2)
