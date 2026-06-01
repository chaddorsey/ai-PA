"""
consume_queue Letta tool.

Atomic row-claim against pa_web.task_queue. Replaces the v1 pattern of
reading queue blocks, parsing JSON, and PATCHing the block.

Single-statement claim: SELECT ... FOR UPDATE SKIP LOCKED + UPDATE
combined into one statement so the row lock survives the sandbox
subprocess lifecycle (a two-statement SELECT-then-UPDATE would lose the
lock when the subprocess returns).
"""

from typing import Dict, Any


def consume_queue(source: str, limit: int = 10) -> Dict[str, Any]:
    """
    Claim up to N unclaimed rows from pa_web.task_queue for a given source.

    Atomically marks the claimed rows with NOW() in claimed_at and returns
    them. Subsequent calls won't see these rows again. The caller is
    responsible for processing them and (optionally) marking processed_at.

    Args:
        source: Queue source to read from. Must be one of:
                'email', 'slack', 'drive', 'meeting', 'meeting_marker'.
        limit: Maximum number of rows to claim. Defaults to 10. Capped at
               100 to avoid runaway claims.

    Returns:
        Dictionary with:
        - status: "ok" or "error"
        - rows: list of claimed row dicts (id, source, source_ref, payload,
                created_at, claimed_at), empty list if nothing available
        - count: int — number of rows claimed
        - error_message: present only when status="error"
    """
    # ALL IMPORTS INSIDE FUNCTION - required for Letta tool extraction
    import os
    import json
    import traceback

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as e:
        return {
            "status": "error",
            "rows": [],
            "count": 0,
            "error_message": f"psycopg import failed: {e}",
        }

    try:
        # Validate inputs
        VALID_SOURCES = {"email", "slack", "drive", "meeting", "meeting_marker", "google-docs-comment", "email-watch", "mc-completion", "docs-meeting"}
        if source not in VALID_SOURCES:
            return {
                "status": "error",
                "rows": [],
                "count": 0,
                "error_message": f"invalid source '{source}'; must be one of {sorted(VALID_SOURCES)}",
            }
        if limit is None or limit < 1:
            limit = 10
        if limit > 100:
            limit = 100

        # Postgres URL — sandbox runs inside the letta container on pa-internal network
        pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
        if not pg_url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            pg_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

        sql = """
            UPDATE pa_web.task_queue
               SET claimed_at = NOW()
             WHERE id IN (
                 SELECT id FROM pa_web.task_queue
                  WHERE claimed_at IS NULL AND source = %s
                  ORDER BY created_at
                  LIMIT %s
                  FOR UPDATE SKIP LOCKED
             )
           RETURNING id, source, source_ref, payload, created_at, claimed_at
        """

        with psycopg.connect(pg_url, autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, (source, limit))
                rows = cur.fetchall()

        # Coerce datetimes + jsonb to JSON-safe primitives
        normalized = []
        for r in rows:
            normalized.append({
                "id": r["id"],
                "source": r["source"],
                "source_ref": r["source_ref"],
                "payload": r["payload"] if isinstance(r["payload"], (dict, list)) else json.loads(r["payload"] or "{}"),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "claimed_at": r["claimed_at"].isoformat() if r["claimed_at"] else None,
            })

        return {"status": "ok", "rows": normalized, "count": len(normalized)}

    except Exception as e:
        return {
            "status": "error",
            "rows": [],
            "count": 0,
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
