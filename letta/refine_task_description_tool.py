"""
refine_task_description — cycle-1 Postgres-canonical version.

Updates the suggested_title (agent's evolving proposed name) for a
task in pa_web.tasks. The pre-cycle-1 version PATCHed the
extracted_tasks BLOCK + replaced the archival passage. Both retired in
cycle-1; pa_web.tasks is canonical.

Per the user's title-lifecycle spec:
- suggested_title: agent's original/refined proposal (what this tool writes)
- confirmed_title: user-finalized via sidebar Confirm action (NOT touched here)

Tool: refine_task_description
"""

from typing import Dict, Any


def refine_task_description(ref_id: str, new_description: str, force: bool = False) -> Dict[str, Any]:
    """
    Update the agent's suggested_title for an extracted task.

    Args:
        ref_id: The 8-char hex reference ID of the task to refine.
        new_description: The refined verb-led task description (max ~120 chars).
        force: If True, bypass the anchor-drift guard. Default False. Use only
               when raw_description is genuinely malformed (truncated, opaque,
               empty) AND ambient context unambiguously establishes the new topic.

    Returns:
        Dictionary with:
          - status: "ok" or "error"
          - ref_id: the ref_id (echoed)
          - old_suggested_title: prior value (may be None)
          - new_suggested_title: the saved value
          - error_message: present only when status="error"
    """
    # ALL IMPORTS INSIDE FUNCTION - required for Letta tool extraction
    import os
    import traceback

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as e:
        return {
            "status": "error",
            "ref_id": ref_id,
            "error_message": f"psycopg import failed: {e}",
        }

    try:
        if not ref_id or not isinstance(ref_id, str):
            return {"status": "error", "ref_id": ref_id,
                    "error_message": "ref_id is required"}
        if not new_description or not isinstance(new_description, str):
            return {"status": "error", "ref_id": ref_id,
                    "error_message": "new_description is required"}
        new_description = new_description.strip()
        if len(new_description) > 500:
            new_description = new_description[:500]

        pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
        if not pg_url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            pg_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

        with psycopg.connect(pg_url, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT ref_id, suggested_title, raw_description, origin "
                    "FROM pa_web.tasks WHERE ref_id = %s",
                    (ref_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return {
                        "status": "error",
                        "ref_id": ref_id,
                        "error_message": f"No row in pa_web.tasks for ref_id {ref_id}",
                    }
                old_title = row.get("suggested_title")
                raw_desc = row.get("raw_description") or ""
                origin = row.get("origin") or ""

                # ── Anchor-drift guard ──
                # When raw_description is the user-supplied/anchor task
                # statement, refuse overwrites that drop too much of its
                # content-word overlap. This stops the agent from synthesizing
                # a different task from ambient thread/channel context.
                if not force and raw_desc and len(raw_desc.split()) >= 3:
                    STOP = {"a","an","the","and","or","but","for","of","in",
                            "on","to","at","by","is","it","be","as","do","if",
                            "so","this","that","with","from","have","has","are",
                            "was","will","can","our","any","i","we","me","my",
                            "you","your","he","she","they","them","his","her"}
                    def _content_words(s):
                        out = set()
                        for w in s.lower().replace("'", "").split():
                            w = "".join(c for c in w if c.isalnum())
                            if len(w) > 2 and w not in STOP:
                                out.add(w)
                        return out
                    raw_words = _content_words(raw_desc)
                    new_words = _content_words(new_description)
                    if raw_words:
                        overlap = len(raw_words & new_words) / max(1, len(raw_words))
                        if overlap < 0.30:
                            return {
                                "status": "blocked_drift",
                                "ref_id": ref_id,
                                "old_suggested_title": old_title,
                                "raw_description": raw_desc,
                                "proposed_new_description": new_description,
                                "content_word_overlap": round(overlap, 2),
                                "error_message": (
                                    f"Refused: proposed new_description has only "
                                    f"{overlap:.0%} content-word overlap with the "
                                    f"user-supplied raw_description. The task "
                                    f"statement must anchor on the user-selected "
                                    f"message; ambient thread/channel context is "
                                    f"for enrichment fields, not redefinition. "
                                    f"If raw_description is genuinely malformed, "
                                    f"call again with force=True (rare)."
                                ),
                            }

                cur.execute(
                    """UPDATE pa_web.tasks
                          SET suggested_title = %s,
                              updated_at = NOW(),
                              migration_source = 'live'
                        WHERE ref_id = %s
                        RETURNING suggested_title""",
                    (new_description, ref_id),
                )
                updated = cur.fetchone()

        return {
            "status": "ok",
            "ref_id": ref_id,
            "old_suggested_title": old_title,
            "new_suggested_title": updated["suggested_title"] if updated else new_description,
        }

    except Exception as e:
        return {
            "status": "error",
            "ref_id": ref_id,
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
