"""
write_packet_info — cycle-1 Postgres-canonical version.

Writes the agent's synthesized PACKET INFO into pa_web.tasks.enrichment
JSONB column. The pre-cycle-1 version wrote a PACKET INFO section to
the archival passage text. Both stores remain readable, but this tool
now writes ONLY to pa_web.tasks (cycle-1 canonical).

The enrichment JSONB shape:
    {
      "packet_info": {
        "direct_action": "...",
        "artifact_provenance": "...",
        "intent_genesis": "...",
        "context_brief": ["...", "..."],          # list of bullets (lines)
        "resources": ["[primary] ... — url ..."],  # list of resource lines
        "related_tasks": ["...", "..."],           # list of ref_id + desc
        "knowns": ["...", "..."],
        "unknowns": ["...", "..."],
        "mismatch_warnings": ["..."],              # list (rare)
        "additional_notes": "..."                  # free-form
      },
      "enriched_at": "<iso>",
      "enriched_by": "<agent-name-or-id>",
      "phase": "phase-a-complete"  (or "phase-b-complete" with backtrace)
    }

Side effect: enrichment_state flips to 'done', closing the loop with
the enrichment-scanner.

Tool: write_packet_info
"""

from typing import Dict, Any, Optional


def write_packet_info(
    ref_id: str,
    direct_action: str,
    artifact_provenance: Optional[str] = None,
    intent_genesis: Optional[str] = None,
    context_brief: Optional[str] = None,
    resources: Optional[str] = None,
    related_tasks: Optional[str] = None,
    knowns: Optional[str] = None,
    unknowns: Optional[str] = None,
    mismatch_warnings: Optional[str] = None,
    additional_notes: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Persist synthesized work-packet context to pa_web.tasks.enrichment.

    Args:
        ref_id: The 8-char hex reference ID of the task. REQUIRED.
        direct_action: Direct-action node summary (who asked, where, what's done). REQUIRED.
        artifact_provenance: Primary artifact location and provenance chain. Optional.
        intent_genesis: Why/strategy/constraints — prior decisions, meetings, context. Optional.
        context_brief: 3-5 bullet synthesis of context. One bullet per line. Optional.
        resources: Key resources for execution. One per line: "[priority] label — url (role)". Optional.
        related_tasks: One per line: ref_id + short description of related tasks. Optional.
        knowns: What is established and verified. One per line. Optional.
        unknowns: What is missing or unresolved. One per line. Optional.
        mismatch_warnings: Overlap/conflict warnings to flag prominently. Optional.
        additional_notes: Any other free-form synthesis. Optional.
        estimated_minutes: Your best estimate of how long this task will take to
            DO, in minutes (think realistically about the actual work; round to
            the nearest 5). Sets the immutable agent baseline original_est_minutes
            — only applied when it is not already set, so re-enrichment never
            overwrites it and never touches the user's revision or actual time. Optional.

    Returns:
        Dictionary with:
          - status: "ok" or "error"
          - ref_id: the ref_id (echoed)
          - enrichment: the resulting enrichment dict that was saved
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
            "error_message": f"psycopg import failed: {e}",
        }

    try:
        if not ref_id or not isinstance(ref_id, str):
            return {"status": "error", "ref_id": ref_id,
                    "error_message": "ref_id is required"}
        if not direct_action or not isinstance(direct_action, str):
            return {"status": "error", "ref_id": ref_id,
                    "error_message": "direct_action is required"}

        # Parse multi-line free-form fields into list-of-strings (one item per
        # line, trimmed, empties dropped). Inlined — NO nested def: Letta's
        # schema generation recurses into nested functions and requires full
        # annotations + docstrings, which broke tool re-registration.
        packet_info = {
            "direct_action": direct_action.strip(),
        }
        if artifact_provenance:
            packet_info["artifact_provenance"] = artifact_provenance.strip()
        if intent_genesis:
            packet_info["intent_genesis"] = intent_genesis.strip()
        cb = [ln.strip() for ln in (context_brief or "").split("\n") if ln.strip()]
        if cb:
            packet_info["context_brief"] = cb
        rs = [ln.strip() for ln in (resources or "").split("\n") if ln.strip()]
        if rs:
            packet_info["resources"] = rs
        rt = [ln.strip() for ln in (related_tasks or "").split("\n") if ln.strip()]
        if rt:
            packet_info["related_tasks"] = rt
        kn = [ln.strip() for ln in (knowns or "").split("\n") if ln.strip()]
        if kn:
            packet_info["knowns"] = kn
        un = [ln.strip() for ln in (unknowns or "").split("\n") if ln.strip()]
        if un:
            packet_info["unknowns"] = un
        mw = [ln.strip() for ln in (mismatch_warnings or "").split("\n") if ln.strip()]
        if mw:
            packet_info["mismatch_warnings"] = mw
        if additional_notes:
            packet_info["additional_notes"] = additional_notes.strip()

        # Agent time estimate -> immutable original_est_minutes baseline.
        # Coerce to a positive int; None if absent/invalid. Persisted via
        # COALESCE so it is set ONLY when currently NULL (never overwrites the
        # agent's first estimate, the user's revision, or the recorded actual).
        est = None
        if estimated_minutes is not None:
            try:
                raw = float(estimated_minutes)
                if raw > 0:
                    est = max(5, int(round(raw / 5.0) * 5))  # nearest 5, floor 5
            except (TypeError, ValueError):
                est = None

        # Phase tag — useful for the enrichment-scanner timeout-recovery
        # and for downstream consumers (pa-web-ui work packet renderer).
        phase = "phase-b-complete" if (rs or rt or kn or un) else "phase-a-complete"

        new_enrichment = {
            "packet_info": packet_info,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "enriched_by": os.environ.get("AGENT_NAME") or "tasks-agent",
            "phase": phase,
        }

        pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
        if not pg_url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            pg_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

        # Merge: preserve any prior enrichment keys (e.g., merge_orphan_parent
        # from archival lift, or stored backtrace materials from earlier
        # phases) under top-level keys; replace packet_info / enriched_at /
        # enriched_by / phase outright.
        merge_sql = """
            UPDATE pa_web.tasks
               SET enrichment = COALESCE(enrichment, '{}'::jsonb) || %(new)s::jsonb,
                   original_est_minutes = COALESCE(original_est_minutes, %(est)s),
                   enrichment_state = 'done',
                   updated_at = NOW(),
                   migration_source = 'live'
             WHERE ref_id = %(ref_id)s
             RETURNING ref_id, enrichment, enrichment_state, original_est_minutes
        """
        with psycopg.connect(pg_url, autocommit=True, connect_timeout=10) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(merge_sql, {
                    "ref_id": ref_id,
                    "new": json.dumps(new_enrichment),
                    "est": est,
                })
                row = cur.fetchone()
        if row is None:
            return {
                "status": "error",
                "ref_id": ref_id,
                "error_message": f"No row in pa_web.tasks for ref_id {ref_id}",
            }

        return {
            "status": "ok",
            "ref_id": ref_id,
            "enrichment": row.get("enrichment"),
            "enrichment_state": row.get("enrichment_state"),
            "original_est_minutes": row.get("original_est_minutes"),
        }

    except Exception as e:
        return {
            "status": "error",
            "ref_id": ref_id,
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
