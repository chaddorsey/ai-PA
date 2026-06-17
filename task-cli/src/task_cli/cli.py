"""
task — agent-first CLI for pa_web.tasks operations.

Wraps the existing pg-canonical Python tool implementations in
`letta/*_tool.py` and `letta/tools/*.py` so the same logic powers
both the (transitional) Letta tool registrations and this CLI.

Why this design (Option 1, decided 2026-05-30):
- One implementation, two interfaces. Bug fixes land in one place.
- Docker Tasks agent keeps working through local-mode migration soak
  (rollback path stays viable).
- After Tasks soak passes, the lib modules will relocate from
  `letta/*_tool.py` → `task-cli/src/task_cli/lib/`. Tracked in
  docs/followups/2026-05-30-task-cli-refactor.md.

JSON output by default; --pretty for human-readable summaries.
"""

import json
import os
import sys
from pathlib import Path

import click


# ─── locate the existing pg-canonical tool implementations ──────────────────
# Add ai-PA repo root to sys.path so `letta.*` imports resolve.
#
# We can't derive this from __file__ when installed via pipx (which
# copies source into ~/.local/pipx/venvs/<name>/...). Override via env or
# fall back to the well-known location on this host.
_REPO_ROOT = Path(
    os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
).resolve()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _emit_json(obj):
    """Dump a tool-return dict to stdout as JSON. Exit non-zero on error."""
    click.echo(json.dumps(obj, indent=2, default=str))
    if isinstance(obj, dict) and obj.get("status") == "error":
        sys.exit(2)


def _ensure_pg_env():
    """The wrapped tools read PA_WEB_POSTGRES_URL. Build one if missing."""
    if os.environ.get("PA_WEB_POSTGRES_URL"):
        return
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("PA_WEB_POSTGRES_HOST", "localhost")
    port = os.environ.get("PA_WEB_POSTGRES_PORT", "5432")
    db = os.environ.get("PA_WEB_POSTGRES_DB", "postgres")
    user = os.environ.get("PA_WEB_POSTGRES_USER", "postgres")
    os.environ["PA_WEB_POSTGRES_URL"] = f"postgresql://{user}:{pw}@{host}:{port}/{db}"


# ─── click root group ───────────────────────────────────────────────────────


@click.group()
def cli():
    """task — agent-first CLI for pa_web.tasks operations.

    Wraps cycle-1 pg-canonical implementations. JSON output by default
    (the Tasks agent and others consume it via Bash).

    Env:
      PA_WEB_POSTGRES_URL     full connection string (preferred)
      POSTGRES_PASSWORD       used to build a connection string against
                              localhost:5432/postgres if URL not set
      LETTA_BASE_URL          used by some wrapped tools that need to
                              hit Letta APIs for ancillary lookups
                              (default: http://localhost:8283)
    """
    _ensure_pg_env()


# ─── read ────────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("ref_id")
@click.option("--field", multiple=True,
              help="Return only these fields (repeatable). Default: full record.")
def read(ref_id, field):
    """Look up a task by ref_id and return its row + source context."""
    from letta.retrieve_task_info_tool import retrieve_task_info
    result = retrieve_task_info(ref_id)
    if field and isinstance(result, dict):
        result = {k: result.get(k) for k in field}
    _emit_json(result)


# ─── search ──────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--status", multiple=True,
              help="Filter by status (repeatable). E.g. --status active --status extracted.")
@click.option("--owner", default=None, help="Filter by owner email.")
@click.option("--source", default=None,
              help="Filter by source: email, slack, drive, meeting, ...")
@click.option("--text", default=None,
              help="Full-text match against raw_description, suggested_title, "
                   "confirmed_title, task_body (ILIKE).")
@click.option("--limit", default=50, show_default=True, type=int)
@click.option("--include-closed", is_flag=True, default=False,
              help="Include rows where closed_at IS NOT NULL.")
@click.option("--fields", default=None,
              help="Comma-separated field whitelist for output.")
