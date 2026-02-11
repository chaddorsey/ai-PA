#!/usr/bin/env python3
"""
Export Granola meetings from local cache to shareable Markdown files.

Reads the Granola cache-v3.json and produces Markdown files with meeting
metadata, enhanced notes, and full transcript. Designed as a parallel
export path alongside the Letta archival ingestion pipeline.

Filename format matches existing convention:
  granolaNote--{calendarEventTime}--{documentId}--{title}.md

Usage:
    # Export all meetings with transcripts
    python scripts/export_granola_meetings.py

    # Export meetings since a specific date
    python scripts/export_granola_meetings.py --since 2026-02-01

    # Export a single meeting by document ID
    python scripts/export_granola_meetings.py --id 96a47439-1f77-49dc-b54c-a1f5347f1ec2

    # Dry run (show what would be exported)
    python scripts/export_granola_meetings.py --dry-run

    # Custom output directory
    python scripts/export_granola_meetings.py --output /path/to/meetings-archive
"""

import json
import argparse
import re
import sys
from pathlib import Path
from datetime import datetime

CACHE_PATH = Path.home() / "Library/Application Support/Granola/cache-v3.json"
DEFAULT_OUTPUT_DIR = Path("/Users/dorseyhomeserver/Dropbox/Granola-exports")


def load_cache(cache_path: Path) -> dict:
    """Load and decode the Granola cache file."""
    raw = json.loads(cache_path.read_text())
    return json.loads(raw["cache"])["state"]


