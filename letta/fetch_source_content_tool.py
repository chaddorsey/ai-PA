"""
Fetch Source Content Tool for Letta

Fetches the full content for a source reference, using the appropriate
API based on source type. Used by Phase A-discover to scan full emails,
meeting transcripts, and comment threads for additional tasks.

Tool: fetch_source_content
"""

from typing import Dict, Any, Optional


def fetch_source_content(
    source_type: Optional[str] = None,
    fetch_hint: Optional[str] = None,
    source_ref: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch full content for a source, using fetch_hint to determine how.

    Used by Phase A to load the complete email, meeting transcript,
    or comment thread for scanning beyond what Phase 0 captured.

    Can be called two ways:
    1. With explicit source_type + fetch_hint (low-level interface)
    2. With ref_id only — queries pa_web.tasks directly to derive
       source_type, source_ref, and fetch_hint from the row's source,
       source_metadata, and source_ref columns. Preferred for enrichment
       pipeline callers.

    Args:
        source_type: One of "email", "meeting", "meeting_marker", "slack",
            "google-docs-comment". Optional if ref_id provided.
        fetch_hint: Retrieval instruction. Optional if ref_id provided.
            Format: "gmail:MESSAGE_ID" for email, "granola:MEETING_ID" for
            meetings. For slack/docs-comment, pass the reference_id instead.
        source_ref: Optional reference_id for additional context lookup.
        ref_id: The 8-char hex reference ID of the task. If provided, the
            row is read from pa_web.tasks and the remaining fields are
            derived automatically.

    Returns:
        Dictionary with status, content text, and metadata.
    """
    import json
    import os
    import re
    import subprocess
    import traceback
    import urllib.request
    import urllib.error

    try:
        # ref_id path: query pa_web.tasks DIRECTLY. The legacy archival-memory
        # lookup at /v1/agents/<TASKS_AGENT_ID>/archival-memory is gone with
        # the Letta-Docker decommissioning, and the row holds everything we
        # need to derive source_type + a source-specific fetch_hint.
        if ref_id:
            try:
                import psycopg as _pg
                pg_url = (
                    os.environ.get("PA_WEB_POSTGRES_URL")
                    or os.environ.get("POSTGRES_URL")
                )
                if not pg_url:
                    pw = os.environ.get("POSTGRES_PASSWORD", "")
                    host = os.environ.get("PA_WEB_POSTGRES_HOST", "localhost")
                    port = os.environ.get("PA_WEB_POSTGRES_PORT", "5432")
                    pg_url = f"postgresql://postgres:{pw}@{host}:{port}/postgres"
                with _pg.connect(pg_url, autocommit=True, connect_timeout=10) as _conn:
                    with _conn.cursor() as _cur:
                        _cur.execute(
                            """SELECT source, source_ref, source_metadata, task_body
                                 FROM pa_web.tasks WHERE ref_id = %s""",
                            (ref_id,),
                        )
                        _row = _cur.fetchone()
            except Exception as _e:
                return {"status": "error",
                        "error_message": f"pa_web.tasks lookup failed for {ref_id}: {_e}"}
            if _row is None:
                return {"status": "error",
                        "error_message": f"No row in pa_web.tasks for ref_id {ref_id}"}

            _src, _sref, _smeta, _body = _row
            if not source_type:
                source_type = _src or "unknown"
            if not source_ref:
                source_ref = _sref

            # Source-specific fetch_hint derivation from source_metadata + source_ref.
            if not fetch_hint:
                smeta = _smeta or {}
                if source_type == "email":
                    mid = smeta.get("message_id") or smeta.get("location_id")
                    if mid:
                        fetch_hint = f"gmail:{mid}"
                    elif _sref and _sref.startswith("email-"):
                        fetch_hint = f"gmail:{_sref[6:]}"
                elif source_type in ("meeting", "meeting_marker"):
                    mid = smeta.get("meeting_id") or smeta.get("location_id")
                    if mid:
                        fetch_hint = f"granola:{mid}"
                else:
                    # slack, google-docs-comment, drive, generic → source_ref is the fetch key
                    fetch_hint = _sref

            # Fast path: if the row has task_body cached AND there's no
            # remote fetch_hint to chase, return task_body as the content.
            # This is the common case for synthetic / direct-write rows.
            if not fetch_hint and _body:
                return {
                    "status": "ok",
                    "source_type": source_type,
                    "content": _body,
                    "metadata": {"source": "pa_web.tasks.task_body", "ref_id": ref_id},
                    "content_length": len(_body),
                }

            # Stash row-derived metadata so meeting/slack/email branches can
            # use it as a content fallback when remote fetches fail.
            _row_smeta = _smeta or {}
            _row_body = _body or ""

        # Helper: build a degraded anchor block from row-only data. Used as
        # a fallback when the source-specific remote fetcher (gws, slack,
        # granola, docs comments) errors out. Keeps the agent unblocked —
        # it gets less context but enough to write a phase-a-complete
        # packet (direct_action + context_brief from row data).
        def _build_row_anchor_from_pg(source_type_, _smeta_, _body_,
                                       ref_id_, source_ref_,
                                       reason_):
            smeta_ = _smeta_ or {}
            body_ = _body_ or ""
            label = {
                "email": "EMAIL (degraded — remote fetch unavailable)",
                "slack": "SLACK MESSAGE (degraded — remote fetch unavailable)",
                "meeting": "MEETING (degraded — remote fetch unavailable)",
                "meeting_marker": "MEETING (degraded — remote fetch unavailable)",
                "google-docs-comment": "DOCS COMMENT (degraded — remote fetch unavailable)",
                "drive": "DRIVE FILE (degraded — remote fetch unavailable)",
            }.get(source_type_, f"{source_type_.upper()} (degraded)")

            # Source-specific header lines from common smeta keys
            header_lines = []
            permalink_ = smeta_.get("permalink") or smeta_.get("source_url")
            if source_type_ == "email":
                if smeta_.get("location"):
                    header_lines.append(f"Subject: {smeta_['location']}")
                if smeta_.get("from_person"):
                    header_lines.append(f"From: {smeta_['from_person']}")
            elif source_type_ == "slack":
                if smeta_.get("location"):
                    header_lines.append(f"Channel: {smeta_['location']}")
                if smeta_.get("from_person"):
                    header_lines.append(f"User: {smeta_['from_person']}")
            elif source_type_ in ("meeting", "meeting_marker"):
                if smeta_.get("title"):
                    header_lines.append(f"Title: {smeta_['title']}")
                if smeta_.get("occurred_at"):
                    header_lines.append(f"Occurred: {smeta_['occurred_at']}")
            elif source_type_ == "google-docs-comment":
                if smeta_.get("doc_title"):
                    header_lines.append(f"Doc: {smeta_['doc_title']}")
                if smeta_.get("comment_author"):
                    header_lines.append(f"Author: {smeta_['comment_author']}")
            if smeta_.get("captured_at"):
                header_lines.append(f"Captured: {smeta_['captured_at']}")
            if permalink_:
                header_lines.append(f"[Permalink: {permalink_}]")

            # Body: prefer task_body (the producer cached this at
            # extraction time — often the actual email/slack/meeting text),
            # else any source-specific excerpt fields in smeta.
            body_block = body_
            if not body_block:
                for fk in ("summary", "transcript_excerpt",
                            "source_text", "comment_text", "preview"):
                    if smeta_.get(fk):
                        body_block = smeta_[fk]
                        break

            parts = [f"[*** ANCHOR — {label} ***]"]
            parts.append(
                "Remote fetcher could not retrieve full source content; "
                "this anchor was assembled from the pa_web.tasks row. "
                "It still gives you enough to write a phase-a-complete "
                "packet (direct_action, context_brief, intent_genesis "
                "from row context). For thread/ambient enrichment "
                "(resources beyond the permalink, knowns/unknowns from "
                f"sibling messages), the remote fetch would be needed — "
                f"reason it failed: {reason_}."
            )
            if header_lines:
                parts.append("\n".join(header_lines))
            if body_block:
                parts.append(body_block)
            parts.append("[*** END ANCHOR ***]")
            return "\n\n".join(parts)

        if not source_type:
            return {"status": "error", "error_message": "source_type required (provide directly or via ref_id)"}
        if not fetch_hint and not source_ref:
            return {"status": "error", "error_message": "fetch_hint or source_ref required (provide directly or via ref_id)"}

        content = ""
        metadata = {}

        if source_type == "email" and fetch_hint and fetch_hint.startswith("gmail:"):
            # Fetch full email via gws CLI
            message_id = fetch_hint.split(":", 1)[1]
            try:
                result = subprocess.run(
                    ["gws", "gmail", "users", "messages", "get",
                     "--params", json.dumps({"userId": "me", "id": message_id, "format": "full"}),
                     "--format", "json"],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode == 0:
                    # Skip keyring line
                    raw = "\n".join(l for l in result.stdout.split("\n") if not l.startswith("Using keyring"))
                    msg = json.loads(raw)

                    # Extract headers
                    headers = {}
                    for h in msg.get("payload", {}).get("headers", []):
                        headers[h["name"]] = h["value"]
                    metadata = {
                        "subject": headers.get("Subject", ""),
                        "from": headers.get("From", ""),
                        "to": headers.get("To", ""),
                        "date": headers.get("Date", ""),
                        "thread_id": msg.get("threadId", ""),
                    }

                    # Extract body text
                    import base64

                    # Extract text body from MIME parts
                    payload = msg.get("payload", {})
                    body_data = None

                    # Walk MIME tree to find text/plain
                    parts_to_check = [payload]
                    while parts_to_check:
                        part = parts_to_check.pop(0)
                        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                            body_data = part["body"]["data"]
                            break
                        parts_to_check.extend(part.get("parts", []))

                    if body_data:
                        body_text = base64.urlsafe_b64decode(body_data).decode("utf-8", "replace")
                    else:
                        body_text = msg.get("snippet", "")

                    # Permalink (gmail web URL). Useful for resources field.
                    permalink = f"https://mail.google.com/mail/u/0/#inbox/{message_id}"
                    metadata["permalink"] = permalink

                    # Wrap email body as the anchor — same framing as slack
                    # so the agent treats it as the canonical task source.
                    content = (
                        "[*** ANCHOR — EMAIL BODY ***]\n"
                        "This is the email the user/system flagged for task "
                        "creation. The task statement (suggested_title, "
                        "direct_action) MUST anchor on this content. "
                        "Thread context below is for enrichment fields ONLY; "
                        "do NOT use it to redefine the task.\n"
                        f"From: {headers.get('From','')}\n"
                        f"Subject: {headers.get('Subject','')}\n"
                        f"Date: {headers.get('Date','')}\n"
                        f"[Permalink: {permalink}]\n\n"
                        f"{body_text}\n"
                        "[*** END ANCHOR ***]"
                    )

                    # Also fetch thread context if this is part of a thread
                    thread_id = msg.get("threadId", "")
                    if thread_id and thread_id != message_id:
                        try:
                            thread_result = subprocess.run(
                                ["gws", "gmail", "users", "threads", "get",
                                 "--params", json.dumps({"userId": "me", "id": thread_id, "format": "metadata",
                                                          "metadataHeaders": ["Subject", "From", "Date"]}),
                                 "--format", "json"],
                                capture_output=True, text=True, timeout=15,
                            )
                            if thread_result.returncode == 0:
                                t_raw = "\n".join(l for l in thread_result.stdout.split("\n")
                                                  if not l.startswith("Using keyring"))
                                thread = json.loads(t_raw)
                                thread_msgs = thread.get("messages", [])
                                if len(thread_msgs) > 1:
                                    # Cap at last 10 messages to avoid context overflow
                                    recent_msgs = thread_msgs[-10:]
                                    thread_context = []
                                    for tm in recent_msgs:
                                        tm_headers = {h["name"]: h["value"]
                                                      for h in tm.get("payload", {}).get("headers", [])}
                                        thread_context.append(
                                            f"[{tm_headers.get('Date','')}] "
                                            f"From: {tm_headers.get('From','')} — "
                                            f"{tm.get('snippet','')[:150]}"
                                        )
                                    prefix = f"({len(thread_msgs)} messages in thread, showing last {len(recent_msgs)})\n" if len(thread_msgs) > 10 else ""
                                    content += (
                                        "\n\n--- AMBIENT THREAD CONTEXT (low-weight; "
                                        "consult only for enrichment, never to "
                                        f"redefine the task) ---\n{prefix}"
                                        + "\n".join(thread_context)
                                    )
                                    metadata["thread_message_count"] = len(thread_msgs)
                        except Exception:
                            pass  # Thread fetch is best-effort
                else:
                    content = _build_row_anchor_from_pg(
                        "email", locals().get("_row_smeta"),
                        locals().get("_row_body"),
                        ref_id, source_ref,
                        f"gws CLI error: {result.stderr[:160].strip()}",
                    )
            except FileNotFoundError:
                content = _build_row_anchor_from_pg(
                    "email", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    "gws CLI not installed in this environment",
                )
            except Exception as e:
                content = _build_row_anchor_from_pg(
                    "email", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    f"gws fetch raised: {str(e)[:160]}",
                )

        elif source_type in ("meeting", "meeting_marker") and (
            (fetch_hint and fetch_hint.startswith("granola:"))
            or 'meeting_id' in (locals().get('_row_smeta') or {})
            or 'granola_note_id' in (locals().get('_row_smeta') or {})
        ):
            # Pull the meeting via the Granola Public API. Replaces the
            # older `granola` CLI subprocess (which used a UUID-only MCP
            # that rejected Public-API `not_*` ids). Falls back to row
            # source_metadata fields if the API call fails or the key is
            # missing.
            if fetch_hint and fetch_hint.startswith("granola:"):
                meeting_id = fetch_hint.split(":", 1)[1]
            else:
                _row_smeta_local = locals().get('_row_smeta') or {}
                meeting_id = (
                    _row_smeta_local.get('meeting_id')
                    or _row_smeta_local.get('granola_note_id', '')
                )

            raw_transcript = ""
            fetched_via_api = False
            api_key = os.environ.get("GRANOLA_API_KEY", "")
            if meeting_id and api_key:
                try:
                    api_url = (
                        f"https://public-api.granola.ai/v1/notes/"
                        f"{meeting_id}?include_transcript=true"
                    )
                    g_req = urllib.request.Request(
                        api_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Accept": "application/json",
                        },
                    )
                    with urllib.request.urlopen(g_req, timeout=15) as g_resp:
                        note = json.loads(g_resp.read().decode("utf-8"))
                    # Compose transcript text + summary + headers.
                    bits = []
                    if note.get("title"):
                        bits.append(f"Title: {note['title']}")
                    if note.get("created_at"):
                        bits.append(f"Created: {note['created_at']}")
                    owner = note.get("owner") or {}
                    if owner.get("name") or owner.get("email"):
                        bits.append(
                            f"Owner: {owner.get('name','')} "
                            f"<{owner.get('email','')}>"
                        )
                    if note.get("web_url"):
                        bits.append(f"[Permalink: {note['web_url']}]")
                    # Granola Public API uses summary_text + summary_markdown.
                    # Prefer summary_text (plain) for token efficiency.
                    summary_block = (
                        note.get("summary_text")
                        or note.get("summary_markdown")
                        or note.get("summary")
                        or ""
                    )
                    if summary_block:
                        bits.append("\n--- Summary ---\n" + summary_block)
                    t = note.get("transcript")
                    if isinstance(t, list) and t:
                        lines = []
                        # Cap at first 200 turns to stay under the 8000-char
                        # truncation. Typical meetings emit 50-150 turns.
                        for entry in t[:200]:
                            sp = entry.get("speaker", "")
                            txt = entry.get("text", "")
                            if sp or txt:
                                lines.append(f"{sp}: {txt}" if sp else txt)
                        if lines:
                            bits.append("\n--- Transcript ---\n"
                                        + "\n".join(lines))
                    elif isinstance(t, str) and t:
                        bits.append("\n--- Transcript ---\n" + t)
                    # raw_transcript is "got SOMETHING from the API" — even
                    # title + summary alone (transcript=None during Granola
                    # processing) is more than the row anchor has.
                    raw_transcript = "\n".join(bits) if bits else ""
                    if raw_transcript:
                        fetched_via_api = True
                except urllib.error.HTTPError as ghe:
                    # Permission denied / not found — fall through to
                    # source_metadata / row-anchor degradation.
                    pass
                except Exception:
                    pass

            # Fallback: synthesize from pa_web.tasks.source_metadata. The
            # Granola poller stashes summary + transcript_excerpt + title
            # there at queue time, which is enough for enrichment.
            if not raw_transcript:
                _smeta_local = locals().get('_row_smeta') or {}
                pieces = []
                if _smeta_local.get('title'):
                    pieces.append(f"Title: {_smeta_local['title']}")
                if _smeta_local.get('occurred_at'):
                    pieces.append(f"Occurred: {_smeta_local['occurred_at']}")
                if _smeta_local.get('summary'):
                    pieces.append("\n--- Summary ---\n" + _smeta_local['summary'])
                if _smeta_local.get('transcript_excerpt'):
                    pieces.append("\n--- Transcript excerpt ---\n"
                                  + _smeta_local['transcript_excerpt'])
                # task_body is the agent's prior synthesis — useful as a
                # last resort
                if not pieces and locals().get('_row_body'):
                    pieces.append(locals()['_row_body'])
                raw_transcript = "\n".join(pieces) if pieces else ""

            if raw_transcript:
                content = (
                    "[*** ANCHOR — MEETING TRANSCRIPT/NOTES ***]\n"
                    f"This is the meeting the system flagged for task creation "
                    f"(meeting_id={meeting_id}). The task statement "
                    "(suggested_title, direct_action) MUST anchor on the marker "
                    "line that produced this task (see raw_description). "
                    "Surrounding transcript content is supporting context for "
                    "enrichment fields ONLY.\n\n"
                    + raw_transcript
                    + "\n[*** END ANCHOR ***]"
                )
                metadata = {
                    "meeting_id": meeting_id,
                    "fetched_via": (
                        "granola_public_api"
                        if fetched_via_api
                        else "pa_web.tasks.source_metadata"
                    ),
                }
            else:
                # Last resort: degraded anchor from row data only
                content = _build_row_anchor_from_pg(
                    "meeting", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    f"granola CLI rejected meeting_id={meeting_id} "
                    "(likely non-UUID Public-API id) and source_metadata "
                    "had no summary/excerpt either",
                )
                metadata = {"meeting_id": meeting_id,
                            "fetched_via": "row_anchor_degraded"}

        elif source_type == "slack":
            # Parse channel + thread_ts from reference_id or fetch_hint
            # Format: slack-CHANNEL_ID-MESSAGE_TS or slack-CHANNEL_ID-MSG_TS-tTHREAD_TS
            ref = fetch_hint or source_ref or ""
            import re as _re
            slack_match = _re.match(r"slack-([A-Z0-9]+)-([\d.]+)(?:-t([\d.]+))?", ref)
            if slack_match:
                channel_id = slack_match.group(1)
                message_ts = slack_match.group(2)
                thread_ts = slack_match.group(3) or message_ts

                # Prefer user token (xoxp) for broader channel access
                slack_token = os.environ.get("SLACK_MCP_XOXP_TOKEN", "") or os.environ.get("SLACK_BOT_TOKEN", "")
                if not slack_token:
                    # Sandbox may not inherit env — try reading from .env
                    try:
                        for env_path in ["/app/.env", os.path.expanduser("~/.env")]:
                            if os.path.exists(env_path):
                                with open(env_path) as ef:
                                    for eline in ef:
                                        if eline.startswith("SLACK_MCP_XOXP_TOKEN="):
                                            slack_token = eline.split("=", 1)[1].strip()
                                            break
                                        if not slack_token and eline.startswith("SLACK_BOT_TOKEN="):
                                            slack_token = eline.split("=", 1)[1].strip()
                            if slack_token:
                                break
                    except Exception:
                        pass
                if slack_token:
                    try:
                        auth_header = {"Authorization": f"Bearer {slack_token}"}
                        thread_lines = []
                        anchor_text = ""
                        anchor_user = ""

                        # ── Anchor: explicitly fetch the user-clicked message ──
                        # Use conversations.history with latest=ts inclusive=true
                        # limit=1. Without this, the anchor's text was missing
                        # from the bundle and the agent would synthesize task
                        # statements from ambient thread/channel messages.
                        try:
                            anchor_url = (
                                f"https://slack.com/api/conversations.history"
                                f"?channel={channel_id}&latest={message_ts}"
                                f"&limit=1&inclusive=true"
                            )
                            aareq = urllib.request.Request(anchor_url, headers=auth_header)
                            with urllib.request.urlopen(aareq, timeout=10) as aaresp:
                                aadata = json.loads(aaresp.read().decode("utf-8"))
                            if aadata.get("ok") and aadata.get("messages"):
                                am = aadata["messages"][0]
                                anchor_text = am.get("text", "") or ""
                                anchor_user = am.get("user", "") or ""
                        except Exception:
                            pass

                        # If message is in a thread, fetch thread replies
                        # (supporting context — NOT to redefine the task).
                        if thread_ts != message_ts:
                            thread_url = (
                                f"https://slack.com/api/conversations.replies"
                                f"?channel={channel_id}&ts={thread_ts}&limit=15"
                            )
                            treq = urllib.request.Request(thread_url, headers=auth_header)
                            with urllib.request.urlopen(treq, timeout=10) as tresp:
                                tdata = json.loads(tresp.read().decode("utf-8"))
                            if tdata.get("ok") and tdata.get("messages"):
                                for tm in tdata["messages"][-15:]:
                                    # Mark which thread reply IS the anchor
                                    is_anchor = (tm.get("ts") == message_ts)
                                    prefix = "[ANCHOR]" if is_anchor else "[reply]"
                                    thread_lines.append(
                                        f"{prefix} [{tm.get('ts','')}] <@{tm.get('user','')}>: "
                                        f"{tm.get('text','')[:200]}"
                                    )

                        # Surrounding channel messages: 3 before, 3 after.
                        # AMBIENT context only — must not be used to redefine task.
                        before_url = (
                            f"https://slack.com/api/conversations.history"
                            f"?channel={channel_id}&latest={message_ts}"
                            f"&limit=4&inclusive=false"
                        )
                        breq = urllib.request.Request(before_url, headers=auth_header)
                        with urllib.request.urlopen(breq, timeout=10) as bresp:
                            bdata = json.loads(bresp.read().decode("utf-8"))
                        before_msgs = list(reversed(bdata.get("messages", [])[:3]))

                        after_url = (
                            f"https://slack.com/api/conversations.history"
                            f"?channel={channel_id}&oldest={message_ts}"
                            f"&limit=4&inclusive=false"
                        )
                        areq = urllib.request.Request(after_url, headers=auth_header)
                        with urllib.request.urlopen(areq, timeout=10) as aresp:
                            adata = json.loads(aresp.read().decode("utf-8"))
                        after_msgs = adata.get("messages", [])[:3]

                        ambient_lines = []
                        for cm in before_msgs:
                            ambient_lines.append(
                                f"[before] <@{cm.get('user','')}>: {cm.get('text','')[:200]}"
                            )
                        for cm in after_msgs:
                            ambient_lines.append(
                                f"[after] <@{cm.get('user','')}>: {cm.get('text','')[:200]}"
                            )

                        # ── Compose content with explicit anchor framing ──
                        # The agent MUST treat the ANCHOR block as the
                        # canonical user-selected message; thread/ambient are
                        # for enrichment only (resources, knowns, unknowns,
                        # intent_genesis), NEVER to redefine the task.
                        parts = []
                        parts.append(
                            "[*** ANCHOR — USER-SELECTED MESSAGE ***]\n"
                            "This is the message the user explicitly tagged for "
                            "task creation. The task statement (suggested_title, "
                            "direct_action) MUST anchor on this content. "
                            "Surrounding thread/ambient context below is ONLY "
                            "for enrichment fields (resources, knowns, unknowns, "
                            "intent_genesis) — do NOT use it to redefine the "
                            "task or swap topic.\n"
                            f"<@{anchor_user}> [{message_ts}]: {anchor_text}\n"
                            "[*** END ANCHOR ***]"
                        )
                        if thread_lines:
                            parts.append(
                                "--- THREAD CONTEXT (supporting; the [ANCHOR] "
                                "line marks the user-selected message; other "
                                "[reply] lines are siblings — do NOT promote "
                                "them over the anchor) ---\n"
                                + "\n".join(thread_lines)
                            )
                        if ambient_lines:
                            parts.append(
                                "--- AMBIENT CHANNEL CONTEXT (low-weight; "
                                "consult only for enrichment, never to "
                                "redefine the task) ---\n"
                                + "\n".join(ambient_lines)
                            )
                        content = "\n\n".join(parts)

                        # Canonical permalink via chat.getPermalink. Works for
                        # both channel messages and DMs; DMs return a workspace-
                        # scoped URL that only resolves for the team. Agents
                        # should render this as hyperlinked "Permalink".
                        permalink = ""
                        try:
                            perm_url = (
                                f"https://slack.com/api/chat.getPermalink"
                                f"?channel={channel_id}&message_ts={message_ts}"
                            )
                            preq = urllib.request.Request(perm_url, headers=auth_header)
                            with urllib.request.urlopen(preq, timeout=10) as presp:
                                pdata = json.loads(presp.read().decode("utf-8"))
                            if pdata.get("ok"):
                                permalink = pdata.get("permalink", "")
                        except Exception:
                            pass

                        metadata = {
                            "channel_id": channel_id,
                            "thread_ts": thread_ts,
                            "thread_count": len(thread_lines),
                            "context_before": len(before_msgs),
                            "context_after": len(after_msgs),
                            "permalink": permalink,
                            "is_dm": channel_id.startswith("D"),
                            "anchor_text": anchor_text,
                            "anchor_user": anchor_user,
                            "anchor_ts": message_ts,
                        }
                        if permalink:
                            content = (
                                f"[Permalink: {permalink}]\n\n" + content
                            )
                    except Exception as e:
                        content = _build_row_anchor_from_pg(
                            "slack", locals().get("_row_smeta"),
                            locals().get("_row_body"),
                            ref_id, source_ref,
                            f"slack API error: {str(e)[:160]}",
                        )
                        metadata = {"hint": "slack API error; row anchor used"}
                else:
                    content = _build_row_anchor_from_pg(
                        "slack", locals().get("_row_smeta"),
                        locals().get("_row_body"),
                        ref_id, source_ref,
                        "no SLACK_MCP_XOXP_TOKEN / SLACK_BOT_TOKEN available",
                    )
                    metadata = {"hint": "no slack token; row anchor used"}
            else:
                # Couldn't parse the slack-CHANNEL-TS reference — use row data
                content = _build_row_anchor_from_pg(
                    "slack", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    f"could not parse slack reference '{ref[:80]}' "
                    "into channel+ts",
                )
                metadata = {"hint": "slack ref parse failed; row anchor used"}

        elif source_type == "google-docs-comment":
            # Parse source_ref (gdocs-comment-<DOC_ID>-<COMMENT_ID>) to get
            # doc + comment ids. fetch_hint is the same string in cycle-1.
            ref = fetch_hint or source_ref or ""
            doc_id = ""
            comment_id = ""
            if ref.startswith("gdocs-comment-"):
                rest = ref[len("gdocs-comment-"):]
                # COMMENT_ID begins after the LAST '-' that separates the
                # 33-char-ish doc id from the comment id (Drive ids contain
                # underscores, sometimes hyphens). Use the heuristic: split
                # at the LAST hyphen if comment id is well-formed (starts
                # with 'AAAB' or all caps + digits, or includes underscore).
                # Simpler & robust: try right-most hyphen first.
                if "-" in rest:
                    doc_id, comment_id = rest.rsplit("-", 1)
                else:
                    doc_id = rest
            try:
                # ── Comment + replies ──
                comment_text = ""
                comment_author = ""
                quoted_passage = ""
                comment_date = ""
                replies_lines = []
                if doc_id and comment_id:
                    cmd = ["gws", "drive", "comments", "get",
                           "--params", json.dumps({
                               "fileId": doc_id, "commentId": comment_id,
                               "fields": "content,author,quotedFileContent,"
                                         "createdTime,resolved,replies",
                           }),
                           "--format", "json"]
                    cresult = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if cresult.returncode == 0:
                        craw = "\n".join(l for l in cresult.stdout.split("\n")
                                         if not l.startswith("Using keyring"))
                        cdata = json.loads(craw) if craw.strip() else {}
                        comment_text = cdata.get("content", "") or ""
                        comment_author = (cdata.get("author") or {}).get("displayName", "")
                        quoted_passage = (cdata.get("quotedFileContent") or {}).get("value", "")
                        comment_date = cdata.get("createdTime", "")
                        for rep in (cdata.get("replies") or []):
                            ra = (rep.get("author") or {}).get("displayName", "")
                            replies_lines.append(
                                f"[reply] [{rep.get('createdTime','')}] "
                                f"{ra}: {(rep.get('content') or '')[:300]}"
                            )

                # ── Parent doc title + mime + permalink ──
                doc_title = ""
                permalink = ""
                mime_type = ""
                if doc_id:
                    cmd = ["gws", "drive", "files", "get",
                           "--params", json.dumps({
                               "fileId": doc_id,
                               "fields": "id,name,mimeType,webViewLink",
                           }),
                           "--format", "json"]
                    fresult = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if fresult.returncode == 0:
                        fraw = "\n".join(l for l in fresult.stdout.split("\n")
                                         if not l.startswith("Using keyring"))
                        fdata = json.loads(fraw) if fraw.strip() else {}
                        doc_title = fdata.get("name", "")
                        mime_type = fdata.get("mimeType", "")
                        permalink = (
                            fdata.get("webViewLink", "")
                            or f"https://docs.google.com/document/d/{doc_id}/edit?disco={comment_id}"
                        )
                        # Append the disco fragment so the link jumps to the
                        # specific comment thread when opened.
                        if "disco=" not in permalink and comment_id:
                            sep = "&" if "?" in permalink else "?"
                            permalink = f"{permalink}{sep}disco={comment_id}"

                # ── Surrounding doc body around the highlighted passage ──
                # quotedFileContent is often a short fragment ("this", "the
                # team", "X"); the agent needs surrounding paragraph(s) to
                # know what the comment actually concerns. Strategy by mime:
                #   - Google Docs: fetch full body, locate quoted passage,
                #     extract ±WINDOW chars around it.
                #   - Google Sheets: fetch sheet metadata + the row containing
                #     the comment-anchored cell (best-effort).
                #   - Google Slides: fetch the slide containing the comment
                #     (best-effort; slides API is structurally different).
                #   - PDFs / images / others: no body extraction available;
                #     rely on doc title + comment alone.
                surrounding_context = ""
                surrounding_kind = ""  # "before+after", "doc-opening", "sheet-row", "slide", or ""
                WINDOW = 800  # chars on each side of the quoted passage
                try:
                    if mime_type == "application/vnd.google-apps.document" and doc_id:
                        cmd = ["gws", "docs", "documents", "get",
                               "--params", json.dumps({"documentId": doc_id}),
                               "--format", "json"]
                        dresult = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                        if dresult.returncode == 0:
                            draw = "\n".join(l for l in dresult.stdout.split("\n")
                                             if not l.startswith("Using keyring"))
                            ddata = json.loads(draw) if draw.strip() else {}
                            paragraphs = []
                            for el in (ddata.get("body") or {}).get("content", []):
                                para = el.get("paragraph")
                                if not para:
                                    continue
                                for elt in para.get("elements", []):
                                    tr = elt.get("textRun") or {}
                                    t = tr.get("content", "")
                                    if t:
                                        paragraphs.append(t)
                            flat_body = "".join(paragraphs)
                            if quoted_passage and flat_body:
                                # Try exact match; fall back to whitespace-
                                # normalized match (Drive sometimes adds
                                # trailing spaces or differs in newlines).
                                idx = flat_body.find(quoted_passage)
                                if idx == -1:
                                    norm_body = " ".join(flat_body.split())
                                    norm_q = " ".join(quoted_passage.split())
                                    nidx = norm_body.find(norm_q)
                                    if nidx >= 0:
                                        # Approximate idx in original body by
                                        # mapping char-count proportionally —
                                        # close enough for window extraction.
                                        ratio = len(flat_body) / max(1, len(norm_body))
                                        idx = int(nidx * ratio)
                                if idx >= 0:
                                    start = max(0, idx - WINDOW)
                                    end = min(len(flat_body), idx + len(quoted_passage) + WINDOW)
                                    pre = flat_body[start:idx].lstrip()
                                    post = flat_body[idx + len(quoted_passage):end].rstrip()
                                    surrounding_context = (
                                        f"[…before…]\n{pre}\n"
                                        f"[HIGHLIGHTED PASSAGE]\n{quoted_passage}\n"
                                        f"[…after…]\n{post}"
                                    )
                                    surrounding_kind = "before+after"
                                else:
                                    # Quoted passage not locatable; fall back
                                    # to doc opening for high-level context.
                                    surrounding_context = flat_body[:1500]
                                    surrounding_kind = "doc-opening"
                            elif flat_body and not quoted_passage:
                                # No quoted passage (rare for Docs); show
                                # opening for orientation.
                                surrounding_context = flat_body[:1500]
                                surrounding_kind = "doc-opening"
                    elif mime_type == "application/vnd.google-apps.spreadsheet":
                        # Sheets: surfacing the anchored cell + neighbors
                        # requires parsing the comment's anchor JSON, which
                        # the Drive comments API does not return cleanly.
                        # Best-effort: include sheet name + first ~30 rows
                        # of first sheet as orientation.
                        cmd = ["gws", "sheets", "spreadsheets", "get",
                               "--params", json.dumps({
                                   "spreadsheetId": doc_id,
                                   "includeGridData": False,
                               }),
                               "--format", "json"]
                        sresult = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                        if sresult.returncode == 0:
                            sraw = "\n".join(l for l in sresult.stdout.split("\n")
                                             if not l.startswith("Using keyring"))
                            sdata = json.loads(sraw) if sraw.strip() else {}
                            sheet_names = [s.get("properties", {}).get("title", "")
                                           for s in (sdata.get("sheets") or [])]
                            surrounding_context = (
                                "Sheets in this spreadsheet: "
                                + ", ".join(sheet_names)
                            )
                            surrounding_kind = "sheet-list"
                    elif mime_type == "application/vnd.google-apps.presentation":
                        # Slides: best-effort — list slide titles.
                        cmd = ["gws", "slides", "presentations", "get",
                               "--params", json.dumps({"presentationId": doc_id}),
                               "--format", "json"]
                        presult = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                        if presult.returncode == 0:
                            praw = "\n".join(l for l in presult.stdout.split("\n")
                                             if not l.startswith("Using keyring"))
                            pdata = json.loads(praw) if praw.strip() else {}
                            slide_count = len(pdata.get("slides") or [])
                            title_block = (pdata.get("title") or "")
                            surrounding_context = (
                                f"Presentation '{title_block}' has {slide_count} slide(s)."
                            )
                            surrounding_kind = "slide-summary"
                    # PDFs / images / other mimes: no fetch (handled by
                    # falling through with empty surrounding_context).
                except FileNotFoundError:
                    pass  # gws unavailable; surrounding context simply omitted
                except Exception:
                    pass  # Best-effort; do not fail enrichment if body fetch errors

                metadata = {
                    "doc_id": doc_id,
                    "comment_id": comment_id,
                    "doc_title": doc_title,
                    "doc_mime_type": mime_type,
                    "comment_author": comment_author,
                    "comment_date": comment_date,
                    "permalink": permalink,
                    "reply_count": len(replies_lines),
                    "surrounding_context_kind": surrounding_kind,
                }

                parts = []
                parts.append(
                    "[*** ANCHOR — DOCS COMMENT ***]\n"
                    "This is the Google Docs comment the system flagged for "
                    "task creation. The task statement (suggested_title, "
                    "direct_action) MUST anchor on this comment. Quoted "
                    "passage and replies below are supporting context for "
                    "enrichment fields ONLY; do NOT use them to redefine "
                    "the task.\n"
                    f"Doc: {doc_title}\n"
                    f"Author: {comment_author}\n"
                    f"Date: {comment_date}\n"
                    f"[Permalink: {permalink}]\n\n"
                    f"COMMENT: {comment_text}\n"
                    "[*** END ANCHOR ***]"
                )
                if quoted_passage:
                    parts.append(
                        "--- QUOTED DOC PASSAGE (the text the comment is "
                        "anchored to in the source document) ---\n"
                        + quoted_passage[:1500]
                    )
                if surrounding_context:
                    if surrounding_kind == "before+after":
                        label = (
                            "--- SURROUNDING DOC CONTEXT (~"
                            f"{WINDOW} chars before + after the highlighted "
                            "passage; supporting context for enrichment "
                            "fields, NEVER for redefining the task) ---"
                        )
                    elif surrounding_kind == "doc-opening":
                        label = (
                            "--- DOC OPENING (highlighted passage could not "
                            "be located in body; first 1500 chars shown for "
                            "orientation; for enrichment only) ---"
                        )
                    elif surrounding_kind == "sheet-list":
                        label = (
                            "--- SPREADSHEET ORIENTATION (sheet names; the "
                            "specific anchored cell is not retrievable from "
                            "the comments API) ---"
                        )
                    elif surrounding_kind == "slide-summary":
                        label = (
                            "--- SLIDE DECK ORIENTATION (deck title + slide "
                            "count; the specific anchored slide is not "
                            "retrievable from the comments API) ---"
                        )
                    else:
                        label = "--- SURROUNDING CONTEXT ---"
                    parts.append(label + "\n" + surrounding_context)
                if replies_lines:
                    parts.append(
                        "--- AMBIENT REPLY THREAD (low-weight; consult only "
                        "for enrichment, never to redefine the task) ---\n"
                        + "\n".join(replies_lines[:10])
                    )
                content = "\n\n".join(parts) if parts else _build_row_anchor_from_pg(
                    "google-docs-comment", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    "gws returned empty data for the comment + parent doc",
                )
            except FileNotFoundError:
                content = _build_row_anchor_from_pg(
                    "google-docs-comment", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    "gws CLI not installed in this environment",
                )
                metadata = {"hint": "gws not present; row anchor used"}
            except Exception as e:
                content = _build_row_anchor_from_pg(
                    "google-docs-comment", locals().get("_row_smeta"),
                    locals().get("_row_body"),
                    ref_id, source_ref,
                    f"docs-comment fetch raised: {str(e)[:160]}",
                )
                metadata = {"hint": "docs fetch failed; row anchor used"}

        else:
            return {"status": "error", "error_message": f"Unsupported source_type: {source_type}"}

        # Truncate very long content. Bumped from 5000 → 8000 so docs-
        # comment surrounding context (anchor + quoted + ±800 before/after
        # + replies) fits without losing the most useful before/after
        # passages. Slack/email/meeting bundles fit comfortably under this.
        if len(content) > 8000:
            content = content[:8000] + "\n\n(truncated at 8000 chars)"

        return {
            "status": "ok",
            "source_type": source_type,
            "content": content,
            "metadata": metadata,
            "content_length": len(content),
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