def search(status, owner, source, text, limit, include_closed, fields):
    """Search pa_web.tasks rows with filters. Returns JSON list."""
    import psycopg
    from psycopg.rows import dict_row

    where = []
    params = {}
    if not include_closed:
        where.append("closed_at IS NULL")
    if status:
        where.append("status = ANY(%(status)s)")
        params["status"] = list(status)
    if owner:
        where.append("owner = %(owner)s")
        params["owner"] = owner
    if source:
        where.append("source = %(source)s")
        params["source"] = source
    if text:
        where.append(
            "(raw_description ILIKE %(text)s OR suggested_title ILIKE %(text)s "
            "OR confirmed_title ILIKE %(text)s OR task_body ILIKE %(text)s)"
        )
        params["text"] = f"%{text}%"

    where_sql = " AND ".join(where) if where else "TRUE"
    params["limit"] = int(limit)

    sql = f"""
        SELECT ref_id, source, source_ref, status, extracted_at,
               raw_description, suggested_title, confirmed_title,
               due_date, priority, owner, tags
          FROM pa_web.tasks
         WHERE {where_sql}
         ORDER BY extracted_at DESC NULLS LAST, ref_id
         LIMIT %(limit)s
    """

    try:
        with psycopg.connect(os.environ["PA_WEB_POSTGRES_URL"]) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    except Exception as e:
        _emit_json({"status": "error", "error_message": str(e), "rows": []})
        return

    field_filter = [f.strip() for f in fields.split(",")] if fields else None
    if field_filter:
        rows = [{k: r.get(k) for k in field_filter} for r in rows]

    _emit_json({"status": "ok", "count": len(rows), "rows": rows})


# ─── write ───────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--ref-id", required=True,
              help="8-char hex reference ID (must be unique).")
@click.option("--raw-description", required=True)
@click.option("--source", required=True,
              type=click.Choice(["email", "slack", "drive", "meeting",
                                 "meeting_marker", "google-docs-comment",
                                 "agent-identified", "user-indicated"]))
@click.option("--source-ref", default=None)
@click.option("--origin", default=None)
@click.option("--suggested-title", default=None)
@click.option("--task-body", default=None)
@click.option("--est-minutes", type=int, default=None)
@click.option("--due-date", default=None, help="ISO 8601 date (YYYY-MM-DD)")
@click.option("--priority", type=int, default=None)
@click.option("--owner", default=None)
@click.option("--related-urls", default=None,
              help="Comma-separated URLs.")
@click.option("--source-metadata", default=None,
              help="JSON string for source_metadata JSONB column.")
def write(ref_id, raw_description, source, source_ref, origin,
          suggested_title, task_body, est_minutes, due_date, priority,
          owner, related_urls, source_metadata):
    """Insert a new row into pa_web.tasks (idempotent on ref_id)."""
    from letta.tools.add_extracted_tasks_postgres import add_extracted_tasks_postgres

    # NOTE: add_extracted_tasks_postgres expects related_urls_csv +
    # source_metadata_json (the historical Letta tool param names).
    # Translate from the user-friendly CLI flag names to those kwargs.
    kwargs = dict(
        ref_id=ref_id, raw_description=raw_description, source=source,
        source_ref=source_ref, origin=origin,
        suggested_title=suggested_title, task_body=task_body,
        original_est_minutes=est_minutes, due_date=due_date,
        priority=priority, owner=owner,
        related_urls_csv=related_urls,
        source_metadata_json=source_metadata,
    )
    # Drop None values so add_extracted_tasks_postgres uses its own defaults
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    result = add_extracted_tasks_postgres(**kwargs)
    _emit_json(result)


# ─── update (refine title + general field updates) ──────────────────────────


@cli.command()
@click.argument("ref_id")
@click.option("--suggested-title", default=None,
              help="Update the agent's suggested title (uses "
                   "refine_task_description; preserves the title-lifecycle "
                   "guard).")
@click.option("--force", is_flag=True, default=False,
              help="Bypass the anchor-drift guard on suggested-title updates.")
@click.option("--status", default=None,
              help="Update status (extracted/active/reviewed/done/etc).")
