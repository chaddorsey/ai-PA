"""
emit_canonical_signal Letta tool.

Cycle-1 Layer-5 write API. Writes an agent-produced signal/digest to the
shared canonical store at agents-canonical/signals/<date>/<source>-<slug>.md.

Counterpart to read_recent_signals. Replaces inline duplication of Gitea
contents-API write code across compose_daily_briefing, generate_daily_briefing,
and any future signal-emitting tool.

Layer-5 path convention (per cycle-1 plan):
    signals/YYYY-MM-DD/<source>-<slug>.md

Frontmatter fields written:
    description, source, attention_level, mentioned_entities, date,
    composed_at

Idempotent: if the file already exists, it is updated (not duplicated).

Tool: emit_canonical_signal
"""

from typing import Dict, Any, Optional


def emit_canonical_signal(
    slug: str,
    body: str,
    source: str,
    description: Optional[str] = None,
    attention_level: Optional[str] = None,
    mentioned_entities: Optional[str] = None,
    date: Optional[str] = None,
    extra_frontmatter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write a Layer-5 signal to the shared canonical repo.

    Args:
        slug: Short identifier for the signal type. Combined with `source`
              to form the filename. Examples: 'slack-vibe', 'morning',
              'plate-snapshot', 'task-extracted'. Avoid the date itself —
              the path already encodes the date.
        body: Markdown body of the signal (no frontmatter — frontmatter is
              composed by this tool from the other args).
        source: Short identifier of the emitting agent (e.g.,
                'pulse-monitor', 'mc', 'calendar-agent', 'tasks-agent').
                Used in the filename and the `source` frontmatter field.
        description: One-line description of the signal. Read by
                     read_recent_signals to decide relevance. Optional.
        attention_level: One of 'routine', 'elevated', 'urgent'. Default
                         'routine'. Optional.
        mentioned_entities: Comma-separated list of entity names this
                            signal references (channels, people, projects).
                            Optional.
        date: YYYY-MM-DD date the signal pertains to. Default: today
              in America/New_York. Optional.
        extra_frontmatter: Optional raw YAML lines to append to the
                           frontmatter block (without the --- delimiters).
                           Use sparingly — for source-specific fields not
                           covered by the standard schema. Optional.

    Returns:
        Dictionary with:
        - status: "ok" or "error"
        - path: the signal path written (e.g., 'signals/2026-04-28/pulse-monitor-slack-vibe.md')
        - html_url: browse URL to the file in Gitea
        - was_update: True if updating an existing file, False if newly created
        - error_message: present only when status="error"
    """
    try:
        import os
        import json
        import base64
        import urllib.request
        import urllib.error
        import traceback
        from datetime import datetime

        if not slug or not isinstance(slug, str):
            return {"status": "error", "error_message": "slug is required (str)"}
        if not body or not isinstance(body, str):
            return {"status": "error", "error_message": "body is required (str)"}
        if not source or not isinstance(source, str):
            return {"status": "error", "error_message": "source is required (str)"}

        slug_clean = slug.strip().strip("/").replace(" ", "-").lower()
        source_clean = source.strip().strip("/").replace(" ", "-").lower()

        if date is None or not date:
            try:
                from zoneinfo import ZoneInfo
                date_str = datetime.now(tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.utcnow().strftime("%Y-%m-%d")
        else:
            date_str = date.strip()

        attn = (attention_level or "routine").strip().lower()
        if attn not in ("routine", "elevated", "urgent"):
            attn = "routine"

        if mentioned_entities:
            ents = [e.strip() for e in mentioned_entities.split(",") if e.strip()]
        else:
            ents = []

        desc = description or f"{source_clean} signal: {slug_clean} for {date_str}"

        signal_path = f"signals/{date_str}/{source_clean}-{slug_clean}.md"

        fm_lines = [
            "---",
            f"description: {desc}",
            f"source: {source_clean}",
            f"attention_level: {attn}",
            "mentioned_entities: ["
            + ", ".join(json.dumps(e) for e in ents)
            + "]",
            f"composed_at: {datetime.utcnow().isoformat()}Z",
            f"date: {date_str}",
        ]
        if extra_frontmatter:
            for line in extra_frontmatter.splitlines():
                if line.strip():
                    fm_lines.append(line.rstrip())
        fm_lines.append("---")
        fm_lines.append("")
        full_content = "\n".join(fm_lines) + body
        if not full_content.endswith("\n"):
            full_content += "\n"

        gitea_token = os.environ.get("GITEA_MEMFS_TOKEN", "")
        gitea_base = os.environ.get(
            "GITEA_BASE_URL", "http://gitea:3000"
        ).rstrip("/")
        if not gitea_token:
            return {
                "status": "error",
                "error_message": "GITEA_MEMFS_TOKEN not set in tool environment",
            }

        contents_url = (
            f"{gitea_base}/api/v1/repos/agents/agents-canonical"
            f"/contents/{signal_path}"
        )
        auth_h = {
            "Authorization": f"token {gitea_token}",
            "Content-Type": "application/json",
        }

        existing_sha = None
        try:
            check_req = urllib.request.Request(
                contents_url + "?ref=main", headers=auth_h
            )
            with urllib.request.urlopen(check_req, timeout=10) as r:
                existing = json.loads(r.read().decode("utf-8"))
                existing_sha = existing.get("sha")
        except urllib.error.HTTPError as he:
            if he.code != 404:
                raise

        method = "PUT" if existing_sha else "POST"
        body_payload = {
            "branch": "main",
            "content": base64.b64encode(full_content.encode("utf-8")).decode("ascii"),
            "message": f"signals: {source_clean} {slug_clean} for {date_str}",
        }
        if existing_sha:
            body_payload["sha"] = existing_sha

        attempts = [body_payload]
        if not existing_sha:
            no_branch = dict(body_payload)
            no_branch.pop("branch", None)
            attempts.append(no_branch)

        last_err = None
        for ab in attempts:
            try:
                wr_req = urllib.request.Request(
                    contents_url,
                    data=json.dumps(ab).encode(),
                    headers=auth_h,
                    method=method,
                )
                with urllib.request.urlopen(wr_req, timeout=20) as wr:
                    res = json.loads(wr.read().decode("utf-8"))
                    cobj = res.get("content") or {}
                    return {
                        "status": "ok",
                        "path": signal_path,
                        "html_url": cobj.get("html_url", ""),
                        "was_update": bool(existing_sha),
                    }
            except Exception as we:
                last_err = we
                continue

        return {
            "status": "error",
            "error_message": f"write failed: {str(last_err)[:300]}",
            "path": signal_path,
        }

    except Exception as e:
        import traceback as _tb
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{_tb.format_exc()[:600]}",
        }
