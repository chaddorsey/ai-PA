#!/usr/bin/env python3
"""poll_granola.py — Granola API poller.

Polls https://public-api.granola.ai/v1/notes for new meetings since the
last successful poll, fetches full note details (with transcript), and
writes pa_web.task_queue rows with source='docs-meeting' so the Docs
agent can extract action items.

Invoked by scripts/poll-granola-meetings.sh (which sets up env) and
ultimately by launchd com.ai-pa.granola-meetings-poller.plist on a
2-min cadence during work hours, 10-min off-hours.

State file: logs/health/granola-poll.state  (JSON, single key 'last_seen_created_at')

Idempotent on source_ref (granola-<note_id>) — re-running on the same
notes is a no-op.

Designed to be tight, deterministic, and obviously correct. The Docs
agent does the interpretive work downstream.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

API_BASE = "https://public-api.granola.ai/v1"
DEFAULT_STATE_PATH = Path("/Volumes/main-drive/ai-PA/logs/health/granola-poll.state")
COLD_START_LOOKBACK = timedelta(hours=24)

# Shadow Markdown-export directory used during the granola-ingest
# decomm soak (Step B of the get-off-archival work). Pointed at a
# parallel dir so we can diff against the legacy granola-ingest output
# in ~/Dropbox/Granola-exports/ before retiring that service.
DEFAULT_EXPORT_DIR = Path.home() / "Dropbox" / "Granola-exports-poller"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def load_state(path: Path) -> str:
    if not path.exists():
        cold = (datetime.now(timezone.utc) - COLD_START_LOOKBACK).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        log(f"cold start — using {cold} as last_seen")
        return cold
    try:
        d = json.loads(path.read_text())
        return d.get("last_seen_created_at") or (
            datetime.now(timezone.utc) - COLD_START_LOOKBACK
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as e:
        log(f"WARN: state file unreadable ({e}); falling back to cold start")
        return (datetime.now(timezone.utc) - COLD_START_LOOKBACK).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )


def save_state(path: Path, last_seen: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_seen_created_at": last_seen}, indent=2))
    tmp.replace(path)


def api_request(path: str, api_key: str, timeout: float = 15.0) -> dict:
    """GET against Granola API. Raises on non-2xx."""
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error for {url}: {e}") from e


def fetch_note_full(note_id: str, api_key: str) -> dict:
    """Get a single note with transcript included."""
    return api_request(
        f"/notes/{urllib.parse.quote(note_id)}?include_transcript=true",
        api_key,
    )


def list_notes_since(since_iso: str, api_key: str, limit: int = 20) -> list[dict]:
    """List notes created after the given timestamp.

    Paginates via 'cursor' if hasMore is true. Caps at 5 pages to avoid
    runaway on cold-start backlog.
    """
    notes: list[dict] = []
    cursor = None
    page = 0
    while page < 5:
        page += 1
        params = {"created_after": since_iso, "limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        q = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params.items())
        data = api_request(f"/notes?{q}", api_key)
        page_notes = data.get("notes", [])
        notes.extend(page_notes)
        log(f"  page {page}: {len(page_notes)} note(s); hasMore={data.get('hasMore')}")
        if not data.get("hasMore"):
            break
        cursor = data.get("cursor")
        if not cursor:
            break
    return notes


def insert_queue_row(note: dict) -> tuple[str, bool]:
    """Idempotent insert into pa_web.task_queue.

    Returns (source_ref, inserted_bool).
    """
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError(f"psycopg required: {e}")

    note_id = note.get("id") or note.get("note_id")
    if not note_id:
        raise ValueError(f"note missing id: {json.dumps(note)[:200]}")

    source_ref = f"granola-{note_id}"

    payload = {
        "granola_note_id": note_id,
        "title": note.get("title", ""),
        "owner_email": (note.get("owner") or {}).get("email", ""),
        "owner_name": (note.get("owner") or {}).get("name", ""),
        "summary": (
            note.get("summary_text")
            or note.get("summary_markdown")
            or note.get("summary")
            or ""
        ),
        "transcript_snippet": _transcript_preview(note),
        "created_at": note.get("created_at", ""),
        "fetch_hint": f"granola:{note_id}",
        "permalink": note.get("web_url") or f"https://notes.granola.ai/d/{note_id}",
        "source_type": "meeting",
    }

    password = os.environ.get("POSTGRES_PASSWORD", "")
    port = os.environ.get("PA_WEB_POSTGRES_PORT", "5433")
    db_url = (
        os.environ.get("PA_WEB_POSTGRES_URL")
        or f"postgresql://postgres:{password}@localhost:{port}/postgres"
    )

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pa_web.task_queue (source, source_ref, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (source, source_ref) DO NOTHING
                RETURNING id
                """,
                ("docs-meeting", source_ref, json.dumps(payload)),
            )
            row = cur.fetchone()
            inserted = row is not None
    return source_ref, inserted


