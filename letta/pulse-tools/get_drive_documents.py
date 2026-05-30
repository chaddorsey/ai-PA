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
            "error_message": f"Error getting Drive documents: {str(e)}
{traceback.format_exc()}"
        }
