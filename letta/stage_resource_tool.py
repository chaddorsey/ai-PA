"""
Stage Resource Tool for Letta

Downloads files (PDFs, HTML, Gmail messages, Drive docs) to a host-accessible
staging directory. Returns a local path usable as openfile:// URL in OmniFocus
notes.

In LOCAL mode the tasks-agent runs on the host via the launchd runner, so it
writes directly to a host-native, env-configurable path. No container-to-host
translation is needed unless an explicit STAGE_OPENFILE_BASE override is set
(for future containerised callers).

  Write path: $STAGE_BASE_DIR   (default: /Users/dorseyhomeserver/Dropbox/letta-shared-files/staged)
  URL  base:  $STAGE_OPENFILE_BASE  (default: same as STAGE_BASE_DIR)

Tool: stage_resource
"""

from typing import Dict, Any, Optional


def stage_resource(
    url: Optional[str] = None,
    label: str = "",
    priority: Optional[str] = None,
    ref_id: Optional[str] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download a resource to the staging directory and return its local path.

    Used by MC during work packet assembly to stage files (PDFs, Drive docs,
    Gmail messages) on disk so the user can open them via openfile:// links
    in the OmniFocus task note.

    Idempotent: if the file already exists at the target path (less than 24
    hours old), reuses the existing file without re-downloading.

    Args:
        url: Source URL or fetch hint (now optional). Supports: HTTPS URLs
             (direct download), Google Drive/Docs URLs (fetched via gws CLI),
             Gmail message IDs in format "gmail:MSG_ID" (fetched via gws CLI).
             Mutually exclusive with text.
        label: Short descriptive label for the resource (used in filename).
        priority: Optional priority marker: "primary", "secondary", or "background". Default "secondary".
        ref_id: Optional 8-char hex ref_id of the task this resource supports. If provided, files are organized under the ref_id directory.
        text: Inline note text to stage as a markdown file instead of
              downloading a url; mutually exclusive with url.

    Returns:
        Dictionary with status, local_path, openfile_url,
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
        priority = priority or "secondary"

        # Host-native staging (local mode): the tasks-agent runs on the host via
        # the launchd runner, so it writes directly to the Dropbox-synced staging
        # tree and the openfile:// URL is that same real path — no container
        # translation. STAGE_BASE_DIR overrides for tests / future relocation.
        # STAGE_OPENFILE_BASE lets a containerised caller map the write path to a
        # host path for the URL (defaults to STAGE_BASE_DIR -> identity mapping).
        DEFAULT_BASE = "/Users/dorseyhomeserver/Dropbox/letta-shared-files/staged"
        STAGE_BASE = os.environ.get("STAGE_BASE_DIR", DEFAULT_BASE)
        OPENFILE_BASE = os.environ.get("STAGE_OPENFILE_BASE", STAGE_BASE)
        # For machine-agnostic openfile:// links: when the resolved URL path is under
        # the current user's home, emit it as a ~-relative path. The handler expands ~
        # to the LOCAL user's home, so the same link resolves on the laptop and server
        # (Dropbox syncs the file to each machine's own ~/Dropbox). The WRITE path stays
        # absolute (below) so the file is actually created. An explicit STAGE_OPENFILE_BASE
        # that points outside $HOME (e.g. a container mapping) is left untouched.
        _HOME = os.path.expanduser("~")

        try:
            os.makedirs(STAGE_BASE, exist_ok=True)
        except Exception as e:
            return {"status": "error",
                    "error_message": f"Cannot access staging directory {STAGE_BASE}: {e}"}
        if not os.access(STAGE_BASE, os.W_OK):
            return {"status": "error",
                    "error_message": f"Staging directory {STAGE_BASE} is not writable"}

        if not label:
            return {"status": "error", "error_message": "label is required"}
        if url and text is not None:
            return {"status": "error",
                    "error_message": "url and text are mutually exclusive"}
        if not url and text is None:
            return {"status": "error", "error_message": "either url or text is required"}

        if text is not None:
            # Inline-text staging -> markdown file the user can read in place.
            category = "notes"
            extension = "md"
            ref_id_part = ref_id or "orphan"
            target_dir = os.path.join(STAGE_BASE, category, ref_id_part)
            os.makedirs(target_dir, exist_ok=True)
            safe_label = re.sub(r"[^a-zA-Z0-9\-_]", "-", label)[:60].strip("-") or "note"
            filename = f"{safe_label}.{extension}"
            target_path = os.path.join(target_dir, filename)
            body = text if text.lstrip().startswith("#") else f"# {label}\n\n{text}"
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(body)
            host_path = target_path.replace(STAGE_BASE, OPENFILE_BASE, 1)
            if host_path.startswith(_HOME + os.sep):
                host_path = "~" + host_path[len(_HOME):]
            return {
                "status": "ok",
                "local_path": target_path,
                "openfile_url": f"openfile://{host_path}",
                "filename": filename,
                "size_bytes": len(body.encode("utf-8")),
                "category": category,
                "priority": priority,
                "reused": False,
            }

        # Determine category and fetch strategy from URL.
        # v1 policy: stage real files for user access. Don't snapshot Google-native
        # docs (user wants the live version) or web pages (usually not needed offline).
        # For agent-driven consumption (future), a separate tool will stage as markdown.
        category = "other"
        fetch_strategy = "http"
        extension = "bin"

        if url.startswith("gmail:"):
            category = "gmail"
            fetch_strategy = "gmail"
            extension = "txt"
        elif "docs.google.com" in url or "drive.google.com" in url:
            # Google-native docs/sheets/slides: keep live URL, don't snapshot.
            # For actual files shared via Drive (PDFs, Word docs), try alt=media.
            category = "drive"
            fetch_strategy = "drive"
        elif url.startswith("http://") or url.startswith("https://"):
            path_part = urllib.parse.urlparse(url).path.lower()
            if path_part.endswith(".pdf"):
                category = "pdf"
                extension = "pdf"
                fetch_strategy = "http"
            elif path_part.endswith((".doc", ".docx")):
                category = "doc"
                extension = path_part.rsplit(".", 1)[1]
                fetch_strategy = "http"
            elif path_part.endswith((".xls", ".xlsx")):
                category = "sheet"
                extension = path_part.rsplit(".", 1)[1]
                fetch_strategy = "http"
            elif path_part.endswith((".ppt", ".pptx")):
                category = "slides"
                extension = path_part.rsplit(".", 1)[1]
                fetch_strategy = "http"
            elif path_part.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
                category = "image"
                extension = path_part.rsplit(".", 1)[1]
                fetch_strategy = "http"
            elif path_part.endswith((".zip", ".tar", ".gz", ".tgz")):
                category = "archive"
                extension = path_part.rsplit(".", 1)[1]
                fetch_strategy = "http"
            else:
                # Not a recognized file extension — don't stage web pages.
                # User will click through to the live URL.
                return {
                    "status": "skipped",
                    "reason": "Web page URL not staged (click-through to live URL recommended)",
                    "url": url,
                }
        else:
            return {
                "status": "error",
                "error_message": f"Unsupported URL scheme: {url[:60]}",
            }

        # Build target directory and filename
        ref_id_part = ref_id or "orphan"
        target_dir = os.path.join(STAGE_BASE, category, ref_id_part)
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
                host_path = target_path.replace(STAGE_BASE, OPENFILE_BASE, 1)
                if host_path.startswith(_HOME + os.sep):
                    host_path = "~" + host_path[len(_HOME):]
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
                # Try multiple URL patterns
                file_id = None
                for pat in [
                    r"/document/d/([a-zA-Z0-9_-]+)",
                    r"/file/d/([a-zA-Z0-9_-]+)",
                    r"/spreadsheets/d/([a-zA-Z0-9_-]+)",
                    r"/presentation/d/([a-zA-Z0-9_-]+)",
                    r"[?&]id=([a-zA-Z0-9_-]+)",
                    r"/d/([a-zA-Z0-9_-]+)",
                ]:
                    m = re.search(pat, url)
                    if m:
                        file_id = m.group(1)
                        break
                if not file_id:
                    return {
                        "status": "error",
                        "error_message": f"Could not extract Drive file ID from URL: {url[:80]}",
                    }

                # Determine export MIME by probing file metadata first
                meta_result = subprocess.run(
                    ["gws", "drive", "files", "get",
                     "--params", json.dumps({"fileId": file_id, "fields": "mimeType,name"}),
                     "--format", "json"],
                    capture_output=True, text=True, timeout=15,
                )
                source_mime = None
                if meta_result.returncode == 0:
                    try:
                        meta_raw = "\n".join(l for l in meta_result.stdout.split("\n") if not l.startswith("Using keyring"))
                        meta = json.loads(meta_raw)
                        source_mime = meta.get("mimeType")
                    except Exception:
                        pass

                if not source_mime:
                    return {
                        "status": "error",
                        "error_message": f"Drive file not accessible via API (file_id={file_id}). File may be shared-with-user but not owned.",
                    }

                # Google-native docs: don't stage, user should click through to live URL
                if source_mime.startswith("application/vnd.google-apps"):
                    return {
                        "status": "skipped",
                        "reason": f"Google-native {source_mime.split('.')[-1]} — click-through to live URL recommended",
                        "url": url,
                    }

                # Non-Google file shared via Drive (PDF, Word, etc.) — download via alt=media
                export_mime = None
                # Map mimeType to extension for filename
                mime_to_ext = {
                    "application/pdf": "pdf",
                    "application/msword": "doc",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
                    "application/vnd.ms-excel": "xls",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
                    "application/vnd.ms-powerpoint": "ppt",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
                    "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
                }
                extension = mime_to_ext.get(source_mime, "bin")

                # Rebuild target path with resolved extension
                filename = f"{safe_label}.{extension}"
                target_path = os.path.join(target_dir, filename)

                # Native file — use files.get with alt=media (relative path, cd to target dir)
                output_filename = filename
                result = subprocess.run(
                    ["gws", "drive", "files", "get",
                     "--params", json.dumps({"fileId": file_id, "alt": "media"}),
                     "--output", output_filename],
                    capture_output=True, text=True, timeout=60,
                    cwd=target_dir,
                )
                if result.returncode != 0:
                    return {
                        "status": "error",
                        "error_message": f"gws drive get (alt=media) failed: {result.stderr[:200]}",
                    }
                if os.path.exists(target_path):
                    size = os.path.getsize(target_path)
                    host_path = target_path.replace(STAGE_BASE, OPENFILE_BASE, 1)
                    if host_path.startswith(_HOME + os.sep):
                        host_path = "~" + host_path[len(_HOME):]
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
                else:
                    return {"status": "error", "error_message": "gws download produced no file"}

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
        host_path = target_path.replace(STAGE_BASE, OPENFILE_BASE, 1)
        if host_path.startswith(_HOME + os.sep):
            host_path = "~" + host_path[len(_HOME):]

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
