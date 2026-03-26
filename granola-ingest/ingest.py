#!/usr/bin/env python3
"""
Granola MCP to Letta Archival Memory ingestion module.

Fetches meetings from the Granola MCP proxy, formats them as markdown,
inserts into Letta archival memory, notifies the agent for post-meeting
processing, and exports shareable markdown files.

All paths are configurable via environment variables for Docker deployment.
"""

import os
import re
import json
import sys
import argparse
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration (all from env vars with sensible defaults)
# ---------------------------------------------------------------------------

AGENT_ID = os.getenv("GRANOLA_AGENT_ID", "agent-398b4f6c-6afa-493f-8063-897c6b171a0d")
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
INTERNAL_DOMAIN = "concord.org"
MAX_PASSAGE_CHARS = 28000

MCP_PROXY_URL = os.getenv("GRANOLA_MCP_URL", "http://host.docker.internal:8089/mcp")

STATE_FILE = Path(os.getenv("GRANOLA_STATE_FILE", "/data/state/granola_import_state.json"))
EXPORT_DIR = Path(os.getenv("GRANOLA_EXPORT_DIR", "/data/exports"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Archival memory helpers
# ---------------------------------------------------------------------------

def split_long_text(text: str, max_chars: int) -> list:
    """Split long text into chunks at sentence or word boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_chars:
        chunk_end = max_chars
        for punct in ['. ', '! ', '? ', '." ', '!" ', '?" ']:
            last_punct = remaining[:max_chars].rfind(punct)
            if last_punct > max_chars // 2:
                chunk_end = last_punct + len(punct)
                break
        else:
            last_space = remaining[:max_chars].rfind(' ')
            if last_space > max_chars // 2:
                chunk_end = last_space + 1
        chunks.append(remaining[:chunk_end].strip())
        remaining = remaining[chunk_end:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


def chunk_content(content: str, meeting_id: str, tags: list, meeting_title: str = "Meeting") -> list:
    """Split content into archival-sized chunks."""
    if len(content) <= MAX_PASSAGE_CHARS:
        return [(content, tags)]

    chunks = []
    parts = content.split("### Transcript")

    if len(parts) == 2:
        header_and_summary = parts[0].strip()
        transcript = parts[1].strip()

        chunk1 = header_and_summary
        chunk1_tags = tags + ["chunk:summary"]
        if len(chunk1) <= MAX_PASSAGE_CHARS:
            chunks.append((chunk1, chunk1_tags))
        else:
            chunks.append((chunk1[:MAX_PASSAGE_CHARS], chunk1_tags))

        transcript_lines = transcript.split('\n')
        expanded_lines = []
        for line in transcript_lines:
            if len(line) > MAX_PASSAGE_CHARS - 500:
                expanded_lines.extend(split_long_text(line, MAX_PASSAGE_CHARS - 500))
            else:
                expanded_lines.append(line)

        current_chunk = f"## Meeting: {meeting_title} (Transcript continued)\n\n**ID:** {meeting_id}\n\n### Transcript\n"
        chunk_num = 1

        def has_dialogue(text: str) -> bool:
            return 'Me:' in text or 'Them:' in text

        for line in expanded_lines:
            test_chunk = current_chunk + line + '\n'
            if len(test_chunk) > MAX_PASSAGE_CHARS:
                if current_chunk.strip() and len(current_chunk) > 500 and has_dialogue(current_chunk):
                    chunk_tags = tags + [f"chunk:transcript-{chunk_num}"]
                    chunks.append((current_chunk.strip(), chunk_tags))
                    chunk_num += 1
                current_chunk = f"## Meeting: {meeting_title} (Transcript continued)\n\n**ID:** {meeting_id}\n\n### Transcript\n{line}\n"
            else:
                current_chunk = test_chunk

        if current_chunk.strip() and "### Transcript" in current_chunk and len(current_chunk) > 500 and has_dialogue(current_chunk):
            chunk_tags = tags + [f"chunk:transcript-{chunk_num}"]
            chunks.append((current_chunk.strip(), chunk_tags))
    else:
        chunk_num = 1
        for i in range(0, len(content), MAX_PASSAGE_CHARS):
            chunk = content[i:i + MAX_PASSAGE_CHARS]
            chunk_tags = tags + [f"chunk:{chunk_num}"]
            chunks.append((chunk, chunk_tags))
            chunk_num += 1

    return chunks


def insert_to_archival(content: str, tags: list, dry_run: bool = False) -> bool:
    """Insert content into Letta archival memory via HTTP API."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would insert {len(content)} chars with tags: {tags[:5]}...")
        return True

    import urllib.request
    payload = json.dumps({"text": content, "tags": tags}).encode()
    req = urllib.request.Request(
        f"{LETTA_BASE_URL}/v1/agents/{AGENT_ID}/archival-memory",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        return True
    except Exception as e:
        logger.error(f"  Archival insert failed: {str(e)[:200]}")
        return False


# ---------------------------------------------------------------------------
# Post-ingestion agent notification
# ---------------------------------------------------------------------------

def notify_agent_new_meeting(meeting_id: str, meeting_title: str):
    """Send a message to the Granola agent to trigger post-meeting processing."""
    import urllib.request as _urllib_req
    import json as _json

    letta_base = LETTA_BASE_URL

    conv_label = f"meeting-{meeting_id[:12]}"
    try:
        conv_req = _urllib_req.Request(
            f"{letta_base}/v1/conversations/?agent_id={AGENT_ID}",
            data=_json.dumps({"label": conv_label}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        conv_resp = _urllib_req.urlopen(conv_req, timeout=15)
        conv_data = _json.loads(conv_resp.read().decode("utf-8"))
        conversation_id = conv_data.get("id")
        logger.info(f"  Created conversation {conversation_id} for meeting {meeting_id[:12]}")
    except Exception as e:
        logger.warning(f"  Failed to create conversation ({e}), falling back to agent-level messaging")
        conversation_id = None

    message_content = (
        f'New meeting archived: "{meeting_title}" (meeting_id: {meeting_id}). '
        f"Execute ALL steps — do NOT summarize, call the tools:\n\n"
        f"Step 1: call scan_meeting_notes(meeting_id=\"{meeting_id}\").\n"
        f"Step 2: Review the scan package. Merge marker extractions with semantic findings.\n"
        f"Step 3: call prepare_meeting_followup with merged results (creates Gmail draft).\n"
        f"Step 4: Check queued_tasks_from_meetings block. For each [c] marker entry, "
        f"call add_extracted_tasks to create a sidebar task. For each [;] entry, "
        f"decide if a follow-up task is implied for Chad — if not, remove from queue. "
        f"Clear processed entries from the queue block.\n\n"
        f"Every step MUST include tool calls. A text-only response is a failure."
    )

    if conversation_id:
        url = f"{letta_base}/v1/conversations/{conversation_id}/messages"
        payload = _json.dumps({
            "input": message_content,
            "streaming": False,
        }).encode("utf-8")
    else:
        url = f"{letta_base}/v1/agents/{AGENT_ID}/messages"
        payload = _json.dumps({
            "messages": [{"role": "user", "content": message_content}],
        }).encode("utf-8")

    req = _urllib_req.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        _urllib_req.urlopen(req, timeout=120)
        logger.info(f"  Notified agent for post-meeting processing")
    except Exception as e:
        logger.warning(f"  Agent notification failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# MCP JSON-RPC helpers
# ---------------------------------------------------------------------------

_request_id = 0


def _next_id() -> int:
    global _request_id
    _request_id += 1
    return _request_id


def mcp_call(method: str, params: dict) -> Optional[dict]:
    """Make a JSON-RPC call to the Granola MCP proxy and return the result."""
    import urllib.request
    import urllib.error

    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": method,
        "params": params,
    }

    req = urllib.request.Request(
        MCP_PROXY_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.URLError as e:
        logger.error(f"MCP proxy unreachable ({MCP_PROXY_URL}): {e}")
        return None

    # Response is SSE - extract the data line
    for line in body.split("\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])

    logger.error(f"No SSE data line in response: {body[:200]}")
    return None


def mcp_tool(name: str, arguments: dict) -> Optional[str]:
    """Call an MCP tool and return the text content."""
    resp = mcp_call("tools/call", {"name": name, "arguments": arguments})
    if not resp:
        return None

    error = resp.get("error")
    if error:
        logger.error(f"MCP tool {name} error: {error}")
        return None

    content = resp.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]

    logger.error(f"Unexpected MCP response shape for {name}")
    return None


# ---------------------------------------------------------------------------
# MCP response parsers
# ---------------------------------------------------------------------------

def parse_list_meetings(xml_text: str) -> list[dict]:
    """Parse the XML-like list_meetings response into meeting dicts."""
    meetings = []
    for m in re.finditer(
        r'<meeting\s+id="([^"]+)"\s+title="([^"]+)"\s+date="([^"]+)"[^>]*>'
        r'(.*?)</meeting>',
        xml_text,
        re.DOTALL,
    ):
        mid, title, date_str, body = m.groups()
        participants = _parse_participants(body)
        meetings.append({
            "id": mid,
            "title": title,
            "date": date_str,
            "participants": participants,
        })
    return meetings


def _parse_participants(body: str) -> list[dict]:
    """Parse <known_participants> block into list of {name, email}."""
    pp_match = re.search(
        r"<known_participants>\s*(.*?)\s*</known_participants>", body, re.DOTALL
    )
    if not pp_match:
        return []

    raw = pp_match.group(1).strip()
    participants = []
    for entry in re.split(r",\s*(?=[A-Z])", raw):
        entry = entry.strip()
        if not entry:
            continue
        email_match = re.search(r"<([^>]+)>", entry)
        email = email_match.group(1) if email_match else ""
        name = re.split(r"\s*[\(<]", entry)[0].strip()
        if name:
            participants.append({"name": name, "email": email})
    return participants


def parse_get_meetings(xml_text: str) -> dict:
    """Parse get_meetings response for a single meeting."""
    summary = ""
    s_match = re.search(r"<summary>\s*(.*?)\s*</summary>", xml_text, re.DOTALL)
    if s_match:
        summary = s_match.group(1).strip()

    notes = ""
    n_match = re.search(r"<private_notes>\s*(.*?)\s*</private_notes>", xml_text, re.DOTALL)
    if n_match:
        notes = n_match.group(1).strip()

    participants = _parse_participants(xml_text)
    return {"summary": summary, "private_notes": notes, "participants": participants}


def parse_transcript(json_text: str) -> str:
    """Parse get_meeting_transcript response into plain transcript text."""
    try:
        data = json.loads(json_text)
        return data.get("transcript", "").strip()
    except json.JSONDecodeError:
        return json_text.strip()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def parse_mcp_date(date_str: str) -> Optional[datetime]:
    """Parse date strings like 'Feb 11, 2026 9:00 PM' into datetime."""
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def generate_tags(meeting: dict) -> list[str]:
    """Generate searchable tags for archival memory."""
    tags = []

    dt = parse_mcp_date(meeting.get("date", ""))
    if dt:
        tags.append(f"date:{dt.strftime('%Y-%m')}")

    tags.append(f"id:{meeting['id']}")

    domains = set()
    for p in meeting.get("participants", []):
        name = p.get("name", "")
        email = p.get("email", "")
        if name:
            first = name.split()[0].lower()
            if first and len(first) > 1 and first.isalpha():
                tags.append(f"participant:{first}")
        if email and "@" in email:
            domain = email.split("@")[1].lower()
            if not domain.startswith("resource.calendar."):
                domains.add(domain)

    for domain in domains:
        if domain != INTERNAL_DOMAIN:
            tags.append(f"org:{domain}")

    count = len(meeting.get("participants", []))
    if count <= 2:
        tags.append("type:1on1")
    elif count <= 4:
        tags.append("type:small-group")
    else:
        tags.append("type:team")

    non_internal = {d for d in domains if d != INTERNAL_DOMAIN}
    if domains and not non_internal:
        tags.append("internal")
    elif non_internal:
        tags.append("external")

    tags.append("source:mcp")
    return list(set(tags))


def format_content(meeting: dict, summary: str, transcript_text: str,
                    private_notes: str = "") -> str:
    """Format meeting into markdown for archival storage."""
    lines = []

    title = meeting.get("title", "Untitled Meeting")
    lines.append(f"## Meeting: {title}")
    lines.append("")
    lines.append(f"**ID:** {meeting['id']}")

    dt = parse_mcp_date(meeting.get("date", ""))
    if dt:
        lines.append(f"**Date:** {dt.strftime('%Y-%m-%d %H:%M')}")

    participant_entries = []
    for p in meeting.get("participants", []):
        name = p.get("name", "")
        email = p.get("email", "")
        if name and email:
            participant_entries.append(f"{name} <{email}>")
        elif name:
            participant_entries.append(name)
    if participant_entries:
        lines.append(f"**Participants:** {', '.join(participant_entries)}")

    if private_notes and private_notes.strip():
        lines.append("")
        lines.append("### My Notes")
        lines.append(private_notes.strip())

    if summary:
        lines.append("")
        lines.append("### Summary")
        lines.append(summary)

    if transcript_text:
        lines.append("")
        lines.append("### Transcript")
        lines.append(transcript_text)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown export (shareable archive)
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use in filenames."""
    name = name.replace("/", "_").replace("\\", "_")
    name = re.sub(r'[<>"|?*]', "", name)
    name = re.sub(r"[_ ]{2,}", " ", name)
    return name.strip()


def export_meeting_markdown(
    meeting: dict, summary: str, private_notes: str, transcript_text: str,
) -> Optional[Path]:
    """Write a shareable Markdown file for one meeting. Idempotent."""
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        mid = meeting["id"]
        title = meeting.get("title", "Untitled Meeting")
        date_str = meeting.get("date", "")
        dt = parse_mcp_date(date_str)

        if dt:
            time_safe = dt.strftime("%Y-%m-%dT%H_%M_%S")
        else:
            time_safe = re.sub(r"[: ]", "_", date_str)
        title_safe = _sanitize_filename(title)
        filename = f"granolaNote--{time_safe}--{mid}--{title_safe}.md"
        output_path = EXPORT_DIR / filename

        if output_path.exists():
            return output_path

        sections = []
        sections.append(f"# {title}\n")

        meta = [
            "| Field | Value |",
            "|-------|-------|",
            f"| **Date** | {date_str} |",
            f"| **Granola Document ID** | `{mid}` |",
            f"| **Granola Link** | [notes.granola.ai/d/{mid}](https://notes.granola.ai/d/{mid}) |",
        ]
        participants = meeting.get("participants", [])
        if participants:
            names = []
            for p in participants:
                name = p.get("name", "")
                email = p.get("email", "")
                if name and email:
                    names.append(f"{name} ({email})")
                elif name:
                    names.append(name)
                elif email:
                    names.append(email)
            if names:
                meta.append(f"| **Participants** | {', '.join(names)} |")
        sections.append("\n".join(meta))

        if private_notes and private_notes.strip():
            sections.append("---\n\n## Meeting Notes\n")
            sections.append(private_notes.strip())

        if summary and summary.strip():
            sections.append("---\n\n## Summary\n")
            sections.append(summary.strip())

        if transcript_text and transcript_text.strip():
            sections.append("---\n\n## Transcript\n")
            sections.append(transcript_text.strip())

        markdown = "\n\n".join(sections) + "\n"
        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    except Exception as e:
        logger.warning(f"  Markdown export failed (non-fatal): {e}")
        return None


# ---------------------------------------------------------------------------
# State management (atomic writes)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"imported_ids": [], "last_check": None}


def save_state(state: dict):
    """Atomic state save: write to temp file then rename."""
    state["last_check"] = datetime.utcnow().isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(STATE_FILE.parent),
        prefix=".granola_state_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, str(STATE_FILE))
        logger.info(f"State saved: {len(state.get('imported_ids', []))} meetings tracked")
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------

def fetch_meeting_list(time_range: str, custom_start: str = "", custom_end: str = "") -> list[dict]:
    """Call list_meetings and return parsed meetings."""
    args = {"time_range": time_range}
    if time_range == "custom":
        args["custom_start"] = custom_start
        args["custom_end"] = custom_end

    text = mcp_tool("list_meetings", args)
    if not text:
        return []
    return parse_list_meetings(text)


def fetch_meeting_detail(meeting_id: str) -> tuple[str, str, list[dict]]:
    """Call get_meetings for one meeting. Returns (summary, private_notes, participants)."""
    text = mcp_tool("get_meetings", {"meeting_ids": [meeting_id]})
    if not text:
        return "", "", []
    detail = parse_get_meetings(text)
    return detail["summary"], detail["private_notes"], detail["participants"]


def fetch_transcript(meeting_id: str) -> str:
    """Call get_meeting_transcript for one meeting."""
    text = mcp_tool("get_meeting_transcript", {"meeting_id": meeting_id})
    if not text:
        return ""
    return parse_transcript(text)


def ingest_meetings(
    meetings: list[dict],
    imported_ids: set,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Ingest a list of meetings into archival memory.

    Returns (success_count, error_count).
    """
    new_meetings = [m for m in meetings if m["id"] not in imported_ids]
    if not new_meetings:
        logger.info("No new meetings to import")
        return 0, 0

    logger.info(f"Found {len(new_meetings)} new meetings to import")

    success = 0
    errors = 0

    for i, meeting in enumerate(new_meetings, 1):
        mid = meeting["id"]
        title = meeting.get("title", "Untitled")[:60]
        logger.info(f"[{i}/{len(new_meetings)}] {title}")

        try:
            summary, private_notes, detail_participants = fetch_meeting_detail(mid)

            if not summary or summary.strip().lower() == "no summary":
                logger.info(f"  Skipping {mid} - no summary yet (Granola still processing)")
                continue

            if detail_participants:
                meeting["participants"] = detail_participants

            transcript_text = fetch_transcript(mid)
            if not transcript_text:
                logger.warning(f"  No transcript for {mid}, skipping")
                continue

            tags = generate_tags(meeting)
            content = format_content(meeting, summary, transcript_text,
                                     private_notes=private_notes)
            tag_line = f"**Tags:** {', '.join(tags)}\n\n"
            full_content = tag_line + content

            meeting_title = meeting.get("title", "Untitled Meeting")
            chunks = chunk_content(full_content, mid, tags, meeting_title)

            all_ok = True
            for cidx, (chunk_text, chunk_tags) in enumerate(chunks, 1):
                if not insert_to_archival(chunk_text, chunk_tags, dry_run=dry_run):
                    all_ok = False
                    logger.error(f"  Failed chunk {cidx}/{len(chunks)}")
                    break

            if all_ok:
                success += 1
                if not dry_run:
                    imported_ids.add(mid)
                size = len(full_content)
                nchunks = len(chunks)
                if nchunks > 1:
                    logger.info(f"  Inserted ({size} chars, {nchunks} chunks)")
                else:
                    logger.info(f"  Inserted ({size} chars)")

                if not dry_run:
                    notify_agent_new_meeting(mid, title)
                    md_path = export_meeting_markdown(
                        meeting, summary, private_notes, transcript_text,
                    )
                    if md_path:
                        logger.info(f"  Exported {md_path.name}")
            else:
                errors += 1

        except Exception as e:
            logger.error(f"  Error processing meeting {mid}: {e}")
            errors += 1

    return success, errors


# ---------------------------------------------------------------------------
# CLI (for manual use / debugging)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import Granola meetings to Letta archival memory via MCP"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--range", choices=["this_week", "last_week", "last_30_days", "custom"],
                        default="last_30_days")
    parser.add_argument("--since", help="Custom range start (ISO date)")
    parser.add_argument("--until", help="Custom range end (ISO date)")
    parser.add_argument("--status", action="store_true", help="Show state and exit")
    args = parser.parse_args()

    if args.status:
        state = load_state()
        ids = state.get("imported_ids", [])
        print(f"Imported meetings: {len(ids)}")
        print(f"Last check: {state.get('last_check', 'never')}")
        return

    time_range = args.range
    custom_start = ""
    custom_end = ""
    if args.since:
        time_range = "custom"
        custom_start = args.since
        custom_end = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("Granola MCP -> Letta Archival Memory Import")
    logger.info("=" * 60)

    state = load_state()
    imported_ids = set(state.get("imported_ids", []))
    logger.info(f"Previously imported: {len(imported_ids)} meetings")

    meetings = fetch_meeting_list(time_range, custom_start, custom_end)
    if not meetings:
        logger.info("No meetings returned from MCP")
        return

    logger.info(f"MCP returned {len(meetings)} meetings in range")
    success, errors = ingest_meetings(meetings, imported_ids, dry_run=args.dry_run)

    if not args.dry_run:
        state["imported_ids"] = list(imported_ids)
        save_state(state)

    logger.info(f"Done: {success} imported, {errors} errors")


if __name__ == "__main__":
    main()
