"""
Trigger Task Extraction Tool for Letta

Allows MC (or any agent) to trigger the task extraction pipeline on a source
entity — producing the same result as if the user had triggered extraction
via the dedicated shortcut.
"""

from typing import Dict, Any, Optional


def trigger_task_extraction(
    source_type: str,
    source_ref: str,
    source_text: Optional[str] = None,
    surrounding_context: Optional[str] = None,
    from_person: Optional[str] = None,
    channel_or_location: Optional[str] = None,
    urls: Optional[str] = None,
    proposed_tasks: Optional[str] = None,
    context_notes: Optional[str] = None,
    origin: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Trigger the task extraction pipeline on a source entity.

    Use this to send a Slack message, email, or other source into the task
    extraction pipeline. Produces the same result as if the user ran the
    Slack shortcut. The tasks agent runs formulate, enrich, extract.

    WHEN TO USE: When you identify a message or source that likely contains
    actionable tasks for Chad. Either the user asked you to extract it, or
    you identified it proactively during a scan.

    INPUT FLEXIBILITY: Provide whatever you have. At minimum, provide
    source_ref (a permalink or ID). The tool fetches the authoritative
    source content automatically for Slack. Any additional fields you
    provide (source_text, surrounding_context, proposed_tasks) are passed
    as supplementary context alongside the fetched source, giving the
    tasks agent richer information.

    PROPOSED TASKS: Strongly encouraged when you have a clear read on
    what actions the source implies. Each line becomes a candidate task
    statement. The tasks agent will verify against the source but will
    not significantly rephrase your proposals unless the source
    contradicts them.

    Args:
        source_type: Source type. One of: "slack", "email", "google-docs-comment", "meeting", "freeform".
        source_ref: Source identifier. For slack: permalink URL or "CHANNEL_ID:MESSAGE_TS". For email: Gmail message ID. For freeform: can be empty.
        source_text: Optional source content you already have. For slack the tool always fetches the authoritative message; your text becomes supplementary context.
        surrounding_context: Optional nearby messages, thread replies, or other contextual text around the source to help the tasks agent understand the full picture.
        from_person: Who sent the source content. Include name and user ID, e.g. "Cynthia McIntyre (U09DXRLAH)". Auto-resolved from Slack if omitted.
        channel_or_location: Where the source lives, e.g. "#mapping-time". Auto-resolved from Slack if omitted.
        urls: Comma-separated URLs relevant to the source. Auto-extracted from Slack messages if omitted.
        proposed_tasks: Strongly encouraged. One or more proposed task statements, one per line. Each line becomes a candidate task verified by the tasks agent. Use when you have a clear read on what actions the source implies.
        context_notes: Your reasoning or analysis — why this was flagged, priority hints, related goals, deadlines you noticed.
        origin: "user-indicated" if user asked you to extract this, "agent-identified" if you proactively flagged it. Defaults to "agent-identified".

    Returns:
        Dictionary with status and extraction details.
    """
    import json
    import os
    import re
    import traceback
    import urllib.request
    import urllib.error

    try:
        LETTA_BASE = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        TASKS_AGENT_ID = "agent-dd15479e-6543-400e-8463-b2a48b13cd4a"

        if not source_type or source_type not in ("slack", "email", "google-docs-comment", "meeting", "freeform"):
            return {"status": "error", "error_message": f"Invalid source_type: {source_type}"}

        if not origin:
            origin = "agent-identified"

        # ── Parse Slack reference ──
        channel_id = None
        message_ts = None
        if source_type == "slack" and source_ref:
            # Permalink: https://slack.com/archives/C0A7.../p1773772275179449
            pm = re.match(r'https://[^/]+/archives/([A-Z0-9]+)/p(\d+)', source_ref)
            if pm:
                channel_id = pm.group(1)
                raw_ts = pm.group(2)
                message_ts = raw_ts[:10] + "." + raw_ts[10:] if len(raw_ts) > 10 else raw_ts
            else:
                # Direct: CHANNEL_ID:MESSAGE_TS
                dm = re.match(r'([A-Z0-9]+):([\d.]+)', source_ref)
                if dm:
                    channel_id = dm.group(1)
                    message_ts = dm.group(2)

        # ── Always fetch Slack message for authoritative source ──
        # MC's source_text becomes supplementary context, not a replacement
        agent_provided_text = source_text  # preserve what MC gave us
        fetched_text = None
        if source_type == "slack" and channel_id and message_ts:
            slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
            if not slack_token:
                try:
                    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
                    with open(env_path) as ef:
                        for eline in ef:
                            if eline.startswith("SLACK_BOT_TOKEN="):
                                slack_token = eline.split("=", 1)[1].strip()
                                break
                except Exception:
                    pass

            if slack_token:
                try:
                    fetch_url = f"https://slack.com/api/conversations.history?channel={channel_id}&latest={message_ts}&limit=1&inclusive=true"
                    freq = urllib.request.Request(fetch_url, headers={"Authorization": f"Bearer {slack_token}"})
                    with urllib.request.urlopen(freq, timeout=10) as fresp:
                        fdata = json.loads(fresp.read().decode("utf-8"))

                    if fdata.get("ok") and fdata.get("messages"):
                        msg = fdata["messages"][0]
                        fetched_text = msg.get("text", "")
                        source_text = fetched_text  # authoritative source
                        msg_user = msg.get("user", "")

                        # Extract URLs from blocks
                        fetched_urls = []
                        for block in msg.get("blocks", []):
                            for element in block.get("elements", []):
                                for item in element.get("elements", []):
                                    if item.get("type") == "link":
                                        u = item.get("url", "")
                                        if u:
                                            fetched_urls.append(u)
                        for um in re.finditer(r'<(https?://[^|>]+)', source_text or ""):
                            u = um.group(1)
                            if u not in fetched_urls:
                                fetched_urls.append(u)
                        if not urls and fetched_urls:
                            urls = ",".join(fetched_urls)

                        # Resolve sender name
                        if not from_person and msg_user:
                            try:
                                ureq = urllib.request.Request(
                                    f"https://slack.com/api/users.info?user={msg_user}",
                                    headers={"Authorization": f"Bearer {slack_token}"},
                                )
                                with urllib.request.urlopen(ureq, timeout=5) as uresp:
                                    udata = json.loads(uresp.read().decode("utf-8"))
                                    if udata.get("ok"):
                                        name = udata["user"].get("real_name", msg_user)
                                        from_person = f"{name} ({msg_user})"
                            except Exception:
                                from_person = msg_user

                        # Resolve channel name
                        if not channel_or_location:
                            try:
                                creq = urllib.request.Request(
                                    f"https://slack.com/api/conversations.info?channel={channel_id}",
                                    headers={"Authorization": f"Bearer {slack_token}"},
                                )
                                with urllib.request.urlopen(creq, timeout=5) as cresp:
                                    cdata = json.loads(cresp.read().decode("utf-8"))
                                    if cdata.get("ok"):
                                        channel_or_location = "#" + cdata["channel"].get("name", channel_id)
                            except Exception:
                                pass
                except Exception:
                    pass

        # ── Build reference_id ──
        reference_id = ""
        if source_type == "slack" and channel_id and message_ts:
            reference_id = f"slack-{channel_id}-{message_ts}"
        elif source_ref:
            reference_id = f"{source_type}-{source_ref}"

        # ── Build permalink ──
        permalink = ""
        if source_type == "slack" and channel_id and message_ts:
            ts_clean = message_ts.replace(".", "")
            permalink = f"https://slack.com/archives/{channel_id}/p{ts_clean}"

        # ── Construct [TASK EXTRACTION] message ──
        parts = [
            "[TASK EXTRACTION]",
            f"Source: {source_type}",
            f"Trigger: {'intentional' if origin == 'user-indicated' else 'agent-identified'}",
            "",
        ]

        if channel_or_location:
            parts.append(f"Channel: {channel_or_location}")
        if from_person:
            parts.append(f"From: {from_person}")
        if source_text:
            parts.append(f"Text: {source_text}")

        # If MC provided its own text AND we fetched authoritative source,
        # include MC's version as supplementary context
        if agent_provided_text and fetched_text and agent_provided_text != fetched_text:
            parts.append(f"\nAgent-provided context (supplementary): {agent_provided_text}")

        # Surrounding context (nearby messages, thread replies)
        if surrounding_context and surrounding_context.strip():
            parts.append(f"\nSurrounding context:\n{surrounding_context.strip()}")

        urls_str = "(none)"
        if urls:
            url_list = [u.strip() for u in urls.split(",") if u.strip()]
            urls_str = "\n".join(f"  - {u}" for u in url_list)
        parts.append(f"URLs:\n{urls_str}")

        if permalink:
            parts.append(f"Permalink: {permalink}")
        if reference_id:
            parts.append(f"reference_id: {reference_id}")

        if proposed_tasks and proposed_tasks.strip():
            parts.append("")
            parts.append("Proposed tasks (from triggering agent — use as strong starting points):")
            for pline in proposed_tasks.strip().split("\n"):
                pline = pline.strip()
                if pline:
                    parts.append(f"  - {pline}")
            parts.append("Verify each against the source. Apply verb review for atomicity.")
            parts.append("Use these as task descriptions unless the source clearly contradicts them.")

        if context_notes and context_notes.strip():
            parts.append("")
            parts.append(f"Agent context: {context_notes.strip()}")

        parts.append("")
        parts.append(
            "This message may contain MULTIPLE tasks — extract each one as a "
            "separate add_extracted_tasks call with its own estimate and relevant URLs. "
            f"Use origin='{origin}'. "
            "Use the same reference_id for all tasks from this message."
        )

        message = "\n".join(parts)

        # ── Send to tasks agent ──
        payload = json.dumps({
            "messages": [{"role": "user", "content": message}]
        }).encode("utf-8")

        send_url = f"{LETTA_BASE}/v1/agents/{TASKS_AGENT_ID}/messages/"

        # urllib doesn't follow 307 redirects for POST — handle manually
        resp_data = None
        for attempt in range(3):
            send_req = urllib.request.Request(
                send_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(send_req, timeout=120) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as he:
                if he.code in (301, 302, 307, 308):
                    redirect_url = he.headers.get("Location", "")
                    if redirect_url:
                        send_url = redirect_url
                        continue
                raise

        task_count = 0
        if isinstance(resp_data, list):
            task_count = len(resp_data)

        return {
            "status": "ok",
            "message": f"Extraction triggered for {source_type} source",
            "reference_id": reference_id,
            "proposed_tasks_provided": bool(proposed_tasks and proposed_tasks.strip()),
            "tasks_agent_response_messages": task_count,
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"{str(e)}\n{traceback.format_exc()}",
        }
