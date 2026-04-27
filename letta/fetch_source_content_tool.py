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
        source_type: One of "email", "meeting", "slack", "google-docs-comment". Optional if ref_id provided.
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
                    #   slack:    fetch_hint = source_ref (slack-CXXX-ts)
                    #   email:    fetch_hint = "gmail:<msgid>" (smeta or strip prefix)
                    #   meeting:  fetch_hint = "granola:<meeting_id>" or pull from smeta
                    #   drive*:   fetch_hint = source_ref
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
                        content = base64.urlsafe_b64decode(body_data).decode("utf-8", "replace")
                    else:
                        content = msg.get("snippet", "")

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
                                    content += f"\n\n--- THREAD CONTEXT ---\n{prefix}" + "\n".join(thread_context)
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
                        content = best.get("text", "")
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
            # Comment content was already enriched by DriveEnricher
            # Discovery would scan comment replies — use run_gws
            content = "(Docs comment replies require run_gws — call run_gws directly)"
            metadata = {"hint": "Use run_gws to fetch comment reply chain for discovery"}

        else:
            return {"status": "error", "error_message": f"Unsupported source_type: {source_type}"}

        # Truncate very long content
        if len(content) > 5000:
            content = content[:5000] + "\n\n(truncated at 5000 chars)"

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
