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

API_BASE = "https://public-api.granola.ai/v1"
DEFAULT_STATE_PATH = Path("/Volumes/main-drive/ai-PA/logs/health/granola-poll.state")
COLD_START_LOOKBACK = timedelta(hours=24)


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
        "summary": note.get("summary", ""),
        "transcript_snippet": _transcript_preview(note),
        "created_at": note.get("created_at", ""),
        "fetch_hint": f"granola:{note_id}",
        "permalink": f"https://notes.granola.ai/d/{note_id}",
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

    last_seen = load_state(state_path)
    log(f"polling Granola for notes created after {last_seen}")

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
            summary = (full.get("summary") or "").strip()
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

            source_ref, inserted = insert_queue_row(full)
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
