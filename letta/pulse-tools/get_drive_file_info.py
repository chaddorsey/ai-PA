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