def prosemirror_to_markdown(node: dict, depth: int = 0) -> str:
    """Convert a ProseMirror/TipTap JSON document to Markdown."""
    node_type = node.get("type", "")
    content = node.get("content", [])
    attrs = node.get("attrs", {})
    marks = node.get("marks", [])

    if node_type == "doc":
        return "\n\n".join(
            prosemirror_to_markdown(child, depth) for child in content
        ).strip()

    if node_type == "text":
        text = node.get("text", "")
        for mark in marks:
            mtype = mark.get("type", "")
            if mtype == "bold":
                text = f"**{text}**"
            elif mtype == "italic":
                text = f"*{text}*"
            elif mtype == "code":
                text = f"`{text}`"
            elif mtype == "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
        return text

    if node_type == "heading":
        level = attrs.get("level", 3)
        heading_text = "".join(prosemirror_to_markdown(c, depth) for c in content)
        return f"{'#' * level} {heading_text}"

    if node_type == "paragraph":
        para_text = "".join(prosemirror_to_markdown(c, depth) for c in content)
        return para_text

    if node_type == "bulletList":
        items = []
        for child in content:
            items.append(prosemirror_to_markdown(child, depth))
        return "\n".join(items)

    if node_type == "orderedList":
        items = []
        for i, child in enumerate(content):
            items.append(prosemirror_to_markdown(child, depth, ))
        return "\n".join(items)

    if node_type == "listItem":
        indent = "  " * depth
        parts = []
        for child in content:
            if child.get("type") in ("bulletList", "orderedList"):
                parts.append(prosemirror_to_markdown(child, depth + 1))
            else:
                text = prosemirror_to_markdown(child, depth)
                if text and not parts:
                    parts.append(f"{indent}- {text}")
                elif text:
                    parts.append(f"{indent}  {text}")
        return "\n".join(parts)

    if node_type == "hardBreak":
        return "\n"

    if node_type == "horizontalRule":
        return "---"

    if node_type == "blockquote":
        inner = "\n\n".join(prosemirror_to_markdown(c, depth) for c in content)
        return "\n".join(f"> {line}" for line in inner.split("\n"))

    if node_type == "codeBlock":
        lang = attrs.get("language", "")
        inner = "".join(prosemirror_to_markdown(c, depth) for c in content)
        return f"```{lang}\n{inner}\n```"

    # Fallback: just render children
    if content:
        return "\n\n".join(prosemirror_to_markdown(c, depth) for c in content)
    return ""


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use in filenames, matching existing convention."""
    # Replace characters that are problematic in filenames
    name = name.replace("/", "_")
    name = name.replace("\\", "_")
    name = re.sub(r'[<>"|?*]', "", name)
    # Collapse multiple spaces/underscores
    name = re.sub(r"[_ ]{2,}", " ", name)
    return name.strip()


def format_event_time(cal_event: dict) -> str:
    """Extract and format the calendar event time for the filename."""
    start = cal_event.get("start", {})
    dt_str = start.get("dateTime", "")
    if not dt_str:
        # Fall back to date-only
        dt_str = start.get("date", "")
    return dt_str


def build_filename(doc_id: str, title: str, event_time: str) -> str:
    """Build filename matching the existing granolaNote convention."""
    # Replace colons with underscores in the timestamp (matching existing files)
    time_safe = event_time.replace(":", "_")
    title_safe = sanitize_filename(title)
    return f"granolaNote--{time_safe}--{doc_id}--{title_safe}.md"


def build_transcript_text(entries: list) -> str:
    """Convert transcript entries into readable Them/Me dialogue format."""
    lines = []
    for entry in entries:
        text = entry.get("text", "").strip()
        if not text:
            continue
        source = entry.get("source", "")
        if source == "microphone":
            speaker = "Me"
        elif source == "system":
            speaker = "Them"
        else:
            speaker = source.capitalize() if source else "Unknown"
        lines.append(f"**{speaker}:** {text}")
    return "\n\n".join(lines)


def extract_attendees(cal_event: dict) -> list:
    """Extract attendee names and emails from calendar event."""
    attendees = []
    for a in cal_event.get("attendees", []):
        email = a.get("email", "")
        name = a.get("displayName", email.split("@")[0] if email else "")
        if email:
            attendees.append({"name": name, "email": email})
    return attendees


def build_markdown(doc: dict, transcript_entries: list,
                   panels: dict = None) -> str:
    """Build a complete Markdown document from a Granola meeting."""
    title = doc.get("title", "Untitled Meeting")
    doc_id = doc.get("id", "")
    cal_event = doc.get("google_calendar_event", {})
    event_time = format_event_time(cal_event)
    cal_title = cal_event.get("summary", title)
    cal_event_id = cal_event.get("id", "")
    attendees = extract_attendees(cal_event)
    granola_link = f"https://notes.granola.ai/d/{doc_id}"

    # Enhanced notes: try documentPanels first (ProseMirror JSON),
    # then fall back to notes_plain or chapters
    enhanced_notes = ""
    if panels and doc_id in panels:
        doc_panels = panels[doc_id]
        for panel_id, panel in doc_panels.items():
            panel_content = panel.get("content", {})
            if isinstance(panel_content, dict) and panel_content.get("type") == "doc":
                enhanced_notes = prosemirror_to_markdown(panel_content)
                break

    if not enhanced_notes:
        if "notes" in doc and isinstance(doc["notes"], str) and doc["notes"].strip():
            enhanced_notes = doc["notes"]
        elif "notes_plain" in doc and doc["notes_plain"]:
            enhanced_notes = doc["notes_plain"]

    # Try to extract enhanced notes from chapters format
    if not enhanced_notes and "chapters" in doc:
        chapters = doc.get("chapters", [])
        if chapters:
            parts = []
            for ch in chapters:
                if isinstance(ch, dict):
                    ch_title = ch.get("title", "")
                    ch_notes = ch.get("notes", ch.get("content", ""))
                    if ch_title:
                        parts.append(f"### {ch_title}\n\n{ch_notes}")
                    elif ch_notes:
                        parts.append(ch_notes)
            enhanced_notes = "\n\n".join(parts)

    # Build the markdown
    sections = []

    # Header
    sections.append(f"# {title}\n")

    # Metadata table
    meta_lines = [
        "| Field | Value |",
        "|-------|-------|",
        f"| **Date** | {event_time} |",
        f"| **Calendar Event** | {cal_title} |",
    ]
    if cal_event_id:
        meta_lines.append(f"| **Calendar Event ID** | `{cal_event_id}` |")
    meta_lines.append(f"| **Granola Document ID** | `{doc_id}` |")
    meta_lines.append(f"| **Granola Link** | [{granola_link}]({granola_link}) |")

    if attendees:
        attendee_strs = []
        for a in attendees:
            if a["name"] and a["name"] != a["email"].split("@")[0]:
                attendee_strs.append(f"{a['name']} ({a['email']})")
            else:
                attendee_strs.append(a["email"])
        meta_lines.append(f"| **Attendees** | {', '.join(attendee_strs)} |")

    sections.append("\n".join(meta_lines))

    # Enhanced notes
    if enhanced_notes:
        sections.append("---\n\n## Meeting Notes\n")
        sections.append(enhanced_notes.strip())

    # Transcript
    if transcript_entries:
        transcript_text = build_transcript_text(transcript_entries)
        if transcript_text:
            sections.append("---\n\n## Transcript\n")
            sections.append(transcript_text)

    return "\n\n".join(sections) + "\n"


def has_enhanced_notes(doc_id: str, panels: dict) -> bool:
    """Check if a document has Granola-generated enhanced notes in its panels."""
    if not panels or doc_id not in panels:
        return False
    for panel in panels[doc_id].values():
        panel_content = panel.get("content", {})
        if isinstance(panel_content, dict) and panel_content.get("type") == "doc":
            # Check that the panel has actual content nodes, not just an empty doc
            content_nodes = panel_content.get("content", [])
            if content_nodes:
                return True
    return False


def export_meeting(doc: dict, transcript_entries: list, output_dir: Path,
                   panels: dict = None, dry_run: bool = False) -> str:
    """Export a single meeting to a Markdown file. Returns the output path."""
    doc_id = doc.get("id", "unknown")
    title = doc.get("title", "Untitled")
    cal_event = doc.get("google_calendar_event", {})
    event_time = format_event_time(cal_event)

    if not event_time:
        # Fall back to created_at
        event_time = doc.get("created_at", "")

    filename = build_filename(doc_id, title, event_time)
    output_path = output_dir / filename

    if dry_run:
        transcript_count = len(transcript_entries) if transcript_entries else 0
        print(f"  Would export: {filename}")
        print(f"    Transcript entries: {transcript_count}")
        return str(output_path)

    markdown = build_markdown(doc, transcript_entries, panels=panels)
    output_path.write_text(markdown, encoding="utf-8")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Export Granola meetings from cache to shareable Markdown files"
    )
    parser.add_argument(
        "--since",
        help="Only export meetings on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--id",
        dest="doc_id",
        help="Export a specific meeting by document ID",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=CACHE_PATH,
        help=f"Granola cache file path (default: {CACHE_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without writing files",
    )
    parser.add_argument(
        "--with-transcript-only",
        action="store_true",
        default=True,
        help="Only export meetings that have transcripts (default: true)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export meetings even without transcripts",
    )
    args = parser.parse_args()

    if args.all:
        args.with_transcript_only = False

    # Load cache
    if not args.cache.exists():
        print(f"Error: Granola cache not found at {args.cache}")
        sys.exit(1)

    print(f"Loading Granola cache from {args.cache}...")
    state = load_cache(args.cache)

    documents = state.get("documents", {})
    transcripts = state.get("transcripts", {})
    panels = state.get("documentPanels", {})
    print(f"Found {len(documents)} documents, {len(transcripts)} transcripts, {len(panels)} document panels")

    # Filter documents
    since_dt = None
    if args.since:
        since_dt = datetime.fromisoformat(args.since)

    candidates = []
    for doc_id, doc in documents.items():
        # Filter by specific ID
        if args.doc_id and doc_id != args.doc_id:
            continue

        # Filter by transcript availability
        has_transcript = doc_id in transcripts
        if args.with_transcript_only and not has_transcript:
            continue

        # Completion gate: require enhanced notes (generated after meeting ends)
        # Skip this check when exporting a specific document by ID
        if not args.doc_id and not has_enhanced_notes(doc_id, panels):
            continue

        # Filter by date
        if since_dt:
            created = doc.get("created_at", "")
            if created:
                try:
                    doc_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if doc_dt.replace(tzinfo=None) < since_dt:
                        continue
                except (ValueError, TypeError):
                    pass

        candidates.append((doc_id, doc))

    if not candidates:
        print("No meetings match the criteria.")
        sys.exit(0)

    print(f"Exporting {len(candidates)} meeting(s)...")

    # Create output directory
    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0
    for doc_id, doc in sorted(candidates, key=lambda x: x[1].get("created_at", "")):
        transcript_entries = transcripts.get(doc_id, [])

        output_path = args.output / build_filename(
            doc_id,
            doc.get("title", "Untitled"),
            format_event_time(doc.get("google_calendar_event", {})) or doc.get("created_at", ""),
        )

        # Skip if already exported (unless specific ID requested)
        if not args.doc_id and output_path.exists() and not args.dry_run:
            skipped += 1
            continue

        export_meeting(doc, transcript_entries, args.output, panels=panels, dry_run=args.dry_run)
        exported += 1

    print()
    print(f"Exported: {exported}")
    if skipped:
        print(f"Skipped (already exist): {skipped}")
    if not args.dry_run:
        print(f"Output directory: {args.output}")


if __name__ == "__main__":
    main()
