#!/usr/bin/env python3
"""draft_meeting_followup.py — script-driven post-meeting follow-up drafts.

Replaces the dead agent chain (scan_meeting_notes → archival → agent hand-rolls
gws). The prior chain's deterministic core, prepare_meeting_followup
(letta/meeting_followup_tool.py), is excellent and is reused verbatim — it
formats the D/NA HTML, normalizes phrasing, creates the gws draft, applies the
Followup label, and returns a real draft_id. We re-source its INPUTS from the
APIs we now have and take the --yolo agent off the side-effect path entirely:

  - participants  ← Granola REST `attendees` ({name,email}) — was the old weak
                    spot (email resolution); now exact.
  - summary       ← Granola REST `summary_markdown`.
  - markers       ← Granola MCP `<private_notes>` ([c]/[;]/D:) — the only place
                    the user's raw notes live (REST doesn't expose them).
  - the 3 lists (decisions | my_actions | their_actions) ← ONE bounded litellm
    call (markers authoritative, summary augments). That is the only LLM step;
    everything else is deterministic, so a draft is either really created
    (real draft_id) or we log a loud failure — never a fabricated success.

Idempotent via a state file of meeting UUIDs already drafted.

Usage: python3 draft_meeting_followup.py [--window-days 2] [--meeting <id>] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Reuse existing building blocks (both live in scripts/).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poll_granola as rest          # api_request / list_notes_since / fetch_note_full
import scan_meeting_markers as mk    # fetch_private_notes / extract_markers

# Reuse the deterministic draft builder.
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
sys.path.insert(0, _REPO)
from letta.meeting_followup_tool import prepare_meeting_followup  # noqa: E402

LITELLM_URL = os.environ.get("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
SYNTH_MODEL = os.environ.get("FOLLOWUP_MODEL", "gpt-4.1-mini")
STATE_PATH = Path(os.environ.get(
    "FOLLOWUP_STATE", f"{_REPO}/logs/health/meeting-drafts.state"))


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"[{ts()}] [followup-draft] {msg}", flush=True)


def load_state() -> set[str]:
    try:
        return set(json.loads(STATE_PATH.read_text()).get("drafted", []))
    except Exception:
        return set()


def save_state(drafted: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"drafted": sorted(drafted)}, indent=2))
    tmp.replace(STATE_PATH)


def _et_datetime(iso: str) -> str:
    """ISO created_at → 'YYYY-MM-DD HH:MM' in America/New_York (for the tool's
    morning/afternoon phrasing). Falls back to the date alone on parse trouble."""
    try:
        import pytz
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(pytz.timezone("America/New_York"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (iso or "")[:10]


def synthesize(summary_md: str, private_notes: str) -> dict | None:
    """ONE litellm call → {decisions, my_actions, their_actions} (lists)."""
    sys_prompt = (
        "You prepare a post-meeting follow-up email for Chad Dorsey. From the "
        "meeting's AI summary and Chad's raw private notes, extract three lists. "
        "Chad's notes may contain markers: [c] = Chad's own task, [;] = someone "
        "else's action item, 'D:' or 'Decision:' = an explicit decision. Markers "
        "are AUTHORITATIVE; the summary AUGMENTS (add clear action items it "
        "contains that the markers missed). Rules:\n"
        "- decisions: ONLY explicit decisions (D:/Decision: markers, or a clear "
        "group agreement). Rare — usually empty. Status/progress are NOT decisions.\n"
        "- my_actions: Chad's action items (from [c] + summary), each a short "
        "imperative phrase; include an inline deadline only if explicitly stated.\n"
        "- their_actions: others' items as full 'Name to <verb> ...' sentences "
        "(from [;] + summary).\n"
        "Output STRICT JSON only: "
        '{"decisions":[],"my_actions":[],"their_actions":[]} . Empty lists are fine.'
    )
    user = f"AI SUMMARY:\n{summary_md or '(none)'}\n\nCHAD'S RAW NOTES:\n{private_notes or '(none)'}"
    body = {
        "model": SYNTH_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        LITELLM_URL.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {LITELLM_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        out = json.loads(content)
    except Exception as e:
        log(f"  synthesis FAILED ({type(e).__name__}: {str(e)[:140]})")
        return None
    # Normalize to lists of clean strings.
    norm = {}
    for k in ("decisions", "my_actions", "their_actions"):
        v = out.get(k) or []
        if isinstance(v, str):
            v = [v]
        norm[k] = [str(x).strip() for x in v if str(x).strip()]
    return norm


def _uuid_from(s: str) -> str | None:
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s or "")
    return m.group(0) if m else None


def process_meeting(full: dict, uuid: str, dry_run: bool) -> str:
    """Return 'created' | 'empty' | 'failed' for one already-fetched REST note.

    `uuid` is the Granola document UUID (from web_url) used for MCP markers +
    state keying; falls back to the REST not_* id when no UUID is available.
    """
    title = full.get("title") or "Meeting"
    summary_md = full.get("summary_markdown") or full.get("summary_text") or ""

    # Participants (exclude none here — the tool drops the sender).
    attendees = full.get("attendees") or []
    participants = ", ".join(
        f"{a.get('name','').strip()} <{a.get('email','').strip()}>"
        for a in attendees if a.get("email")
    )

    # Markers from MCP private_notes (best-effort; summary alone still works).
    private_notes = ""
    if uuid and re.match(r"^[0-9a-f-]{36}$", uuid):
        pn = mk.fetch_private_notes(uuid)
        if pn:  # None=fetch failed, ""=no notes — both → no markers
            private_notes = pn
    had_markers = bool(mk.extract_markers(private_notes)) if private_notes else False

    if not summary_md and not private_notes:
        return "empty"

    lists = synthesize(summary_md, private_notes)
    if lists is None:
        return "failed"
    if not (lists["decisions"] or lists["my_actions"] or lists["their_actions"]):
        log(f"  no actions/decisions for {title[:40]!r} — skipping draft")
        return "empty"

    if dry_run:
        log(f"  [DRY] would draft {title[:40]!r} to [{participants[:60]}] "
            f"decisions={len(lists['decisions'])} my={len(lists['my_actions'])} "
            f"their={len(lists['their_actions'])} markers={had_markers}")
        return "created"

    res = prepare_meeting_followup(
        meeting_id=uuid,
        meeting_title=title,
        meeting_date=_et_datetime(full.get("created_at", "")),
        participants=participants,
        decisions="|".join(lists["decisions"]) or None,
        my_actions="|".join(lists["my_actions"]) or None,
        their_actions="|".join(lists["their_actions"]) or None,
        proposed=(not had_markers),  # label AI-only drafts "Proposed"
    )
    if res.get("status") == "ok" and res.get("draft_id"):
        log(f"  ✓ draft {res['draft_id']} for {title[:40]!r} → {res.get('email_to','')[:60]}")
        return "created"
    log(f"  ✗ draft FAILED for {title[:40]!r}: {res.get('error_message','?')[:160]}")
    return "failed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=2)
    ap.add_argument("--meeting", default=None, help="Target a single REST note id.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Ignore the drafted-state file.")
    args = ap.parse_args()

    api_key = os.environ.get("GRANOLA_API_KEY", "")
    if not api_key:
        log("FATAL: GRANOLA_API_KEY not set")
        return 1

    if args.meeting:
        notes = [{"id": args.meeting}]
    else:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=args.window_days)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        notes = rest.list_notes_since(since, api_key, limit=20)
    log(f"considering {len(notes)} meeting(s) (last ~{args.window_days}d)")

    state = set() if args.force else load_state()
    created = skipped = empty = failed = 0
    for note in notes:
        nid = note.get("id")
        try:
            full = rest.fetch_note_full(nid, api_key)
        except Exception as e:
            log(f"  ERROR fetching {nid}: {type(e).__name__}: {str(e)[:120]}")
            failed += 1
            continue
        uuid = _uuid_from(full.get("web_url", "")) or nid  # UUID for MCP + state
        if uuid in state and not args.force:
            skipped += 1
            continue
        try:
            outcome = process_meeting(full, uuid, args.dry_run)
        except Exception as e:
            log(f"  ERROR on {nid}: {type(e).__name__}: {str(e)[:140]}")
            outcome = "failed"
        if outcome == "created":
            created += 1
            if not args.dry_run:
                state.add(uuid)
                save_state(state)
        elif outcome == "empty":
            empty += 1
            if not args.dry_run:   # nothing to draft → don't reconsider forever
                state.add(uuid)
                save_state(state)
        elif outcome == "skipped":
            skipped += 1
        else:
            failed += 1

    log(f"done: created={created} empty/skip-noted={empty} already_drafted={skipped} "
        f"failed={failed}" + (" (dry-run)" if args.dry_run else ""))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