# ─── Markdown export ─────────────────────────────────────────────────────────


def _sanitize_filename(text: str, max_len: int = 80) -> str:
    """Strip characters that misbehave on macOS/iCloud/Dropbox path layers."""
    import re as _re
    cleaned = _re.sub(r"[\\/:*?\"<>|\n\r\t]", "", text or "")
    cleaned = cleaned.strip().replace("  ", " ")
    return cleaned[:max_len] or "untitled"


def _format_iso_for_filename(iso_ts: str) -> str:
    """Render a Granola created_at into a filesystem-safe time component.

    Falls back to a sanitized version of the raw string if parsing fails.
    """
    if not iso_ts:
        return "unknown-time"
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return ts.strftime("%Y-%m-%dT%H_%M_%S")
    except Exception:
        import re as _re
        return _re.sub(r"[: ]", "_", iso_ts)[:32] or "unknown-time"


def _format_transcript_block(transcript) -> str:
    """Render the transcript as one speaker per paragraph, blank-line
    separated.

    Public API shape: list of {speaker, text, timestamp?} entries.
    String shape: pass through (Granola's pipeline rarely emits this).
    Empty/None: empty string.
    """
    if isinstance(transcript, list):
        lines = []
        for entry in transcript:
            speaker = (entry.get("speaker") or "").strip()
            text = (entry.get("text") or "").strip()
            if not text and not speaker:
                continue
            lines.append(f"{speaker}: {text}" if speaker else text)
        # Blank line between every speaker turn for human readability.
        return "\n\n".join(lines)
    if isinstance(transcript, str):
        return transcript.strip()
    return ""


