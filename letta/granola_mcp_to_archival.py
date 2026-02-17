#!/usr/bin/env python3
"""
Import Granola meeting transcripts to Letta archival memory via MCP.

Uses the Granola MCP server (through the local supergateway proxy) instead
of the local Granola cache file. This is the preferred ingestion path — it
works on any machine with proxy access, doesn't depend on the Granola desktop
app's cache, and gets the canonical server-side data.

Shares state with the cache-based watcher (granola_watcher.py) so the two
won't double-import.

Usage:
    # Dry run — parse and format but don't insert
    python granola_mcp_to_archival.py --dry-run

    # Import meetings from the last 30 days
    python granola_mcp_to_archival.py

    # Import a specific date range
    python granola_mcp_to_archival.py --since 2026-02-01 --until 2026-02-12

    # Import this week only
    python granola_mcp_to_archival.py --range this_week

    # Show what's in state
    python granola_mcp_to_archival.py --status
"""

import os
import re
import json
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from granola_cache_to_archival import (
    chunk_content,
    insert_to_archival,
    AGENT_ID,
    INTERNAL_DOMAIN,
    MAX_PASSAGE_CHARS,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MCP_PROXY_URL = os.getenv("GRANOLA_MCP_URL", "http://localhost:8089/mcp")

# Shared state file — same one the cache watcher uses
STATE_FILE = Path("/Volumes/main-drive/ai-PA/letta/.granola_watcher_state.json")

LOG_FILE = Path("/Volumes/main-drive/ai-PA/letta/logs/granola_mcp_ingest.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Post-ingestion agent notification
# ---------------------------------------------------------------------------

def notify_agent_new_meeting(meeting_id: str, meeting_title: str):
    """Send a message to the Granola agent to trigger post-meeting processing."""
    import urllib.request as _urllib_req
    import json as _json

    letta_base = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    url = f"{letta_base}/v1/agents/{AGENT_ID}/messages"
    payload = _json.dumps({
        "role": "user",
        "content": (
            f'New meeting archived: "{meeting_title}" (meeting_id: {meeting_id}). '
            f"Run post-meeting processing: call scan_meeting_notes with this meeting_id, "
            f"review the scan package for additional action items, expand any pointers, "
            f"then call prepare_meeting_followup with merged results."
        ),
    }).encode("utf-8")
    req = _urllib_req.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        _urllib_req.urlopen(req, timeout=60)
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

    # Response is SSE — extract the data line
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
    """Parse the XML-like list_meetings response into meeting dicts.

    Returns list of:
        {"id": "uuid", "title": "...", "date": "Feb 11, 2026 9:00 PM",
         "participants": [{"name": "...", "email": "..."}]}
    """
    meetings = []
    # Match each <meeting ...> ... </meeting> block
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
    # Format: "Name (note creator) from Org <email>, Name2 <email2>"
    for entry in re.split(r",\s*(?=[A-Z])", raw):
        entry = entry.strip()
        if not entry:
            continue
        email_match = re.search(r"<([^>]+)>", entry)
        email = email_match.group(1) if email_match else ""
        # Name is everything before the first parenthetical or angle bracket
        name = re.split(r"\s*[\(<]", entry)[0].strip()
        if name:
            participants.append({"name": name, "email": email})
    return participants


def parse_get_meetings(xml_text: str) -> dict:
    """Parse get_meetings response for a single meeting.

    Returns:
        {"summary": "...", "private_notes": "...", "participants": [...]}
    """
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
    """Parse get_meeting_transcript response into plain transcript text.

    The response is JSON with a "transcript" field already in "Me:/Them:" format.
    """
    try:
        data = json.loads(json_text)
        return data.get("transcript", "").strip()
    except json.JSONDecodeError:
        # Might already be plain text
        return json_text.strip()


# ---------------------------------------------------------------------------
# Formatting (mirrors granola_cache_to_archival but from MCP data)
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
    """Generate searchable tags — same scheme as cache-based ingestion."""
    tags = []

    # Date tag
    dt = parse_mcp_date(meeting.get("date", ""))
    if dt:
        tags.append(f"date:{dt.strftime('%Y-%m')}")

    # Meeting ID
    tags.append(f"id:{meeting['id']}")

    # Participant and org tags
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
            # Skip resource calendar domains
            if not domain.startswith("resource.calendar."):
                domains.add(domain)

    for domain in domains:
        if domain != INTERNAL_DOMAIN:
            tags.append(f"org:{domain}")

    # Meeting type
    count = len(meeting.get("participants", []))
    if count <= 2:
        tags.append("type:1on1")
    elif count <= 4:
        tags.append("type:small-group")
    else:
        tags.append("type:team")

    # Internal/external
    non_internal = {d for d in domains if d != INTERNAL_DOMAIN}
    if domains and not non_internal:
        tags.append("internal")
    elif non_internal:
        tags.append("external")

    # Source marker — distinguishes from cache-based imports
    tags.append("source:mcp")

    return list(set(tags))


def format_content(meeting: dict, summary: str, transcript_text: str,
                    private_notes: str = "") -> str:
    """Format meeting into markdown — same layout as cache-based ingestion."""
    lines = []

    title = meeting.get("title", "Untitled Meeting")
    lines.append(f"## Meeting: {title}")
    lines.append("")

    lines.append(f"**ID:** {meeting['id']}")

    dt = parse_mcp_date(meeting.get("date", ""))
    if dt:
        lines.append(f"**Date:** {dt.strftime('%Y-%m-%d %H:%M')}")

    names = [p["name"] for p in meeting.get("participants", []) if p.get("name")]
    if names:
        lines.append(f"**Participants:** {', '.join(names)}")

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
# State management (shared with cache watcher)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"imported_ids": [], "last_check": None, "last_cache_mtime": None, "last_verified": None}


def save_state(state: dict):
    state["last_check"] = datetime.utcnow().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


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


def ingest_meeting_by_id(
    meeting_id: str,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """Ingest a single meeting by ID. Callable from external hooks.

    Args:
        meeting_id: Granola meeting UUID.
        dry_run: If True, parse and format but don't insert.
        force: If True, re-import even if already in state.

    Returns:
        True if the meeting was successfully ingested (or already existed).
    """
    state = load_state()
    imported_ids = set(state.get("imported_ids", []))

    if meeting_id in imported_ids and not force:
        logger.info(f"Meeting {meeting_id} already imported (use --force to re-import)")
        return True

    logger.info(f"Fetching meeting {meeting_id}...")

    # Get detail (title, summary, private_notes, participants)
    summary, private_notes, participants = fetch_meeting_detail(meeting_id)

    # Build a meeting dict from the detail response
    meeting = {
        "id": meeting_id,
        "title": "Untitled Meeting",
        "date": "",
        "participants": participants,
    }

    # Try to get title/date from the detail XML
    text = mcp_tool("get_meetings", {"meeting_ids": [meeting_id]})
    if text:
        title_match = re.search(r'title="([^"]+)"', text)
        date_match = re.search(r'date="([^"]+)"', text)
        if title_match:
            meeting["title"] = title_match.group(1)
        if date_match:
            meeting["date"] = date_match.group(1)

    transcript_text = fetch_transcript(meeting_id)
    if not transcript_text:
        logger.warning(f"No transcript for {meeting_id}")
        return False

    tags = generate_tags(meeting)
    content = format_content(meeting, summary, transcript_text,
                             private_notes=private_notes)
    tag_line = f"**Tags:** {', '.join(tags)}\n\n"
    full_content = tag_line + content

    meeting_title = meeting.get("title", "Untitled Meeting")
    chunks = chunk_content(full_content, meeting_id, tags, meeting_title)

    for cidx, (chunk_text, chunk_tags) in enumerate(chunks, 1):
        if not insert_to_archival(chunk_text, chunk_tags, dry_run=dry_run):
            logger.error(f"Failed chunk {cidx}/{len(chunks)}")
            return False

    if not dry_run:
        imported_ids.add(meeting_id)
        state["imported_ids"] = list(imported_ids)
        save_state(state)

    nchunks = len(chunks)
    size = len(full_content)
    logger.info(f"Ingested: {meeting['title'][:60]} ({size} chars, {nchunks} chunks)")

    # Trigger post-meeting processing
    if not dry_run:
        notify_agent_new_meeting(meeting_id, meeting.get("title", "Untitled Meeting"))

    return True


def ingest_meetings(
    meetings: list[dict],
    imported_ids: set,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Ingest a list of meetings into archival memory.

    Returns (success_count, error_count).
    """
    # Filter already imported
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

        # Fetch detailed data
        summary, private_notes, detail_participants = fetch_meeting_detail(mid)

        # Merge participants — detail may have more info
        if detail_participants:
            meeting["participants"] = detail_participants

        transcript_text = fetch_transcript(mid)
        if not transcript_text:
            logger.warning(f"  No transcript for {mid}, skipping")
            continue

        # Generate tags
        tags = generate_tags(meeting)

        # Format content
        content = format_content(meeting, summary, transcript_text,
                                 private_notes=private_notes)
        tag_line = f"**Tags:** {', '.join(tags)}\n\n"
        full_content = tag_line + content

        # Chunk
        meeting_title = meeting.get("title", "Untitled Meeting")
        chunks = chunk_content(full_content, mid, tags, meeting_title)

        # Insert
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

            # Trigger post-meeting processing
            if not dry_run:
                notify_agent_new_meeting(mid, title)
        else:
            errors += 1

    return success, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import Granola meetings to Letta archival memory via MCP"
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not insert")
    parser.add_argument(
        "--range",
        choices=["this_week", "last_week", "last_30_days", "custom"],
        default="last_30_days",
        help="Time range for list_meetings (default: last_30_days)",
    )
    parser.add_argument("--since", help="Custom range start (ISO date, implies --range custom)")
    parser.add_argument("--until", help="Custom range end (ISO date, implies --range custom)")
    parser.add_argument("--meeting-id", help="Import a single meeting by UUID (on-demand)")
    parser.add_argument("--force", action="store_true", help="Re-import even if already in state")
    parser.add_argument("--status", action="store_true", help="Show state and exit")
    parser.add_argument("--reset", action="store_true", help="Reset import state")
    args = parser.parse_args()

    # On-demand single-meeting import
    if args.meeting_id:
        logger.info(f"On-demand import: {args.meeting_id}")
        ok = ingest_meeting_by_id(args.meeting_id, dry_run=args.dry_run, force=args.force)
        sys.exit(0 if ok else 1)

    if args.status:
        state = load_state()
        ids = state.get("imported_ids", [])
        print(f"Imported meetings: {len(ids)}")
        print(f"Last check: {state.get('last_check', 'never')}")
        print(f"Last verified: {state.get('last_verified', 'never')}")
        return

    if args.reset:
        save_state({"imported_ids": [], "last_check": None, "last_cache_mtime": None, "last_verified": None})
        logger.info("State reset")
        return

    # Determine time range
    time_range = args.range
    custom_start = ""
    custom_end = ""

    if args.since:
        time_range = "custom"
        custom_start = args.since
        custom_end = args.until or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("Granola MCP → Letta Archival Memory Import")
    logger.info("=" * 60)
    logger.info(f"Agent: {AGENT_ID}")
    logger.info(f"Proxy: {MCP_PROXY_URL}")
    logger.info(f"Range: {time_range}" + (f" ({custom_start} → {custom_end})" if time_range == "custom" else ""))
    logger.info(f"Dry run: {args.dry_run}")

    # Load state
    state = load_state()
    imported_ids = set(state.get("imported_ids", []))
    logger.info(f"Previously imported: {len(imported_ids)} meetings")

    # Fetch meeting list
    logger.info("Fetching meeting list from Granola MCP...")
    meetings = fetch_meeting_list(time_range, custom_start, custom_end)
    if not meetings:
        logger.info("No meetings returned from MCP")
        return

    logger.info(f"MCP returned {len(meetings)} meetings in range")

    # Ingest
    success, errors = ingest_meetings(meetings, imported_ids, dry_run=args.dry_run)

    # Save state
    if not args.dry_run:
        state["imported_ids"] = list(imported_ids)
        save_state(state)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Done: {success} imported, {errors} errors")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("[DRY RUN] No data was inserted")


if __name__ == "__main__":
    main()
