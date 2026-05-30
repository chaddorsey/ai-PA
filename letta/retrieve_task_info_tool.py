"""
Retrieve Task Info Tool for Letta — cycle-1 pg-canonical rewrite.

Reads from pa_web.tasks instead of the deprecated extracted_tasks_archive.
Same return shape as the original archival-backed version, so callers
(persona, system-prompt recipes, downstream tool chains) keep working
unchanged.

Substrate mapping (archival passage field → pa_web.tasks column):
    REF_ID                  → ref_id
    TASK: <title>           → suggested_title / confirmed_title / raw_description
    - Type:                 → source
    - Context:              → source_metadata->>'source_context'  (best-effort)
    - Reference ID:         → source_ref
    - From:                 → source_metadata->>'from_person'      (best-effort)
    - Location:             → source_metadata->>'location'         (best-effort)
    - Source: <iso>         → extracted_at (ISO)
    - Due:                  → due_date
    - Priority:             → priority
    - Status:               → status (OmniFocus sync state)
    RELATED URLS            → related_urls (text[])
    MERGED_IDS              → merge_parent_id / merged_into

Merged tasks: pa_web.tasks tracks merges via merge_parent_id (child →
parent) and merged_into (the absorbed ref_id at the leaf row). For a
parent row, child rows are: SELECT ref_id FROM pa_web.tasks WHERE
merge_parent_id = <parent>. For each child, emit a merged_sources
entry shaped like the legacy passage's child summary.

Tool: retrieve_task_info
"""

from typing import Dict, Any, Optional


