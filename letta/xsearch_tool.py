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


# channel name → search fn. Tasks 3+4 extend this map.
_CHANNELS = {
    "tasks": _search_tasks,
}


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
