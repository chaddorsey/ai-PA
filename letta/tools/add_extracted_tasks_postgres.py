"""
add_extracted_tasks_postgres Letta tool.

Replaces the legacy v1 add_extracted_tasks tool that PATCHed the
extracted_tasks shared block + wrote an archival passage. Writes
directly to pa_web.tasks instead.

Schema reminder (pa_web.tasks key columns):
- ref_id (PK), source, source_ref, origin, extracted_by, extracted_at
- suggested_title, raw_description, original_est_minutes, due_date,
  priority, owner
- task_body, source_metadata (jsonb), related_urls (text[])
- status, tags
- migration_source ('live' set automatically here)
"""

from typing import Dict, Any, Optional


def add_extracted_tasks_postgres(
    ref_id: str,
    raw_description: str,
    source: str,
    source_ref: Optional[str] = None,
    origin: Optional[str] = None,
    suggested_title: Optional[str] = None,
    task_body: Optional[str] = None,
    original_est_minutes: Optional[int] = None,
    due_date: Optional[str] = None,
    priority: Optional[int] = None,
    owner: Optional[str] = None,
    source_metadata_json: Optional[str] = None,
    related_urls_csv: Optional[str] = None,
    tags_csv: Optional[str] = None,
    extracted_by: Optional[str] = None,
    location: Optional[str] = None,
    location_id: Optional[str] = None,
    source_timestamp: Optional[str] = None,
    from_person: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert a newly-extracted task into pa_web.tasks.

    Idempotent on ref_id: re-inserting the same ref_id returns the
    existing row unchanged (no UPDATE). Use the pa-web-ui sidebar /
    api_update_task for mutations after creation.

    Args:
        ref_id: 8-character hex slug uniquely identifying the task. REQUIRED.
        raw_description: Concise task description (single sentence).
                         Becomes the block-line layer's primary content. REQUIRED.
        source: Where the task came from. One of: 'email', 'slack', 'meeting',
                'drive', or any custom origin. REQUIRED.
        source_ref: Source-system reference (gmail msg-id, slack ts,
                    meeting_id, drive file-id). Optional.
        origin: Human-readable origin context (e.g., "From: Danielle re: Q3").
                Optional.
        suggested_title: Concise 6-10-word title proposed by the agent.
                         User confirms via sidebar (writes confirmed_title later).
        task_body: Full multi-paragraph task description for archival
                   detail. Optional.
        original_est_minutes: Agent's first-pass time estimate in minutes.
                              Optional.
        due_date: ISO date string YYYY-MM-DD. Optional.
        priority: Integer 1-3 (1=highest). Optional.
        owner: Owner name (e.g., 'chad'). Optional.
        source_metadata_json: JSON string with source-specific metadata
                              (sender, thread_id, received_at, etc.).
                              Optional.
        related_urls_csv: Comma-separated URL list. Optional.
        tags_csv: Comma-separated tag list (e.g., "work,q3-planning").
                  Optional.
        extracted_by: Agent name or service that extracted this task
                      (e.g., 'tasks-agent', 'gmail-watch'). Optional.
        location: Human-readable source location (e.g., meeting title,
                  Slack channel name). Folded into source_metadata.
                  Optional.
        location_id: Source-system ID for the location (meeting_id,
                     slack channel_id, doc_id). Folded into
                     source_metadata. Optional.
        source_timestamp: ISO timestamp of when the source occurred
                          (meeting start, message ts, comment created_at).
                          Folded into source_metadata. Optional.
        from_person: Source author name + email (e.g.,
                     "Jane Doe <jane@example.com>"). Folded into
                     source_metadata. Optional.

    Returns:
        Dictionary with:
        - status: "ok", "exists", or "error"
        - ref_id: the ref_id (echoed)
        - inserted: bool — True if a new row was created, False if it
                    already existed (status="exists")
        - row: the canonical row dict on success
        - error_message: present only when status="error"
    """
    # ALL IMPORTS INSIDE FUNCTION - required for Letta tool extraction
    import os
    import json
    import traceback
    from datetime import datetime, timezone

    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except Exception as e:
        return {
            "status": "error",
            "ref_id": ref_id,
            "inserted": False,
            "row": None,
            "error_message": f"psycopg import failed: {e}",
        }

    try:
        # Validate required inputs
        if not ref_id or not isinstance(ref_id, str):
            return {"status": "error", "ref_id": ref_id, "inserted": False, "row": None,
                    "error_message": "ref_id is required and must be a string"}
        if not raw_description or not isinstance(raw_description, str):
            return {"status": "error", "ref_id": ref_id, "inserted": False, "row": None,
                    "error_message": "raw_description is required and must be a string"}
        if not source or not isinstance(source, str):
            return {"status": "error", "ref_id": ref_id, "inserted": False, "row": None,
                    "error_message": "source is required and must be a string"}

        # Parse optional structured fields (inline — no nested defs)
        source_metadata = None
        if source_metadata_json:
            try:
                source_metadata = json.loads(source_metadata_json)
            except json.JSONDecodeError as e:
                return {"status": "error", "ref_id": ref_id, "inserted": False, "row": None,
                        "error_message": f"source_metadata_json is not valid JSON: {e}"}

        # Fold convenience kwargs (location, location_id, source_timestamp,
        # from_person) into source_metadata if the agent passed them as
        # top-level args. This matches what callers like scan_meeting_notes
        # naturally produce; without these the LLM commonly passes them
        # as bare kwargs and Letta's tool runner errors with NameError.
        _convenience_extras = {
            "location": location,
            "location_id": location_id,
            "source_timestamp": source_timestamp,
            "from_person": from_person,
        }
        _convenience_extras = {k: v for k, v in _convenience_extras.items() if v}
        if _convenience_extras:
            if source_metadata is None:
                source_metadata = {}
            for k, v in _convenience_extras.items():
                source_metadata.setdefault(k, v)

        related_urls = None
        if related_urls_csv:
            related_urls = [u.strip() for u in related_urls_csv.split(",") if u.strip()]

        tags = None
        if tags_csv:
            tags = [t.strip() for t in tags_csv.split(",") if t.strip()]

        due_date_value = None
        if due_date:
            # Validate ISO format inline
            try:
                due_date_value = datetime.strptime(due_date, "%Y-%m-%d").date()
            except ValueError as e:
                return {"status": "error", "ref_id": ref_id, "inserted": False, "row": None,
                        "error_message": f"due_date must be YYYY-MM-DD: {e}"}

        # Postgres connection
        pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
        if not pg_url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            pg_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

        # ON CONFLICT DO NOTHING + RETURNING gives us "did this insert?"
        # Then a follow-up SELECT to fetch the canonical row regardless.
        # status='extracted' marks the row as raw-capture awaiting triage;
        # enrichment_state='pending' queues it for the cycle-1 enrichment
        # pipeline (enrichment-scanner.py picks up pending rows).
        insert_sql = """
            INSERT INTO pa_web.tasks (
                ref_id, raw_description, source, source_ref, origin,
                suggested_title, task_body, original_est_minutes,
                due_date, priority, owner,
                source_metadata, related_urls, tags,
                extracted_by, extracted_at,
                status, enrichment_state,
                migration_source, created_at, updated_at
            ) VALUES (
                %(ref_id)s, %(raw_description)s, %(source)s, %(source_ref)s, %(origin)s,
                %(suggested_title)s, %(task_body)s, %(original_est_minutes)s,
                %(due_date)s, %(priority)s, %(owner)s,
                %(source_metadata)s, %(related_urls)s, %(tags)s,
                %(extracted_by)s, NOW(),
                %(status)s, 'pending',
                'live', NOW(), NOW()
            )
            ON CONFLICT (ref_id) DO NOTHING
            RETURNING ref_id
        """
        select_sql = "SELECT * FROM pa_web.tasks WHERE ref_id = %s"

        params = {
            "ref_id": ref_id,
            "raw_description": raw_description,
            "source": source,
            "source_ref": source_ref,
            "origin": origin,
            "suggested_title": suggested_title,
            "task_body": task_body,
            "original_est_minutes": original_est_minutes,
            "due_date": due_date_value,
            "priority": priority,
            "owner": owner,
            "source_metadata": Jsonb(source_metadata) if source_metadata is not None else None,
            "related_urls": related_urls,
            "tags": tags if tags is not None else [],
            "extracted_by": extracted_by,
            # status='extracted' = raw capture awaiting triage; this also
            # signals to enrichment-scanner.py that the row is a candidate.
            "status": "extracted",
        }

        with psycopg.connect(pg_url, autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(insert_sql, params)
                inserted_row = cur.fetchone()
                inserted = inserted_row is not None
                cur.execute(select_sql, (ref_id,))
                row = cur.fetchone()

        # Coerce datetimes/dates to ISO strings for JSON-safety
        if row:
            for k, v in list(row.items()):
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()

        return {
            "status": "ok" if inserted else "exists",
            "ref_id": ref_id,
            "inserted": inserted,
            "row": row,
        }

    except Exception as e:
        return {
            "status": "error",
            "ref_id": ref_id,
            "inserted": False,
            "row": None,
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
