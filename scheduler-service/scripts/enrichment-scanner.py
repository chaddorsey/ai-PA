#!/usr/local/bin/python3
"""
Enrichment Pipeline Scanner — cycle-1 Postgres-canonical version.

Runs as a scheduler service script action every 30 seconds.

Cycle-1 redesign (2026-04-27):
- Pre-cycle-1 read from `spark_queue` and `pending_enrichment` BLOCKS.
  Both retired in Pattern 2 + new Postgres-canonical task substrate.
- This version reads `pa_web.tasks WHERE enrichment_state='pending'`
  and dispatches enrichment per row.
- Spark-drain dropped: slackbot, gmail-watch, and scan_meeting_notes
  now nudge tasks-agent directly when they write rows to
  `pa_web.task_queue`. The drain-from-block path no longer applies.

Source-aware dispatch:
- Each row in pa_web.tasks has `source` set (email | slack | meeting |
  meeting_marker | drive | google-docs-comment | ...). The dispatched
  enrichment message is unchanged — fetch_source_content uses the
  source field internally to dispatch to the right fetcher.
- Sources may add their own tooling extensions (e.g., email needs
  thread-walk, slack needs surrounding-channel-fetch, meeting needs
  Granola transcript). The 4-tool chain (Phase A.3) handles these
  distinctions internally.

Operational model:
- Cron: every 30s
- Per cycle: claim ONE pending row, mark it in_progress, dispatch the
  enrichment message
- Atomic claim: UPDATE pa_web.tasks SET enrichment_state='in_progress',
  ... WHERE enrichment_state='pending' RETURNING ref_id (single
  statement; concurrent scanner cycles can't double-claim).
- On enrichment success: write_packet_info_tool (Phase A.3) flips
  enrichment_state to 'done'.
- On enrichment failure / timeout: a separate timeout-recovery pass
  (still pending) flips 'in_progress' rows older than N minutes back
  to 'pending' or 'failed'.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import psycopg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [enrichment-scanner] %(levelname)s %(message)s",
)
log = logging.getLogger("enrichment-scanner")

# Local-mode (2026-06-03): dispatch to letta-push-receiver instead of
# the Docker Letta server. The scanner runs inside scheduler-service,
# which reaches the host-side daemon via host.docker.internal.
PUSH_RECEIVER_URL = os.environ.get(
    "LETTA_PUSH_RECEIVER_URL",
    "http://host.docker.internal:8099/push",
)
PA_WEB_PG = os.environ.get(
    "PA_WEB_POSTGRES_URL",
    "postgresql://postgres:dev_password_123@supabase-db:5432/postgres",
)
TIMEOUT_MINUTES = int(os.environ.get("ENRICHMENT_TIMEOUT_MINUTES", "20"))


# ─── Postgres helpers ──────────────────────────────────────────────────

def claim_pending_row():
    """Atomically claim ONE row in enrichment_state='pending'.

    Returns the row's ref_id + source + minimal context, or None.
    """
    sql = """
        UPDATE pa_web.tasks
           SET enrichment_state = 'in_progress',
               updated_at = NOW()
         WHERE ref_id = (
             SELECT ref_id FROM pa_web.tasks
              WHERE enrichment_state = 'pending'
                AND closed_at IS NULL
                AND status IN ('extracted', 'active')
              ORDER BY extracted_at ASC NULLS LAST
              LIMIT 1
              FOR UPDATE SKIP LOCKED
         )
         RETURNING ref_id, source, source_ref, raw_description
    """
    with psycopg.connect(PA_WEB_PG, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "ref_id": row[0],
                "source": row[1],
                "source_ref": row[2],
                "raw_description": row[3],
            }


def recover_stuck_rows():
    """Flip 'in_progress' rows older than TIMEOUT_MINUTES back to 'pending'.

    Lets a stuck enrichment retry on a future scanner cycle. Capped at 3
    retries (tracked via enrichment.retry_count) before flipping to
    'failed' for human review.
    """
    sql = """
        WITH bumped AS (
            SELECT ref_id,
                   COALESCE((enrichment->>'retry_count')::int, 0) + 1 AS new_count
              FROM pa_web.tasks
             WHERE enrichment_state = 'in_progress'
               AND updated_at < NOW() - INTERVAL '%s minutes'
        )
        UPDATE pa_web.tasks t
           SET enrichment_state = CASE
                   WHEN bumped.new_count >= 3 THEN 'failed'
                   ELSE 'pending'
               END,
               enrichment = COALESCE(enrichment, '{}'::jsonb)
                          || jsonb_build_object('retry_count', bumped.new_count),
               updated_at = NOW()
          FROM bumped
         WHERE t.ref_id = bumped.ref_id
         RETURNING t.ref_id, t.enrichment_state, bumped.new_count
    """ % TIMEOUT_MINUTES
    with psycopg.connect(PA_WEB_PG, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            recovered = cur.fetchall()
    if recovered:
        for r in recovered:
            log.warning(
                f"timeout recovery: ref_id={r[0]} → state={r[1]} retry={r[2]}"
            )


# ─── Receiver dispatch helpers ─────────────────────────────────────────


def dispatch_enrichment(row):
    """Send the source-aware enrichment message.

    fetch_source_content auto-detects source via source_metadata in
    pa_web.tasks, so the message itself is source-agnostic; per-source
    handling lives in the tool.
    """
    ref_id = row["ref_id"]
    source = row["source"] or "unknown"
    desc = (row["raw_description"] or "")[:120]

    message = (
        f"[Enrich] task ref_id={ref_id} source={source}\n"
        f"Current raw_description (USER-SUPPLIED ANCHOR — preserve unless "
        f"clearly malformed): {desc}\n\n"
        f"Run the enrichment chain:\n"
        f'1. fetch_source_content(ref_id="{ref_id}") to load the full '
        f"source content (auto-dispatches to email/slack/meeting/drive "
        f"fetcher based on the row's source field).\n"
        f"2. Examine the content. For slack sources, the user-selected "
        f"message is wrapped in [*** ANCHOR — USER-SELECTED MESSAGE ***] "
        f"... [*** END ANCHOR ***]. For other sources the anchor is the "
        f"primary fetched content (email body, meeting transcript head, "
        f"comment text). The TASK STATEMENT must anchor on this content; "
        f"thread/channel/ambient context is for enrichment fields ONLY "
        f"(resources, knowns, unknowns, intent_genesis), NEVER to redefine "
        f"or swap the task topic.\n"
        f"3. ONLY call refine_task_description if the existing "
        f"raw_description (shown above) is clearly malformed — truncated "
        f"mid-sentence, contains an opaque ID with no verb, or is empty. "
        f"In normal cases (raw_description is a coherent verb-led "
        f"statement), DO NOT call refine_task_description; the user's "
        f"phrasing is canonical. If you do refine, the new title must "
        f"have substantial token overlap with raw_description and the "
        f"anchor message — not introduce a new topic from ambient context.\n"
        f"4. If the task warrants deeper context (links, related items, "
        f"resources to stage): call backtrace_task to get hop candidates, "
        f"pursue useful hops, then — AFTER staging any file/note-text "
        f"materials per step 4b so their openfile:// links are ready — call "
        f'write_packet_info(ref_id="{ref_id}", ...) with your synthesis '
        f"(direct_action, artifact_provenance, intent_genesis, context_brief, "
        f"resources, knowns, unknowns). Populate ALL THREE context nodes "
        f"whenever discoverable — they are the heart of the work packet: "
        f"(a) direct_action — who asked / where / what's done; MUST paraphrase "
        f"the anchor message, not a sibling/ambient one. "
        f"(b) artifact_provenance — where the primary artifact actually lives "
        f"and how it got there (the Drive doc, Slack file, repo, etc.). "
        f"(c) intent_genesis — WHY this matters: the originating decision, "
        f"prior meeting, strategy, or success criteria behind the ask. "
        f"Leave a node empty only when it is genuinely not discoverable.\n"
        f"4b. STAGING — do this BEFORE your write_packet_info call (step 4) so the "
        f"openfile:// links can be included in resources. Preferred for files & note "
        f"text. For resources that are real files or note text — NOT live Google "
        f"Workspace editing docs (Docs/Sheets/Slides — leave those as live links so the "
        f"user edits the current version) and NOT generic web pages — run "
        f"`task stage` to save a local copy and get an openfile:// link. Two forms:\n"
        f"   - Download a file/email/Drive attachment: "
        f'`task stage --url "<https-or-gmail:ID-or-drive-url>" --label "<label>" '
        f'--ref-id "{ref_id}" --priority primary`\n'
        f"   - Stage note text you already fetched (meeting transcript, email body) as "
        f'markdown: pipe the text in — `task fetch-source --ref-id "{ref_id}" | jq -r .content '
        f'| task stage --text - --label "Meeting notes" --ref-id "{ref_id}"`\n'
        f"   (--priority is optional; it defaults to secondary.) "
        f"   Each call returns an `openfile_url`. Add it to the SAME resource line as the "
        f"live link so the user can pick: "
        f"`[primary] <label> — <live-url> | offline: <openfile-url> (read)`. If there is no "
        f"live URL, the openfile:// link alone is fine.\n\n"
        f"5. If the task is already clear from the anchor, call "
        f'write_packet_info(ref_id="{ref_id}", direct_action="...") with '
        f"minimal fields and stop.\n"
        f"6. ALWAYS pass estimated_minutes on your write_packet_info call — your "
        f"realistic best estimate of how long the task will take to DO (not to "
        f"schedule), based on its complexity and the context you gathered, rounded "
        f"to the nearest 5 minutes. This is the agent baseline the eval loop "
        f"measures against, so estimate honestly even when the task seems quick.\n\n"
        f"RESOURCE FORMATTING (ALL sources — not just slack): fetch_source_content "
        f"returns artifact URLs in `metadata`. ALWAYS populate the `resources` field "
        f"so the user can click straight to what they need:\n"
        f"  - The source permalink (metadata.permalink): the slack message, the email "
        f"(mail.google.com permalink), the Granola meeting note (web_url), or the docs "
        f"comment (disco-anchored doc URL). Use the EXACT permalink URL.\n"
        f"  - The PRIMARY ARTIFACT the task acts on, if different from the source: e.g. "
        f"a task to 'revise the SOW doc' → the Google Doc URL; 'review the attached PDF' "
        f"→ that file. Harvest these from the fetched content / backtrace anchors.\n"
        f"Format each on its own line: `[priority] <short label> — <url> (role)` where "
        f"priority is primary|secondary|background and role is a hint like edit, review, "
        f"reference, or read. Example:\n"
        f"  [primary] Audubon SOW draft — https://docs.google.com/document/d/XXX/edit (edit)\n"
        f"  [secondary] Kickoff meeting notes — https://notes.granola.ai/d/YYY (reference)\n"
        f"  [primary] Signed PDF — https://example.com/contract.pdf | offline: openfile:///path/contract.pdf (read)\n"
        f"If a resource is a downloadable FILE (PDF, Word/Excel/PPT, a Gmail message you "
        f"want available offline, or note text the user should read in place), ALSO stage "
        f"a local copy — see step 4b.\n\n"
        f"All writes go to pa_web.tasks (NOT archival passages — that "
        f"path was retired in cycle 1)."
    )

    # Push to receiver — routes 'mc-completion' / explicit agent='tasks'
    # to the tasks agent's warm subprocess. We use agent='tasks' directly
    # since enrichment is intrinsically a tasks-agent responsibility,
    # not a per-source dispatch.
    body = {
        "agent": "tasks",
        "source_ref": ref_id,
        "prompt": message,
        "priority": "normal",
    }
    req = urllib.request.Request(
        PUSH_RECEIVER_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())
            log.info(
                f"dispatched ref_id={ref_id} via push receiver "
                f"(pid={payload.get('pid')}, push_count={payload.get('push_count')})"
            )
            return {"status": "dispatched"}
    except urllib.error.HTTPError as e:
        log.error(
            f"dispatch failed for ref_id={ref_id}: HTTP {e.code} "
            f"{e.read()[:200].decode('utf-8', 'replace')}"
        )
        return {"status": "error"}
    except Exception as e:
        log.error(f"dispatch unreachable for ref_id={ref_id}: {e}")
        return {"status": "error"}


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    # 1. Recover any stuck in_progress rows (timeout-driven retry).
    try:
        recover_stuck_rows()
    except Exception as e:
        log.error(f"timeout recovery failed: {e}")

    # 2. Claim + dispatch one pending row.
    try:
        row = claim_pending_row()
    except Exception as e:
        log.error(f"claim failed: {e}")
        return 1
    if row is None:
        return 0  # nothing pending; quiet exit

    log.info(f"claimed ref_id={row['ref_id']} source={row['source']}")
    result = dispatch_enrichment(row)

    # 3. If dispatch failed, flip back to pending so next cycle retries.
    if result.get("status") != "dispatched":
        try:
            with psycopg.connect(PA_WEB_PG, autocommit=True, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pa_web.tasks SET enrichment_state='pending' WHERE ref_id=%s",
                        (row['ref_id'],),
                    )
            log.info(f"reverted ref_id={row['ref_id']} to pending")
        except Exception as e:
            log.error(f"revert-to-pending failed for {row['ref_id']}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