@click.option("--owner", default=None)
@click.option("--priority", type=int, default=None)
@click.option("--due-date", default=None)
@click.option("--agent-notes", default=None)
def update(ref_id, suggested_title, force, status, owner, priority,
           due_date, agent_notes):
    """Update fields on a pa_web.tasks row.

    suggested_title goes through refine_task_description (which applies
    the title-lifecycle guard). Other fields update directly.
    """
    results = {}

    if suggested_title is not None:
        from letta.refine_task_description_tool import refine_task_description
        results["suggested_title"] = refine_task_description(
            ref_id=ref_id, new_description=suggested_title, force=force,
        )

    # General field updates via direct UPDATE
    field_updates = {
        "status": status, "owner": owner, "priority": priority,
        "due_date": due_date, "agent_notes": agent_notes,
    }
    field_updates = {k: v for k, v in field_updates.items() if v is not None}
    if field_updates:
        import psycopg
        set_clauses = [f"{k} = %({k})s" for k in field_updates]
        sql = (
            f"UPDATE pa_web.tasks SET {', '.join(set_clauses)}, "
            f"updated_at = NOW() WHERE ref_id = %(ref_id)s RETURNING ref_id"
        )
        params = {**field_updates, "ref_id": ref_id}
        try:
            with psycopg.connect(os.environ["PA_WEB_POSTGRES_URL"]) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone()
                    conn.commit()
            results["fields"] = {
                "status": "ok" if row else "not_found",
                "ref_id": ref_id,
                "updated": list(field_updates.keys()),
            }
        except Exception as e:
            results["fields"] = {
                "status": "error",
                "error_message": str(e),
            }

    if not results:
        _emit_json({"status": "error", "error_message":
                    "no update fields given (--suggested-title, --status, etc.)"})
        return

    overall = "ok" if all(
        (isinstance(v, dict) and v.get("status") in (None, "ok"))
        for v in results.values()
    ) else "error"
    _emit_json({"status": overall, "results": results})


# ─── queue-claim ─────────────────────────────────────────────────────────────


@cli.command(name="queue-claim")
@click.option("--source", required=True,
              type=click.Choice(["email", "slack", "drive", "meeting",
                                 "meeting_marker", "google-docs-comment",
                                 "email-watch", "mc-completion",
                                 "docs-meeting"]))
@click.option("--limit", default=10, show_default=True, type=int)
def queue_claim(source, limit):
    """Atomically claim up to N unclaimed rows from pa_web.task_queue."""
    from letta.tools.consume_queue import consume_queue
    _emit_json(consume_queue(source=source, limit=limit))


@cli.command(name="queue-mark")
@click.option("--id", "row_id", required=True, type=int,
              help="pa_web.task_queue row id to mark processed.")
@click.option("--status", default="processed",
              type=click.Choice(["processed", "reset"]),
              help="'processed' sets processed_at=NOW(); "
                   "'reset' clears claimed_at and processed_at "
                   "(use after a failed extraction to retry).")
def queue_mark(row_id, status):
    """Mark a pa_web.task_queue row as processed (or reset for retry).

    Replaces the raw `UPDATE pa_web.task_queue ...` psql invocation in
    extraction recipes, so producer agents don't need psql in their PATH.
    """
    import json
    import os
    try:
        import psycopg
    except Exception as e:
        _emit_json({"status": "error", "error_message": f"psycopg import failed: {e}"})
        return

    db_url = os.environ.get("PA_WEB_POSTGRES_URL")
    if not db_url:
        password = os.environ.get("POSTGRES_PASSWORD", "")
        port = os.environ.get("PA_WEB_POSTGRES_PORT", "5433")
        db_url = f"postgresql://postgres:{password}@localhost:{port}/postgres"

    if status == "processed":
        sql = ("UPDATE pa_web.task_queue SET processed_at = NOW() "
               "WHERE id = %s RETURNING id, source, source_ref, "
               "claimed_at, processed_at")
    else:  # reset
        sql = ("UPDATE pa_web.task_queue SET claimed_at = NULL, "
               "processed_at = NULL WHERE id = %s "
               "RETURNING id, source, source_ref")

    try:
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (row_id,))
                row = cur.fetchone()
                if not row:
                    _emit_json({"status": "error",
                                "error_message": f"no row with id={row_id}"})
                    return
                cols = [d[0] for d in cur.description]
                result = dict(zip(cols, row))
                # Stringify timestamps for JSON
                for k, v in list(result.items()):
                    if hasattr(v, "isoformat"):
                        result[k] = v.isoformat()
        _emit_json({"status": "ok", "action": status, "row": result})
    except Exception as e:
        _emit_json({"status": "error", "error_message": str(e)})


