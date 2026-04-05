"""
Stage Resource Tool for Letta

Downloads files (PDFs, HTML, Gmail messages, Drive docs) to a host-accessible
staging directory. Returns a local path usable as openfile:// URL in OmniFocus
notes.

Volume mapping:
  Container write path: /data/shared/staged/{category}/{ref_id}/
  Host read path:       /Users/dorseyhomeserver/Dropbox/letta-shared-files/staged/{category}/{ref_id}/

The returned openfile_url uses the HOST path since openfile-handler runs on
the host and expects real POSIX paths.

Tool: stage_resource
"""

from typing import Dict, Any, Optional


def stage_resource(
    url: str,
    label: str,
    priority: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download a resource to the staging directory and return its local path.

    Used by MC during work packet assembly to stage files (PDFs, Drive docs,
    Gmail messages) on disk so the user can open them via openfile:// links
    in the OmniFocus task note.

    Idempotent: if the file already exists at the target path (less than 24
    hours old), reuses the existing file without re-downloading.

    Args:
        url: Source URL or fetch hint. Supports: HTTPS URLs (direct download),
             Google Drive/Docs URLs (fetched via gws CLI), Gmail message IDs
             in format "gmail:MSG_ID" (fetched via gws CLI).
        label: Short descriptive label for the resource (used in filename).
        priority: Optional priority marker: "primary", "secondary", or "background". Default "secondary".
        ref_id: Optional 8-char hex ref_id of the task this resource supports. If provided, files are organized under the ref_id directory.

    Returns:
        Dictionary with status, local_path (container), openfile_url (host),
        filename, size_bytes, category, and reused flag.
    """
    import hashlib
    import json
    import os
    import re
    import subprocess
    import traceback
    import urllib.parse
    import urllib.request
    import urllib.error
    from datetime import datetime, timedelta

    try:
        if not url or not label:
            return {"status": "error", "error_message": "url and label are required"}

        priority = priority or "secondary"

        # Volume mapping (verified in docker-compose.yml:658)
        CONTAINER_BASE = "/data/shared/staged"
        HOST_BASE = "/Users/dorseyhomeserver/Dropbox/letta-shared-files/staged"

        # Verify container base is writable
        if not os.path.exists(CONTAINER_BASE):
            try:
                os.makedirs(CONTAINER_BASE, exist_ok=True)
            except Exception as e:
                return {
                    "status": "error",
                    "error_message": f"Cannot access staging directory {CONTAINER_BASE}: {e}",
                }

        if not os.access(CONTAINER_BASE, os.W_OK):
            return {
                "status": "error",
                "error_message": f"Staging directory {CONTAINER_BASE} is not writable",
            }

        # Determine category and fetch strategy from URL
        category = "other"
        fetch_strategy = "http"
        extension = "bin"

        if url.startswith("gmail:"):
            category = "gmail"
            fetch_strategy = "gmail"
            extension = "txt"
        elif "docs.google.com" in url or "drive.google.com" in url:
            category = "drive"
            fetch_strategy = "drive"
            extension = "html"
        elif url.startswith("http://") or url.startswith("https://"):
            # Determine category from URL extension
            path_part = urllib.parse.urlparse(url).path.lower()
            if path_part.endswith(".pdf"):
                category = "pdf"
                extension = "pdf"
            elif path_part.endswith(".html") or path_part.endswith(".htm"):
                category = "html"
                extension = "html"
            elif path_part.endswith((".doc", ".docx")):
                category = "other"
                extension = path_part.rsplit(".", 1)[1]
            else:
                category = "other"
                extension = "html"  # default for web pages
            fetch_strategy = "http"
        else:
            return {
                "status": "error",
                "error_message": f"Unsupported URL scheme: {url[:60]}",
            }

        # Build target directory and filename
        ref_id_part = ref_id or "orphan"
        target_dir = os.path.join(CONTAINER_BASE, category, ref_id_part)
        os.makedirs(target_dir, exist_ok=True)

        # Sanitize label for filename
        safe_label = re.sub(r"[^a-zA-Z0-9\-_]", "-", label)[:60].strip("-") or "resource"
        filename = f"{safe_label}.{extension}"
        target_path = os.path.join(target_dir, filename)

        # Idempotency: reuse if file exists and is <24h old
        reused = False
        if os.path.exists(target_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(target_path))
            age = datetime.now() - mtime
            if age < timedelta(hours=24):
                reused = True
                size = os.path.getsize(target_path)
                host_path = target_path.replace(CONTAINER_BASE, HOST_BASE, 1)
                return {
                    "status": "ok",
                    "local_path": target_path,
                    "openfile_url": f"openfile://{host_path}",
                    "filename": filename,
                    "size_bytes": size,
                    "category": category,
                    "priority": priority,
                    "reused": True,
                }

        # Download based on strategy
        content = b""
        try:
            if fetch_strategy == "gmail":
                # gmail:MSG_ID — fetch via gws CLI
                msg_id = url.split(":", 1)[1]
                result = subprocess.run(
                    ["gws", "gmail", "users", "messages", "get",
                     "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"}),
                     "--format", "json"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    return {
                        "status": "error",
                        "error_message": f"gws failed: {result.stderr[:200]}",
                    }
                raw = "\n".join(l for l in result.stdout.split("\n") if not l.startswith("Using keyring"))
                msg = json.loads(raw)
                # Extract subject + from + body
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "(no subject)")
                from_addr = headers.get("From", "(unknown)")
                date = headers.get("Date", "")

                import base64
                body_text = ""
                payload = msg.get("payload", {})
                parts_to_check = [payload]
                while parts_to_check:
                    part = parts_to_check.pop(0)
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
                        break
                    parts_to_check.extend(part.get("parts", []))

                if not body_text:
                    body_text = msg.get("snippet", "")

                full_text = f"Subject: {subject}\nFrom: {from_addr}\nDate: {date}\n\n{body_text}"
                content = full_text.encode("utf-8")

            elif fetch_strategy == "drive":
                # Google Drive/Docs URL — extract file ID and fetch via gws
                doc_id_match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", url)
                if not doc_id_match:
                    doc_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
                if not doc_id_match:
                    return {
                        "status": "error",
                        "error_message": f"Could not extract Drive file ID from URL: {url[:80]}",
                    }
                file_id = doc_id_match.group(1)
                # Try exporting as HTML (for Google Docs)
                result = subprocess.run(
                    ["gws", "drive", "files", "export",
                     "--params", json.dumps({"fileId": file_id, "mimeType": "text/html"}),
                     "--format", "raw"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    # Strip any "Using keyring" header lines
                    lines = result.stdout.split("\n")
                    html = "\n".join(l for l in lines if not l.startswith("Using keyring"))
                    content = html.encode("utf-8")
                else:
                    return {
                        "status": "error",
                        "error_message": f"gws drive export failed: {result.stderr[:200]}",
                    }

            elif fetch_strategy == "http":
                # Direct HTTP(S) download
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (stage_resource/letta)"},
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    # Cap download size at 50MB
                    max_size = 50 * 1024 * 1024
                    content = resp.read(max_size + 1)
                    if len(content) > max_size:
                        return {
                            "status": "error",
                            "error_message": f"Download exceeds 50MB limit for {url[:60]}",
                        }

        except subprocess.TimeoutExpired:
            return {"status": "error", "error_message": "Download timed out"}
        except urllib.error.HTTPError as e:
            return {"status": "error", "error_message": f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"status": "error", "error_message": f"URL error: {e.reason}"}

        if not content:
            return {"status": "error", "error_message": "Downloaded content was empty"}

        # Write to target path
        with open(target_path, "wb") as f:
            f.write(content)

        size = len(content)
        host_path = target_path.replace(CONTAINER_BASE, HOST_BASE, 1)

        return {
            "status": "ok",
            "local_path": target_path,
            "openfile_url": f"openfile://{host_path}",
            "filename": filename,
            "size_bytes": size,
            "category": category,
            "priority": priority,
            "reused": False,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