def write_markdown_export(note: dict, export_dir: Path) -> Optional[Path]:
    """Idempotent Markdown export for one note.

    Filename: granolaNote--<created>--<id>--<title>.md
    Sections: title, metadata table, Meeting Notes (if any), Summary,
    Transcript (one speaker per paragraph, blank line between).

    Returns the path written (or already-present), or None on failure.
    """
    try:
        export_dir.mkdir(parents=True, exist_ok=True)

        note_id = note.get("id") or note.get("note_id") or ""
        title = (note.get("title") or "Untitled Meeting").strip()
        created_at = note.get("created_at") or ""
        web_url = note.get("web_url") or (
            f"https://notes.granola.ai/d/{note_id}" if note_id else ""
        )

        time_component = _format_iso_for_filename(created_at)
        title_component = _sanitize_filename(title)
        filename = f"granolaNote--{time_component}--{note_id}--{title_component}.md"
        output_path = export_dir / filename

        # Idempotent: don't rewrite. If content evolves and we need a
        # forced re-export, delete the file or bump a hash suffix.
        if output_path.exists():
            return output_path

        # Metadata table
        meta_rows = [
            "| Field | Value |",
            "|-------|-------|",
            f"| **Date** | {created_at or '(unknown)'} |",
            f"| **Granola Document ID** | `{note_id}` |",
        ]
        if web_url:
            display = web_url.replace("https://", "")
            meta_rows.append(f"| **Granola Link** | [{display}]({web_url}) |")

        attendees = note.get("attendees") or []
        if attendees:
            names = []
            for a in attendees:
                if not isinstance(a, dict):
                    continue
                name = (a.get("name") or "").strip()
                email = (a.get("email") or "").strip()
                if name and email:
                    names.append(f"{name} ({email})")
                elif name:
                    names.append(name)
                elif email:
                    names.append(email)
            if names:
                meta_rows.append(f"| **Participants** | {', '.join(names)} |")

        owner = note.get("owner") or {}
        if isinstance(owner, dict) and (owner.get("name") or owner.get("email")):
            on = owner.get("name", "")
            oe = owner.get("email", "")
            owner_disp = f"{on} ({oe})" if on and oe else (on or oe)
            meta_rows.append(f"| **Owner** | {owner_disp} |")

        sections = [f"# {title}\n", "\n".join(meta_rows)]

        # Granola Public API field naming: summary_markdown is the
        # AI-generated summary (rich), summary_text is plain-text
        # rendering of it. private_notes is the user's own notes.
        private_notes = (
            note.get("private_notes")
            or note.get("notes_plain")
            or ""
        ).strip()
        if private_notes:
            sections.append("---\n\n## Meeting Notes\n")
            sections.append(private_notes)

        summary = (
            note.get("summary_markdown")
            or note.get("summary_text")
            or note.get("summary")
            or ""
        ).strip()
        if summary:
            sections.append("---\n\n## Summary\n")
            sections.append(summary)

        transcript_block = _format_transcript_block(note.get("transcript"))
        if transcript_block:
            sections.append("---\n\n## Transcript\n")
            sections.append(transcript_block)

        markdown = "\n\n".join(sections) + "\n"
        # Atomic write — avoids half-written files if killed mid-write.
        tmp = output_path.with_suffix(".md.tmp")
        tmp.write_text(markdown, encoding="utf-8")
        tmp.replace(output_path)
        return output_path

    except Exception as e:
        log(f"  WARN: markdown export failed for note: {e}")
        return None


def _transcript_preview(note: dict) -> str:
    """Build a short transcript preview from the note's transcript entries."""
    t = note.get("transcript")
    if isinstance(t, list):
        parts = []
        for entry in t[:10]:  # first 10 turns
            sp = entry.get("speaker", "")
            txt = entry.get("text", "")
            if sp or txt:
                parts.append(f"{sp}: {txt}" if sp else txt)
        return "\n".join(parts)[:2000]
    if isinstance(t, str):
        return t[:2000]
    return ""


