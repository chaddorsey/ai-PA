"""Read-modify-write of canonical markdown files via the Gitea contents API."""
import base64
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("GITEA_BASE_URL", "http://127.0.0.1:3030").rstrip("/")
TOKEN = os.environ.get("GITEA_MEMFS_TOKEN", "")
REPO = f"{BASE}/api/v1/repos/agents/agents-canonical"

_FRONT = ("---\n"
          "description: {title}\n"
          "source: bookmark-archiver\n"
          "attention_level: routine\n"
          "mentioned_entities: []\n"
          "---\n\n")


def prepend_entries(existing: str, entries: list[str], title: str) -> str:
    """Insert entries (newest first) right after the frontmatter block."""
    block = "\n".join(entries).rstrip() + "\n"
    if not existing.strip():
        return _FRONT.format(title=title) + block
    if existing.startswith("---\n"):
        end = existing.find("\n---\n", 4)
        if end != -1:
            head = existing[:end + 5]
            rest = existing[end + 5:].lstrip("\n")
            return head + "\n" + block + "\n" + rest
    return _FRONT.format(title=title) + block + "\n" + existing


def _get(path: str):
    req = urllib.request.Request(f"{REPO}/contents/{path}?ref=main",
                                 headers={"Authorization": f"token {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            return base64.b64decode(d["content"]).decode("utf-8"), d.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "", None
        raise


def write_entries(path: str, entries: list[str], title: str) -> str:
    """Prepend entries to the canonical file at path; return html_url."""
    existing, sha = _get(path)
    content = prepend_entries(existing, entries, title)
    body = {"branch": "main", "message": f"bookmarks: +{len(entries)} to {path}",
            "content": base64.b64encode(content.encode()).decode("ascii")}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        f"{REPO}/contents/{path}", data=json.dumps(body).encode(),
        method="PUT" if sha else "POST",
        headers={"Authorization": f"token {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return (json.loads(r.read()).get("content") or {}).get("html_url", "")