# ─── plate ───────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--owner", default=None, help="Filter to a specific owner.")
@click.option("--window", default=7, type=int, show_default=True,
              help="Days into the future to count as 'due soon'.")
@click.option("--max-tasks", default=12, type=int, show_default=True,
              help="Cap on rows returned in the plate digest.")
def plate(owner, window, max_tasks):
    """Build a plate-digest from active rows in pa_web.tasks."""
    from letta.tools.refresh_plate import refresh_plate
    kwargs = {"include_due_within_days": window, "max_tasks": max_tasks}
    if owner:
        kwargs["owner"] = owner
    _emit_json(refresh_plate(**kwargs))


# ─── backtrace ───────────────────────────────────────────────────────────────


@cli.command()
@click.argument("ref_id")
@click.option("--max-hops", default=None, type=int)
def backtrace(ref_id, max_hops):
    """Fetch raw materials for cross-source backtracing of a task."""
    from letta.backtrace_task_tool import backtrace_task
    kwargs = {"ref_id": ref_id}
    if max_hops is not None:
        kwargs["max_hops"] = max_hops
    _emit_json(backtrace_task(**kwargs))


# ─── fetch-source ────────────────────────────────────────────────────────────


@cli.command(name="fetch-source")
@click.option("--ref-id", default=None,
              help="Task ref_id (preferred — derives source_type + fetch_hint).")
@click.option("--source-type", default=None,
              help="Used if --ref-id is omitted.")
@click.option("--fetch-hint", default=None,
              help="Used if --ref-id is omitted (e.g., 'gmail:MID').")
def fetch_source(ref_id, source_type, fetch_hint):
    """Fetch the full source content for a task (email/transcript/slack thread)."""
    from letta.fetch_source_content_tool import fetch_source_content
    if ref_id:
        _emit_json(fetch_source_content(ref_id=ref_id))
    else:
        if not source_type or not fetch_hint:
            _emit_json({"status": "error",
                        "error_message": "either --ref-id or "
                                         "(--source-type + --fetch-hint) required"})
            return
        _emit_json(fetch_source_content(source_type=source_type,
                                        fetch_hint=fetch_hint))


# ─── packet-write ────────────────────────────────────────────────────────────


@cli.command(name="packet-write")
@click.option("--ref-id", required=True,
              help="The 8-char hex ref_id of the task being enriched.")
@click.option("--direct-action", required=True,
              help="REQUIRED. Direct-action node: who asked / where / "
                   "what's being asked, paraphrased from the anchor.")
@click.option("--artifact-provenance", default=None,
              help="Primary artifact location + provenance chain.")
@click.option("--intent-genesis", default=None,
              help="Why this task exists: prior decisions, meetings, "
                   "strategic context.")
@click.option("--context-brief", default=None,
              help="3-5 bullets synthesizing context. One bullet per line.")
@click.option("--resources", default=None,
              help='One per line: "[priority] label — url (role)". '
                   "url is the canonical link the renderer hyperlinks.")
@click.option("--related-tasks", default=None,
              help="One per line: 'ref_id — short description'.")
@click.option("--knowns", default=None,
              help="What's established + verified. One per line.")
@click.option("--unknowns", default=None,
              help="What's missing / unresolved. One per line.")
@click.option("--mismatch-warnings", default=None,
              help="Overlap / conflict warnings to flag prominently.")
@click.option("--additional-notes", default=None,
              help="Any other free-form synthesis.")
@click.option("--estimated-minutes", type=int, default=None,
              help="Your realistic estimate of how long the task takes to DO, "
                   "in minutes (round to nearest 5). Sets the immutable agent "
                   "baseline original_est_minutes (only if not already set; never "
                   "overwrites the user's revision or the recorded actual).")
