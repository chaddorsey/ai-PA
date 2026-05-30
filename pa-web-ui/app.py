"""PA Web UI - Flask application for chat interface."""

import json
import os
import queue
import re
import threading
import time
import uuid
from typing import Any, Dict, Generator, Optional

import httpx


# Pattern to strip internal SUMMARY/REFS lines from user-facing responses
# SUMMARY can appear at start of line OR after punctuation mid-text
SUMMARY_PATTERN = re.compile(r"\s*SUMMARY:.*$", re.MULTILINE)
REFS_PATTERN = re.compile(r"\s*REFS:\s*\{.*\}$", re.MULTILINE)

# Common phrases that start user-facing responses (after inner monologue)
USER_FACING_STARTERS = [
    "Here is ", "Here's ", "I found ", "I've found ", "I located ",
    "The ", "Your ", "Based on ", "According to ", "Looking at ",
    "Let me ", "I'll ", "I can ", "I see ", "I notice ",
    "There are ", "There is ", "This is ", "That ",
    "Yes", "No", "Sure", "Absolutely", "Unfortunately",
    "---",  # Markdown separator often starts formatted content
]


def clean_response_for_user(text: str) -> str:
    """Strip SUMMARY, REFS, and Inner monologue sections from user-facing response."""
    if not text:
        return text

    cleaned = text

    # Handle "Inner monologue:" sections - find where actual content starts
    if cleaned.startswith("Inner monologue:"):
        # Try to find where user-facing content begins
        best_pos = -1
        for starter in USER_FACING_STARTERS:
            pos = cleaned.find(starter)
            if pos > 0 and (best_pos == -1 or pos < best_pos):
                best_pos = pos

        if best_pos > 0:
            # Found user-facing content - extract it
            cleaned = cleaned[best_pos:]
        else:
            # Fallback: look for double newline followed by non-internal text
            # Try splitting on common internal markers and take last section
            parts = re.split(r'\n\n(?=(?!Inner monologue:|Action plan:|Proceeding to))', cleaned)
            if len(parts) > 1:
                # Take the last substantial part
                for part in reversed(parts):
                    stripped = part.strip()
                    if stripped and not stripped.startswith(("Inner monologue:", "Action plan:", "Proceeding to")):
                        cleaned = stripped
                        break

    # Strip SUMMARY and REFS lines
    cleaned = SUMMARY_PATTERN.sub("", cleaned)
    cleaned = REFS_PATTERN.sub("", cleaned)

    # Clean up extra blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()
import structlog
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

# Retry configuration for transient errors
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = {502, 503, 504}

# Keepalive ping interval in seconds (keeps frontend connection alive during long operations)
KEEPALIVE_PING_INTERVAL = 15.0
# Letta stream timeout in seconds
LETTA_STREAM_TIMEOUT = 300.0

# Configure structured logging
import logging
import sys

# Set up basic logging to stdout
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


def build_web_ui_system_reminder() -> str:
    """Build a <system-reminder> block identifying the pa-web-ui environment.

    Tells the agent what rendering capabilities are available so it can
    format responses appropriately (e.g. HTML tables, styled blocks, etc.).
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "<system-reminder>\n"
        "## Environment\n"
        "- **Client**: pa-web-ui (custom web dashboard)\n"
        "- **Renderer**: HTML with markdown support\n"
        "- **Supports**: HTML tags, markdown, tables, code blocks with syntax highlighting, "
        "links, images, lists, bold/italic/strikethrough, blockquotes, horizontal rules\n"
        "- **Does NOT support**: ANSI escape codes, terminal formatting, LaTeX math\n"
        "- **Prefer**: Rich HTML formatting over plain text when presenting structured data "
        "(tables, styled lists, cards). Use markdown headers for section organization.\n"
        f"- **Timestamp**: {now}\n"
        "</system-reminder>"
    )


app = Flask(__name__)
CORS(app)

# HTTP ingress guard: Origin allowlist + CSRF double-submit + Host allowlist.
# Runs before route dispatch on all requests. See docs/security/pa-web-ui-threat-model.md.
from ingress_guard import configure_ingress_guard
configure_ingress_guard(app)

# Letta-code subprocess pool (Phase 1). Module-level singleton.
# Gated by PA_WEB_UI_PHASE_1_ENABLED for the /stream MC dispatch (Unit 1.5).
from subprocess_pool import (
    SpawnTimeoutError,
    SubprocessDeadError,
    TurnLockedException,
    get_registry,
)
subprocess_registry = get_registry()

PA_WEB_UI_PHASE_1_ENABLED = os.environ.get(
    "PA_WEB_UI_PHASE_1_ENABLED", "false"
).strip().lower() in ("true", "1", "yes", "on")

PA_WEB_UI_PHASE_2_ENABLED = os.environ.get(
    "PA_WEB_UI_PHASE_2_ENABLED", "false"
).strip().lower() in ("true", "1", "yes", "on")

# Phase 2 Unit 2.5: LLM auto-naming. Fires once per conversation on its
# first `result` event, unless the user has manually renamed it.
PA_WEB_UI_AUTONAME_ENABLED = os.environ.get(
    "PA_WEB_UI_AUTONAME_ENABLED", "true"
).strip().lower() in ("true", "1", "yes", "on")
PA_WEB_UI_AUTONAME_MODEL = os.environ.get(
    "PA_WEB_UI_AUTONAME_MODEL", "gpt-5.4-mini"
)
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

_AUTONAME_TIMESTAMP_RE = re.compile(
    r"^(New conversation|Fork) \d{4}-\d{2}-\d{2}"
)

# Phase 2 backfill gate. Mutation routes (POST/PATCH/DELETE/fork) return
# HTTP 503 "backfill_in_progress" until the background migration finishes.
# Read routes serve during backfill (data pre-backfill is still valid history).
_PHASE2_BACKFILL_COMPLETE = threading.Event()

# Configuration from environment
ROUTING_HANDLER_URL = os.getenv(
    "PA_ROUTING_HANDLER_URL", "http://pa-routing-handler:5201"
)
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")
GWS_BRIDGE_URL = os.getenv("GWS_BRIDGE_URL", "http://gws-bridge:8098")
MISSION_CONTROL_AGENT_ID = os.environ.get(
    "MISSION_CONTROL_AGENT_ID", "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"
)
LETTABOT_API_URL = os.environ.get("LETTABOT_API_URL", "http://host.docker.internal:8080")
LETTABOT_API_KEY = os.environ.get("LETTABOT_API_KEY", "")

# Database configuration
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from contextlib import contextmanager

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@supabase-db:5432/postgres"
)


def ensure_pa_web_schema():
    """Create or migrate pa_web schema. Idempotent on every boot.

    Phase 1 originally returned early if the schema existed. Phase 2's
    DDL (ADD COLUMN, RENAME COLUMN, new conversation_meta table) must
    run on existing deploys, so the early-return is gone. All statements
    use `IF NOT EXISTS` idempotency; the one exception (RENAME COLUMN,
    which has no IF EXISTS form) is wrapped in an information_schema
    type-check guard so the second boot is a no-op.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                # Phase-1 baseline DDL — every statement already idempotent.
                cur.execute("""
                    CREATE SCHEMA IF NOT EXISTS pa_web;

                    CREATE TABLE IF NOT EXISTS pa_web.conversations (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        message TEXT NOT NULL,
                        agent_id TEXT DEFAULT '',
                        agent_name TEXT DEFAULT '',
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS pa_web.routing_signals (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        slash_command TEXT NOT NULL,
                        utterance TEXT,
                        target_agent_id TEXT NOT NULL,
                        target_agent_name TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS pa_web.thread_exchanges (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        thread_position INTEGER NOT NULL,
                        role TEXT NOT NULL,
                        message TEXT NOT NULL,
                        agent_id TEXT DEFAULT '',
                        agent_name TEXT DEFAULT '',
                        parent_request_id TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS pa_web.response_feedback (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        feedback_type TEXT NOT NULL,
                        actual_agent_id TEXT DEFAULT '',
                        actual_agent_name TEXT DEFAULT '',
                        intended_agent_id TEXT,
                        intended_agent_name TEXT,
                        conversation_id INTEGER,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_conversations_session ON pa_web.conversations(session_id);
                    CREATE INDEX IF NOT EXISTS idx_conversations_created ON pa_web.conversations(created_at);
                    CREATE INDEX IF NOT EXISTS idx_routing_signals_session ON pa_web.routing_signals(session_id);
                    CREATE INDEX IF NOT EXISTS idx_thread_exchanges_session ON pa_web.thread_exchanges(session_id);
                    CREATE INDEX IF NOT EXISTS idx_thread_exchanges_request ON pa_web.thread_exchanges(request_id);
                    CREATE INDEX IF NOT EXISTS idx_response_feedback_session ON pa_web.response_feedback(session_id);
                """)

                # --- Phase 2 Unit 2.1: schema extension (idempotent) ---

                # Rename the dead INTEGER response_feedback.conversation_id
                # to local_conversation_pk so we can reuse the conversation_id
                # name for the new TEXT Letta-UUID column. The rename is
                # guarded by information_schema: it only fires when the
                # column still has its old INTEGER shape. After the first
                # successful boot under Phase 2, this guard short-circuits.
                cur.execute("""
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                         WHERE table_schema='pa_web'
                           AND table_name='response_feedback'
                           AND column_name='conversation_id'
                           AND data_type='integer'
                      ) THEN
                        ALTER TABLE pa_web.response_feedback
                          RENAME COLUMN conversation_id TO local_conversation_pk;
                      END IF;
                    END $$;
                """)

                # Add new TEXT conversation_id to all four tables.
                cur.execute("""
                    ALTER TABLE pa_web.conversations
                      ADD COLUMN IF NOT EXISTS conversation_id TEXT;
                    ALTER TABLE pa_web.routing_signals
                      ADD COLUMN IF NOT EXISTS conversation_id TEXT;
                    ALTER TABLE pa_web.thread_exchanges
                      ADD COLUMN IF NOT EXISTS conversation_id TEXT;
                    ALTER TABLE pa_web.response_feedback
                      ADD COLUMN IF NOT EXISTS conversation_id TEXT;
                """)

                # Conversation-level metadata table. See the Phase 2 plan
                # Key Technical Decisions: per-conv attributes (label,
                # parent link, user_renamed gate) live here 1:1 with
                # Letta conversation UUIDs; per-message data stays in
                # pa_web.conversations.
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pa_web.conversation_meta (
                        conversation_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        session_id TEXT,
                        label TEXT,
                        parent_conversation_id TEXT,
                        user_renamed BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        renamed_at TIMESTAMP,
                        metadata JSONB
                    );

                    CREATE INDEX IF NOT EXISTS idx_conversation_meta_agent
                      ON pa_web.conversation_meta(agent_id);
                    CREATE INDEX IF NOT EXISTS idx_conversations_conv_id
                      ON pa_web.conversations(conversation_id);
                    CREATE INDEX IF NOT EXISTS idx_thread_exchanges_conv_id
                      ON pa_web.thread_exchanges(conversation_id);
                """)

                # --- Cycle 1: organizational memory substrate ---
                # Pattern 2: single task_queue replaces the per-source queue
                # blocks. Pattern 5: pa_web.tasks absorbs both block-line and
                # archival-passage layers; tasks_quarantine catches malformed
                # passages during the archival lift (Unit 12).

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pa_web.task_queue (
                        id BIGSERIAL PRIMARY KEY,
                        source TEXT NOT NULL CHECK (source IN
                            ('email','slack','drive','meeting','meeting_marker')),
                        source_ref TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        claimed_at TIMESTAMPTZ NULL,
                        processed_at TIMESTAMPTZ NULL,
                        UNIQUE (source, source_ref)
                    );

                    CREATE INDEX IF NOT EXISTS idx_task_queue_source_unclaimed
                      ON pa_web.task_queue (source, created_at)
                      WHERE claimed_at IS NULL;

                    CREATE TABLE IF NOT EXISTS pa_web.tasks (
                        ref_id TEXT PRIMARY KEY,
                        extracted_at TIMESTAMPTZ,
                        source TEXT,
                        source_ref TEXT,
                        origin TEXT,
                        suggested_title TEXT NULL,
                        confirmed_title TEXT NULL,
                        original_est_minutes INTEGER,
                        revised_est_minutes INTEGER NULL,
                        actual_minutes INTEGER NULL,
                        raw_description TEXT,
                        extracted_by TEXT,
                        status TEXT,
                        merged_into TEXT NULL,
                        omnifocus_id TEXT NULL,
                        due_date DATE NULL,
                        priority INTEGER NULL,
                        owner TEXT NULL,
                        task_body TEXT,
                        source_metadata JSONB,
                        related_urls TEXT[],
                        omnifocus_pending_at TIMESTAMPTZ NULL,
                        omnifocus_created_at TIMESTAMPTZ NULL,
                        enrichment JSONB NULL,
                        agent_notes TEXT NULL,
                        merge_parent_id TEXT NULL,
                        tags TEXT[] DEFAULT '{}',
                        migration_source TEXT NOT NULL DEFAULT 'live'
                            CHECK (migration_source IN ('archival_lift','live')),
                        enrichment_state TEXT NULL
                            CHECK (enrichment_state IS NULL OR enrichment_state IN
                                   ('pending','in_progress','done','skipped','failed')),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        started_at TIMESTAMPTZ NULL,
                        closed_at TIMESTAMPTZ NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_tasks_status_updated
                      ON pa_web.tasks (status, updated_at);
                    CREATE INDEX IF NOT EXISTS idx_tasks_merged_into
                      ON pa_web.tasks (merged_into) WHERE merged_into IS NOT NULL;
                    CREATE INDEX IF NOT EXISTS idx_tasks_owner
                      ON pa_web.tasks (owner) WHERE owner IS NOT NULL;
                    CREATE INDEX IF NOT EXISTS idx_tasks_enrichment_state
                      ON pa_web.tasks (enrichment_state)
                      WHERE enrichment_state IN ('pending','in_progress','failed');

                    CREATE TABLE IF NOT EXISTS pa_web.tasks_quarantine (
                        passage_id TEXT PRIMARY KEY,
                        raw_text TEXT NOT NULL,
                        parse_error TEXT NOT NULL,
                        quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                    GRANT USAGE ON SCHEMA pa_web TO PUBLIC;
                    GRANT SELECT, INSERT, UPDATE, DELETE
                      ON pa_web.task_queue, pa_web.tasks, pa_web.tasks_quarantine
                      TO PUBLIC;
                    GRANT USAGE, SELECT ON SEQUENCE pa_web.task_queue_id_seq TO PUBLIC;
                """)

            conn.commit()
            logger.info("pa_web_schema_ready")
        finally:
            conn.close()
    except Exception as e:
        logger.error("pa_web_schema_creation_failed", error=str(e))


def _maybe_autoname_conversation(
    conv_id: str, first_user_message: str
) -> Optional[str]:
    """Phase 2 Unit 2.5: LLM-rename a conversation after its first turn.

    Returns the new label on success, None otherwise (flag-off, user
    already renamed, label not-default-pattern, litellm failure, or a
    race with a concurrent manual rename). Silent fail is intentional —
    label stays as the timestamp default and chat still works.
    """
    if not PA_WEB_UI_AUTONAME_ENABLED:
        return None
    if not conv_id or conv_id == "default":
        return None
    if not first_user_message:
        return None

    # Pre-check: is this conversation still auto-nameable?
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT label, user_renamed
                      FROM pa_web.conversation_meta
                     WHERE conversation_id = %s
                    """,
                    (conv_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                label, user_renamed = row
                if user_renamed:
                    return None
                if not label or not _AUTONAME_TIMESTAMP_RE.match(label):
                    return None
    except Exception as exc:
        logger.warning("autoname_precheck_failed", conv_id=conv_id, error=str(exc))
        return None

    # Call litellm (3s timeout; swallow failures).
    try:
        resp = http_client.post(
            f"{LITELLM_URL}/v1/chat/completions",
            json={
                "model": PA_WEB_UI_AUTONAME_MODEL,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Summarize the following in 3-6 words as a short "
                        "conversation title. No quotes, no period, no "
                        "trailing punctuation.\n\n"
                        + first_user_message[:500]
                    ),
                }],
                "max_tokens": 20,
                "temperature": 0.3,
            },
            headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"} if LITELLM_MASTER_KEY else {},
            timeout=3.0,
        )
        resp.raise_for_status()
        data = resp.json()
        new_label = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        new_label = new_label.strip('"\'').strip().rstrip(".").strip()
        if not new_label:
            return None
        new_label = new_label[:80]
    except Exception as exc:
        logger.warning("autoname_litellm_failed", conv_id=conv_id, error=str(exc))
        return None

    # Race-safe UPDATE: the user_renamed predicate guards against a
    # manual rename landing between our pre-check and UPDATE.
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pa_web.conversation_meta
                       SET label = %s, renamed_at = %s
                     WHERE conversation_id = %s
                       AND user_renamed = FALSE
                    """,
                    (new_label, datetime.utcnow(), conv_id),
                )
                if cur.rowcount == 0:
                    return None  # lost the race; user wins
            conn.commit()
    except Exception as exc:
        logger.warning("autoname_update_failed", conv_id=conv_id, error=str(exc))
        return None

    logger.info("autoname_applied", conv_id=conv_id, new_label=new_label)
    return new_label