def push_to_receiver(receiver_url: str | None, note_id: str) -> bool:
    """Best-effort POST to letta-push-receiver.

    Returns True if the push succeeded; False otherwise. Queue write
    already happened, so a failed push isn't fatal — the row will be
    picked up by the launchd backup processor sweep eventually.
    """
    if not receiver_url:
        return False
    try:
        req = urllib.request.Request(
            receiver_url.rstrip("/") + "/push",
            data=json.dumps(
                {
                    "agent": "docs",
                    "prompt": (
                        f"New Granola meeting queued in pa_web.task_queue "
                        f"(source=docs-meeting, granola note {note_id}). "
                        f"Run task_extraction_process_docs_transcripts.md "
                        f"LOCAL-MODE WRITE STEP. Use payload directly; "
                        f"granola transcript {note_id} only if needed."
                    ),
                    "source_ref": f"granola-{note_id}",
                    "priority": "normal",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        log(f"  push to receiver failed (non-fatal): {e}")
        return False


def main() -> int:
    api_key = os.environ.get("GRANOLA_API_KEY", "").strip()
    if not api_key:
        log("ERROR: GRANOLA_API_KEY not set")
        return 2

    state_path = Path(os.environ.get("GRANOLA_POLL_STATE", str(DEFAULT_STATE_PATH)))
    receiver_url = os.environ.get("LETTA_PUSH_RECEIVER_URL", "http://localhost:8099")
    export_dir = Path(os.environ.get("GRANOLA_EXPORT_DIR", str(DEFAULT_EXPORT_DIR)))

    last_seen = load_state(state_path)
    log(f"polling Granola for notes created after {last_seen}")
    log(f"markdown export dir: {export_dir}")

    try:
        notes = list_notes_since(last_seen, api_key)
    except Exception as e:
        log(f"ERROR listing notes: {e}")
        return 1

    if not notes:
        log("no new notes since last poll")
        return 0

    log(f"found {len(notes)} new note(s) — queueing")

    new_max_created = last_seen
    inserted_count = 0
    pushed_count = 0
    skipped_empty = 0
    for note in notes:
        note_id = note.get("id") or note.get("note_id") or "?"
        title = note.get("title", "(no title)")[:60]
        created_at = note.get("created_at", "")
        try:
            # Fetch full note details (with transcript) before queueing —
            # the payload is more useful with transcript snippet included.
            full = fetch_note_full(note_id, api_key)

            # SKIP notes that Granola hasn't finished processing yet
            # (no AI summary AND no transcript content). They'll appear
            # again on the next poll once Granola's pipeline completes.
            # Without this filter we'd queue + process empty rows,
            # marking them processed and losing the chance to extract
            # tasks once content arrives.
            # Public API uses summary_text / summary_markdown; older
            # entries may still have a `summary` field — accept either.
            summary = (
                full.get("summary_text")
                or full.get("summary_markdown")
                or full.get("summary")
                or ""
            ).strip()
            transcript = full.get("transcript")
            has_transcript = bool(transcript) and (
                (isinstance(transcript, str) and transcript.strip())
                or (isinstance(transcript, list) and any(
                    (e.get("text") or "").strip() for e in transcript
                ))
            )
            if not summary and not has_transcript:
                skipped_empty += 1
                log(f"  skipped (Granola still processing): {note_id} | {title}")
                # DO NOT advance new_max_created — we want to re-fetch this
                # note next poll. Stay at the last successful note's created_at.
                continue

            # Markdown export — idempotent, independent of queue insert.
            # Shadow-mode during the granola-ingest decomm soak; once
            # confidence is built up, point GRANOLA_EXPORT_DIR at the
            # canonical ~/Dropbox/Granola-exports/ and retire ingest.
            # Run BEFORE the queue insert so an export still happens
            # even if Postgres is down.
            md_path = write_markdown_export(full, export_dir)
            if md_path:
                log(f"  exported: {md_path.name}")

            try:
                source_ref, inserted = insert_queue_row(full)
            except Exception as qe:
                log(f"  WARN queue insert failed for {note_id} (export ok): {qe}")
                # Still advance the cursor — we don't want to keep
                # re-fetching the same note just because the queue is
                # temporarily unreachable.
                if created_at and created_at > new_max_created:
                    new_max_created = created_at
                continue

            if inserted:
                inserted_count += 1
                log(f"  queued: {note_id} | {title}")
                if push_to_receiver(receiver_url, note_id):
                    pushed_count += 1
            else:
                log(f"  already queued: {note_id} | {title}")

            if created_at and created_at > new_max_created:
                new_max_created = created_at
        except Exception as e:
            log(f"  FAILED for {note_id}: {e}")
            # Don't update last_seen on failure — we'll retry next poll

    # Only advance the cursor if at least one note succeeded
    if inserted_count > 0 or new_max_created != last_seen:
        save_state(state_path, new_max_created)
        log(f"state advanced to {new_max_created}")

    log(
        f"done: notes={len(notes)} inserted={inserted_count} "
        f"skipped_empty={skipped_empty} pushed={pushed_count}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
