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
    1. With explicit source_type + fetch_hint (original interface)
    2. With ref_id only — looks up the archival passage to extract source_type
       and fetch_hint automatically. Simpler for enrichment pipeline callers.

    Args:
        source_type: One of "email", "meeting", "meeting_marker", "slack", "google-docs-comment". Optional if ref_id provided.
        fetch_hint: Retrieval instruction from the spark record. Optional if ref_id provided.
            Format: "gmail:MESSAGE_ID" for email, "granola:MEETING_ID" for meetings.
            For slack/docs-comment, pass the reference_id instead.
        source_ref: Optional reference_id for additional context lookup.
        ref_id: The 8-char hex reference ID of the task. If provided, looks up the archival passage to extract source_type and fetch_hint automatically.

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
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        AGENT_ID = os.environ.get("TASKS_AGENT_ID", "agent-dd15479e-6543-400e-8463-b2a48b13cd4a")

        # If ref_id provided, look up archival passage to extract source_type and fetch_hint
        if ref_id:
            search_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={ref_id}&limit=3"
            req = urllib.request.Request(search_url)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    passages = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 307, 308):
                    req2 = urllib.request.Request(e.headers.get("Location", ""))
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        passages = json.loads(resp2.read().decode("utf-8"))
                else:
                    raise
            if not isinstance(passages, list):
                passages = []

            task_passage = None
            for p in passages:
                if isinstance(p, dict) and f"REF_ID: {ref_id}" in p.get("text", ""):
                    task_passage = p
                    break

            if not task_passage:
                # Cycle-1 fallback: live-flow tasks live in pa_web.tasks,
                # not archival. Look up the row and extract source_type +
                # fetch_hint from source / source_metadata / source_ref.
                try:
                    import psycopg as _pg
                    pg_url = os.environ.get("PA_WEB_POSTGRES_URL") or os.environ.get("POSTGRES_URL")
                    if not pg_url:
                        pw = os.environ.get("POSTGRES_PASSWORD", "")
                        pg_url = f"postgresql://postgres:{pw}@supabase-db:5432/postgres"
                    with _pg.connect(pg_url, autocommit=True, connect_timeout=10) as _conn:
                        with _conn.cursor() as _cur:
                            _cur.execute(
                                """SELECT source, source_ref, source_metadata, task_body
                                     FROM pa_web.tasks WHERE ref_id = %s""",
                                (ref_id,),
                            )
                            _row = _cur.fetchone()
                    if _row is None:
                        return {"status": "error", "error_message": f"No row in pa_web.tasks (or archival) for ref_id {ref_id}"}
                    _src, _sref, _smeta, _body = _row
                    if not source_type:
                        source_type = _src or "unknown"
                    # Source-specific fetch_hint derivation:
                    #   slack:               fetch_hint = source_ref (slack-CXXX-ts)
                    #   email:               fetch_hint = "gmail:<msgid>" (smeta or strip prefix)
                    #   meeting:             fetch_hint = "granola:<meeting_id>" or pull from smeta
                    #   google-docs-comment: fetch_hint = source_ref (gdocs-comment-<doc>-<cmt>)
                    if not fetch_hint:
                        smeta = _smeta or {}
                        if source_type == "email":
                            mid = smeta.get("message_id") or (smeta.get("location_id") if smeta.get("location_id") else None)
                            if mid:
                                fetch_hint = f"gmail:{mid}"
                            elif _sref and _sref.startswith("email-"):
                                fetch_hint = f"gmail:{_sref[6:]}"
                        elif source_type in ("meeting", "meeting_marker"):
                            mid = smeta.get("meeting_id") or smeta.get("location_id")
                            if mid:
                                fetch_hint = f"granola:{mid}"
                        else:
                            # slack, google-docs-comment, drive, generic
                            fetch_hint = _sref
                    if not source_ref:
                        source_ref = _sref
                    # If still no fetch_hint AND task_body contains the source text,
                    # return that directly — same shortcut as the archival path.
                    if not fetch_hint and not source_ref and _body:
                        return {
                            "status": "ok",
                            "source_type": source_type,
                            "content": _body,
                            "metadata": {"source": "pa_web.tasks.task_body", "ref_id": ref_id},
                            "content_length": len(_body),
                        }
                except Exception as _e:
                    return {"status": "error", "error_message": f"pa_web.tasks fallback failed for {ref_id}: {_e}"}
                # Skip the rest of the archival-passage extraction since
                # we now have what we need (source_type + fetch_hint/source_ref)
                p_text = ""
            else:
                p_text = task_passage.get("text", "")

            # Extract source_type from passage
            type_match = re.search(r"- Type: (.+)$", p_text, re.MULTILINE)
            if type_match and not source_type:
                source_type = type_match.group(1).strip()

            # Extract fetch_hint from passage
            hint_match = re.search(r"FETCH HINT: (.+)$", p_text, re.MULTILINE)
            if hint_match and not fetch_hint:
                fetch_hint = hint_match.group(1).strip()

            # Extract reference_id as source_ref fallback
            ref_match = re.search(r"- Reference ID: (.+)$", p_text, re.MULTILINE)
            if ref_match and not source_ref:
                source_ref = ref_match.group(1).strip()

            # If no fetch_hint found, fall back to source text from passage
            if not fetch_hint and not source_ref:
                st_match = re.search(r"SOURCE TEXT\n(.+?)(?=\nFETCH HINT:|\nENRICH|\nPACKET INFO|\Z)", p_text, re.DOTALL)
                if st_match:
                    return {
                        "status": "ok",
                        "source_type": source_type or "unknown",
                        "content": st_match.group(1).strip(),
                        "metadata": {"source": "passage_text", "ref_id": ref_id},
                        "content_length": len(st_match.group(1).strip()),
                    }

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
                    content = f"(gws error: {result.stderr[:200]})"
            except FileNotFoundError:
                # gws not available in this container — try via archival
                content = "(gws CLI not available — use archival search instead)"
            except Exception as e:
                content = f"(fetch error: {str(e)[:200]})"

        elif source_type == "meeting" and fetch_hint and fetch_hint.startswith("granola:"):
            # Fetch meeting from archival
            meeting_id = fetch_hint.split(":", 1)[1]
            try:
                search_url = f"{LETTA_BASE}/v1/agents/{AGENT_ID}/archival-memory/?search={meeting_id}&limit=3"
                req = urllib.request.Request(search_url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    passages = json.loads(resp.read().decode("utf-8"))

                if isinstance(passages, list):
                    # Find the meeting passage (longest one with meeting content)
                    best = max(passages, key=lambda p: len(p.get("text", "")) if isinstance(p, dict) else 0)
                    if isinstance(best, dict):
                        raw = best.get("text", "")
                        # Wrap as anchor — same framing as slack/email/docs.
                        # The meeting transcript IS the anchor; for marker-
                        # tagged tasks, the marker line within the transcript
                        # is the focal item, but the whole transcript provides
                        # context. The agent should anchor on whatever line
                        # produced the marker (raw_description tells it).
                        content = (
                            "[*** ANCHOR — MEETING TRANSCRIPT/NOTES ***]\n"
                            "This is the meeting the system flagged for task "
                            "creation (granola_id=" + meeting_id + "). The "
                            "task statement (suggested_title, direct_action) "
                            "MUST anchor on the marker line that produced "
                            "this task (see raw_description). Surrounding "
                            "transcript content is supporting context for "
                            "enrichment fields ONLY.\n\n"
                            + raw
                            + "\n[*** END ANCHOR ***]"
                        )
                        metadata = {"meeting_id": meeting_id}
            except Exception as e:
                content = f"(archival search error: {str(e)[:200]})"

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
                        content = f"(Slack fetch error: {str(e)[:200]})"
                else:
                    content = "(No SLACK_BOT_TOKEN available)"
            else:
                content = f"(Could not parse Slack reference: {ref[:60]})"
            metadata = metadata if content and not content.startswith("(") else {"hint": "Parse failed"}

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
                content = "\n\n".join(parts) if parts else "(no docs comment content)"
            except FileNotFoundError:
                content = "(gws CLI not available for docs-comment fetch)"
                metadata = {"hint": "gws not present"}
            except Exception as e:
                content = f"(docs-comment fetch error: {str(e)[:200]})"
                metadata = {"hint": "fetch failed"}

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
