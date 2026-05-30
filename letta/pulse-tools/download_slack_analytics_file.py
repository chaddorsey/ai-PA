import os
import json
import time

def download_slack_analytics_file(file_url: str, save_path: str = None) -> str:
    """Download a Slack file and return its path.
    
    Args:
        file_url: The url_private_download from list_recent_slack_files()
        save_path: Optional path to save (defaults to /tmp/)
    
    Returns:
        JSON with file path and size
    """
    import urllib.request
    
    TOKEN = os.getenv("SLACK_MCP_XOXP_TOKEN", "")
    if not TOKEN:
        return "❌ SLACK_MCP_XOXP_TOKEN not set"
    
    if not file_url:
        return "❌ No file URL provided"
    
    try:
        req = urllib.request.Request(file_url, headers={"Authorization": f"Bearer {TOKEN}"})
        
        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read()
        
        if not save_path:
            filename = file_url.split("/")[-1].split("?")[0] or f"slack_{int(time.time())}.csv"
            save_path = f"/tmp/{filename}"
        
        with open(save_path, "wb") as f:
            f.write(content)
        
        return json.dumps({
            "success": True,
            "file_path": save_path,
            "size_bytes": len(content),
            "size_kb": round(len(content) / 1024, 1)
        }, indent=2)
    except Exception as e:
        return f"❌ Error: {str(e)}"