def _resolve_mc_default_conv_uuid() -> Optional[str]:
    """Resolve MC's "default" alias to its real Letta conversation UUID.

    See docs/reference/letta-default-alias-resolution.md. The resolver
    uses the `order_by=last_message_at&limit=1` path; returns the conv
    UUID of MC's most-recently-active conversation, which IS the one
    letta-code's "default" alias routes to server-side.
    """
    try:
        resp = http_client.get(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={
                "agent_id": MISSION_CONTROL_AGENT_ID,
                "order_by": "last_message_at",
                "limit": 1,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        convs = resp.json()
        if not convs:
            return None
        return convs[0]["id"]
    except Exception as exc:
        logger.error("default_conv_resolve_failed", error=str(exc))
        return None


def _phase2_backfill_once() -> None:
    """Background-thread backfill. Runs once after Flask starts serving.

    1. Resolve MC's default conv UUID.
    2. Batched UPDATE on the four pa_web tables — fill conversation_id
       for rows where NULL.
    3. INSERT conversation_meta row for the default conv (labeled "Main").
    Sets _PHASE2_BACKFILL_COMPLETE when done; mutation routes gate on it.

    Idempotent: re-running is a no-op (UPDATEs find no NULL rows; INSERT
    uses ON CONFLICT DO NOTHING).
    """
    try:
        default_uuid = _resolve_mc_default_conv_uuid()
        if not default_uuid:
            logger.warning("phase2_backfill_skipped_no_default_conv")
            _PHASE2_BACKFILL_COMPLETE.set()
            return

        logger.info("phase2_backfill_begin", default_uuid=default_uuid)
        batch = int(os.environ.get("PA_WEB_UI_BACKFILL_BATCH", "1000"))
        total_updated = 0

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for table in ("conversations", "routing_signals",
                              "thread_exchanges", "response_feedback"):
                    while True:
                        cur.execute(f"""
                            WITH todo AS (
                              SELECT id FROM pa_web.{table}
                               WHERE conversation_id IS NULL
                               LIMIT %s
                            )
                            UPDATE pa_web.{table} t
                               SET conversation_id = %s
                              FROM todo
                             WHERE t.id = todo.id
                        """, (batch, default_uuid))
                        n = cur.rowcount
                        conn.commit()
                        total_updated += n
                        if n == 0:
                            break

                # Insert Main meta row (idempotent).
                cur.execute("""
                    INSERT INTO pa_web.conversation_meta
                    (conversation_id, agent_id, session_id, label,
                     parent_conversation_id, user_renamed, created_at, metadata)
                    VALUES (%s, %s, NULL, %s, NULL, TRUE, NOW(), NULL)
                    ON CONFLICT (conversation_id) DO NOTHING
                """, (default_uuid, MISSION_CONTROL_AGENT_ID, "Main"))
                conn.commit()

        logger.info(
            "phase2_backfill_complete",
            default_uuid=default_uuid,
            rows_updated=total_updated,
        )
    except Exception as exc:
        logger.error("phase2_backfill_failed", error=str(exc))
    finally:
        _PHASE2_BACKFILL_COMPLETE.set()


def _start_phase2_backfill_thread() -> None:
    """Fire the backfill thread after Flask has bound. Called from
    app startup after the HTTP server is ready.
    """
    def _run():
        # Small delay to let Flask finish starting before we block the
        # first DB connection on a potentially-slow UPDATE.
        time.sleep(3)
        _phase2_backfill_once()

    t = threading.Thread(target=_run, name="phase2-backfill", daemon=True)
    t.start()


@contextmanager
def get_db_connection():
    """Get a database connection from the pool."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_conversation_message(
    session_id: str,
    role: str,
    message: str,
    agent_id: str = None,
    agent_name: str = None,
    request_id: str = None,
    extra_metadata: dict = None,
    conversation_id: str = None,
) -> None:
    """Save a conversation message to the database.

    Phase 2: conversation_id is the Letta conv UUID the message belongs
    to. When omitted (old Phase-1 call sites), the row is inserted with
    NULL — the Phase-2 backfill thread sweeps NULL rows at startup and
    fills them with the default conv UUID.
    """
    try:
        meta = {}
        if request_id:
            meta["request_id"] = request_id
        if extra_metadata:
            meta.update(extra_metadata)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.conversations
                    (session_id, role, message, agent_id, agent_name,
                     metadata, created_at, conversation_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        role,
                        message,
                        agent_id or "",
                        agent_name or "",
                        json.dumps(meta) if meta else None,
                        datetime.utcnow(),
                        conversation_id,
                    ),
                )
        logger.info("conversation_saved", session_id=session_id, role=role)
    except Exception as e:
        logger.error("conversation_save_failed", error=str(e))


def get_conversation_history(
    session_id: str, limit: int = 100, conversation_id: str = None
) -> list:
    """Get conversation history for a session.

    Phase 2: when `conversation_id` is provided, it is the source of
    truth — the conversation thread is shared across all of the user's
    Tailnet devices/sessions (threat-model "shared-list-across-devices"
    invariant). session_id is IGNORED in that case so history from
    every device shows up.

    Back-compat: when conversation_id is None, filter by session_id
    only (original Phase-1 behavior — individual device's history).
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get most recent N messages, then order them chronologically for display
                if conversation_id:
                    cur.execute(
                        """
                        SELECT * FROM (
                            SELECT id, session_id, role, message, agent_id, agent_name,
                                   metadata, created_at, conversation_id
                            FROM pa_web.conversations
                            WHERE conversation_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                        ) sub
                        ORDER BY created_at ASC
                        """,
                        (conversation_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM (
                            SELECT id, session_id, role, message, agent_id, agent_name,
                                   metadata, created_at
                            FROM pa_web.conversations
                            WHERE session_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s
                        ) sub
                        ORDER BY created_at ASC
                        """,
                        (session_id, limit),
                    )
                rows = cur.fetchall()
                # Convert to list of dicts with proper serialization
                result = []
                for row in rows:
                    item = dict(row)
                    item["created_at"] = item["created_at"].isoformat() if item["created_at"] else None
                    result.append(item)
                return result
    except Exception as e:
        logger.error("conversation_load_failed", error=str(e))
        return []


def save_routing_signal(
    session_id: str,
    slash_command: str,
    utterance: str,
    target_agent_id: str,
    target_agent_name: str = None,
) -> None:
    """Save an explicit routing signal (slash command) for learning."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.routing_signals
                    (session_id, slash_command, utterance, target_agent_id, target_agent_name, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        slash_command,
                        utterance,
                        target_agent_id,
                        target_agent_name or "",
                        datetime.utcnow(),
                    ),
                )
        logger.info("routing_signal_saved", session_id=session_id, command=slash_command)
    except Exception as e:
        logger.error("routing_signal_save_failed", error=str(e))


def save_thread_exchange(
    session_id: str,
    request_id: str,
    thread_position: int,
    role: str,
    message: str,
    agent_id: str = None,
    agent_name: str = None,
    parent_request_id: str = None,
) -> None:
    """Save a thread exchange for learning."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.thread_exchanges
                    (session_id, request_id, thread_position, role, message, agent_id, agent_name, parent_request_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        request_id,
                        thread_position,
                        role,
                        message,
                        agent_id or "",
                        agent_name or "",
                        parent_request_id,
                        datetime.utcnow(),
                    ),
                )
        logger.info("thread_exchange_saved", session_id=session_id, request_id=request_id, position=thread_position)
    except Exception as e:
        logger.error("thread_exchange_save_failed", error=str(e))


def save_response_feedback(
    session_id: str,
    request_id: str,
    feedback_type: str,
    actual_agent_id: str = None,
    actual_agent_name: str = None,
    intended_agent_id: str = None,
    intended_agent_name: str = None,
    local_conversation_pk: int = None,
    conversation_id: str = None,
) -> None:
    """Save user feedback on a response (thumbs up/down or agent correction).

    Phase 2 renames of `response_feedback.conversation_id INTEGER`
    → `local_conversation_pk`, and adds a new TEXT `conversation_id`
    column for Letta conv UUIDs. Both are optional for back-compat.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.response_feedback
                    (session_id, request_id, feedback_type, actual_agent_id, actual_agent_name,
                     intended_agent_id, intended_agent_name, local_conversation_pk,
                     conversation_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        request_id,
                        feedback_type,
                        actual_agent_id or "",
                        actual_agent_name or "",
                        intended_agent_id,
                        intended_agent_name,
                        local_conversation_pk,
                        conversation_id,
                        datetime.utcnow(),
                    ),
                )
        logger.info("response_feedback_saved", session_id=session_id, request_id=request_id, feedback_type=feedback_type)
    except Exception as e:
        logger.error("response_feedback_save_failed", error=str(e))


# HTTP client for short requests (agent list, config, etc.)
# Note: Streaming requests create their own clients to avoid concurrency issues
http_client = httpx.Client(timeout=30.0, follow_redirects=True)


# ── Task Lifecycle Log ──
# Single append-only JSONL capturing every task state transition for analytics/RL.
LIFECYCLE_LOG = os.path.join(
    os.getenv("FOLLOWUP_QUEUE", "/data/timer-logs/pending-followups.jsonl").rsplit("/", 1)[0],
    "task-lifecycle.jsonl",
)


def log_lifecycle(event: str, **fields):
    """Append a lifecycle event to the task-lifecycle.jsonl log."""
    entry = {"event": event, "timestamp": datetime.utcnow().isoformat() + "Z"}
    entry.update({k: v for k, v in fields.items() if v is not None})
    try:
        with open(LIFECYCLE_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Non-fatal — don't break the operation for logging


@app.route("/")
def index():
    """Main chat interface."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "pa-web-ui"})


@app.route("/api/subprocess/status", methods=["GET"])
def subprocess_status():
    """Observability endpoint for the letta-code subprocess pool (Unit 1.6 / R26).

    Gated by the ingress guard (R29) — same CSRF/Origin/Host check as
    /stream. Prevents Tailnet-visible conversation-id enumeration from
    non-allowlisted browsers.
    """
    return jsonify({
        "phase_1_enabled": PA_WEB_UI_PHASE_1_ENABLED,
        "mission_control_agent_id": MISSION_CONTROL_AGENT_ID,
        "handles": subprocess_registry.list_handles(),
    })


# NOTE: /api/subprocess/events/<conv_id> was a temporary debug endpoint
# used during Phase-1 live smoke to inspect the actual stream-json event
# shapes letta-code 0.23.8 emits. It was wired to help land the native-
# event → chat.js-event translator (commit 00b62fc). Removed now that
# Phase 1 + Phase 2 are stable. The ring buffer is still introspectable
# via /api/subprocess/status (Unit 1.6 endpoint).


# =====================================================================
# Phase 2 — first-class conversations: list, create, rename, delete, fork
# All routes gated by PA_WEB_UI_PHASE_2_ENABLED + ingress_guard.
# See docs/plans/2026-04-20-002-feat-pa-web-ui-conversation-switcher-plan.md
# =====================================================================


def _phase2_precondition_check() -> Optional[tuple]:
    """Shared gate for Phase-2 mutation routes. Returns None if ok;
    else a (response, status) tuple to `return *` from the caller."""
    if not PA_WEB_UI_PHASE_2_ENABLED:
        return jsonify({
            "error": "feature_disabled",
            "flag": "PA_WEB_UI_PHASE_2_ENABLED",
        }), 503
    if not _PHASE2_BACKFILL_COMPLETE.is_set():
        return jsonify({"error": "backfill_in_progress"}), 503
    return None


def _phase2_read_gate() -> Optional[tuple]:
    """Read routes only gate on flag; backfill-in-progress is fine."""
    if not PA_WEB_UI_PHASE_2_ENABLED:
        return jsonify({
            "error": "feature_disabled",
            "flag": "PA_WEB_UI_PHASE_2_ENABLED",
        }), 503
    return None


UUID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{3,100}$")


def _is_valid_conv_id(conv_id: Any) -> bool:
    return isinstance(conv_id, str) and bool(UUID_RE.match(conv_id))


def _letta_conversations_list(agent_id: str, limit: int = 100) -> list:
    """Fetch conv list from Letta, ordered most-recently-active first."""
    resp = http_client.get(
        f"{LETTA_BASE_URL}/v1/conversations/",
        params={
            "agent_id": agent_id,
            "order_by": "last_message_at",
            "limit": limit,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def _conversation_meta_rows(conv_ids: list) -> Dict[str, Dict[str, Any]]:
    """Fetch pa_web.conversation_meta rows for a set of conv_ids."""
    if not conv_ids:
        return {}
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT conversation_id, agent_id, session_id, label,
                       parent_conversation_id, user_renamed,
                       created_at, renamed_at, metadata
                  FROM pa_web.conversation_meta
                 WHERE conversation_id = ANY(%s)
                """,
                (conv_ids,),
            )
            return {row["conversation_id"]: dict(row) for row in cur.fetchall()}


@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    """List conversations for a specific agent. Defaults to MC.

    Query params:
      agent_id  — fleet agent ID (default: MC). Used to scope the
                  conversation list to the agent's workspace, so the
                  sidebar follows the model picker.

    Letta server is the canonical source; we LEFT-JOIN
    pa_web.conversation_meta for local metadata.
    """
    gate = _phase2_read_gate()
    if gate is not None:
        return gate
    requested_agent_id = (request.args.get("agent_id") or "").strip() or MISSION_CONTROL_AGENT_ID
    try:
        letta_convs = _letta_conversations_list(requested_agent_id, limit=100)
    except Exception as exc:
        logger.error("list_conversations_letta_failed", error=str(exc), agent_id=requested_agent_id)
        return jsonify({"error": "letta_unreachable"}), 502

    conv_ids = [c["id"] for c in letta_convs]
    meta_rows = _conversation_meta_rows(conv_ids)

    result = []
    for c in letta_convs:
        cid = c["id"]
        meta = meta_rows.get(cid, {})
        result.append({
            "id": cid,
            "agent_id": c["agent_id"],
            "label": meta.get("label"),
            "parent_conversation_id": meta.get("parent_conversation_id"),
            "user_renamed": meta.get("user_renamed", False),
            "last_message_at": c.get("last_message_at"),
            "created_at": c.get("created_at"),
        })
    return jsonify({"conversations": result})


@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    """Create a new Letta conversation + pa_web.conversation_meta row."""
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate

    data = request.get_json(force=True, silent=True) or {}
    label = data.get("label")
    agent_id = data.get("agent_id") or MISSION_CONTROL_AGENT_ID

    if label is not None:
        if not isinstance(label, str):
            return jsonify({"error": "label_must_be_string"}), 400
        label = label.strip()[:200] or None

    user_set = bool(label)
    if not user_set:
        label = f"New conversation {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

    try:
        resp = http_client.post(
            f"{LETTA_BASE_URL}/v1/conversations/",
            params={"agent_id": agent_id},
            json={"label": label},
            timeout=10.0,
        )
        resp.raise_for_status()
        letta_conv = resp.json()
    except Exception as exc:
        logger.error("create_conversation_letta_failed", error=str(exc))
        return jsonify({"error": "letta_create_failed"}), 502

    conv_id = letta_conv.get("id")
    if not _is_valid_conv_id(conv_id):
        logger.error("create_conversation_malformed_response", response=letta_conv)
        return jsonify({"error": "letta_malformed_response"}), 502

    device_id = request.cookies.get("pa_device_id", "").strip() or None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.conversation_meta
                    (conversation_id, agent_id, session_id, label,
                     parent_conversation_id, user_renamed, created_at)
                    VALUES (%s, %s, %s, %s, NULL, %s, NOW())
                    """,
                    (conv_id, agent_id, device_id, label, user_set),
                )
            conn.commit()
    except Exception as exc:
        logger.error("conversation_meta_insert_failed", error=str(exc), conv_id=conv_id)
        # Roll back the Letta conv to avoid orphans.
        try:
            http_client.delete(f"{LETTA_BASE_URL}/v1/conversations/{conv_id}/", timeout=5.0)
        except Exception:
            pass
        return jsonify({"error": "conversation_meta_insert_failed"}), 500

    return jsonify({
        "id": conv_id,
        "agent_id": agent_id,
        "label": label,
        "user_renamed": user_set,
        "parent_conversation_id": None,
        "created_at": letta_conv.get("created_at"),
    }), 201


@app.route("/api/conversations/<conv_id>", methods=["PATCH"])
def rename_conversation(conv_id: str):
    """Rename a conversation (sets user_renamed=TRUE)."""
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate
    if not _is_valid_conv_id(conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400

    data = request.get_json(force=True, silent=True) or {}
    new_label = data.get("label")
    if not isinstance(new_label, str) or not new_label.strip():
        return jsonify({"error": "label_required"}), 400
    new_label = new_label.strip()[:200]

    # Verify the conversation exists on the Letta server before we
    # mint a local meta row for it.
    try:
        letta_resp = http_client.get(
            f"{LETTA_BASE_URL}/v1/conversations/{conv_id}/",
            timeout=10.0,
        )
        if letta_resp.status_code == 404:
            return jsonify({"error": "not_found"}), 404
        letta_resp.raise_for_status()
        letta_conv = letta_resp.json()
    except Exception as exc:
        logger.error("rename_conversation_letta_lookup_failed",
                     error=str(exc), conv_id=conv_id)
        return jsonify({"error": "letta_unreachable"}), 502

    conv_agent_id = letta_conv.get("agent_id") or MISSION_CONTROL_AGENT_ID
    device_id = request.cookies.get("pa_device_id", "").strip() or None

    # UPSERT the meta row. Covers two cases:
    # 1. Row exists (pa-web-ui-created conv) → UPDATE label / user_renamed.
    # 2. Row missing (pre-existing Letta conv with no local meta) → INSERT
    #    with user_renamed=TRUE and the new label.
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.conversation_meta
                    (conversation_id, agent_id, session_id, label,
                     parent_conversation_id, user_renamed, created_at, renamed_at)
                    VALUES (%s, %s, %s, %s, NULL, TRUE, NOW(), NOW())
                    ON CONFLICT (conversation_id) DO UPDATE
                      SET label = EXCLUDED.label,
                          user_renamed = TRUE,
                          renamed_at = NOW()
                    """,
                    (conv_id, conv_agent_id, device_id, new_label),
                )
            conn.commit()
    except Exception as exc:
        logger.error("rename_conversation_failed", error=str(exc), conv_id=conv_id)
        return jsonify({"error": "rename_failed"}), 500

    return jsonify({"id": conv_id, "label": new_label, "user_renamed": True})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def delete_conversation(conv_id: str):
    """Hard-delete: remove from all pa_web tables + Letta server.

    Client's 10s undo toast fires this after the timer expires.
    """
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate
    if not _is_valid_conv_id(conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400

    # Notify any attached SSE subscribers before we kill their handle.
    handle = subprocess_registry._handles.get(conv_id)
    if handle is not None:
        marker = {
            "type": "conversation_deleted",
            "conv_id": conv_id,
            "_seq_id": 0,
            "_emitted_at": time.time(),
        }
        with handle.subscriber_lock:
            subs = list(handle.subscribers)
        for sub in subs:
            try:
                sub.put_nowait(marker)
            except queue.Full:
                pass
        subprocess_registry.invalidate(conv_id)

    # Delete from all 5 pa_web tables in one transaction.
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM pa_web.conversations WHERE conversation_id = %s", (conv_id,))
                cur.execute("DELETE FROM pa_web.thread_exchanges WHERE conversation_id = %s", (conv_id,))
                cur.execute("DELETE FROM pa_web.routing_signals WHERE conversation_id = %s", (conv_id,))
                cur.execute("DELETE FROM pa_web.response_feedback WHERE conversation_id = %s", (conv_id,))
                cur.execute("DELETE FROM pa_web.conversation_meta WHERE conversation_id = %s", (conv_id,))
            conn.commit()
    except Exception as exc:
        logger.error("delete_conversation_db_failed", error=str(exc), conv_id=conv_id)
        return jsonify({"error": "db_delete_failed"}), 500

    # Letta server copy — outside the transaction. If it fails, log and
    # continue; the local delete has already committed.
    try:
        resp = http_client.delete(
            f"{LETTA_BASE_URL}/v1/conversations/{conv_id}/",
            timeout=5.0,
        )
        if resp.status_code >= 400:
            logger.warning(
                "delete_conversation_letta_error",
                conv_id=conv_id,
                status=resp.status_code,
            )
    except Exception as exc:
        logger.warning("delete_conversation_letta_exception", error=str(exc), conv_id=conv_id)

    return jsonify({"id": conv_id, "status": "deleted"})


@app.route("/api/conversations/<conv_id>/cancel", methods=["POST"])
def cancel_conversation(conv_id: str):
    """Stop in-flight runs on a conversation: belt-and-suspenders cancel.

    1. Hit Letta's `POST /v1/conversations/{id}/cancel` — Redis-backed,
       terminates any active run at the next checkpoint.
    2. Invalidate the local subprocess handle — kills letta-code subprocess
       so it can't continue auto-approving the next Bash request after the
       cancelled run terminates.

    The Letta cancel alone often returns 409 ("no active runs to cancel")
    because runs in an approval loop complete in milliseconds with
    `stop_reason=requires_approval`; the *real* hang is the subprocess's
    next-step approval, which only the subprocess kill stops.

    Per task #102 — see docs/plans/2026-05-12-pa-web-cancel-button-plan.md.
    """
    if not _is_valid_conv_id(conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400

    handle = subprocess_registry._handles.get(conv_id)

    # Notify SSE subscribers so the UI can drop the streaming card.
    if handle is not None:
        marker = {
            "type": "conversation_cancelled",
            "conv_id": conv_id,
            "_seq_id": 0,
            "_emitted_at": time.time(),
        }
        with handle.subscriber_lock:
            subs = list(handle.subscribers)
        for sub in subs:
            try:
                sub.put_nowait(marker)
            except queue.Full:
                pass

    # Step 1: ask Letta to cancel any active run. Best-effort; a 409 just means
    # there's no run in flight at this microsecond (common when approval-loop
    # turns are completing every few ms). The subprocess kill below is what
    # actually breaks the loop.
    letta_status = None
    letta_detail = None
    try:
        resp = http_client.post(
            f"{LETTA_BASE_URL}/v1/conversations/{conv_id}/cancel",
            timeout=5.0,
        )
        letta_status = resp.status_code
        if resp.status_code >= 500:
            logger.warning(
                "cancel_conversation_letta_5xx",
                conv_id=conv_id, status=resp.status_code,
            )
        if resp.status_code >= 400:
            try:
                letta_detail = resp.json().get("detail")
            except Exception:
                letta_detail = resp.text[:200]
    except Exception as exc:
        logger.warning("cancel_conversation_letta_exception", error=str(exc), conv_id=conv_id)

    # Step 2: invalidate the subprocess handle — pops from _handles, bumps
    # generation, terminates the letta-code process (SIGTERM, then SIGKILL
    # after grace). Idempotent.
    subprocess_invalidated = handle is not None
    if subprocess_invalidated:
        try:
            subprocess_registry.invalidate(conv_id)
        except Exception as exc:
            logger.warning("cancel_conversation_invalidate_failed", error=str(exc), conv_id=conv_id)
            subprocess_invalidated = False

    log_lifecycle(
        "cancel_requested",
        conv_id=conv_id,
        letta_status=letta_status,
        letta_detail=letta_detail,
        subprocess_invalidated=subprocess_invalidated,
    )

    return jsonify({
        "id": conv_id,
        "status": "cancel_requested",
        "letta_status": letta_status,
        "subprocess_invalidated": subprocess_invalidated,
    })


@app.route("/api/conversations/<conv_id>/fork", methods=["POST"])
def fork_conversation(conv_id: str):
    """Fork a conversation via Letta. Atomic turn-lock check via
    handle.state_lock + `forking` flag.

    Memory-block caveat: Letta's fork shares agent-level blocks between
    parent and fork (Branch B; see docs/reference/letta-conversations-fork.md).
    The client UX is responsible for showing a banner — server doesn't
    restrict the fork itself.
    """
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate
    if not _is_valid_conv_id(conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400

    data = request.get_json(force=True, silent=True) or {}
    raw_label = data.get("label")
    label = raw_label.strip()[:200] if isinstance(raw_label, str) and raw_label.strip() else None
    user_set_label = bool(label)
    if not user_set_label:
        label = f"Fork {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    parent_request_id = data.get("parent_request_id") if isinstance(data.get("parent_request_id"), str) else None

    # Verify parent exists in conversation_meta.
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent_id FROM pa_web.conversation_meta WHERE conversation_id = %s",
                (conv_id,),
            )
            row = cur.fetchone()
            if row is None:
                return jsonify({"error": "parent_not_found"}), 410
            parent_agent_id = row[0]

    # Atomic turn-lock: under the parent handle's state_lock, verify
    # not in_flight / not already forking, then set forking=True.
    handle = subprocess_registry._handles.get(conv_id)
    if handle is not None:
        with handle.state_lock:
            if handle.in_flight or handle.forking:
                return jsonify({
                    "error": "parent_conversation_streaming",
                    "conv_id": conv_id,
                    "current_device_id": handle.in_flight_device_id,
                    "seq_id": handle.current_seq_id,
                }), 409
            handle.forking = True

    try:
        # Call Letta's fork endpoint.
        try:
            resp = http_client.post(
                f"{LETTA_BASE_URL}/v1/conversations/{conv_id}/fork/",
                params={"agent_id": parent_agent_id},
                timeout=15.0,
            )
            resp.raise_for_status()
            letta_conv = resp.json()
        except Exception as exc:
            logger.error("fork_conversation_letta_failed", error=str(exc), conv_id=conv_id)
            return jsonify({"error": "letta_fork_failed"}), 502

        child_id = letta_conv.get("id")
        if not _is_valid_conv_id(child_id):
            logger.error("fork_conversation_malformed_response", response=letta_conv)
            return jsonify({"error": "letta_malformed_fork_response"}), 502

        device_id = request.cookies.get("pa_device_id", "").strip() or None
        metadata = {"forked_at_request_id": parent_request_id} if parent_request_id else None
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO pa_web.conversation_meta
                        (conversation_id, agent_id, session_id, label,
                         parent_conversation_id, user_renamed, created_at, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                        """,
                        (child_id, parent_agent_id, device_id, label,
                         conv_id, user_set_label,
                         json.dumps(metadata) if metadata else None),
                    )
                conn.commit()
        except Exception as exc:
            logger.error("fork_conversation_meta_insert_failed", error=str(exc), child_id=child_id)
            # Best effort: tear down the orphan fork on Letta.
            try:
                http_client.delete(f"{LETTA_BASE_URL}/v1/conversations/{child_id}/", timeout=5.0)
            except Exception:
                pass
            return jsonify({"error": "conversation_meta_insert_failed"}), 500

        return jsonify({
            "id": child_id,
            "agent_id": parent_agent_id,
            "label": label,
            "parent_conversation_id": conv_id,
            "user_renamed": user_set_label,
            "created_at": letta_conv.get("created_at"),
        }), 201
    finally:
        if handle is not None:
            with handle.state_lock:
                handle.forking = False


# ---------------------------------------------------------------------
# Inline /btw — ephemeral side-question fork rendered inline in the
# parent conversation's chat view. See the Letta support agent's Q&A
# (2026-04-20): fork message rows are SHARED-not-copied, concurrent
# streams are safe at the lock layer (different conv_ids), no server-
# side TTL or tool-restriction primitive exists, so we own cleanup +
# tool restriction client-side.
# ---------------------------------------------------------------------

# Tools we strip from a /btw subprocess. Phase 1's R4b set is extended
# with memory-mutating tools so an ephemeral side-question can't leave
# state behind in the agent's shared memory blocks (Branch B propagation
# risk; see docs/reference/letta-conversations-fork.md).
BTW_DISALLOWED_TOOLS: tuple = (
    "Task", "TodoWrite", "EnterPlanMode", "AskUserQuestion",
    "manage_todo", "Write", "Edit",
)

# Idle TTL for a btw fork. The sliding timer is reset on every turn
# (initial + each continue). When it fires, the Letta fork is DELETEd
# and the subprocess handle is invalidated.
BTW_IDLE_TTL_S = float(os.environ.get("PA_WEB_UI_BTW_IDLE_TTL_S", "300"))

# Registry of live btw forks: fork_conv_id → {"agent_id", "parent_conv_id",
# "timer": threading.Timer}. Protected by _btw_lock.
_btw_forks: Dict[str, Dict[str, Any]] = {}
_btw_lock = threading.Lock()


def _btw_perform_delete(conv_id: str) -> None:
    """DELETE the fork on Letta and invalidate its subprocess. Called
    from the sliding-TTL timer or from an explicit /btw/end request.
    """
    try:
        resp = http_client.delete(
            f"{LETTA_BASE_URL}/v1/conversations/{conv_id}/",
            timeout=5.0,
        )
        if resp.status_code >= 400:
            logger.warning(
                "btw_fork_delete_non_2xx",
                conv_id=conv_id,
                status=resp.status_code,
            )
        else:
            logger.info("btw_fork_deleted", conv_id=conv_id)
    except Exception as exc:
        logger.warning("btw_fork_delete_failed", conv_id=conv_id, error=str(exc))
    try:
        subprocess_registry.invalidate(conv_id)
    except Exception as exc:
        logger.debug("btw_fork_invalidate_failed", conv_id=conv_id, error=str(exc))


def _btw_register_fork(fork_conv_id: str, agent_id: str, parent_conv_id: str) -> None:
    """Record a new btw fork and arm/reset its idle TTL timer."""
    with _btw_lock:
        entry = _btw_forks.get(fork_conv_id)
        if entry and entry.get("timer"):
            try:
                entry["timer"].cancel()
            except Exception:
                pass
        _btw_forks[fork_conv_id] = {
            "agent_id": agent_id,
            "parent_conv_id": parent_conv_id,
            "timer": None,
        }


def _btw_reset_idle_timer(fork_conv_id: str, ttl_s: Optional[float] = None) -> None:
    """(Re)arm the sliding idle timer for a btw fork. No-op if fork is
    not registered (already torn down)."""
    delay = BTW_IDLE_TTL_S if ttl_s is None else ttl_s
    with _btw_lock:
        entry = _btw_forks.get(fork_conv_id)
        if not entry:
            return
        old = entry.get("timer")
        if old:
            try:
                old.cancel()
            except Exception:
                pass
        timer = threading.Timer(delay, _btw_fire_expiry, args=(fork_conv_id,))
        timer.daemon = True
        entry["timer"] = timer
        timer.start()


def _btw_fire_expiry(fork_conv_id: str) -> None:
    """Timer callback: remove the fork from the registry and tear it down."""
    with _btw_lock:
        entry = _btw_forks.pop(fork_conv_id, None)
    if entry is not None:
        _btw_perform_delete(fork_conv_id)


def _btw_force_end(fork_conv_id: str) -> bool:
    """Cancel any pending timer and tear the fork down now. Returns True
    if the fork was known; False otherwise."""
    with _btw_lock:
        entry = _btw_forks.pop(fork_conv_id, None)
        if entry and entry.get("timer"):
            try:
                entry["timer"].cancel()
            except Exception:
                pass
    if entry is None:
        return False
    _btw_perform_delete(fork_conv_id)
    return True


def _btw_get(fork_conv_id: str) -> Optional[Dict[str, Any]]:
    with _btw_lock:
        entry = _btw_forks.get(fork_conv_id)
        if entry is None:
            return None
        return {"agent_id": entry["agent_id"], "parent_conv_id": entry["parent_conv_id"]}


# Legacy shim — kept for the existing tests that patch this name. New
# code should use the sliding-timer helpers above.
def _schedule_letta_delete(conv_id: str, delay_s: float) -> None:
    def _run():
        try:
            time.sleep(delay_s)
            _btw_perform_delete(conv_id)
        except Exception as exc:
            logger.warning("btw_fork_delete_failed", conv_id=conv_id, error=str(exc))

    threading.Thread(target=_run, name=f"btw-delete-{conv_id[:8]}", daemon=True).start()


@app.route("/api/conversations/<parent_conv_id>/btw", methods=["POST"])
def btw_conversation(parent_conv_id: str):
    """Ephemeral /btw side-question. Forks the parent, streams the
    reply from a fresh subprocess (with state-mutating tools stripped),
    then deletes the fork on the Letta server after a brief delay.

    No local persistence: no conversation_meta row, no
    pa_web.conversations save. The exchange lives only in the live
    SSE stream + the client's DOM. On page reload, it's gone.
    """
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate
    if not _is_valid_conv_id(parent_conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400

    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or data.get("message") or "").strip()
    if not question:
        return jsonify({"error": "question_required"}), 400

    # Verify parent exists; extract agent_id (fork endpoint needs it
    # when path-param is "default" — and conv_meta is the SoT anyway).
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent_id FROM pa_web.conversation_meta WHERE conversation_id = %s",
                (parent_conv_id,),
            )
            row = cur.fetchone()
            if row is None:
                # Allow parents that aren't in conversation_meta (pre-existing
                # Letta convs) — look up via the Letta server.
                try:
                    letta_resp = http_client.get(
                        f"{LETTA_BASE_URL}/v1/conversations/{parent_conv_id}/",
                        timeout=5.0,
                    )
                    if letta_resp.status_code == 404:
                        return jsonify({"error": "parent_not_found"}), 410
                    letta_resp.raise_for_status()
                    parent_agent_id = letta_resp.json().get("agent_id") or MISSION_CONTROL_AGENT_ID
                except Exception as exc:
                    logger.error("btw_parent_lookup_failed",
                                 error=str(exc), parent=parent_conv_id)
                    return jsonify({"error": "letta_unreachable"}), 502
            else:
                parent_agent_id = row[0]

    # Create the fork on Letta.
    try:
        fork_resp = http_client.post(
            f"{LETTA_BASE_URL}/v1/conversations/{parent_conv_id}/fork/",
            params={"agent_id": parent_agent_id},
            timeout=15.0,
        )
        fork_resp.raise_for_status()
        fork_body = fork_resp.json()
    except Exception as exc:
        logger.error("btw_fork_create_failed", error=str(exc), parent=parent_conv_id)
        return jsonify({"error": "letta_fork_failed"}), 502

    fork_conv_id = fork_body.get("id")
    if not _is_valid_conv_id(fork_conv_id):
        logger.error("btw_fork_malformed", response=fork_body)
        return jsonify({"error": "letta_malformed_fork_response"}), 502

    # Register the fork in the btw tracker so /btw/continue + /btw/end
    # can find it, then spawn the restricted subprocess.
    _btw_register_fork(fork_conv_id, parent_agent_id, parent_conv_id)
    try:
        handle = subprocess_registry.ensure(
            agent_id=parent_agent_id,
            conv_id=fork_conv_id,
            disallowed_tools_override=BTW_DISALLOWED_TOOLS,
        )
    except SpawnTimeoutError as exc:
        logger.error("btw_spawn_timeout", error=str(exc), fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "subprocess_spawn_timeout"}), 504
    except SubprocessDeadError as exc:
        logger.error("btw_subprocess_dead", error=str(exc), fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "subprocess_dead"}), 503

    # Send the question. No turn-lock fight here — the fork is fresh.
    device_id = request.cookies.get("pa_device_id", "").strip() or None
    try:
        subprocess_registry.send(handle, question, device_id=device_id)
    except TurnLockedException:
        logger.error("btw_send_turn_locked_unexpected", fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "turn_locked_on_fresh_handle"}), 500
    except SubprocessDeadError as exc:
        logger.error("btw_send_on_dead", error=str(exc), fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "subprocess_dead"}), 503

    request_id = str(uuid.uuid4())
    subscriber = handle.subscribe(since=None)
    return _btw_stream_response(
        fork_conv_id=fork_conv_id,
        parent_conv_id=parent_conv_id,
        request_id=request_id,
        handle=handle,
        subscriber=subscriber,
        is_initial=True,
    )


def _btw_stream_response(
    *,
    fork_conv_id: str,
    parent_conv_id: str,
    request_id: str,
    handle,
    subscriber,
    is_initial: bool,
) -> Response:
    """Shared SSE generator for the initial /btw turn and /btw/continue
    turns. Rearms the sliding idle timer on stream completion."""

    def generate() -> Generator[str, None, None]:
        if is_initial:
            yield f"data: {json.dumps({'type': 'btw_start', 'fork_conv_id': fork_conv_id, 'parent_conv_id': parent_conv_id, 'request_id': request_id})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'btw_continue', 'fork_conv_id': fork_conv_id, 'request_id': request_id})}\n\n"
        try:
            yield from _stream_direct_generator(
                subscriber,
                session_id="__btw__",
                request_id=request_id,
                conv_id=None,
                first_user_message=None,
            )
        finally:
            handle.unsubscribe(subscriber)
            # Arm sliding idle timer. If fork was force-ended mid-stream,
            # this is a no-op.
            _btw_reset_idle_timer(fork_conv_id)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/conversations/<fork_conv_id>/btw/continue", methods=["POST"])
def btw_continue(fork_conv_id: str):
    """Follow-up turn on an existing btw fork. Reuses the same subprocess
    handle and resets the fork's sliding idle TTL."""
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate
    if not _is_valid_conv_id(fork_conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400

    entry = _btw_get(fork_conv_id)
    if entry is None:
        return jsonify({"error": "btw_fork_expired"}), 410

    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or data.get("message") or "").strip()
    if not question:
        return jsonify({"error": "question_required"}), 400

    # Cancel the idle timer while this turn is in flight; it's rearmed
    # when the stream finishes.
    _btw_reset_idle_timer(fork_conv_id, ttl_s=3600)

    try:
        handle = subprocess_registry.ensure(
            agent_id=entry["agent_id"],
            conv_id=fork_conv_id,
            disallowed_tools_override=BTW_DISALLOWED_TOOLS,
        )
    except SpawnTimeoutError as exc:
        logger.error("btw_continue_spawn_timeout", error=str(exc), fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "subprocess_spawn_timeout"}), 504
    except SubprocessDeadError as exc:
        logger.error("btw_continue_subprocess_dead", error=str(exc), fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "subprocess_dead"}), 503

    device_id = request.cookies.get("pa_device_id", "").strip() or None
    try:
        subprocess_registry.send(handle, question, device_id=device_id)
    except TurnLockedException as exc:
        current = getattr(exc, "current_device_id", None)
        seq = getattr(exc, "seq_id", None)
        return jsonify({
            "error": "turn_locked",
            "current_device_id": current,
            "seq_id": seq,
        }), 409
    except SubprocessDeadError as exc:
        logger.error("btw_continue_send_on_dead", error=str(exc), fork=fork_conv_id)
        _btw_force_end(fork_conv_id)
        return jsonify({"error": "subprocess_dead"}), 503

    request_id = str(uuid.uuid4())
    subscriber = handle.subscribe(since=None)
    return _btw_stream_response(
        fork_conv_id=fork_conv_id,
        parent_conv_id=entry["parent_conv_id"],
        request_id=request_id,
        handle=handle,
        subscriber=subscriber,
        is_initial=False,
    )


@app.route("/api/conversations/<fork_conv_id>/btw/end", methods=["POST"])
def btw_end(fork_conv_id: str):
    """Force-end a btw fork: cancel the idle timer, DELETE on Letta, and
    invalidate the subprocess handle. Idempotent."""
    gate = _phase2_precondition_check()
    if gate is not None:
        return gate
    if not _is_valid_conv_id(fork_conv_id):
        return jsonify({"error": "invalid_conversation_id"}), 400
    ended = _btw_force_end(fork_conv_id)
    return jsonify({"ended": ended, "fork_conv_id": fork_conv_id}), 200


@app.route("/api/agents")
def get_agents():
    """Proxy to routing handler to get available agents."""
    try:
        response = http_client.get(f"{ROUTING_HANDLER_URL}/v1/agents")
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        logger.error("get_agents_failed", error=str(e))
        return jsonify({"agents": [], "error": str(e)}), 500


@app.route("/api/config")
def get_config():
    """Get frontend configuration."""
    return jsonify({
        "routing_handler_url": ROUTING_HANDLER_URL,
        "letta_base_url": LETTA_BASE_URL,
    })


MC_AGENT_ID = os.getenv("MC_AGENT_ID", "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef")

# Approximate cost per 1M tokens (input / output) in USD. "plan" means
# included in a fixed subscription (ChatGPT Plus/Pro via OAuth, Anthropic
# Max). Use ~ prefix when figure is inferred vs. published. Updated 2026-05.
MC_MODEL_COSTS = {
    # OpenAI API
    "gpt-5.5": "~$4/$16",
    "gpt-5.4": "$2/$8",
    "gpt-5.4-mini": "$0.40/$1.60",
    "gpt-5.4-nano": "$0.10/$0.40",
    "gpt-5.3-chat-latest": "$1.25/$10",
    "gpt-5.2": "$1.25/$10",
    "gpt-5-mini": "$0.25/$2",
    "gpt-4.1": "$2/$8",
    # Anthropic
    "claude-sonnet-4-6": "$3/$15",
    "claude-opus-4-6": "$15/$75",
    "claude-haiku-4-5": "$1/$5",
    # Fireworks (open-weights via litellm)
    "deepseek-v4-pro": "$1.20/$1.20",
    "kimi-k2p6": "$0.60/$2.50",
    "kimi-k2p5": "$0.60/$2.50",
    "glm-5p1": "$0.55/$2.19",
    "minimax-m2p7": "~$0.30/$1.20",
    "gpt-oss-120b": "$0.15/$0.60",
}

# Compatibility class per model. Used by the pulldown to flag risky swaps.
# - "openai-reasoning": emits reasoning_content_signature; tolerates everything
# - "openai-chat": vanilla chat; tolerant
# - "anthropic": uses thinking blocks; tolerates other fields via drop_params
# - "fireworks-strict": rejects unknown fields (Kimi/DeepSeek/GLM/MiniMax/gpt-oss).
#   The litellm cross_provider_compat hook scrubs incompatible fields on the
#   way out, so swaps INTO this class work — but stay aware.
MC_MODEL_COMPAT = {
    "gpt-5.5": "openai-reasoning",
    "gpt-5.4": "openai-reasoning",
    "gpt-5.4-mini": "openai-reasoning",
    "gpt-5.4-nano": "openai-reasoning",
    "gpt-5.3-chat-latest": "openai-reasoning",
    "gpt-5.2": "openai-reasoning",
    "gpt-5-mini": "openai-chat",
    "gpt-4.1": "openai-chat",
    "claude-sonnet-4-6": "anthropic",
    "claude-opus-4-6": "anthropic",
    "claude-haiku-4-5": "anthropic",
    "deepseek-v4-pro": "fireworks-strict",
    "kimi-k2p6": "fireworks-strict",
    "kimi-k2p5": "fireworks-strict",
    "glm-5p1": "fireworks-strict",
    "minimax-m2p7": "fireworks-strict",
    "gpt-oss-120b": "fireworks-strict",
}

# Model presets for the MC model switcher
MC_MODEL_PRESETS = {
    "gpt-5.4 (oauth)": {
        "model": "gpt-5.4",
        "model_endpoint_type": "chatgpt_oauth",
        "model_endpoint": "https://chatgpt.com/backend-api/codex/responses",
        "provider_name": "chatgpt-plus-pro",
        "provider_category": "byok",
        "handle": "chatgpt-plus-pro/gpt-5.4",
        "context_window": 272000,
        "max_tokens": 128000,
        "reasoning_effort": "low",
        "strict": True,
        "parallel_tool_calls": True,
        "_reasoning_options": ["low", "medium", "high"],
    },
    "gpt-5.2 (oauth)": {
        "model": "gpt-5.2",
        "model_endpoint_type": "chatgpt_oauth",
        "model_endpoint": "https://chatgpt.com/backend-api/codex/responses",
        "provider_name": "chatgpt-plus-pro",
        "provider_category": "byok",
        "handle": "chatgpt-plus-pro/gpt-5.2",
        "context_window": 272000,
        "max_tokens": 128000,
        "reasoning_effort": "medium",
        "strict": True,
        "parallel_tool_calls": True,
        "_reasoning_options": ["low", "medium", "high"],
    },
    "gpt-5.3 (API)": {
        "model": "gpt-5.3-chat-latest",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5.3-chat-latest",
        "context_window": 272000,
        "max_tokens": 128000,
        "reasoning_effort": "medium",
        "_reasoning_options": ["medium"],
    },
    "gpt-5.2 (API)": {
        "model": "gpt-5.2",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5.2",
        "context_window": 272000,
        "max_tokens": 128000,
        "_reasoning_options": ["low", "medium", "high"],
    },
    "gpt-5.5 (API)": {
        "model": "gpt-5.5",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5.5",
        "context_window": 400000,
        "max_tokens": 32768,
        "_reasoning_options": [],
    },
    "gpt-5.4 (API)": {
        "model": "gpt-5.4",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5.4",
        "context_window": 400000,
        "max_tokens": 32768,
        "_reasoning_options": [],
    },
    "gpt-5.4-mini (API)": {
        "model": "gpt-5.4-mini",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5.4-mini",
        "context_window": 128000,
        "max_tokens": 32768,
        "_reasoning_options": [],
    },
    "gpt-5.4-nano (API)": {
        "model": "gpt-5.4-nano",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5.4-nano",
        "context_window": 128000,
        "max_tokens": 32768,
        "_reasoning_options": [],
    },
    "claude-sonnet-4.6 (API)": {
        "model": "claude-sonnet-4-6",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/claude-sonnet-4-6",
        "context_window": 200000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
    "claude-opus-4.6 (API)": {
        "model": "claude-opus-4-6",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/claude-opus-4-6",
        "context_window": 200000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
    "claude-haiku-4.5 (API)": {
        "model": "claude-haiku-4-5",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/claude-haiku-4-5",
        "context_window": 200000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
    "gpt-5-mini (API)": {
        "model": "gpt-5-mini",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-5-mini",
        "context_window": 128000,
        "max_tokens": 32768,
        "_reasoning_options": [],
    },
    "gpt-4.1 (API)": {
        "model": "gpt-4.1",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-4.1",
        "context_window": 128000,
        "max_tokens": 32768,
        "_reasoning_options": [],
    },
    # --- Fireworks AI open-weight models (routed via LiteLLM) ---
    # DeepSeek v3.x was retired from Fireworks serverless in May 2026;
    # v4-pro is the current serverless flagship.
    "deepseek-v4-pro (fireworks)": {
        "model": "deepseek-v4-pro",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/deepseek-v4-pro",
        "context_window": 160000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
    # Kimi K2.x on Fireworks rejects any non-streamed request with
    # max_tokens > 4096 ("Requests with max_tokens > 4096 must have
    # stream=true"). Letta/LettaBot have at least one non-streamed
    # path (result-summarizer / reasoning completion), so we pin
    # max_tokens at 4096 here to avoid hard-400s on Telegram + mid-run.
    "kimi-k2.6 (fireworks)": {
        "model": "kimi-k2p6",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/kimi-k2p6",
        "context_window": 262144,
        "max_tokens": 4096,
        "_reasoning_options": [],
    },
    "kimi-k2.5 (fireworks)": {
        "model": "kimi-k2p5",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/kimi-k2p5",
        "context_window": 262144,
        "max_tokens": 4096,
        "_reasoning_options": [],
    },
    "glm-5.1 (fireworks)": {
        "model": "glm-5p1",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/glm-5p1",
        "context_window": 128000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
    "minimax-m2.7 (fireworks)": {
        "model": "minimax-m2p7",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/minimax-m2p7",
        "context_window": 200000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
    "gpt-oss-120b (fireworks)": {
        "model": "gpt-oss-120b",
        "model_endpoint_type": "openai",
        "model_endpoint": "http://litellm:4000/v1",
        "provider_name": "litellm",
        "handle": "litellm/gpt-oss-120b",
        "context_window": 128000,
        "max_tokens": 16384,
        "_reasoning_options": [],
    },
}


@app.route("/api/mc-model")
def get_mc_model():
    """Get MC's current model configuration."""
    try:
        resp = http_client.get(f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}")
        resp.raise_for_status()
        llm = resp.json().get("llm_config", {})
        model = llm.get("model", "unknown")
        provider = llm.get("model_endpoint_type", "unknown")
        # Find which preset matches the current config
        label = f"{model} ({('oauth' if provider == 'chatgpt_oauth' else 'API')})"
        for preset_name, preset_cfg in MC_MODEL_PRESETS.items():
            if preset_cfg.get("model") == model and preset_cfg.get("model_endpoint_type") == provider:
                label = preset_name
                break
        # Build reasoning options map for frontend
        preset_reasoning = {
            name: cfg.get("_reasoning_options", [])
            for name, cfg in MC_MODEL_PRESETS.items()
        }
        # Build cost-hint map for frontend (per 1M tokens, input/output)
        preset_costs = {}
        for name, cfg in MC_MODEL_PRESETS.items():
            if cfg.get("model_endpoint_type") == "chatgpt_oauth":
                preset_costs[name] = "plan"
            else:
                preset_costs[name] = MC_MODEL_COSTS.get(cfg.get("model"), "?")
        # Build compat-class map; current agent's class is the "from" axis.
        preset_compat = {
            name: MC_MODEL_COMPAT.get(cfg.get("model"), "unknown")
            for name, cfg in MC_MODEL_PRESETS.items()
        }
        current_compat = MC_MODEL_COMPAT.get(model, "unknown")
        # Check if oauth is available (from model manager state file)
        oauth_available = False
        try:
            state_path = os.path.join(
                os.getenv("FOLLOWUP_QUEUE", "").rsplit("/", 1)[0],
                "mc-model-state.json",
            )
            if os.path.exists(state_path):
                with open(state_path) as f:
                    state = json.load(f)
                    oauth_available = bool(state.get("oauth_available"))
        except Exception:
            pass

        return jsonify({
            "model": model,
            "provider": provider,
            "label": label,
            "reasoning_effort": llm.get("reasoning_effort") or "none",
            "presets": list(MC_MODEL_PRESETS.keys()),
            "preset_reasoning": preset_reasoning,
            "preset_costs": preset_costs,
            "preset_compat": preset_compat,
            "current_compat": current_compat,
            "oauth_available": oauth_available,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mc-model", methods=["POST"])
def set_mc_model():
    """Switch MC's model to a preset."""
    try:
        data = request.get_json()
        preset_name = data.get("preset")
        if preset_name not in MC_MODEL_PRESETS:
            return jsonify({"error": f"Unknown preset: {preset_name}"}), 400

        # Get current config
        resp = http_client.get(f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}")
        resp.raise_for_status()
        agent = resp.json()
        llm = agent.get("llm_config", {})

        # Apply preset overrides
        preset = MC_MODEL_PRESETS[preset_name]
        for k, v in preset.items():
            llm[k] = v

        # Patch agent
        patch_resp = http_client.patch(
            f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}",
            json={"llm_config": llm},
        )
        patch_resp.raise_for_status()
        new_llm = patch_resp.json().get("llm_config", {})
        return jsonify({
            "model": new_llm.get("model"),
            "provider": new_llm.get("model_endpoint_type"),
            "label": preset_name,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mc-reasoning", methods=["POST"])
def set_mc_reasoning():
    """Set MC's reasoning effort level."""
    try:
        data = request.get_json()
        effort = data.get("effort")
        if effort not in ("low", "medium", "high"):
            return jsonify({"error": "effort must be low, medium, or high"}), 400

        resp = http_client.get(f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}")
        resp.raise_for_status()
        llm = resp.json().get("llm_config", {})
        llm["reasoning_effort"] = effort

        patch_resp = http_client.patch(
            f"{LETTA_BASE_URL}/v1/agents/{MC_AGENT_ID}",
            json={"llm_config": llm},
        )
        patch_resp.raise_for_status()
        new_llm = patch_resp.json().get("llm_config", {})
        return jsonify({"reasoning_effort": new_llm.get("reasoning_effort")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.getenv("LITELLM_MASTER_KEY", "")


@app.route("/api/mc-usage")
def get_mc_usage():
    """Get the most recent LLM usage stats for MC, including cache info."""
    try:
        # Query litellm DB directly (much faster than litellm's spend API)
        litellm_db_url = os.getenv(
            "LITELLM_DATABASE_URL",
            "postgresql://litellm:litellm_secret@supabase-db:5432/litellm"
        )
        import psycopg2 as _pg
        conn = _pg.connect(litellm_db_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT model, spend,
                           (metadata::json->'usage_object'->>'prompt_tokens')::int as prompt_tokens,
                           (metadata::json->'usage_object'->>'completion_tokens')::int as completion_tokens,
                           (metadata::json->'usage_object'->>'total_tokens')::int as total_tokens,
                           (metadata::json->'usage_object'->'prompt_tokens_details'->>'cached_tokens')::int as cached_tokens,
                           (metadata::json->'usage_object'->'completion_tokens_details'->>'reasoning_tokens')::int as reasoning_tokens,
                           "startTime" as timestamp
                    FROM "LiteLLM_SpendLogs"
                    ORDER BY "startTime" DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"error": "no data"})

        prompt_tokens = row["prompt_tokens"] or 0
        cached_tokens = row["cached_tokens"] or 0
        completion_tokens = row["completion_tokens"] or 0
        reasoning_tokens = row["reasoning_tokens"] or 0
        spend = row["spend"] or 0
        model = (row["model"] or "").replace("openai/", "")
        cache_pct = round(cached_tokens / prompt_tokens * 100) if prompt_tokens > 0 else 0

        return jsonify({
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "cache_pct": cache_pct,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": row["total_tokens"] or 0,
            "spend": round(float(spend), 4),
            "model": model,
            "timestamp": str(row["timestamp"] or ""),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/conversations/<session_id>")
def get_conversations(session_id):
    """Get conversation history for a session.

    Phase 2: optional `?conversation_id=` filter restricts to a single
    Letta conv. Without it, returns all session rows (back-compat).
    """
    try:
        limit = request.args.get("limit", 100, type=int)
        conversation_id = request.args.get("conversation_id") or None
        history = get_conversation_history(
            session_id, limit=limit, conversation_id=conversation_id
        )
        return jsonify({"conversations": history, "session_id": session_id})
    except Exception as e:
        logger.error("get_conversations_failed", error=str(e), session_id=session_id)
        return jsonify({"conversations": [], "error": str(e)}), 500


@app.route("/api/feedback", methods=["POST"])
def record_feedback():
    """Record user feedback on a response (thumbs up/down or agent correction)."""
    data = request.get_json(force=True, silent=True) or {}

    session_id = data.get("session_id")
    request_id = data.get("request_id")
    feedback_type = data.get("feedback_type")  # "thumbs_up", "thumbs_down", "agent_correction"

    if not session_id or not request_id or not feedback_type:
        return jsonify({"error": "session_id, request_id, and feedback_type are required"}), 400

    if feedback_type not in ("thumbs_up", "thumbs_down", "agent_correction"):
        return jsonify({"error": "Invalid feedback_type"}), 400

    # Phase 2 column rename: old clients may still send an INTEGER
    # `conversation_id` (= old pa_web.response_feedback.conversation_id);
    # new clients send a TEXT UUID. Disambiguate by type.
    raw_conv = data.get("conversation_id")
    local_pk = data.get("local_conversation_pk")
    conv_uuid = None
    if isinstance(raw_conv, int):
        local_pk = raw_conv
    elif isinstance(raw_conv, str) and raw_conv:
        conv_uuid = raw_conv

    save_response_feedback(
        session_id=session_id,
        request_id=request_id,
        feedback_type=feedback_type,
        actual_agent_id=data.get("actual_agent_id"),
        actual_agent_name=data.get("actual_agent_name"),
        intended_agent_id=data.get("intended_agent_id"),
        intended_agent_name=data.get("intended_agent_name"),
        local_conversation_pk=local_pk,
        conversation_id=conv_uuid,
    )

    return jsonify({"status": "ok", "feedback_type": feedback_type})


@app.route("/api/coordinate", methods=["POST"])
def coordinate():
    """Execute multi-agent coordination task.

    Proxies to the routing handler's coordination endpoint.
    Useful for tasks like meeting prep that gather info from multiple agents.

    Request body:
    - task_type: str (e.g., "meeting_prep")
    - context: dict (e.g., {"meeting_identifier": "board meeting"})
    - identity_id: str (optional, defaults to system default)
    - session_id: str (optional, for conversation tracking)
    """
    data = request.get_json(force=True, silent=True) or {}

    task_type = data.get("task_type")
    context = data.get("context", {})
    identity_id = data.get("identity_id")
    session_id = data.get("session_id")

    if not task_type:
        return jsonify({"error": "task_type is required"}), 400

    if not context:
        return jsonify({"error": "context is required"}), 400

    logger.info(
        "coordinate_request",
        task_type=task_type,
        context_keys=list(context.keys()),
        session_id=session_id,
    )

    try:
        # Call the routing handler's coordination endpoint
        # Use a longer timeout since coordination involves multiple agents
        with httpx.Client(timeout=180.0) as coord_client:
            coord_response = coord_client.post(
                f"{ROUTING_HANDLER_URL}/v1/coordinate",
                json={
                    "task_type": task_type,
                    "context": context,
                    "identity_id": identity_id or "default",
                },
            )
            coord_response.raise_for_status()
            result = coord_response.json()

        logger.info(
            "coordinate_complete",
            task_type=task_type,
            status=result.get("status"),
            agents_completed=result.get("agents_completed"),
            coordination_time_ms=result.get("coordination_time_ms"),
        )

        # Optionally save to conversation history if session provided
        if session_id and result.get("synthesis"):
            # Save as a system message with the coordination result
            save_conversation_message(
                session_id=session_id,
                role="assistant",
                message=result["synthesis"],
                agent_name="Coordination",
            )

        return jsonify(result)

    except httpx.HTTPStatusError as e:
        logger.error("coordinate_http_error", status_code=e.response.status_code)
        return jsonify({
            "status": "error",
            "error_message": f"Coordination failed: HTTP {e.response.status_code}",
        }), e.response.status_code

    except Exception as e:
        logger.error("coordinate_error", error=str(e))
        return jsonify({
            "status": "error",
            "error_message": f"Coordination failed: {str(e)}",
        }), 500


@app.route("/api/heartbeats", methods=["GET"])
def get_heartbeats():
    """Fetch recent heartbeat turns from Mission Control via Letta API."""
    # Heartbeats were previously fetched from Open-WebUI's LettaBot pipeline.
    # That pipeline is removed; heartbeat data is not available via Letta API.
    # Return empty list to keep the frontend happy.
    return jsonify({"heartbeats": []}), 200


# Coordination slash commands: command -> (task_type, context_key)
COORDINATION_COMMANDS = {
    "mprep": ("meeting_prep", "meeting_identifier"),
}

# Pattern to match coordination slash commands: /command argument
COORD_SLASH_PATTERN = re.compile(r"^/(\w+)\s+(.+)$", re.DOTALL)


def stream_coordination(
    task_type: str,
    context: dict,
    session_id: str,
    original_message: str,
) -> Response:
    """Stream coordination results as SSE events.

    Args:
        task_type: Coordination task type (e.g., "meeting_prep")
        context: Context dict for the task
        session_id: Session ID for conversation tracking
        original_message: Original user message for history
    """

    def generate() -> Generator[str, None, None]:
        try:
            # Notify frontend we're coordinating
            yield f"data: {json.dumps({'type': 'routing', 'agent_id': 'coordination', 'agent_name': 'Meeting Prep', 'request_id': None})}\n\n"
            yield f"data: {json.dumps({'type': 'tool_call', 'tool': 'coordination_start'})}\n\n"

            logger.info(
                "coordination_stream_start",
                task_type=task_type,
                session_id=session_id,
            )

            # Save user message
            save_conversation_message(
                session_id=session_id,
                role="user",
                message=original_message,
                agent_name="Coordination",
            )

            # Call coordination API
            with httpx.Client(timeout=180.0) as client:
                response = client.post(
                    f"{ROUTING_HANDLER_URL}/v1/coordinate",
                    json={
                        "task_type": task_type,
                        "context": context,
                        "identity_id": "default",
                    },
                )
                response.raise_for_status()
                result = response.json()

            logger.info(
                "coordination_stream_complete",
                task_type=task_type,
                status=result.get("status"),
                agents_completed=result.get("agents_completed"),
                agents_failed=result.get("agents_failed"),
                coordination_time_ms=result.get("coordination_time_ms"),
            )

            # Stream the synthesis as text
            synthesis = result.get("synthesis", "")
            if synthesis:
                yield f"data: {json.dumps({'type': 'text', 'content': synthesis})}\n\n"

                # Save to conversation history
                save_conversation_message(
                    session_id=session_id,
                    role="assistant",
                    message=synthesis,
                    agent_name="Coordination",
                )

            # Send completion metadata
            agents_completed = result.get("agents_completed", [])
            agents_failed = result.get("agents_failed", [])
            if agents_failed:
                status_msg = f"\n\n---\n*Agents: {', '.join(agents_completed)} completed"
                if agents_failed:
                    status_msg += f"; {', '.join(agents_failed)} failed"
                status_msg += "*"
                yield f"data: {json.dumps({'type': 'text', 'content': status_msg})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except httpx.HTTPStatusError as e:
            logger.error("coordination_stream_http_error", status_code=e.response.status_code)
            yield f"data: {json.dumps({'type': 'error', 'message': f'Coordination failed: HTTP {e.response.status_code}'})}\n\n"

        except Exception as e:
            logger.error("coordination_stream_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def stream_mission_control(message: str, session_id: str) -> Generator[str, None, None]:
    """Stream a message to Mission Control via LettaBot's OpenAI-compatible API.

    LettaBot handles the tool execution loop (Write, Edit, Bash, etc.) internally
    and returns the final response. This preserves MC's full tool access.
    """
    import uuid

    request_id = str(uuid.uuid4())

    # Emit routing event
    yield f"data: {json.dumps({'type': 'routing', 'agent_id': MISSION_CONTROL_AGENT_ID, 'agent_name': 'Mission Control', 'request_id': request_id})}\n\n"

    # Save user message
    save_conversation_message(
        session_id=session_id,
        role="user",
        message=message,
        agent_id=MISSION_CONTROL_AGENT_ID,
        agent_name="Mission Control",
        request_id=request_id,
    )

    headers = {
        "Content-Type": "application/json",
    }
    if LETTABOT_API_KEY:
        headers["Authorization"] = f"Bearer {LETTABOT_API_KEY}"

    lettabot_payload = {
        "messages": [
            {"role": "system", "content": build_web_ui_system_reminder()},
            {"role": "user", "content": message},
        ],
        "stream": True,
    }

    assistant_content = ""

    # Use a queue-based approach with keepalive pings to prevent
    # connection drops during long tool executions (e.g., Rover calls)
    event_queue = queue.Queue()

    def run_lettabot_stream():
        """Background thread to stream from LettaBot and put events in queue."""
        try:
            with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                with client.stream(
                    "POST",
                    f"{LETTABOT_API_URL}/v1/chat/completions",
                    json=lettabot_payload,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        event_queue.put({"type": "error", "message": f"Mission Control returned {response.status_code}"})
                        event_queue.put(None)  # Signal done
                        return

                    for line in response.iter_lines():
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                continue
                            try:
                                event = json.loads(data_str)
                                event_queue.put(event)
                            except json.JSONDecodeError:
                                pass

        except httpx.TimeoutException:
            event_queue.put({"type": "error", "message": "Mission Control request timed out"})
        except Exception as e:
            logger.error("mission_control_stream_error", error=str(e))
            event_queue.put({"type": "error", "message": f"Mission Control error: {str(e)}"})
        finally:
            event_queue.put(None)  # Signal done

    stream_thread = threading.Thread(target=run_lettabot_stream, daemon=True)
    stream_thread.start()

    try:
        while True:
            try:
                event = event_queue.get(timeout=15)  # 15s keepalive interval
            except queue.Empty:
                # No event — send keepalive ping to prevent connection drop
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                continue

            if event is None:
                break  # Stream done

            event_type = event.get("type", "")

            # OpenAI chat completion format
            choices = event.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")

                content = delta.get("content", "")
                if content:
                    assistant_content += content
                    yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"

                # Forward tool calls — OpenAI streams these in chunks:
                # first chunk has name+args, subsequent chunks may only have args fragments
                tool_calls = delta.get("tool_calls", [])
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    tool_args = fn.get("arguments", "")
                    if tool_name:
                        try:
                            tool_input = json.loads(tool_args) if tool_args else {}
                        except json.JSONDecodeError:
                            tool_input = {"raw": tool_args} if tool_args else {}
                        yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'args': tool_input})}\n\n"

            # Error objects
            if "error" in event:
                error_msg = event["error"].get("message", "Unknown error")
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"

    except GeneratorExit:
        pass  # Client disconnected

    # Fetch per-response usage stats from litellm DB (fast direct query)
    usage_data = None
    try:
        litellm_db_url = os.getenv(
            "LITELLM_DATABASE_URL",
            "postgresql://litellm:litellm_secret@supabase-db:5432/litellm"
        )
        usage_conn = psycopg2.connect(litellm_db_url)
        try:
            with usage_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT model, spend,
                           (metadata::json->'usage_object'->>'prompt_tokens')::int as prompt_tokens,
                           (metadata::json->'usage_object'->>'completion_tokens')::int as completion_tokens,
                           (metadata::json->'usage_object'->>'total_tokens')::int as total_tokens,
                           (metadata::json->'usage_object'->'prompt_tokens_details'->>'cached_tokens')::int as cached_tokens,
                           (metadata::json->'usage_object'->'completion_tokens_details'->>'reasoning_tokens')::int as reasoning_tokens
                    FROM "LiteLLM_SpendLogs"
                    ORDER BY "startTime" DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
        finally:
            usage_conn.close()
        if row:
            prompt = row["prompt_tokens"] or 0
            cached = row["cached_tokens"] or 0
            cache_pct = round(cached / prompt * 100) if prompt > 0 else 0
            usage_data = {
                "prompt_tokens": prompt,
                "completion_tokens": row["completion_tokens"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "cached_input_tokens": cached,
                "reasoning_tokens": row["reasoning_tokens"] or 0,
                "cache_pct": cache_pct,
                "spend": float(row["spend"] or 0),
                "model": (row["model"] or "").replace("openai/", ""),
            }
            yield f"data: {json.dumps({'type': 'usage', 'data': usage_data})}\n\n"
    except Exception:
        pass  # Usage is optional

    # Save assistant response with usage metadata
    if assistant_content:
        save_conversation_message(
            session_id=session_id,
            role="assistant",
            message=assistant_content,
            agent_id=MISSION_CONTROL_AGENT_ID,
            agent_name="Mission Control",
            request_id=request_id,
            extra_metadata={"usage": usage_data} if usage_data else None,
        )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


def _translate_letta_code_event(ev: dict) -> Optional[dict]:
    """Translate letta-code 0.23.8 native stream-json into the event shape
    chat.js's existing handlers already understand.

    letta-code wraps most content in `{type: "message", message_type: ...}`.
    chat.js handlers are keyed on the outer `type` field
    (`text`, `tool_call`, `tool_result`, `thinking`, `usage`, etc.) —
    these are the shapes LettaBot used to emit after translating from
    the same underlying letta-code output.

    Returns None for events we deliberately drop from the client stream
    (e.g., stop_reason, which is redundant with the subsequent result event).
    """
    t = ev.get("type")

    # Preserve server-side envelope metadata on the translated event.
    envelope = {k: v for k, v in ev.items() if k.startswith("_")}

    if t == "message":
        mt = ev.get("message_type")
        if mt == "assistant_message":
            content = ev.get("content") or ""
            if not content:
                return None
            return {"type": "text", "content": content, **envelope}
        if mt == "reasoning_message":
            content = ev.get("reasoning") or ev.get("content") or ""
            if not content:
                return None
            return {"type": "thinking", "content": content, **envelope}
        if mt == "tool_call_message":
            tc = ev.get("tool_call") or {}
            tool_name = tc.get("name") or ev.get("name") or ""
            raw_args = tc.get("arguments", ev.get("arguments"))
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except (ValueError, json.JSONDecodeError):
                    args = {"raw": raw_args}
            else:
                args = raw_args or {}
            return {
                "type": "tool_call",
                "tool": tool_name,
                "args": args,
                **envelope,
            }
        if mt in ("tool_return_message", "tool_response_message"):
            content = ev.get("content") or ev.get("tool_return") or ev.get("result") or ""
            is_error = (
                ev.get("is_err") is True
                or ev.get("status") == "error"
                or ev.get("tool_return_status") == "error"
            )
            return {
                "type": "tool_result",
                "content": content if isinstance(content, str) else json.dumps(content),
                "is_error": is_error,
                **envelope,
            }
        if mt == "usage_statistics":
            data = {
                "prompt_tokens": ev.get("prompt_tokens") or 0,
                "completion_tokens": ev.get("completion_tokens") or 0,
                "total_tokens": ev.get("total_tokens") or 0,
                "cached_input_tokens": ev.get("cached_input_tokens") or 0,
                "reasoning_tokens": ev.get("reasoning_tokens") or 0,
                "model": ev.get("model") or "",
            }
            prompt = data["prompt_tokens"]
            cached = data["cached_input_tokens"]
            data["cache_pct"] = round(cached / prompt * 100) if prompt else 0
            return {"type": "usage", "data": data, **envelope}
        if mt == "stop_reason":
            # Drop — result event carries the terminal signal.
            return None
        # Unknown message_type — forward untouched so the frontend can log
        # it and we don't lose data.
        return ev

    if t == "result":
        # Map to `done` for chat.js's existing terminal handler.
        return {
            "type": "done",
            "result": ev.get("result"),
            "run_ids": ev.get("run_ids") or [],
            **envelope,
        }

    # routing, ping, error, resync_required, slow_subscriber, turn_locked,
    # and anything else already in chat.js-compatible shape — pass through.
    return ev


def _stream_direct_generator(
    subscriber,
    session_id: str,
    request_id: str,
    conv_id: Optional[str] = None,
    first_user_message: Optional[str] = None,
) -> Generator[str, None, None]:
    """SSE generator reading from a subprocess-pool subscriber queue.

    Translates letta-code's native stream-json event shapes into the
    forms chat.js already renders. Keepalive pings on queue.Empty.
    Exits on terminal event (result / done) OR GeneratorExit.

    Phase 2 Unit 2.5: on the terminal `result`/`done`, if the conversation
    qualifies for auto-naming, fire an in-band litellm call and emit a
    `conversation_label_updated` SSE event BEFORE the terminal event so
    the client's rail updates before the turn formally completes.
    """
    assistant_accumulator = ""
    try:
        while True:
            try:
                raw_event = subscriber.get(timeout=KEEPALIVE_PING_INTERVAL)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                continue

            event = _translate_letta_code_event(raw_event)
            if event is None:
                continue

            # Accumulate text for DB save on completion.
            if event.get("type") == "text":
                piece = event.get("content") or ""
                if piece:
                    assistant_accumulator += piece

            event_type = event.get("type")
            if event_type in ("result", "done"):
                # Fire the auto-name probe BEFORE the terminal event so
                # chat.js processes the label update first, then treats
                # done as the turn close.
                if conv_id and first_user_message:
                    try:
                        new_label = _maybe_autoname_conversation(
                            conv_id, first_user_message
                        )
                        if new_label:
                            yield f"data: {json.dumps({'type': 'conversation_label_updated', 'conv_id': conv_id, 'label': new_label})}\n\n"
                    except Exception as exc:
                        logger.warning(
                            "autoname_inline_failed",
                            conv_id=conv_id,
                            error=str(exc),
                        )
                yield f"data: {json.dumps(event)}\n\n"
                break
            else:
                yield f"data: {json.dumps(event)}\n\n"
    except GeneratorExit:
        # Client disconnected; do NOT save assistant content (turn may
        # still be running on the subprocess — another device may pick it up).
        return
    finally:
        try:
            # Always detach from the fan-out so reader doesn't keep pushing.
            # The subscriber lives on its handle; we need both references.
            # The `subscriber` object carries no back-pointer; unsubscribe
            # is delegated to the route handler via closure in stream().
            pass
        except Exception:
            pass

    # Save assistant response on clean completion.
    if assistant_accumulator:
        try:
            save_conversation_message(
                session_id=session_id,
                role="assistant",
                message=assistant_accumulator,
                agent_id=MISSION_CONTROL_AGENT_ID,
                agent_name="Mission Control",
                request_id=request_id,
                conversation_id=conv_id,
            )
        except Exception as exc:
            logger.error("direct_assistant_save_failed", error=str(exc))


# Friendly names for fleet agents — kept in sync with pa-routing-handler's
# AGENT_ID_TO_NAME. Keep this short; the routing handler is source of truth.
FLEET_AGENT_NAMES: Dict[str, str] = {
    "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef": "Mission Control",
    "agent-dd15479e-6543-400e-8463-b2a48b13cd4a": "Task Agent",
    "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d": "Calendar Agent",
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8": "Pulse Agent",
    "agent-398b4f6c-6afa-493f-8063-897c6b171a0d": "Documents Agent",
    "agent-b4928949-8012-4436-a3c7-a9e510785147": "Email Agent",
}


def _agent_name_for(agent_id: str) -> str:
    return FLEET_AGENT_NAMES.get(agent_id, "Agent")


def _dispatch_agent_subprocess(
    message: str,
    session_id: str,
    device_id: str,
    conversation_id: str,
    since: Optional[int],
    agent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Response:
    """Preflight the subprocess pool and return an SSE Response.

    Pre-SSE work happens here (where HTTP status can still be set):
    - ensure handle (spawn if cold)
    - send message if non-empty (TurnLockedException → HTTP 409)
    - subscribe with since (replay seed OR resync_required)

    Only after all that starts the SSE stream.

    agent_id/agent_name default to MC so callers that haven't switched
    yet keep working. Any letta_v1 + memfs-enabled fleet agent works
    here — the subprocess pool spawns letta-code with `--agent <id>`.
    """
    target_agent_id = agent_id or MISSION_CONTROL_AGENT_ID
    target_agent_name = agent_name or (
        "Mission Control"
        if target_agent_id == MISSION_CONTROL_AGENT_ID
        else _agent_name_for(target_agent_id)
    )
    request_id = str(uuid.uuid4())

    try:
        handle = subprocess_registry.ensure(
            agent_id=target_agent_id,
            conv_id=conversation_id,
        )
    except SpawnTimeoutError as exc:
        logger.error("mc_direct_spawn_timeout", error=str(exc), conv_id=conversation_id)
        return jsonify({"error": "subprocess_spawn_timeout"}), 504
    except SubprocessDeadError as exc:
        logger.error("mc_direct_subprocess_dead", error=str(exc), conv_id=conversation_id)
        return jsonify({"error": "subprocess_dead"}), 503
    except Exception as exc:
        logger.exception("mc_direct_ensure_error")
        return jsonify({"error": f"subprocess_pool_error: {exc}"}), 500

    if message:
        try:
            subprocess_registry.send(handle, message, device_id=device_id)
        except TurnLockedException as tl:
            return (
                jsonify({
                    "type": "turn_locked",
                    "conv_id": tl.conv_id,
                    "current_device_id": tl.current_device_id,
                    "seq_id": tl.seq_id,
                }),
                409,
            )
        except SubprocessDeadError as exc:
            logger.error("mc_direct_send_on_dead", error=str(exc))
            return jsonify({"error": "subprocess_dead"}), 503

        save_conversation_message(
            session_id=session_id,
            role="user",
            message=message,
            agent_id=target_agent_id,
            agent_name=target_agent_name,
            request_id=request_id,
            conversation_id=conversation_id,
        )

    # Subscribe AFTER send so the subscriber's seq_id floor excludes the
    # just-submitted turn's history baseline.
    subscriber = handle.subscribe(since=since)

    def generate() -> Generator[str, None, None]:
        # Emit routing event (backwards-compat with existing chat.js handler).
        yield f"data: {json.dumps({'type': 'routing', 'agent_id': target_agent_id, 'agent_name': target_agent_name, 'request_id': request_id})}\n\n"
        try:
            # Phase 2 Unit 2.5: pass conv_id + first user message so the
            # generator can fire LLM auto-naming on the terminal event.
            yield from _stream_direct_generator(
                subscriber,
                session_id,
                request_id,
                conv_id=conversation_id,
                first_user_message=message,
            )
        finally:
            handle.unsubscribe(subscriber)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/stream", methods=["POST"])
def stream():
    """
    SSE endpoint for chat messages.

    Receives a message, routes it to the appropriate agent,
    and streams the response back via Server-Sent Events.

    Supports coordination slash commands:
    - /mprep <meeting description> - Multi-agent meeting prep
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    agent_id = data.get("agent_id")
    session_id = data.get("session_id")
    # Learning signals from frontend
    slash_command = data.get("slash_command")  # e.g., "calendar", "main"
    original_message = data.get("original_message")  # Full message before slash removal
    thread_position = data.get("thread_position", 0)  # Position in thread (0 = head)
    parent_request_id = data.get("parent_request_id")  # For threaded replies

    # Phase 1 resume shape: empty message + since=<seq> is a reconnect/
    # replay-only request. Allow it when the flag is on AND since is set.
    phase1_resume = (
        PA_WEB_UI_PHASE_1_ENABLED
        and not message
        and data.get("since") is not None
    )
    if not message and not phase1_resume:
        return jsonify({"error": "Message is required"}), 400

    if not session_id:
        return jsonify({"error": "Session ID is required"}), 400

    # Check for coordination slash commands (e.g., /mprep board meeting)
    coord_match = COORD_SLASH_PATTERN.match(message.strip())
    if coord_match:
        command = coord_match.group(1).lower()
        argument = coord_match.group(2).strip()

        if command in COORDINATION_COMMANDS:
            task_type, context_key = COORDINATION_COMMANDS[command]
            logger.info(
                "coordination_slash_command",
                command=command,
                task_type=task_type,
                argument=argument,
                session_id=session_id,
            )
            return stream_coordination(
                task_type=task_type,
                context={context_key: argument},
                session_id=session_id,
                original_message=message,
            )

    # Check if this is a slash command (explicit agent routing)
    is_slash_command = bool(slash_command) or bool(agent_id)

    # Phase 1 subprocess-pool dispatch covers MC AND any explicit fleet
    # agent (all 6 are memfs-enabled + autoclear=false, ready for
    # letta-code spawn). Legacy server-side path only kicks in for
    # agents not in FLEET_AGENT_NAMES (none today).
    is_fleet_target = (not agent_id) or (agent_id in FLEET_AGENT_NAMES)

    if PA_WEB_UI_PHASE_1_ENABLED and is_fleet_target:
        # Device identity: prefer the CSRF-paired cookie (ingress_guard
        # set this); fall back to request body for CLI-style clients.
        device_id = (
            request.cookies.get("pa_device_id", "").strip()
            or data.get("device_id")
            or ""
        )
        conversation_id = (data.get("conversation_id") or "default").strip() or "default"
        since_raw = data.get("since")
        since: Optional[int] = None
        if isinstance(since_raw, int):
            since = since_raw
        elif isinstance(since_raw, str) and since_raw.isdigit():
            since = int(since_raw)
        target_agent_id = agent_id or MISSION_CONTROL_AGENT_ID
        logger.info(
            "agent_subprocess_direct_request",
            session_id=session_id,
            device_id=device_id,
            conversation_id=conversation_id,
            since=since,
            message_length=len(message),
            agent_id=target_agent_id,
            slash_command=slash_command,
        )
        return _dispatch_agent_subprocess(
            message=message,
            session_id=session_id,
            device_id=device_id,
            conversation_id=conversation_id,
            since=since,
            agent_id=target_agent_id,
        )

    if not is_slash_command:

        # Pre-Phase-1 default: route to LettaBot
        logger.info(
            "mission_control_stream_request",
            session_id=session_id,
            message_length=len(message),
        )
        return Response(
            stream_mission_control(message, session_id),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    logger.info(
        "stream_request",
        session_id=session_id,
        agent_id=agent_id,
        message_length=len(message),
        slash_command=slash_command,
        thread_position=thread_position,
    )

    def generate() -> Generator[str, None, None]:
        """Generate SSE events from Letta response."""
        try:
            # Step 1: Route the message to get the appropriate agent
            # Use a fresh client per request for concurrent safety
            with httpx.Client(timeout=30.0) as route_client:
                route_response = route_client.post(
                    f"{ROUTING_HANDLER_URL}/v1/route",
                    json={
                        "session_id": session_id,
                        "message": message,
                        "agent_id": agent_id,
                    },
                )
                route_response.raise_for_status()
                route_data = route_response.json()

            selected_agent_id = route_data.get("agent_id")
            agent_name = route_data.get("agent_name", "Assistant")
            request_id = route_data.get("request_id")
            context_injection = route_data.get("context_injection")  # Pattern 2
            briefing_injection = route_data.get("briefing_injection")  # Pattern 4
            identity_id = route_data.get("identity_id")  # Resolved identity
            conversation_id = route_data.get("conversation_id")  # Letta conversation

            logger.info(
                "routed_message",
                session_id=session_id,
                selected_agent_id=selected_agent_id,
                routing_method=route_data.get("routing_method"),
                request_id=request_id,
                identity_id=identity_id,
                conversation_id=conversation_id,
                has_context=bool(context_injection),
                has_briefing=bool(briefing_injection),
            )

            # Send routing event to frontend
            yield f"data: {json.dumps({'type': 'routing', 'agent_id': selected_agent_id, 'agent_name': agent_name, 'request_id': request_id})}\n\n"

            # Save user message to database
            save_conversation_message(
                session_id=session_id,
                role="user",
                message=message,
                agent_id=selected_agent_id,
                agent_name=agent_name,
                request_id=request_id,
            )

            # Save routing signal if user used slash command
            if slash_command:
                save_routing_signal(
                    session_id=session_id,
                    slash_command=slash_command,
                    utterance=original_message or message,
                    target_agent_id=selected_agent_id,
                    target_agent_name=agent_name,
                )

            # Save thread exchange for user message
            save_thread_exchange(
                session_id=session_id,
                request_id=request_id,
                thread_position=thread_position,
                role="user",
                message=message,
                agent_id=selected_agent_id,
                agent_name=agent_name,
                parent_request_id=parent_request_id,
            )

            # Step 2: Stream message to Letta agent with step notifications
            letta_url = f"{LETTA_BASE_URL}/v1/agents/{selected_agent_id}/messages/stream"

            # Build augmented message with injections (Pattern 2 + Pattern 4)
            # Order: briefing (main agent only) -> context -> user message
            message_parts = []
            if briefing_injection:
                message_parts.append(briefing_injection)
            if context_injection:
                message_parts.append(context_injection)
            message_parts.append(message)
            augmented_message = "\n\n".join(message_parts)

            letta_payload = {"messages": [
                {"role": "system", "content": build_web_ui_system_reminder()},
                {"role": "user", "content": augmented_message},
            ]}
            # Include conversation_id if available (for Letta Conversations persistence)
            if conversation_id:
                letta_payload["conversation_id"] = conversation_id

            logger.info(
                "letta_stream_starting",
                agent_id=selected_agent_id,
                agent_name=agent_name,
                request_id=request_id,
                conversation_id=conversation_id,
            )

            # Use a queue-based approach with keepalive pings
            # This keeps the frontend connection alive during long Letta operations
            event_queue = queue.Queue()
            assistant_response_parts = []
            tool_calls_made = []  # Track tool calls for summary extraction
            report_refs_data = None  # Capture report_refs tool call for handler

            def run_letta_stream():
                """Background thread to run Letta stream and put events in queue."""
                last_error = None
                stream_success = False

                for attempt in range(MAX_RETRIES):
                    try:
                        with httpx.Client(timeout=LETTA_STREAM_TIMEOUT) as stream_client:
                            with stream_client.stream(
                                "POST",
                                letta_url,
                                json=letta_payload,
                                params={"stream_steps": "true"},
                            ) as letta_stream:

                                logger.info(
                                    "letta_stream_opened",
                                    status_code=letta_stream.status_code,
                                    agent_id=selected_agent_id,
                                )

                                if letta_stream.status_code != 200:
                                    if letta_stream.status_code in RETRYABLE_STATUS_CODES:
                                        last_error = f"Letta returned {letta_stream.status_code}"
                                        logger.warning(
                                            "letta_stream_transient_error",
                                            status_code=letta_stream.status_code,
                                            attempt=attempt + 1,
                                        )
                                        if attempt < MAX_RETRIES - 1:
                                            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                                            continue
                                    else:
                                        last_error = f"Letta returned {letta_stream.status_code}"
                                        break

                                stream_success = True

                                # Process SSE stream from Letta
                                buffer = ""
                                for chunk in letta_stream.iter_text():
                                    buffer += chunk
                                    while "\n" in buffer:
                                        line, buffer = buffer.split("\n", 1)
                                        line = line.strip()

                                        if not line or line.startswith(":"):
                                            continue

                                        if line.startswith("data: "):
                                            data_str = line[6:]
                                            if data_str == "[DONE]":
                                                continue

                                            try:
                                                event_data = json.loads(data_str)
                                                msg_type = event_data.get("message_type", "")

                                                # Log all events for debugging
                                                logger.info(
                                                    "letta_event",
                                                    message_type=msg_type,
                                                    agent_id=selected_agent_id,
                                                    has_content="content" in event_data,
                                                )

                                                # Put event in queue for main thread
                                                event_queue.put(("event", msg_type, event_data))

                                            except json.JSONDecodeError:
                                                pass

                                logger.info(
                                    "letta_stream_completed",
                                    agent_id=selected_agent_id,
                                    request_id=request_id,
                                )
                                break  # Success, exit retry loop

                    except httpx.TimeoutException as e:
                        last_error = f"Letta timeout: {str(e)}"
                        logger.warning(
                            "letta_stream_timeout",
                            attempt=attempt + 1,
                            max_retries=MAX_RETRIES,
                        )
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                            continue

                    except Exception as e:
                        last_error = f"Stream error: {str(e)}"
                        logger.error("letta_stream_error", error=str(e))
                        break

                # Signal completion or error
                if stream_success:
                    event_queue.put(("done", None, None))
                else:
                    error_msg = last_error or "Failed to stream from Letta"
                    event_queue.put(("error", None, {"message": error_msg}))

            # Start Letta stream in background thread
            letta_thread = threading.Thread(target=run_letta_stream, daemon=True)
            letta_thread.start()

            # Process events from queue with keepalive pings
            stream_done = False
            stream_error = None

            while not stream_done:
                try:
                    # Wait for event with timeout for keepalive
                    event_type, msg_type, event_data = event_queue.get(
                        timeout=KEEPALIVE_PING_INTERVAL
                    )

                    if event_type == "done":
                        stream_done = True
                    elif event_type == "error":
                        stream_error = event_data.get("message", "Unknown error")
                        stream_done = True
                    elif event_type == "event":
                        # Process Letta event
                        if msg_type == "tool_call_message":
                            tool_call = event_data.get("tool_call", {})
                            tool_name = tool_call.get("name", "tool")
                            tool_calls_made.append(tool_name)  # Track for summary
                            # Capture report_refs tool call for handler
                            if tool_name == "report_refs":
                                report_refs_data = tool_call.get("arguments", "")
                                logger.info(
                                    "report_refs_captured",
                                    refs_data=report_refs_data[:200] if report_refs_data else None,
                                )
                            # Note: send_message is deprecated in letta_v1_agent
                            # User-facing content comes via assistant_message directly
                            yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

                        elif msg_type == "assistant_message":
                            # Per Letta docs: assistant_message IS the user-facing response
                            # Yield immediately - no need for fallback logic
                            # Debug: log all event_data keys to understand structure
                            logger.info(
                                "assistant_message_structure",
                                keys=list(event_data.keys()),
                                has_internal_monologue="internal_monologue" in event_data,
                                has_inner_thoughts="inner_thoughts" in event_data,
                            )
                            content = event_data.get("content", "")
                            if content:
                                # Store for server-side processing (DB saves, /complete endpoint)
                                assistant_response_parts.append(content)
                                # Yield to frontend immediately
                                cleaned_content = clean_response_for_user(content)
                                if cleaned_content:
                                    sse_data = f"data: {json.dumps({'type': 'text', 'content': cleaned_content})}\n\n"
                                    logger.info(
                                        "yielding_assistant_message",
                                        agent_id=selected_agent_id,
                                        content_length=len(cleaned_content),
                                        sse_preview=sse_data[:150],  # Show start of SSE data
                                        content_start=cleaned_content[:100],  # Show start of content
                                    )
                                    yield sse_data
                                    logger.debug(
                                        "yield_completed",
                                        agent_id=selected_agent_id,
                                    )
                                else:
                                    logger.warning(
                                        "cleaned_content_empty",
                                        agent_id=selected_agent_id,
                                        raw_content_length=len(content),
                                        raw_content_start=content[:200],
                                    )

                        elif msg_type == "user_message":
                            # Letta memory compaction or system alert - log but don't display
                            logger.debug(
                                "letta_system_message",
                                agent_id=selected_agent_id,
                                content_preview=str(event_data.get("content", ""))[:100],
                            )

                        elif msg_type in ("stop_reason", "usage_statistics", "ping"):
                            # Expected Letta stream events - no action needed
                            pass

                        elif msg_type == "reasoning_message":
                            # Agent is thinking - send a ping to keep connection alive
                            yield f"data: {json.dumps({'type': 'ping'})}\n\n"

                        elif msg_type == "internal_error":
                            error_msg = event_data.get("internal_error", "Internal error")
                            logger.error(
                                "letta_internal_error",
                                error=error_msg,
                            )
                            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                            stream_done = True

                except queue.Empty:
                    # No event received within timeout - send keepalive ping
                    logger.info("keepalive_ping", agent_id=selected_agent_id)
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"

            # Wait for thread to finish (with timeout)
            letta_thread.join(timeout=5.0)

            if stream_error:
                yield f"data: {json.dumps({'type': 'error', 'message': stream_error})}\n\n"
                return

            # Save assistant response to database
            # Save even if no text content - create summary from tool calls
            raw_response = "\n\n".join(assistant_response_parts) if assistant_response_parts else ""
            # Clean SUMMARY/REFS lines before saving to database (user will see this on refresh)
            full_response = clean_response_for_user(raw_response) if raw_response else ""
            if full_response or tool_calls_made:
                # If no text response but tools were called, create a brief summary
                if not full_response and tool_calls_made:
                    full_response = f"[Completed: {', '.join(tool_calls_made)}]"
                save_conversation_message(
                    session_id=session_id,
                    role="assistant",
                    message=full_response,
                    agent_id=selected_agent_id,
                    agent_name=agent_name,
                    request_id=request_id,
                )
                # Save thread exchange for assistant response
                save_thread_exchange(
                    session_id=session_id,
                    request_id=request_id,
                    thread_position=thread_position,
                    role="assistant",
                    message=full_response,
                    agent_id=selected_agent_id,
                    agent_name=agent_name,
                    parent_request_id=parent_request_id,
                )

            # Mark thread as complete for contextual routing and summary extraction
            # NOTE: Send raw_response (with SUMMARY lines) to routing handler for extraction
            if request_id:
                try:
                    complete_url = f"{ROUTING_HANDLER_URL}/v1/sessions/{session_id}/threads/{request_id}/complete"
                    # Build params - tool_calls as repeated keys for FastAPI list handling
                    complete_params = [
                        ("agent_id", selected_agent_id),
                        ("agent_name", agent_name),
                        ("response_content", raw_response),
                        ("user_message", message),  # For Pattern 3 archival passage
                        ("report_refs_json", report_refs_data or ""),  # Structured refs from tool call
                        ("identity_id", identity_id),  # For session context keying
                    ]
                    # Add each tool call as a separate param for FastAPI list handling
                    for tool in tool_calls_made:
                        complete_params.append(("tool_calls", tool))

                    with httpx.Client(timeout=10.0) as complete_client:
                        complete_response = complete_client.post(
                            complete_url,
                            params=complete_params,
                        )
                        complete_data = complete_response.json()
                    logger.info(
                        "thread_completed",
                        session_id=session_id,
                        request_id=request_id,
                        agent_id=selected_agent_id,
                        summary=complete_data.get("summary"),
                    )
                except Exception as e:
                    logger.warning("thread_complete_failed", error=str(e))

            # Post summary to Mission Control (fire-and-forget)
            if assistant_response_parts:
                summary_text = "".join(assistant_response_parts)[:500]
                try:
                    with httpx.Client(timeout=10.0) as summary_client:
                        summary_client.post(
                            f"{LETTA_BASE_URL}/v1/agents/{MISSION_CONTROL_AGENT_ID}/messages",
                            json={"messages": [{"role": "user", "content": f"[System: Agent handoff summary] The user invoked /{slash_command or 'agent'} and asked: \"{message[:200]}\"\n{agent_name} responded: \"{summary_text}\""}]},
                        )
                except Exception as e:
                    logger.warning("mission_control_summary_failed", error=str(e))

            # Send done event
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except httpx.HTTPStatusError as e:
            logger.error("stream_http_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': f'HTTP error: {e.response.status_code}'})}\n\n"

        except Exception as e:
            logger.error("stream_error", error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Task Review Sidebar API ──

TASKS_AGENT_ID = "agent-dd15479e-6543-400e-8463-b2a48b13cd4a"
EXTRACTED_TASKS_BLOCK_ID = "block-90300b77-6b72-42cb-8e67-c74fbb497cf6"
TASKS_ARCHIVE_ID = "archive-f9bcaa87-7630-41c9-9694-41d46fc47d26"
OMNIFOCUS_BRIDGE_URL = os.getenv(
    "OMNIFOCUS_BRIDGE_URL", "http://host.docker.internal:8889"
)

# Task block line pattern:
# [extracted_time: 2026-02-15T10:30:00-05:00; ref_id: a1b2c3d4] Description
# [extracted_time: ...; ref_id: ...; origin: meeting_transcript] Description
TASK_LINE_PATTERN = re.compile(
    r'\[extracted_time:\s*([^;]+);\s*ref_id:\s*([a-f0-9]+)'
    r'(?:;\s*origin:\s*([^\];]*))?'
    r'(?:;\s*est:\s*(\d+))?\]\s*(.+)'
)


def parse_task_block(block_value):
    """Parse extracted_tasks block text into list of task dicts."""
    tasks = []
    for line in block_value.split('\n'):
        line = line.strip()
        if not line:
            continue
        m = TASK_LINE_PATTERN.search(line)
        if m:
            est_raw = m.group(4)
            tasks.append({
                "extracted_time": m.group(1).strip(),
                "ref_id": m.group(2).strip(),
                "origin": (m.group(3) or "").strip() or None,
                "estimate_minutes": int(est_raw) if est_raw else None,
                "description": m.group(5).strip(),
            })
    return tasks


def parse_archival_passage(text):
    """Parse structured archival passage text into sections."""
    result = {}

    # Include raw text for note formatting
    result['raw_text'] = text

    m = re.search(r'^TASK:\s*(.+)$', text, re.MULTILINE)
    if m:
        result['task'] = m.group(1).strip()

    m = re.search(r'^REF_ID:\s*(\S+)', text, re.MULTILINE)
    if m:
        result['ref_id'] = m.group(1).strip()

    m = re.search(r'^ORIGIN:\s*(.+)$', text, re.MULTILINE)
    if m:
        result['origin'] = m.group(1).strip()

    # TASK METADATA - Estimate (current, may be user-edited)
    m = re.search(r'^- Estimate:\s*(\d+)', text, re.MULTILINE)
    if m:
        result['estimate_minutes'] = int(m.group(1))

    # TASK METADATA - Agent Estimate (original, immutable)
    m = re.search(r'^- Agent Estimate:\s*(\d+)', text, re.MULTILINE)
    if m:
        result['agent_estimate_minutes'] = int(m.group(1))

    # SOURCE REFERENCE
    source_ref = {}
    m = re.search(r'SOURCE REFERENCE\n((?:- .+\n)*)', text)
    if m:
        for line in m.group(1).strip().split('\n'):
            lm = re.match(r'- (.+?):\s*(.+)', line)
            if lm:
                source_ref[lm.group(1).strip().lower().replace(' ', '_')] = lm.group(2).strip()
    if source_ref:
        result['source_reference'] = source_ref

    # SOURCE METADATA
    source_meta = {}
    m = re.search(r'SOURCE METADATA\n((?:- .+\n)*)', text)
    if m:
        for line in m.group(1).strip().split('\n'):
            lm = re.match(r'- (.+?):\s*(.+)', line)
            if lm:
                source_meta[lm.group(1).strip().lower().replace(' ', '_')] = lm.group(2).strip()
    if source_meta:
        result['source_metadata'] = source_meta

    # RELATED URLS
    urls_section = re.search(r'RELATED URLS\n((?:- .+\n)*)', text)
    if urls_section:
        urls = []
        for line in urls_section.group(1).strip().split('\n'):
            url_match = re.match(r'- (.+)', line)
            if url_match:
                urls.append(url_match.group(1).strip())
        if urls:
            result['related_urls'] = urls

    # TIMESTAMPS
    timestamps = []
    ts_section = re.search(r'TIMESTAMPS\n((?:- .+\n)*)', text)
    if ts_section:
        for ts_line in ts_section.group(1).strip().split('\n'):
            ts_match = re.match(r'- (.+?):\s*(.+)', ts_line)
            if ts_match:
                timestamps.append({
                    'label': ts_match.group(1).strip(),
                    'value': ts_match.group(2).strip(),
                })
    result['timestamps'] = timestamps

    # OMNIFOCUS
    omnifocus = {}
    m = re.search(r'- Task ID:\s*(.+)', text)
    if m:
        omnifocus['task_id'] = m.group(1).strip()
    m = re.search(r'- Status:\s*(.+)', text)
    if m:
        omnifocus['status'] = m.group(1).strip()
    if omnifocus:
        result['omnifocus'] = omnifocus

    # PACKET INFO
    packet_match = re.search(
        r'PACKET INFO\n(.+?)(?=\nSOURCE TEXT\n|\nFETCH HINT:|\Z)',
        text, re.DOTALL,
    )
    if packet_match:
        packet = {}
        ptext = packet_match.group(1).strip()

        # Three-node model
        da = re.search(r'- Direct-action:\s*(.+)', ptext)
        if da:
            packet['direct_action'] = da.group(1).strip()
        ap = re.search(r'- Artifact provenance:\s*(.+)', ptext)
        if ap:
            packet['artifact_provenance'] = ap.group(1).strip()
        ig = re.search(r'- Intent genesis:\s*(.+)', ptext)
        if ig:
            packet['intent_genesis'] = ig.group(1).strip()

        # Context brief
        brief_match = re.search(
            r'Context brief:\n(.+?)(?=\nResources:|\nRelated|\nKnowns|\nAgent notes|\Z)',
            ptext, re.DOTALL,
        )
        if brief_match:
            items = []
            for line in brief_match.group(1).strip().split('\n'):
                line = line.strip().lstrip('- ')
                if line:
                    items.append(line)
            packet['context_brief'] = items

        # Resources
        resources_match = re.search(
            r'Resources:\n(.+?)(?=\nRelated|\nKnowns|\nAgent notes|\Z)',
            ptext, re.DOTALL,
        )
        if resources_match:
            items = []
            for line in resources_match.group(1).strip().split('\n'):
                line = line.strip().lstrip('- ')
                if line:
                    items.append(line)
            packet['resources'] = items

        # Related tasks
        related_match = re.search(
            r'Related tasks:\n(.+?)(?=\nKnowns|\nAgent notes|\Z)',
            ptext, re.DOTALL,
        )
        if related_match:
            items = []
            for line in related_match.group(1).strip().split('\n'):
                line = line.strip().lstrip('- ')
                if line:
                    items.append(line)
            packet['related_tasks'] = items

        # Knowns / Unknowns
        knowns_match = re.search(
            r'Knowns / (?:Assumptions / )?Unknowns:\n(.+?)(?=\nAgent notes|\Z)',
            ptext, re.DOTALL,
        )
        if knowns_match:
            knowns = []
            unknowns = []
            for line in knowns_match.group(1).strip().split('\n'):
                line = line.strip()
                if line.startswith('Known:'):
                    knowns.append(line[6:].strip())
                elif line.startswith('Unknown:'):
                    unknowns.append(line[8:].strip())
            if knowns:
                packet['knowns'] = knowns
            if unknowns:
                packet['unknowns'] = unknowns

        # Agent notes
        notes_match = re.search(r'Agent notes:\n(.+?)(?=\Z)', ptext, re.DOTALL)
        if notes_match:
            packet['agent_notes'] = notes_match.group(1).strip()

        # Mismatch warnings
        mismatch = re.search(r'>>> ⚠ (.+?) <<<', ptext)
        if mismatch:
            packet['mismatch_warning'] = mismatch.group(1).strip()

        result['packet_info'] = packet

    # ENRICHMENT status
    enrich_match = re.search(r'ENRICHMENT\n- Status:\s*(.+)', text)
    if enrich_match:
        result['enrichment_status'] = enrich_match.group(1).strip()

    # SOURCE TEXT
    m = re.search(r'SOURCE TEXT\n(.+)', text, re.DOTALL)
    if m:
        result['source_text'] = m.group(1).strip()

    return result


def call_omnifocus_bridge(method, params=None):
    """Call OmniFocus via the host bridge service (port 8889).

    Same protocol used by omnifocus-cli in Docker containers.
    """
    url = f"{OMNIFOCUS_BRIDGE_URL}/execute"
    resp = httpx.post(
        url,
        json={"command": method, "args": params or {}},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"OmniFocus bridge error: {data['error']}")
    result = data.get("result", data)
    # Bridge may double-encode JSON as a string
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, ValueError):
            pass
    return result


def _find_archival_passage(client, ref_id):
    """Search archival memory for a passage matching ref_id. Returns (passage, error_response)."""
    resp = client.get(
        f"{LETTA_BASE_URL}/v1/agents/{TASKS_AGENT_ID}/archival-memory",
        params={"search": ref_id},
    )
    resp.raise_for_status()
    for p in resp.json():
        if f"REF_ID: {ref_id}" in p.get('text', '') and p.get('archive_id') == TASKS_ARCHIVE_ID:
            return p, None
    return None, (jsonify({"error": f"No passage found for {ref_id}"}), 404)


def _build_work_packet_segments(ref_id, passage_text, enrichment=None):
    """Build rich-text segments for an OmniFocus work packet note.

    Shared by both first-pass assembly (in confirm handler) and
    re-assembly endpoint (for MC-enriched updates).

    Cycle-1: when `enrichment` (the pa_web.tasks.enrichment JSONB) is
    provided and contains packet_info, prefer it over the legacy
    archival-passage-parsed shape. Falls back to parsed passage for
    back-compat with rows whose enrichment was never run.

    Returns a list of segment dicts/strings for the setRichText bridge call.
    """
    parsed = parse_archival_passage(passage_text)
    pi = parsed.get("packet_info", {}) or {}

    # Cycle-1 canonical: enrichment.packet_info from write_packet_info_tool.
    # Shape: direct_action, artifact_provenance, intent_genesis,
    # context_brief[], resources[], related_tasks[], knowns[], unknowns[],
    # mismatch_warnings[] (plural — list), additional_notes.
    if enrichment and isinstance(enrichment, dict):
        cycle1_pi = enrichment.get("packet_info") or {}
        if cycle1_pi:
            # Normalize plural→singular for renderer keys, prefer cycle-1 values.
            mw_list = cycle1_pi.get("mismatch_warnings") or []
            pi = {
                "context_brief": cycle1_pi.get("context_brief") or pi.get("context_brief") or [],
                "resources": cycle1_pi.get("resources") or pi.get("resources") or [],
                "related_tasks": cycle1_pi.get("related_tasks") or pi.get("related_tasks") or [],
                "knowns": cycle1_pi.get("knowns") or pi.get("knowns") or [],
                "unknowns": cycle1_pi.get("unknowns") or pi.get("unknowns") or [],
                "mismatch_warning": (mw_list[0] if mw_list else pi.get("mismatch_warning")),
                "agent_notes": cycle1_pi.get("additional_notes") or pi.get("agent_notes"),
                # Pass through cycle-1-only fields for downstream rendering
                "direct_action": cycle1_pi.get("direct_action"),
                "artifact_provenance": cycle1_pi.get("artifact_provenance"),
                "intent_genesis": cycle1_pi.get("intent_genesis"),
            }

    segments = []

    # Source context line
    sr = parsed.get("source_reference", {})
    sm = parsed.get("source_metadata", {})
    if sr.get("context"):
        segments.append({"text": f"Source: {sr['context']}\n", "italic": True, "size": 11})
    if sm.get("from"):
        segments.append({"text": f"From: {sm['from']}\n", "italic": True, "size": 11})

    # Ref ID for traceability
    segments.append({"text": f"ref_id: {ref_id}\n\n", "size": 10, "color": [0.5, 0.5, 0.5, 1]})

    # Mismatch warning (prominent)
    if pi.get("mismatch_warning"):
        segments.append({"text": f"⚠ {pi['mismatch_warning']}\n\n", "bold": True, "color": [0.9, 0.2, 0, 1]})

    # Context brief
    if pi.get("context_brief"):
        segments.append({"text": "Context\n", "bold": True, "size": 13})
        for item in pi["context_brief"]:
            segments.append(f"  • {item}\n")

    # Resources (with clickable links)
    if pi.get("resources"):
        segments.append("\n")
        segments.append({"text": "Resources\n", "bold": True, "size": 13})
        for item in pi["resources"]:
            url_match = re.search(r"(openfile://\S+|https?://\S+)", item)
            if url_match:
                url = url_match.group(1).rstrip(")")
                label = item[:item.find(url_match.group(0))].strip().rstrip("—").strip()
                role_match = re.search(r"\((\w+)\)\s*$", item)
                role = f" ({role_match.group(1)})" if role_match else ""
                segments.append({"text": f"  {label}{role}: ", "size": 11})
                # For slack permalinks (workspace-scoped, ugly), use the
                # word "Permalink" as the visible hyperlink text.
                if "slack.com/archives/" in url:
                    display_text = "Permalink"
                else:
                    display_text = url[:60] + ("..." if len(url) > 60 else "")
                segments.append({"text": f"{display_text}\n", "url": url, "underline": True, "size": 11})
            else:
                segments.append(f"  • {item}\n")

    # Related tasks
    if pi.get("related_tasks"):
        segments.append("\n")
        segments.append({"text": "Related Tasks\n", "bold": True, "size": 13})
        for item in pi["related_tasks"]:
            segments.append(f"  • {item}\n")

    # Knowns / Unknowns
    if pi.get("knowns") or pi.get("unknowns"):
        segments.append("\n")
        segments.append({"text": "Knowns / Unknowns\n", "bold": True, "size": 13})
        for k in (pi.get("knowns") or []):
            segments.append(f"  ✓ {k}\n")
        for u in (pi.get("unknowns") or []):
            segments.append({"text": f"  ? {u}\n", "italic": True})

    # Agent notes
    if pi.get("agent_notes"):
        segments.append("\n")
        segments.append({"text": f"{pi['agent_notes']}\n", "size": 10, "italic": True, "color": [0.5, 0.5, 0.5, 1]})

    # Source text (collapsed)
    if parsed.get("source_text"):
        src = parsed["source_text"][:200]
        segments.append("\n")
        segments.append({"text": "Source\n", "bold": True, "size": 13})
        segments.append({"text": f"{src}\n", "size": 11, "color": [0.4, 0.4, 0.4, 1]})

    # Related URLs (separate from resources)
    if parsed.get("related_urls"):
        segments.append("\n")
        segments.append({"text": "Links\n", "bold": True, "size": 13})
        for url in parsed["related_urls"]:
            if url.startswith("http"):
                display = url[:60] + ("..." if len(url) > 60 else "")
                segments.append({"text": f"  {display}\n", "url": url, "underline": True})

    return segments


# Per-ref_id locks to serialize first-pass assembly and MC re-assembly.
# Short-lived — only held around the bridge call.
import threading as _threading
_work_packet_locks = {}
_work_packet_locks_guard = _threading.Lock()


def _get_work_packet_lock(ref_id):
    """Get or create a threading lock for a ref_id's work packet writes."""
    with _work_packet_locks_guard:
        if ref_id not in _work_packet_locks:
            _work_packet_locks[ref_id] = _threading.Lock()
        return _work_packet_locks[ref_id]


def _write_work_packet_note(ref_id, omnifocus_task_id, passage_text, enrichment=None):
    """Write the work packet note to OmniFocus via setRichText (atomic replace).

    Uses per-ref_id lock to prevent races between first-pass and re-assembly.
    """
    segments = _build_work_packet_segments(ref_id, passage_text, enrichment=enrichment)
    if not segments:
        return False

    lock = _get_work_packet_lock(ref_id)
    with lock:
        try:
            with httpx.Client(timeout=15.0) as c:
                c.post(
                    f"{OMNIFOCUS_BRIDGE_URL}/execute",
                    json={
                        "command": "setRichText",
                        "args": {
                            "taskId": omnifocus_task_id,
                            "segments": segments,
                        },
                    },
                )
            return True
        except Exception:
            return False


def _replace_passage(client, passage_id, new_text, tags):
    """Delete old passage and insert replacement in shared archive."""
    client.delete(
        f"{LETTA_BASE_URL}/v1/archives/{TASKS_ARCHIVE_ID}/passages/{passage_id}"
    )
    ins_resp = client.post(
        f"{LETTA_BASE_URL}/v1/archives/{TASKS_ARCHIVE_ID}/passages",
        json={"text": new_text, "tags": tags},
    )
    ins_resp.raise_for_status()
    return ins_resp.json()


def _remove_ref_from_block(client, ref_id):
    """Remove a task line from the extracted_tasks block (best-effort)."""
    try:
        block_resp = client.get(
            f"{LETTA_BASE_URL}/v1/blocks/{EXTRACTED_TASKS_BLOCK_ID}"
        )
        block_resp.raise_for_status()
        val = block_resp.json().get('value', '')
        new_val = re.sub(
            rf'[^\n]*ref_id: {re.escape(ref_id)}[^\n]*\n*', '', val
        )
        while '\n\n\n' in new_val:
            new_val = new_val.replace('\n\n\n', '\n\n')
        if new_val != val:
            client.patch(
                f"{LETTA_BASE_URL}/v1/blocks/{EXTRACTED_TASKS_BLOCK_ID}",
                json={"value": new_val},
            )
    except Exception:
        pass


# --- Cycle-1 Pattern 5 cutover (2026-04-26) ---
# Task routes below read/write pa_web.tasks directly instead of the legacy
# extracted_tasks block + tasks-agent archival. Mirror writer regenerates
# the legacy block on a 30s tick for not-yet-migrated agent readers.
# Every UPDATE sets migration_source='live' so Unit 12's archival re-run
# predicate skips these rows.

_TASK_TERMINAL_STATUSES = {"done", "completed", "rejected", "merged", "archived"}
_TASK_TRIAGE_STATUSES = ("extracted", "active")


def _set_live_marker(updates: dict) -> dict:
    """Ensure every CRUD UPDATE flips migration_source to 'live'."""
    updates = dict(updates)
    updates.setdefault("migration_source", "live")
    return updates


@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    """Triage queue: tasks awaiting confirm or reject.

    Per the cycle-1 sidebar contract: only 'extracted' or 'active' rows
    that haven't been closed (rejected/completed/merged). Confirmed
    tasks drop out (they've moved into the work pipeline via
    OmniFocus / MC).
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ref_id, extracted_at, origin,
                           original_est_minutes, revised_est_minutes,
                           raw_description, suggested_title, confirmed_title,
                           status, source, source_ref
                      FROM pa_web.tasks
                     WHERE closed_at IS NULL
                       AND status IN %s
                       AND raw_description IS NOT NULL
                       AND length(trim(raw_description)) > 0
                     ORDER BY extracted_at DESC NULLS LAST, ref_id
                    """,
                    (_TASK_TRIAGE_STATUSES,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        tasks = []
        for r in rows:
            ts = r["extracted_at"].isoformat() if r["extracted_at"] else ""
            tasks.append({
                "ref_id": r["ref_id"],
                "extracted_time": ts,
                "origin": r["origin"],
                # estimate_minutes preserves the legacy key the sidebar reads;
                # prefer the revised value when set, else original.
                "estimate_minutes": r["revised_est_minutes"]
                                    if r["revised_est_minutes"] is not None
                                    else r["original_est_minutes"],
                "description": r["confirmed_title"]
                               or r["suggested_title"]
                               or r["raw_description"],
                # New cycle-1 fields the sidebar may opt into:
                "status": r["status"],
                "suggested_title": r["suggested_title"],
                "confirmed_title": r["confirmed_title"],
                "source": r["source"],
                "source_ref": r["source_ref"],
            })
        return jsonify({"tasks": tasks})
    except Exception as e:
        logger.error("api_get_tasks_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/<ref_id>', methods=['GET'])
def api_get_task_detail(ref_id):
    """Get full task detail.

    Returns the same shape parse_archival_passage produced — sidebar.js
    consumes keys: task, ref_id, source_reference, source_metadata,
    related_urls, timestamps, omnifocus, packet_info, raw_text. We
    rebuild that shape from pa_web.tasks columns + (when present)
    re-parse the stored task_body for backward-compat sections.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM pa_web.tasks WHERE ref_id = %s", (ref_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return jsonify({"error": f"Task {ref_id} not found"}), 404

        # If we have the original archival passage text, parse_archival_passage
        # gives us all the canonical sections. Otherwise build minimal shape.
        body = row.get("task_body") or ""
        if body:
            detail = parse_archival_passage(body)
        else:
            detail = {"raw_text": "", "task": row.get("raw_description") or ""}

        # Cycle-1: overlay enrichment.packet_info (canonical) onto detail.packet_info.
        # Sidebar consumes detail.packet_info as the rendered section.
        enrichment = row.get("enrichment") or {}
        cy1_pi = (enrichment.get("packet_info") or {}) if isinstance(enrichment, dict) else {}
        if cy1_pi:
            mw_list = cy1_pi.get("mismatch_warnings") or []
            existing_pi = detail.get("packet_info") or {}
            detail["packet_info"] = {
                **existing_pi,
                "context_brief": cy1_pi.get("context_brief") or existing_pi.get("context_brief") or [],
                "resources": cy1_pi.get("resources") or existing_pi.get("resources") or [],
                "related_tasks": cy1_pi.get("related_tasks") or existing_pi.get("related_tasks") or [],
                "knowns": cy1_pi.get("knowns") or existing_pi.get("knowns") or [],
                "unknowns": cy1_pi.get("unknowns") or existing_pi.get("unknowns") or [],
                "mismatch_warning": (mw_list[0] if mw_list else existing_pi.get("mismatch_warning")),
                "agent_notes": cy1_pi.get("additional_notes") or existing_pi.get("agent_notes"),
                "direct_action": cy1_pi.get("direct_action"),
                "artifact_provenance": cy1_pi.get("artifact_provenance"),
                "intent_genesis": cy1_pi.get("intent_genesis"),
            }
            detail["enrichment_state"] = row.get("enrichment_state")
            detail["enrichment_phase"] = enrichment.get("phase")
            detail["enriched_at"] = enrichment.get("enriched_at")

        # Overlay PG-canonical fields (PG is source of truth post-cutover).
        detail["ref_id"] = row["ref_id"]
        detail["task"] = (row.get("confirmed_title")
                          or row.get("suggested_title")
                          or row.get("raw_description") or "")
        detail.setdefault("origin", row.get("origin"))
        if row.get("source_metadata"):
            detail["source_metadata"] = {
                **(detail.get("source_metadata") or {}),
                **row["source_metadata"],
            }
        if row.get("related_urls"):
            detail["related_urls"] = list(row["related_urls"])
        # Estimate fields (cycle-1 schema additions)
        if row.get("original_est_minutes") is not None:
            detail["agent_estimate_minutes"] = row["original_est_minutes"]
        if row.get("revised_est_minutes") is not None:
            detail["estimate_minutes"] = row["revised_est_minutes"]
        elif row.get("original_est_minutes") is not None:
            detail["estimate_minutes"] = row["original_est_minutes"]
        if row.get("actual_minutes") is not None:
            detail["actual_minutes"] = row["actual_minutes"]
        # OmniFocus state
        of = dict(detail.get("omnifocus") or {})
        if row.get("omnifocus_id"):
            of["task_id"] = row["omnifocus_id"]
        of.setdefault("status", row.get("status") or "")
        if of:
            detail["omnifocus"] = of
        # Lifecycle timestamps
        for label, val in (
            ("Extracted", row.get("extracted_at")),
            ("Started", row.get("started_at")),
            ("Closed", row.get("closed_at")),
            ("OmniFocus pending", row.get("omnifocus_pending_at")),
            ("OmniFocus created", row.get("omnifocus_created_at")),
        ):
            if val:
                detail.setdefault("timestamps", []).append(
                    {"label": label, "value": val.isoformat()
                                                if hasattr(val, "isoformat") else str(val)}
                )
        detail["status"] = row.get("status")
        return jsonify(detail)
    except Exception as e:
        logger.error("api_get_task_detail_error", ref_id=ref_id, error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/<ref_id>', methods=['PATCH'])
def api_update_task(ref_id):
    """Inline edit of task title and/or estimate.

    Cycle-1 update semantics:
      - task_description → confirmed_title (the user-finalized title).
        If never set, suggested_title remains the agent's original.
      - estimate_minutes → revised_est_minutes (original_est_minutes is
        immutable agent-set value).
      - migration_source flips to 'live'.
      - closed_at NEVER changes here — only status transitions close.
    """
    try:
        data = request.get_json() or {}
        task_description = data.get('task_description')
        estimate_minutes = data.get('estimate_minutes')

        if not task_description and estimate_minutes is None:
            return jsonify({"error": "task_description or estimate_minutes required"}), 400

        sets = ["updated_at = NOW()", "migration_source = 'live'"]
        params = []
        if task_description:
            sets.append("confirmed_title = %s")
            params.append(task_description)
        if estimate_minutes is not None:
            sets.append("revised_est_minutes = %s")
            params.append(int(estimate_minutes))
        params.append(ref_id)

        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE pa_web.tasks SET {', '.join(sets)} "
                    f"WHERE ref_id = %s RETURNING ref_id",
                    params,
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if not row:
            return jsonify({"error": f"Task {ref_id} not found"}), 404

        return jsonify({"status": "ok", "ref_id": ref_id})
    except Exception as e:
        logger.error("api_update_task_error", ref_id=ref_id, error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/<ref_id>/transition', methods=['POST'])
def api_transition_task(ref_id):
    """Transition task: confirm, reject, or complete.

    Cycle-1 lifecycle rules (per user spec 2026-04-26):
      - reject → status='rejected', closed_at=NOW() (terminal)
      - complete → status='completed', closed_at=NOW() (terminal,
        typically driven by OmniFocus completion)
      - confirm → status='confirmed', closed_at stays NULL
        (task moves into work pipeline, not closed)
    """
    try:
        data = request.get_json() or {}
        action = data.get('action')
        omnifocus_task_id = data.get('omnifocus_task_id')
        rush = bool(data.get('rush', False))

        valid_actions = {"confirm", "reject", "complete"}
        if action not in valid_actions:
            return jsonify({
                "error": f"Invalid action. Must be one of: {', '.join(sorted(valid_actions))}"
            }), 400

        if action == "confirm" and not omnifocus_task_id:
            return jsonify({"error": "omnifocus_task_id required for confirm"}), 400

        # Read old row first (for work-packet downstream + logging)
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM pa_web.tasks WHERE ref_id = %s", (ref_id,))
                old_row = cur.fetchone()
            if not old_row:
                return jsonify({"error": f"Task {ref_id} not found"}), 404

            # Build status transition
            if action == "confirm":
                new_status = "confirmed"
                close_clause = ""  # closed_at stays NULL per user spec
            elif action == "reject":
                new_status = "rejected"
                close_clause = ", closed_at = NOW()"
            elif action == "complete":
                new_status = "completed"
                close_clause = ", closed_at = NOW()"

            params: list = [new_status]
            of_set = ""
            if action == "confirm" and omnifocus_task_id:
                of_set = ", omnifocus_id = %s, omnifocus_created_at = NOW()"
                params.append(omnifocus_task_id)
            params.append(ref_id)

            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE pa_web.tasks
                           SET status = %s{of_set}{close_clause},
                               updated_at = NOW(),
                               migration_source = 'live'
                         WHERE ref_id = %s""",
                    params,
                )
            conn.commit()
        finally:
            conn.close()

        # task_body still holds the original archival passage; reuse for logging
        old_text = old_row.get("task_body") or ""
        task_desc = (old_row.get("confirmed_title")
                     or old_row.get("suggested_title")
                     or old_row.get("raw_description"))
        source_type = old_row.get("source")

        log_lifecycle(
            action,
            ref_id=ref_id,
            task=task_desc,
            source_type=source_type,
            omnifocus_id=omnifocus_task_id,
        )

        # On confirmation: assemble work packet + trigger backtrace if needed
        if action == "confirm":
            import threading

            def _assemble_work_packet():
                """Build OmniFocus task note from archival passage context.

                Uses setRichText (atomic clear+replace) via the shared helper,
                so re-invocations are idempotent and won't duplicate content.
                Cycle-1 source-of-truth: pa_web.tasks.task_body holds the
                original archival passage text.
                """
                try:
                    passage_text = old_row.get("task_body") or ""
                    enrichment = old_row.get("enrichment") or None
                    if passage_text or enrichment:
                        _write_work_packet_note(
                            ref_id, omnifocus_task_id, passage_text,
                            enrichment=enrichment,
                        )
                except Exception:
                    pass  # Work packet assembly is best-effort

            # Fire work packet assembly in background (first-pass, uses current PACKET INFO)
            threading.Thread(target=_assemble_work_packet, daemon=True).start()

            # Deterministic gate: only dispatch MC if enrichment is missing/incomplete
            # OR if Rush was clicked. Cycle-1 enrichment lives in
            # pa_web.tasks.enrichment.packet_info; back-compat with legacy
            # archival-passage PACKET INFO sections.
            cy1_pi = ((old_row.get("enrichment") or {}).get("packet_info") or {})
            has_cycle1_enrichment = bool(
                cy1_pi.get("direct_action")
                and (cy1_pi.get("context_brief") or cy1_pi.get("resources"))
            )
            has_packet_info = "PACKET INFO" in old_text or has_cycle1_enrichment
            has_complete_enrichment = (
                has_cycle1_enrichment
                or (
                    "PACKET INFO" in old_text
                    and "Context brief:" in old_text
                    and "Resources:" in old_text
                )
            )
            should_dispatch_mc = rush or not has_complete_enrichment

            logger.info(
                "mc_work_packet_gate",
                ref_id=ref_id,
                has_packet_info=has_packet_info,
                has_complete_enrichment=has_complete_enrichment,
                rush=rush,
                should_dispatch=should_dispatch_mc,
            )

            if should_dispatch_mc:
                def _dispatch_mc_work_packet():
                    """Dispatch work packet assembly to the work-packet-assembler worker.

                    Worker executes the 4-step protocol: fetch_source_content,
                    backtrace_task, stage_resource (for real files), write_packet_info.
                    write_packet_info auto-triggers the reassemble endpoint.
                    """
                    WORKER_AGENT_ID = os.environ.get(
                        "WORK_PACKET_WORKER_AGENT_ID",
                        "agent-06a5b4a8-1e63-4cc6-a8bd-5a026518a763",
                    )

                    try:
                        # Build focused message for the worker agent
                        priority_line = "PRIORITY: rush\n" if rush else ""
                        message = (
                            f"{priority_line}"
                            f"Work packet assembly for ref_id {ref_id}. "
                            f"Execute the 4-step protocol from your persona: "
                            f"fetch_source_content, backtrace_task, stage_resource (real files only), "
                            f"write_packet_info. write_packet_info auto-triggers reassemble."
                        )

                        # Send via conversations endpoint (SSE, read full stream)
                        # Retry on 409 (MC busy with prior task) with exponential backoff
                        import time as _time
                        max_retries = 8
                        backoff_seconds = 15  # first retry in 15s, then 30s, 60s, 120s...
                        last_status = None

                        for attempt in range(max_retries + 1):
                            try:
                                with httpx.Client(timeout=600.0, follow_redirects=True) as c:
                                    resp = c.post(
                                        f"{LETTA_BASE_URL}/v1/agents/{WORKER_AGENT_ID}/messages/",
                                        json={"messages": [{"role": "user", "content": message}]},
                                    )
                                    last_status = resp.status_code
                                    if resp.status_code == 200:
                                        logger.info(
                                            "mc_work_packet_dispatched",
                                            ref_id=ref_id,
                                            rush=rush,
                                            attempts=attempt + 1,
                                        )
                                        return
                                    elif resp.status_code == 409 and attempt < max_retries:
                                        # MC busy with prior task — wait and retry
                                        wait = min(backoff_seconds * (2 ** attempt), 300)
                                        logger.info(
                                            "mc_work_packet_retry",
                                            ref_id=ref_id,
                                            attempt=attempt + 1,
                                            wait_seconds=wait,
                                        )
                                        _time.sleep(wait)
                                        continue
                                    else:
                                        logger.warning(
                                            "mc_work_packet_dispatch_failed",
                                            ref_id=ref_id,
                                            status=resp.status_code,
                                            rush=rush,
                                            attempts=attempt + 1,
                                        )
                                        return
                            except Exception as e:
                                if attempt < max_retries:
                                    _time.sleep(backoff_seconds * (2 ** attempt))
                                    continue
                                raise

                        # Exhausted retries
                        logger.warning(
                            "mc_work_packet_retry_exhausted",
                            ref_id=ref_id,
                            last_status=last_status,
                            rush=rush,
                        )
                    except Exception as e:
                        logger.warning(
                            "mc_work_packet_dispatch_error",
                            ref_id=ref_id,
                            error=str(e)[:200],
                        )

                threading.Thread(target=_dispatch_mc_work_packet, daemon=True).start()

        return jsonify({"status": "ok", "ref_id": ref_id, "action": action})
    except Exception as e:
        logger.error(
            "api_transition_task_error",
            ref_id=ref_id, error=str(e),
        )
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/<ref_id>/reassemble-work-packet', methods=['POST'])
def api_reassemble_work_packet(ref_id):
    """Re-assemble the OmniFocus work packet note from current PACKET INFO.

    Called by MC after it updates PACKET INFO via write_packet_info.
    Uses setRichText to atomically clear and replace the note with
    fresh segments based on the updated archival passage.

    Per-ref_id lock prevents races with the first-pass assembly thread.
    """
    try:
        # Cycle-1: read row from pa_web.tasks; task_body holds the archival
        # passage text that _write_work_packet_note expects.
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM pa_web.tasks WHERE ref_id = %s", (ref_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return jsonify({"error": f"Task {ref_id} not found"}), 404

        omnifocus_task_id = row.get("omnifocus_id")
        if not omnifocus_task_id:
            return jsonify({
                "status": "error",
                "error": f"Task {ref_id} has no OmniFocus ID (not confirmed?)",
            }), 400

        if (row.get("status") or "") != "confirmed":
            return jsonify({
                "status": "error",
                "error": f"Task {ref_id} is not in confirmed state",
            }), 400

        passage_text = row.get("task_body") or ""
        enrichment = row.get("enrichment") or None
        if not passage_text and not enrichment:
            return jsonify({
                "status": "error",
                "error": f"Task {ref_id} has no stored body or enrichment to reassemble from",
            }), 400

        # Re-assemble using shared helper (uses setRichText atomically)
        success = _write_work_packet_note(
            ref_id, omnifocus_task_id, passage_text, enrichment=enrichment,
        )

        if not success:
            return jsonify({
                "status": "error",
                "error": "OmniFocus bridge write failed",
            }), 500

        log_lifecycle(
            "reassemble-work-packet",
            ref_id=ref_id,
            omnifocus_id=omnifocus_task_id,
        )

        return jsonify({
            "status": "ok",
            "ref_id": ref_id,
            "omnifocus_task_id": omnifocus_task_id,
        })

    except Exception as e:
        logger.error("api_reassemble_work_packet_error", ref_id=ref_id, error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/merge', methods=['POST'])
def api_merge_tasks():
    """Merge multiple tasks into one parent.

    Cycle-1 lifecycle:
      - Each child gets status='merged' and merged_into=<parent_ref_id>.
        closed_at stays NULL (merge is NOT terminal per user spec; the
        parent carries the lifecycle from here).
      - A new parent row is INSERTed with status='extracted' so it
        appears in the triage queue for the user to confirm/reject.
    """
    try:
        data = request.get_json() or {}
        ref_ids = data.get('ref_ids', [])
        merged_description = data.get('merged_task_description', '')

        if len(ref_ids) < 2:
            return jsonify({"error": "At least 2 ref_ids required"}), 400
        if not merged_description:
            return jsonify({"error": "merged_task_description required"}), 400

        import uuid
        new_ref_id = uuid.uuid4().hex[:8]

        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                # Verify all children exist
                cur.execute(
                    "SELECT ref_id FROM pa_web.tasks WHERE ref_id = ANY(%s)",
                    (ref_ids,),
                )
                found = {r[0] for r in cur.fetchall()}
                missing = [r for r in ref_ids if r not in found]
                if missing:
                    return jsonify({
                        "error": f"Tasks not found: {', '.join(missing)}"
                    }), 404

                # Mark each child as merged into the new parent.
                # closed_at stays NULL (merge not terminal per user spec).
                cur.execute(
                    """UPDATE pa_web.tasks
                          SET status = 'merged',
                              merged_into = %s,
                              updated_at = NOW(),
                              migration_source = 'live'
                        WHERE ref_id = ANY(%s)""",
                    (new_ref_id, ref_ids),
                )

                # Create the new parent in extracted state so the user
                # can triage it from the sidebar.
                cur.execute(
                    """INSERT INTO pa_web.tasks (
                           ref_id, raw_description, suggested_title,
                           status, extracted_at, migration_source,
                           created_at, updated_at,
                           enrichment
                       ) VALUES (
                           %s, %s, %s, 'extracted', NOW(), 'live',
                           NOW(), NOW(),
                           %s::jsonb
                       )""",
                    (
                        new_ref_id, merged_description, merged_description,
                        json.dumps({"merged_from": ref_ids}),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        log_lifecycle(
            "merge",
            ref_id=new_ref_id,
            task=merged_description,
            merged_ids=ref_ids,
        )

        return jsonify({
            "status": "ok",
            "ref_id": new_ref_id,
            "merged_ids": ref_ids,
        })
    except Exception as e:
        logger.error("api_merge_tasks_error", error=str(e))
        return jsonify({"error": str(e)}), 500


def _normalize_of_tree(subfolders):
    """Convert OmniFocus MCP tree format to sidebar-friendly {id, name, type, children}."""
    nodes = []
    for item in subfolders:
        folder = item.get("folder", {})
        children = _normalize_of_tree(item.get("subfolders", []))
        # Add projects from this folder
        for p in item.get("projects", []):
            children.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "type": "project",
                "children": [],
            })
        nodes.append({
            "id": folder.get("id"),
            "name": folder.get("name"),
            "type": "folder",
            "children": children,
        })
    return nodes


@app.route('/api/tasks/omnifocus-tree', methods=['GET'])
def api_omnifocus_tree():
    """Get OmniFocus folder/project tree with projects."""
    try:
        result = call_omnifocus_bridge(
            "getFolderHierarchy", {"includeProjects": True},
        )
        raw = result.get("result", result) if isinstance(result, dict) else result
        subfolders = raw.get("subfolders", []) if isinstance(raw, dict) else []
        tree = _normalize_of_tree(subfolders)
        return jsonify({"tree": tree})
    except Exception as e:
        logger.error("api_omnifocus_tree_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/omnifocus-create', methods=['POST'])
def api_omnifocus_create():
    """Create an OmniFocus task with optional note containing full context."""
    try:
        data = request.get_json()
        name = data.get('name')
        project_id = data.get('projectId')
        note = data.get('note', '')

        if not name:
            return jsonify({"error": "name required"}), 400

        args = {"name": name}
        if project_id:
            args["projectId"] = project_id
        if note:
            args["note"] = note
        estimated = data.get('estimatedMinutes')
        if estimated:
            args["estimatedMinutes"] = int(estimated)

        result = call_omnifocus_bridge("createTask", args)
        # Response may be nested: {result: {id: ...}} or flat {id: ...}
        inner = result.get("result", result)
        task_id = inner.get("id", inner.get("taskId", ""))

        if not task_id:
            raise Exception(
                f"No task ID in OmniFocus response: {json.dumps(result)[:200]}"
            )

        return jsonify({"status": "ok", "omnifocus_task_id": task_id})
    except Exception as e:
        logger.error("api_omnifocus_create_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/widget-queue', methods=['POST'])
def api_widget_queue():
    """Proxy widget queue commands to the host bridge -> laptop SSH."""
    try:
        data = request.get_json()
        action = data.get('action')
        if not action:
            return jsonify({"error": "action required"}), 400

        resp = http_client.post(
            f"{OMNIFOCUS_BRIDGE_URL}/widget-queue",
            json=data,
            timeout=50.0,
        )
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        logger.error("api_widget_queue_error", error=str(e))
        return jsonify({"error": str(e)}), 500


# ── Gmail Drafts API (proxied via gws-bridge) ──
GWS_BRIDGE_TIMEOUT = 60  # gws-bridge can take 30-35s for filtered queries

FOLLOWUP_QUEUE = os.getenv(
    "FOLLOWUP_QUEUE",
    "/Volumes/main-drive/ai-PA/omnifocus-timer/logs/pending-followups.jsonl",
)


@app.route('/api/drafts', methods=['GET'])
def api_list_drafts():
    """List all follow-ups: Gmail drafts + pending follow-up queue."""
    gmail_drafts = []
    queue_items = []

    # 1. Gmail drafts — fetch ALL drafts
    try:
        with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
            resp = client.get(
                f"{GWS_BRIDGE_URL}/gmail/drafts",
                params={"maxResults": 50},
            )
            resp.raise_for_status()
            data = resp.json()
            for draft in data.get("drafts", []):
                if draft.get("error"):
                    continue
                names = draft.get("labelNames", [])
                # Determine follow-up type from labels
                if "Followup" in names:
                    draft["followup_type"] = "meeting"
                    draft["followup_icon"] = "meeting"
                    draft["followup_section"] = "followups"
                else:
                    draft["followup_type"] = "draft"
                    draft["followup_icon"] = "draft"
                    draft["followup_section"] = "drafts"
                draft["source"] = "gmail"
                gmail_drafts.append(draft)
    except Exception as e:
        logger.error("api_list_drafts_gmail_error", error=str(e))

    # 2. Follow-up queue (Slack, Docs, Email from task completions)
    try:
        if os.path.exists(FOLLOWUP_QUEUE):
            with open(FOLLOWUP_QUEUE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        if item.get("status") in ("dismissed", "sent"):
                            continue
                        # Map to a draft-like structure for the frontend
                        fu_type = item.get("type", "unknown")
                        item["followup_type"] = fu_type
                        item["followup_icon"] = {
                            "slack": "slack",
                            "docs_comment": "docs",
                            "email": "email",
                        }.get(fu_type, "email")
                        item["source"] = "queue"
                        item["followup_section"] = "followups"
                        # Map fields for card rendering compatibility
                        item["subject"] = item.get("task_description", "")
                        item["to"] = item.get("from_person", "")
                        queue_items.append(item)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error("api_list_drafts_queue_error", error=str(e))

    # Deduplicate: remove Gmail drafts that have a scheduled tracking entry
    scheduled_draft_ids = set()
    for item in queue_items:
        if item.get("status") == "scheduled" and item.get("gmail_draft_id"):
            scheduled_draft_ids.add(item["gmail_draft_id"])
    gmail_draft_ids = set(d.get("id") for d in gmail_drafts)
    gmail_drafts = [d for d in gmail_drafts if d.get("id") not in scheduled_draft_ids]

    # Reverse check: dismiss scheduled tracking entries whose Gmail draft no longer exists
    stale_tracking = []
    for item in queue_items:
        if (item.get("status") == "scheduled"
                and item.get("gmail_draft_id")
                and item["gmail_draft_id"] not in gmail_draft_ids):
            stale_tracking.append(item["id"])
    if stale_tracking:
        for stale_id in stale_tracking:
            _update_followup_status(stale_id, "dismissed")
        queue_items = [q for q in queue_items if q["id"] not in stale_tracking]

    all_items = queue_items + gmail_drafts
    return jsonify({"drafts": all_items})


@app.route('/api/drafts/<draft_id>', methods=['GET'])
def api_get_draft(draft_id):
    """Get a single draft with full body."""
    try:
        with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
            resp = client.get(f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}")
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_get_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>', methods=['PUT'])
def api_update_draft(draft_id):
    """Update a draft's to, cc, subject, or body."""
    try:
        data = request.get_json()
        with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
            resp = client.put(
                f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}",
                json=data,
            )
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_update_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>/send', methods=['POST'])
def api_send_draft(draft_id):
    """Send a draft."""
    try:
        with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
            resp = client.post(f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}/send")
            resp.raise_for_status()
            # Clean up any scheduled tracking entry
            _update_followup_status(f"sched-{draft_id}", "sent")
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found (may already be sent)"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_send_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/drafts/<draft_id>', methods=['DELETE'])
def api_delete_draft(draft_id):
    """Delete (discard) a draft or follow-up queue item."""
    # Check if it's a follow-up queue item (fu-xxx format)
    if draft_id.startswith("fu-"):
        return _dismiss_followup(draft_id)

    try:
        with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
            resp = client.delete(f"{GWS_BRIDGE_URL}/gmail/drafts/{draft_id}")
            resp.raise_for_status()
            return jsonify(resp.json())
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"error": f"Bridge error: {status}"}), 502
    except Exception as e:
        logger.error("api_delete_draft_error", error=str(e))
        return jsonify({"error": str(e)}), 502


@app.route('/api/followups/<followup_id>/send', methods=['POST'])
def api_send_followup(followup_id):
    """Dispatch a follow-up queue item (Slack reply, Docs comment, etc.)."""
    try:
        data = request.get_json() or {}
        message = data.get("message", "")

        # Find the follow-up in the queue
        item = _find_followup(followup_id)
        if not item:
            return jsonify({"error": "Follow-up not found"}), 404

        routing = item.get("routing", {})
        fu_type = item.get("type", "")
        final_message = message or item.get("draft_message", "")

        if fu_type == "slack":
            # Post Slack threaded reply as the user (not the bot)
            slack_token = os.getenv("SLACK_USER_TOKEN") or os.getenv("SLACK_BOT_TOKEN", "")
            if not slack_token:
                return jsonify({"error": "No Slack token configured"}), 500

            # Convert @username mentions to Slack <@USERID> format
            final_message = _resolve_slack_mentions(final_message, slack_token)

            slack_resp = http_client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {slack_token}"},
                json={
                    "channel": routing.get("channel", ""),
                    "thread_ts": routing.get("thread_ts", ""),
                    "text": final_message,
                },
            )
            slack_data = slack_resp.json()
            if not slack_data.get("ok"):
                return jsonify({"error": f"Slack error: {slack_data.get('error', '?')}"}), 500
            _mark_followup_sent(followup_id)
            return jsonify({"status": "sent", "channel": routing.get("channel")})

        elif fu_type == "docs_comment":
            # Reply to Google Docs comment via gws bridge
            reply_params = routing.get("reply_params", {})
            with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
                resp = client.post(
                    f"{GWS_BRIDGE_URL}/drive/replies/create",
                    json={**reply_params, "content": final_message},
                )
                resp.raise_for_status()
            # Reply only — resolve is a separate action via /resolve endpoint
            _mark_followup_sent(followup_id)
            return jsonify({"status": "sent"})

        elif fu_type == "email":
            # Create Gmail draft reply via gws bridge
            message_id = routing.get("message_id", "")
            if not message_id:
                return jsonify({"error": "No message_id in routing"}), 400

            import base64
            from email.mime.text import MIMEText

            with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
                # Get original message headers for reply
                orig_resp = client.get(
                    f"{GWS_BRIDGE_URL}/gmail/messages/{message_id}",
                    params={"format": "metadata"},
                )
                if orig_resp.status_code == 200:
                    orig = orig_resp.json()
                    headers_list = orig.get("payload", {}).get("headers", [])
                    headers = {h["name"]: h["value"] for h in headers_list}
                    thread_id = orig.get("threadId", "")
                else:
                    headers = {}
                    thread_id = ""

                subject = headers.get("Subject", "")
                if subject and not subject.startswith("Re:"):
                    subject = f"Re: {subject}"
                reply_to = headers.get("From", item.get("from_person", ""))
                orig_msg_id_header = headers.get("Message-ID", "")

                mime = MIMEText(final_message)
                mime["To"] = reply_to
                mime["Subject"] = subject
                if orig_msg_id_header:
                    mime["In-Reply-To"] = orig_msg_id_header
                    mime["References"] = orig_msg_id_header

                raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

                # Create draft via gws bridge proxy to Gmail API
                draft_resp = client.post(
                    f"{GWS_BRIDGE_URL}/gmail/drafts",
                    json={"message": {"raw": raw, "threadId": thread_id}},
                )
                if draft_resp.status_code >= 400:
                    return jsonify({
                        "error": f"Draft creation failed: {draft_resp.text[:200]}"
                    }), 500

            _mark_followup_sent(followup_id)
            return jsonify({"status": "drafted", "detail": "Gmail draft reply created"})

        else:
            return jsonify({"error": f"Unknown follow-up type: {fu_type}"}), 400

    except Exception as e:
        logger.error("api_send_followup_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route('/api/followups/<followup_id>/resolve', methods=['POST'])
def api_resolve_followup(followup_id):
    """Resolve a Google Docs comment without replying."""
    try:
        item = _find_followup(followup_id)
        if not item:
            return jsonify({"error": "Follow-up not found"}), 404

        routing = item.get("routing", {})
        resolve_params = routing.get("resolve_params", {})
        if not resolve_params:
            return jsonify({"error": "No resolve params in routing"}), 400

        with httpx.Client(timeout=GWS_BRIDGE_TIMEOUT) as client:
            client.patch(
                f"{GWS_BRIDGE_URL}/drive/comments/update",
                json={**resolve_params, "resolved": True},
            )

        _mark_followup_sent(followup_id)
        return jsonify({"status": "resolved"})

    except Exception as e:
        logger.error("api_resolve_followup_error", error=str(e))
        return jsonify({"error": str(e)}), 500


def _find_followup(followup_id):
    """Find a follow-up in the queue by ID."""
    if not os.path.exists(FOLLOWUP_QUEUE):
        return None
    with open(FOLLOWUP_QUEUE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if item.get("id") == followup_id:
                    return item
            except json.JSONDecodeError:
                continue
    return None


def _mark_followup_sent(followup_id):
    """Mark a follow-up as sent in the queue file."""
    _update_followup_status(followup_id, "sent")
    item = _find_followup(followup_id)
    log_lifecycle(
        "followup_sent",
        followup_id=followup_id,
        type=item.get("type") if item else None,
        ref_id=item.get("ref_id") if item else None,
    )


def _dismiss_followup(followup_id):
    """Mark a follow-up as dismissed."""
    _update_followup_status(followup_id, "dismissed")
    log_lifecycle("followup_dismissed", followup_id=followup_id)
    return jsonify({"status": "dismissed"})


@app.route('/api/followups/<followup_id>', methods=['PATCH'])
def api_update_followup(followup_id):
    """Update a follow-up queue item (e.g., draft_message)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    item = _find_followup(followup_id)
    if not item:
        return jsonify({"error": "Follow-up not found"}), 404

    _update_followup_status(followup_id, item.get("status", "pending"), data)
    return jsonify({"status": "ok", "id": followup_id})


def _resolve_slack_mentions(text, token):
    """Convert @username mentions to Slack <@USERID> format."""
    import re as _re
    mention_pattern = _re.compile(r'@(\w+)')
    mentions = mention_pattern.findall(text)
    if not mentions:
        return text

    # Build a username → user_id map by fetching the workspace user list (cached)
    if not hasattr(_resolve_slack_mentions, '_cache'):
        _resolve_slack_mentions._cache = {}
        _resolve_slack_mentions._cache_time = 0

    import time
    now = time.time()
    cache = _resolve_slack_mentions._cache
    if now - _resolve_slack_mentions._cache_time > 3600 or not cache:
        try:
            resp = http_client.get(
                "https://slack.com/api/users.list",
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": 500},
            )
            data = resp.json()
            if data.get("ok"):
                for member in data.get("members", []):
                    name = member.get("name", "").lower()
                    display = (member.get("profile", {}).get("display_name") or "").lower()
                    real = (member.get("real_name") or "").lower()
                    uid = member["id"]
                    if name:
                        cache[name] = uid
                    if display:
                        cache[display] = uid
                    # Also map first.last and first_last patterns
                    if real:
                        parts = real.split()
                        if len(parts) >= 2:
                            cache[parts[0].lower()] = uid  # first name only
                            cache[f"{parts[0]}{parts[-1]}".lower()] = uid  # firstlast
                _resolve_slack_mentions._cache_time = now
        except Exception:
            pass

    def replace_mention(match):
        username = match.group(1).lower()
        uid = cache.get(username)
        return f"<@{uid}>" if uid else match.group(0)

    return mention_pattern.sub(replace_mention, text)


@app.route('/api/followups/<followup_id>/unschedule', methods=['POST'])
def api_unschedule_followup(followup_id):
    """Cancel a scheduled follow-up, reverting to pending."""
    item = _find_followup(followup_id)
    if not item:
        return jsonify({"error": "Follow-up not found"}), 404

    # Revert to pending — item moves from Scheduled section back to active list
    _update_followup_status(followup_id, "pending", {"scheduled_at": None})
    log_lifecycle("followup_unscheduled", followup_id=followup_id)

    # TODO: also cancel the scheduler-service job if one was created

    return jsonify({"status": "unscheduled"})


def _update_followup_status(followup_id, new_status, extra_fields=None):
    """Update a follow-up's status in the JSONL queue."""
    if not os.path.exists(FOLLOWUP_QUEUE):
        return
    lines = []
    with open(FOLLOWUP_QUEUE, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
                if item.get("id") == followup_id:
                    item["status"] = new_status
                    if extra_fields:
                        item.update(extra_fields)
                lines.append(json.dumps(item) + "\n")
            except json.JSONDecodeError:
                lines.append(line)
    with open(FOLLOWUP_QUEUE, "w") as f:
        f.writelines(lines)


# ── Schedule Send ──

SCHEDULER_SERVICE_URL = os.getenv(
    "SCHEDULER_SERVICE_URL", "http://scheduler-service:8087"
)
SCHEDULER_API_KEY = os.getenv("SCHEDULER_API_KEY", "")


@app.route('/api/followups/<followup_id>/schedule', methods=['POST'])
def api_schedule_followup(followup_id):
    """Schedule a follow-up queue item for future sending."""
    data = request.get_json()
    send_at = data.get("send_at")
    if not send_at:
        return jsonify({"error": "send_at required"}), 400

    item = _find_followup(followup_id)
    if not item:
        return jsonify({"error": "Follow-up not found"}), 404

    # Store schedule in the queue entry
    _update_followup_status(followup_id, "scheduled", {"scheduled_at": send_at})

    # Create a scheduler-service job to fire at the scheduled time
    try:
        _create_schedule_job(
            name=f"followup-{followup_id}",
            send_at=send_at,
            callback_url=f"http://pa-web-ui:5200/api/followups/{followup_id}/send",
            callback_body={"message": item.get("draft_message", "")},
        )
    except Exception as e:
        logger.error("schedule_followup_job_error", error=str(e))
        # Schedule is stored even if job creation fails — can retry

    log_lifecycle(
        "followup_scheduled",
        followup_id=followup_id,
        type=item.get("type"),
        ref_id=item.get("ref_id"),
        send_at=send_at,
    )
    return jsonify({"status": "scheduled", "send_at": send_at})


@app.route('/api/drafts/<draft_id>/schedule', methods=['POST'])
def api_schedule_draft(draft_id):
    """Schedule a Gmail draft for future sending."""
    data = request.get_json()
    send_at = data.get("send_at")
    if not send_at:
        return jsonify({"error": "send_at required"}), 400

    # Store tracking entry in follow-up queue so Scheduled section can display it
    from datetime import datetime as dt
    entry = {
        "id": f"sched-{draft_id}",
        "type": "email",
        "status": "scheduled",
        "scheduled_at": send_at,
        "created_at": dt.utcnow().isoformat() + "Z",
        "source": "gmail-scheduled",
        "gmail_draft_id": draft_id,
        "subject": data.get("subject", ""),
        "to": data.get("to", ""),
        "followup_type": data.get("followup_type", "draft"),
        "followup_icon": data.get("followup_icon", "draft"),
        "followup_section": "drafts",
    }
    try:
        with open(FOLLOWUP_QUEUE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error("schedule_draft_queue_write_error", error=str(e))

    # Create scheduler job
    try:
        _create_schedule_job(
            name=f"draft-{draft_id}",
            send_at=send_at,
            callback_url=f"http://pa-web-ui:5200/api/drafts/{draft_id}/send",
            callback_body={},
        )
    except Exception as e:
        logger.error("schedule_draft_job_error", error=str(e))
        # Entry is stored even if job creation fails

    log_lifecycle("draft_scheduled", draft_id=draft_id, send_at=send_at,
                  subject=data.get("subject"))
    return jsonify({"status": "scheduled", "send_at": send_at})


def _create_schedule_job(name, send_at, callback_url, callback_body):
    """Create a one-shot scheduler-service job with HTTP action."""
    headers = {}
    if SCHEDULER_API_KEY:
        headers["X-API-Key"] = SCHEDULER_API_KEY

    job_payload = {
        "title": f"Scheduled send: {name}",
        "description": f"Auto-send {name} at {send_at}",
        "created_by": "pa-web-ui",
        "category": "follow_up",
        "schedule": {
            "type": "one_off",
            "expression": {"run_at": send_at},
            "next_run_at": send_at,
        },
        "actions": [
            {
                "action_type": "http",
                "config": {
                    "url": callback_url,
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "json": callback_body,
                    "timeout_seconds": 60,
                },
            }
        ],
    }

    resp = httpx.post(
        f"{SCHEDULER_SERVICE_URL}/v1/jobs",
        json=job_payload,
        headers=headers,
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5200"))
    ensure_pa_web_schema()
    _start_phase2_backfill_thread()
    logger.info("pa_web_ui_starting", port=port)
    # threaded=True enables concurrent request handling for SSE streams
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