@click.option("--packet-info-json", default=None,
              help="ALTERNATIVE: full packet dict as JSON. If given, "
                   "all individual --* flags are ignored and the JSON's "
                   "fields are passed directly to write_packet_info() "
                   "(include estimated_minutes there too). "
                   "Useful when the agent already has structured output.")
def packet_write(ref_id, direct_action, artifact_provenance, intent_genesis,
                 context_brief, resources, related_tasks, knowns, unknowns,
                 mismatch_warnings, additional_notes, estimated_minutes,
                 packet_info_json):
    """Write PACKET INFO to a task's enrichment after backtrace synthesis.

    Flips enrichment_state to 'done' (or 'phase-b-complete' /
    'phase-a-complete' depending on how much was filled in) and persists
    the packet to pa_web.tasks.enrichment.
    """
    from letta.write_packet_info_tool import write_packet_info

    if packet_info_json:
        try:
            data = json.loads(packet_info_json)
        except Exception as e:
            _emit_json({"status": "error",
                        "error_message": f"--packet-info-json parse failed: {e}"})
            return
        if not isinstance(data, dict):
            _emit_json({"status": "error",
                        "error_message": "--packet-info-json must be a JSON object"})
            return
        kwargs = {"ref_id": ref_id, **data}
    else:
        kwargs = dict(
            ref_id=ref_id,
            direct_action=direct_action,
            artifact_provenance=artifact_provenance,
            intent_genesis=intent_genesis,
            context_brief=context_brief,
            resources=resources,
            related_tasks=related_tasks,
            knowns=knowns,
            unknowns=unknowns,
            mismatch_warnings=mismatch_warnings,
            additional_notes=additional_notes,
            estimated_minutes=estimated_minutes,
        )
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

    _emit_json(write_packet_info(**kwargs))


# ─── stage ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--url", default=None,
              help="Source to download: https URL, 'gmail:MSG_ID', or a Drive/Docs URL. "
                   "Mutually exclusive with --text.")
@click.option("--text", default=None,
              help="Inline note text to stage as markdown. Use '-' to read from stdin.")
@click.option("--label", required=True, help="Short label (used in the filename).")
@click.option("--priority", default="secondary",
              type=click.Choice(["primary", "secondary", "background"]),
              help="Resource priority marker.")
@click.option("--ref-id", default=None, help="Task ref_id (organizes files by task).")
def stage(url, text, label, priority, ref_id):
    """Stage a material (download a file or write note text) -> openfile:// link.

    Skips live Google-native docs and generic web pages (returns status=skipped);
    keep those as live links in resources instead.
    """
    from letta.stage_resource_tool import stage_resource
    if text == "-":
        text = sys.stdin.read()
    if not url and text is None:
        _emit_json({"status": "error",
                    "error_message": "either --url or --text required"})
        return
    _emit_json(stage_resource(url=url, text=text, label=label,
                              priority=priority, ref_id=ref_id))


# ─── xsearch ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--terms", required=True, help="Comma-separated search terms.")
@click.option("--channels", default=None,
              help="Comma-separated channels (default: all). "
                   "drive,gmail,slack,tasks,meetings,canonical,history,reference")
@click.option("--limit", "limit_per_channel", default=8, type=int, show_default=True)
def xsearch(terms, channels, limit_per_channel):
    """Concurrent multi-channel candidate search from anchor terms (JSON out)."""
    from letta.xsearch_tool import xsearch as _xsearch
    term_list = [t.strip() for t in terms.split(",") if t.strip()]
    chan_list = [c.strip() for c in channels.split(",")] if channels else None
    _emit_json(_xsearch(term_list, channels=chan_list, limit_per_channel=limit_per_channel))


# ─── health ──────────────────────────────────────────────────────────────────


@cli.command()
def health():
    """Probe pa_web.tasks connectivity."""
    import psycopg
    try:
        with psycopg.connect(os.environ["PA_WEB_POSTGRES_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total, "
                    "COUNT(*) FILTER (WHERE closed_at IS NULL) AS open "
                    "FROM pa_web.tasks"
                )
                total, open_ = cur.fetchone()
        _emit_json({"status": "healthy", "total": total, "open": open_})
    except Exception as e:
        _emit_json({"status": "unhealthy", "error_message": str(e)})


if __name__ == "__main__":
    cli()