def retrieve_task_info(
    ref_id: str,
) -> Dict[str, Any]:
    """
    Look up an extracted task by ref_id and return its source context.

    Reads from pa_web.tasks (cycle-1 canonical store). Replaces the
    previous version that read from the extracted_tasks_archive Letta
    archival memory.

    Handles merged tasks: if a row has child rows pointing back via
    merge_parent_id, their source details are returned in merged_sources.

    Args:
        ref_id: The 8-character hex reference ID to look up (e.g.,
            "9257de13"). Matches the ref_id PK in pa_web.tasks.

    Returns:
        Dictionary with keys (all present; empty when not applicable):
        - status: "ok", "not_found", or "error"
        - ref_id, passage_id (kept for API compat — empty in pg version)
        - task_description: confirmed_title || suggested_title || raw_description
        - is_merged, merged_ids
        - source_type, source_context, reference_id, from_person, location
        - source_timestamp (ISO 8601 from extracted_at)
        - due_date, priority, omnifocus_status (from status)
        - related_urls: list[str]
        - full_text: synthesized passage-shaped string (for legacy callers
          that scan for fields with regex)
        - tags: list[str] (from pa_web.tasks.tags)
        - merged_sources: list of dicts (ref_id, task_description,
          source_type, source_context, from_person, location,
          source_timestamp, full_text)
        - error_message: present only when status="error"
    """
    import os
    import traceback

    EMPTY_RESULT = {
        "status": "error", "ref_id": "", "passage_id": "",
        "task_description": "", "is_merged": False, "merged_ids": [],
        "source_type": "", "source_context": "", "reference_id": "",
        "from_person": "", "location": "", "source_timestamp": "",
        "due_date": "", "priority": "", "omnifocus_status": "",
        "related_urls": [], "full_text": "", "tags": [], "merged_sources": [],
        "error_message": "",
    }

    try:
        if not ref_id or not str(ref_id).strip():
            r = dict(EMPTY_RESULT)
            r["error_message"] = "ref_id is required"
            return r
        ref_id = str(ref_id).strip()

        # psycopg import is wrapped so the missing-dep error surfaces clearly
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as e:
            r = dict(EMPTY_RESULT)
            r["ref_id"] = ref_id
            r["error_message"] = f"psycopg import failed: {e}"
            return r

        pg_password = os.getenv("POSTGRES_PASSWORD", "")
        pg_url = os.getenv(
            "PA_WEB_POSTGRES_URL",
            f"postgresql://postgres:{pg_password}@supabase-db:5432/postgres",
        )

        def _row_to_fields(row):
            """Project a pa_web.tasks row to the legacy field dict + full_text."""
            sm = row.get("source_metadata") or {}
            if not isinstance(sm, dict):
                sm = {}
            extracted_iso = ""
            ext_at = row.get("extracted_at") or row.get("created_at")
            if ext_at is not None and hasattr(ext_at, "isoformat"):
                extracted_iso = ext_at.isoformat()
            due_iso = ""
            dd = row.get("due_date")
            if dd is not None and hasattr(dd, "isoformat"):
                due_iso = dd.isoformat()

            title = (
                row.get("confirmed_title")
                or row.get("suggested_title")
                or row.get("raw_description")
                or ""
            )
            source_type = row.get("source") or ""
            source_context = sm.get("source_context") or sm.get("context") or ""
            reference_id = row.get("source_ref") or ""
            from_person = sm.get("from_person") or sm.get("from") or row.get("owner") or ""
            location = sm.get("location") or ""
            priority_val = row.get("priority")
            priority_str = "" if priority_val is None else str(priority_val)
            of_status = row.get("status") or ""

            tags = row.get("tags") or []
            if not isinstance(tags, list):
                tags = []

            related = row.get("related_urls") or []
            if not isinstance(related, list):
                related = []

            # Synthesize a passage-shaped body so legacy regex callers
            # still find the fields they expect.
            lines = [
                f"REF_ID: {row.get('ref_id', '')}",
                f"TASK: {title}",
                f"- Type: {source_type}",
                f"- Context: {source_context}",
                f"- Reference ID: {reference_id}",
                f"- From: {from_person}",
                f"- Location: {location}",
                f"- Source: {extracted_iso}",
                f"- Due: {due_iso}",
                f"- Priority: {priority_str}",
                f"- Status: {of_status}",
            ]
            if related:
                lines.append("RELATED URLS")
                for u in related:
                    lines.append(f"- {u}")
            full_text = "\n".join(lines)

            return {
                "task_description": title,
                "source_type": source_type,
                "source_context": source_context,
                "reference_id": reference_id,
                "from_person": from_person,
                "location": location,
                "source_timestamp": extracted_iso,
                "due_date": due_iso,
                "priority": priority_str,
                "omnifocus_status": of_status,
                "related_urls": related,
                "full_text": full_text,
                "tags": tags,
            }

        with psycopg.connect(pg_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT ref_id, source, source_ref, status,
                           extracted_at, created_at,
                           raw_description, suggested_title, confirmed_title,
                           due_date, priority, owner,
                           source_metadata, related_urls, tags,
                           merged_into, merge_parent_id
                      FROM pa_web.tasks
                     WHERE ref_id = %s
                    """,
                    (ref_id,),
                )
                row = cur.fetchone()

                if not row:
                    r = dict(EMPTY_RESULT)
                    r["status"] = "not_found"
                    r["ref_id"] = ref_id
                    r["error_message"] = (
                        f"No row found in pa_web.tasks with ref_id={ref_id}"
                    )
                    return r

                primary_fields = _row_to_fields(row)

                # Detect merged-parent: rows pointing at this one via
                # merge_parent_id are the merged children.
                cur.execute(
                    """
                    SELECT ref_id, source, source_ref, status,
                           extracted_at, created_at,
                           raw_description, suggested_title, confirmed_title,
                           due_date, priority, owner,
                           source_metadata, related_urls, tags,
                           merged_into, merge_parent_id
                      FROM pa_web.tasks
                     WHERE merge_parent_id = %s
                    """,
                    (ref_id,),
                )
                child_rows = cur.fetchall() or []

        merged_sources = []
        for child in child_rows:
            cf = _row_to_fields(child)
            merged_sources.append({
                "ref_id": child.get("ref_id", ""),
                "task_description": cf["task_description"],
                "source_type": cf["source_type"],
                "source_context": cf["source_context"],
                "from_person": cf["from_person"],
                "location": cf["location"],
                "source_timestamp": cf["source_timestamp"],
                "full_text": cf["full_text"],
            })

        merged_ids = [c.get("ref_id", "") for c in child_rows if c.get("ref_id")]
        is_merged = bool(merged_ids)

        return {
            "status": "ok",
            "ref_id": ref_id,
            "passage_id": "",  # API-compat field; archival passage IDs are gone
            "is_merged": is_merged,
            "merged_ids": merged_ids,
            "merged_sources": merged_sources,
            "error_message": "",
            **primary_fields,
        }

    except Exception as e:
        r = dict(EMPTY_RESULT)
        r["ref_id"] = ref_id if isinstance(ref_id, str) else ""
        r["error_message"] = f"{str(e)}\n{traceback.format_exc()}"
        return r
