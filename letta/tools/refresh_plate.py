"""
refresh_plate Letta tool.

Generates MC's plate-digest text from current pa_web.tasks state.
Cycle-1 minimal version: tasks-only digest. Signals + canonical
priorities integration land after Unit 11 (canonical store skill).

The agent calling this tool is responsible for writing the returned
digest to its own memfs at reference/current-plate.md (via Edit/Write
tool). This separation keeps the Postgres-read concern out of memfs
write-coordination.
"""

from typing import Dict, Any, Optional


def refresh_plate(
    owner: Optional[str] = None,
    max_tasks: int = 12,
    include_due_within_days: int = 7,
    include_signals: bool = True,
    signals_days_back: int = 3,
    signals_attention_min: str = "routine",
    max_signals: int = 5,
) -> Dict[str, Any]:
    """
    Build a plate-digest from active tasks in pa_web.tasks AND recent
    Layer-5 signals from agents-canonical/signals/.

    Args:
        owner: Filter to a specific owner (e.g., 'chad'). If None, no
               owner filter is applied (all active tasks). Optional.
        max_tasks: Cap on tasks to include in the digest. Defaults to 12.
                   Capped at 50 to prevent runaway prompts.
        include_due_within_days: Lookahead window in days for due-soon
                                 highlighting. Defaults to 7. Capped at 60.
        include_signals: Whether to read + include recent Layer-5 signals
                         (briefings, etc.) from agents-canonical. Defaults
                         to True. Set False for tasks-only digest.
        signals_days_back: Days of signals history to scan. Default 3,
                           capped at 14.
        signals_attention_min: Minimum attention level — 'routine',
                               'elevated', or 'urgent'. Default 'routine'.
        max_signals: Cap on signals included in digest. Default 5.

    Returns:
        Dictionary with:
        - status: "ok" or "error"
        - digest: rendered text of the plate (~200-400 tokens target).
                  Caller writes this to reference/current-plate.md.
        - tasks_count: int — total active tasks selected
        - due_soon_count: int — tasks with due_date within the window
        - signals_count: int — recent signals included
        - generated_at: ISO timestamp
        - error_message: present only when status="error"
    """
    # ALL IMPORTS INSIDE FUNCTION - required for Letta tool extraction
    import os
    import traceback
    from datetime import datetime, timezone, timedelta

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as e:
        return {
            "status": "error",
            "digest": "",
            "tasks_count": 0,
            "due_soon_count": 0,
            "generated_at": None,
            "error_message": f"psycopg import failed: {e}",
        }

    try:
        # Bound inputs
        if max_tasks is None or max_tasks < 1:
            max_tasks = 12
        if max_tasks > 50:
            max_tasks = 50
        if include_due_within_days is None or include_due_within_days < 0:
            include_due_within_days = 7
        if include_due_within_days > 60:
            include_due_within_days = 60

        pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
        if not pg_url:
            password = os.environ.get("POSTGRES_PASSWORD", "")
            pg_url = f"postgresql://postgres:{password}@supabase-db:5432/postgres"

        # Active = closed_at IS NULL AND status NOT IN terminal set.
        # Order: due-soon first, then priority, then most-recently-updated.
        sql = """
            SELECT ref_id,
                   COALESCE(confirmed_title, suggested_title, raw_description) AS display_title,
                   status, due_date, priority, owner,
                   source, origin, started_at, updated_at
              FROM pa_web.tasks
             WHERE closed_at IS NULL
               AND (status IS NULL OR status NOT IN ('done','archived','rejected','merged'))
               AND (%(owner)s::text IS NULL OR owner = %(owner)s::text)
             ORDER BY
                 CASE WHEN due_date IS NOT NULL AND due_date <= (CURRENT_DATE + (%(window)s || ' days')::interval)::date
                      THEN 0 ELSE 1 END,
                 due_date NULLS LAST,
                 COALESCE(priority, 99),
                 updated_at DESC
             LIMIT %(limit)s
        """
        params = {
            "owner": owner,
            "window": str(include_due_within_days),
            "limit": max_tasks,
        }

        with psycopg.connect(pg_url, autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        now = datetime.now(timezone.utc)
        cutoff_date = now.date() + timedelta(days=include_due_within_days)

        # Build digest text inline (no nested def)
        lines = []
        lines.append(f"## Current plate ({len(rows)} active)")
        lines.append("")

        due_soon = []
        in_progress = []
        other = []
        for r in rows:
            in_progress_flag = r.get("started_at") is not None
            due_date = r.get("due_date")
            is_due_soon = bool(due_date and due_date <= cutoff_date)
            if is_due_soon:
                due_soon.append(r)
            elif in_progress_flag:
                in_progress.append(r)
            else:
                other.append(r)

        if due_soon:
            lines.append("**Due soon:**")
            for r in due_soon:
                due = r["due_date"].isoformat() if r.get("due_date") else "?"
                title = (r.get("display_title") or "(untitled)")[:80]
                lines.append(f"- [{r['ref_id']}] {title} (due {due})")
            lines.append("")

        if in_progress:
            lines.append("**In progress:**")
            for r in in_progress:
                title = (r.get("display_title") or "(untitled)")[:80]
                lines.append(f"- [{r['ref_id']}] {title}")
            lines.append("")

        if other:
            lines.append("**Active:**")
            for r in other:
                title = (r.get("display_title") or "(untitled)")[:80]
                pri = f" p{r['priority']}" if r.get("priority") else ""
                lines.append(f"- [{r['ref_id']}] {title}{pri}")
            lines.append("")

        if not rows:
            lines.append("(no active tasks)")
            lines.append("")

        # ── Layer-5 signals augmentation ──
        # Pull recent signals from agents-canonical/signals/ inline so the
        # plate digest reflects what worker agents have surfaced. Best-
        # effort: failures don't block the tasks-only digest.
        signals_count = 0
        signals_included: list = []
        if include_signals:
            # Bound signal-specific args
            sdays = signals_days_back or 3
            if sdays < 1:
                sdays = 1
            if sdays > 14:
                sdays = 14
            ms = max_signals or 5
            if ms < 0:
                ms = 0
            if ms > 20:
                ms = 20
            attn_rank_map = {"routine": 0, "elevated": 1, "urgent": 2}
            min_rank = attn_rank_map.get(
                (signals_attention_min or "routine").lower(), 0
            )

            try:
                import base64 as _b64
                import json as _json
                import urllib.request as _ureq
                import urllib.error as _uerr
                import urllib.parse as _uparse

                gitea_token = os.environ.get("GITEA_MEMFS_TOKEN", "")
                gitea_base = os.environ.get(
                    "GITEA_BASE_URL", "http://gitea:3000"
                ).rstrip("/")
                if gitea_token:
                    auth_h = {"Authorization": f"token {gitea_token}"}
                    today_d = now.date()
                    candidates = []
                    for offset in range(sdays):
                        day = today_d - timedelta(days=offset)
                        day_str = day.strftime("%Y-%m-%d")
                        list_url = (
                            f"{gitea_base}/api/v1/repos/agents/agents-canonical"
                            f"/contents/signals/{day_str}?ref=main"
                        )
                        try:
                            req = _ureq.Request(list_url, headers=auth_h)
                            with _ureq.urlopen(req, timeout=8) as r:
                                listing = _json.loads(r.read().decode("utf-8"))
                        except _uerr.HTTPError as he:
                            if he.code == 404:
                                continue
                            raise
                        except Exception:
                            continue
                        if not isinstance(listing, list):
                            continue
                        for entry in listing:
                            if entry.get("type") != "file":
                                continue
                            nm = entry.get("name", "") or ""
                            if not nm.endswith(".md"):
                                continue
                            file_path = entry.get("path", "")
                            f_url = (
                                f"{gitea_base}/api/v1/repos/agents/agents-canonical"
                                f"/contents/{_uparse.quote(file_path)}?ref=main"
                            )
                            try:
                                fr = _ureq.Request(f_url, headers=auth_h)
                                with _ureq.urlopen(fr, timeout=8) as fresp:
                                    fdata = _json.loads(fresp.read().decode("utf-8"))
                            except Exception:
                                continue
                            content_b64 = fdata.get("content", "") or ""
                            if not content_b64:
                                continue
                            try:
                                raw_md = _b64.b64decode(content_b64).decode(
                                    "utf-8", "replace"
                                )
                            except Exception:
                                continue
                            # Inline YAML frontmatter parse (no PyYAML)
                            fm: dict = {}
                            if raw_md.startswith("---\n") or raw_md.startswith("---\r\n"):
                                ml = raw_md.split("\n")
                                end_i = -1
                                for ix in range(1, len(ml)):
                                    if ml[ix].strip() == "---":
                                        end_i = ix
                                        break
                                if end_i > 0:
                                    for fl in ml[1:end_i]:
                                        if ":" in fl:
                                            k, _, v = fl.partition(":")
                                            fm[k.strip()] = v.strip()
                            attn = (fm.get("attention_level") or "routine").lower()
                            if attn_rank_map.get(attn, 0) < min_rank:
                                continue
                            candidates.append({
                                "source": fm.get("source", ""),
                                "attention_level": attn,
                                "description": fm.get("description", ""),
                                "date": fm.get("date", day.strftime("%Y-%m-%d")),
                                "html_url": fdata.get("html_url", ""),
                            })
                    # Sort: highest attention first, then most recent date
                    candidates.sort(
                        key=lambda s: (
                            attn_rank_map.get(s["attention_level"], 0),
                            s["date"],
                        ),
                        reverse=True,
                    )
                    signals_included = candidates[:ms]
                    signals_count = len(signals_included)
            except Exception:
                pass  # Best-effort: signals failure must not break tasks digest

        if signals_included:
            lines.append("**Recent signals:**")
            for s in signals_included:
                attn_tag = (
                    "🔴 " if s["attention_level"] == "urgent"
                    else "🟡 " if s["attention_level"] == "elevated"
                    else ""
                )
                desc = (s.get("description") or "(no description)")[:120]
                src = s.get("source", "?")
                date = s.get("date", "")
                lines.append(
                    f"- {attn_tag}[{date} {src}] {desc}"
                )
            lines.append("")

        lines.append(f"_Generated {now.isoformat()}_")

        digest = "\n".join(lines)

        return {
            "status": "ok",
            "digest": digest,
            "tasks_count": len(rows),
            "due_soon_count": len(due_soon),
            "signals_count": signals_count,
            "generated_at": now.isoformat(),
        }

    except Exception as e:
        return {
            "status": "error",
            "digest": "",
            "tasks_count": 0,
            "due_soon_count": 0,
            "signals_count": 0,
            "generated_at": None,
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
