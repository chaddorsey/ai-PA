"""xsearch — deterministic concurrent multi-channel candidate search.

Execution is deterministic + reproducible; the AGENT decides terms + judges
relevance/tiering downstream. Each channel runs in its own thread and degrades
independently — a failing channel is reported in failed_channels, never a
silent empty (the no-silent-failure rule).

Channels: tasks (this file), drive/gmail/slack (Task 3), canonical/history/
reference/meetings (Task 4).

Normalized candidate: {channel,title,url,permalink,snippet,date,id}
"""
from typing import Dict, Any, List
import subprocess
import json


def _dedup(rows: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for r in rows:
        key = (r.get("channel"), r.get("url") or r.get("permalink") or r.get("id") or r.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _search_tasks(terms: List[str], limit: int) -> List[dict]:
    """pa_web.tasks ILIKE over raw/suggested/confirmed/task_body for any term."""
    import os
    import psycopg
    from psycopg.rows import dict_row
    pg = os.environ.get("PA_WEB_POSTGRES_URL")
    if not pg:
        pw = os.environ.get("POSTGRES_PASSWORD", "")
        port = os.environ.get("PA_WEB_POSTGRES_PORT", "5433")
        pg = f"postgresql://postgres:{pw}@localhost:{port}/postgres"
    like = [f"%{t}%" for t in terms if t]
    if not like:
        return []
    clauses = " OR ".join(
        ["(raw_description ILIKE %s OR suggested_title ILIKE %s OR "
         "confirmed_title ILIKE %s OR task_body ILIKE %s)"] * len(like)
    )
    params = []
    for p in like:
        params += [p, p, p, p]
    sql = (
        "SELECT ref_id, COALESCE(suggested_title, raw_description, '') AS title, "
        "source, source_ref, COALESCE(extracted_at, created_at) AS dt "
        "FROM pa_web.tasks WHERE closed_at IS NULL AND (" + clauses + ") "
        "ORDER BY dt DESC NULLS LAST LIMIT %s"
    )
    params.append(limit)
    out = []
    with psycopg.connect(pg, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            for r in cur.fetchall():
                out.append({
                    "channel": "tasks", "title": r["title"][:120],
                    "url": "", "permalink": "",
                    "snippet": f"{r['source']} {r['source_ref']}",
                    "date": str(r["dt"] or "")[:10], "id": r["ref_id"],
                })
    return out


def _gws_json(args: List[str], timeout: int = 20) -> dict:
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"gws failed: {r.stderr[:160]}")
    raw = "\n".join(l for l in r.stdout.split("\n") if not l.startswith("Using keyring"))
    return json.loads(raw) if raw.strip() else {}


def _search_drive(terms: List[str], limit: int) -> List[dict]:
    q = " or ".join([f"fullText contains '{t}'" for t in terms[:5]])
    data = _gws_json(["drive", "files", "list", "--params", json.dumps({
        "q": q, "pageSize": limit, "orderBy": "modifiedTime desc",
        "fields": "files(id,name,webViewLink,modifiedTime,mimeType)"}), "--format", "json"])
    out = []
    for f in data.get("files", []):
        out.append({"channel": "drive", "title": f.get("name", "")[:120],
                    "url": f.get("webViewLink", ""), "permalink": f.get("webViewLink", ""),
                    "snippet": f.get("mimeType", ""), "date": (f.get("modifiedTime") or "")[:10],
                    "id": f.get("id", "")})
    return out


def _search_gmail(terms: List[str], limit: int) -> List[dict]:
    q = " OR ".join([f'"{t}"' for t in terms[:5]])
    data = _gws_json(["gmail", "users", "messages", "list", "--params", json.dumps({
        "userId": "me", "q": q, "maxResults": limit}), "--format", "json"])
    out = []
    for m in data.get("messages", [])[:limit]:
        mid = m.get("id", "")
        meta = _gws_json(["gmail", "users", "messages", "get", "--params", json.dumps({
            "userId": "me", "id": mid, "format": "metadata",
            "metadataHeaders": ["Subject", "From", "Date"]}), "--format", "json"])
        hdr = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
        out.append({"channel": "gmail", "title": hdr.get("Subject", "(no subject)")[:120],
                    "url": f"https://mail.google.com/mail/u/0/#all/{mid}",
                    "permalink": f"https://mail.google.com/mail/u/0/#all/{mid}",
                    "snippet": (hdr.get("From", "") + " — " + meta.get("snippet", ""))[:160],
                    "date": hdr.get("Date", "")[:16], "id": mid})
    return out


def _search_slack(terms: List[str], limit: int) -> List[dict]:
    query = " ".join(terms[:4])
    r = subprocess.run(
        ["slack", "--format", "json", "search", "messages", "--query", query, "--count", str(limit)],
        capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise RuntimeError(f"slack failed: {r.stderr[:160]}")
    data = json.loads(r.stdout) if r.stdout.strip() else {}
    msgs = data.get("messages")
    matches = msgs.get("matches", []) if isinstance(msgs, dict) else []
    out = []
    for m in matches[:limit]:
        ch = m.get("channel") or {}
        out.append({"channel": "slack", "title": (m.get("text", "") or "")[:120],
                    "url": m.get("permalink", ""), "permalink": m.get("permalink", ""),
                    "snippet": (ch.get("name", "") if isinstance(ch, dict) else str(ch)),
                    "date": str(m.get("ts", ""))[:10], "id": m.get("ts", "")})
    return out


# channel name → search fn. Tasks 3+4 extend this map.
_CHANNELS = {
    "tasks": _search_tasks,
}

_CHANNELS.update({"drive": _search_drive, "gmail": _search_gmail, "slack": _search_slack})


def xsearch(terms: List[str], channels: List[str] = None,
            limit_per_channel: int = 8) -> Dict[str, Any]:
    import concurrent.futures
    channels = channels or list(_CHANNELS.keys())
    chans = [c for c in channels if c in _CHANNELS]
    candidates: List[dict] = []
    failed: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_CHANNELS[c], terms, limit_per_channel): c for c in chans}
        for fut in concurrent.futures.as_completed(futs):
            c = futs[fut]
            try:
                candidates.extend(fut.result())
            except Exception as e:
                failed.append({"channel": c, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    unknown = [c for c in channels if c not in _CHANNELS]
    for c in unknown:
        failed.append({"channel": c, "error": "unknown channel"})
    return {"status": "ok", "candidates": _dedup(candidates), "failed_channels": failed}
