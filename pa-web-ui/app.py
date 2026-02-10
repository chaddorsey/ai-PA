"""PA Web UI - Flask application for chat interface."""

import json
import os
import queue
import re
import threading
import time
from typing import Generator

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

app = Flask(__name__)
CORS(app)

# Configuration from environment
ROUTING_HANDLER_URL = os.getenv(
    "PA_ROUTING_HANDLER_URL", "http://pa-routing-handler:5201"
)
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283")

# Database configuration
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from contextlib import contextmanager

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@supabase-db:5432/postgres"
)


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
) -> None:
    """Save a conversation message to the database."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.conversations
                    (session_id, role, message, agent_id, agent_name, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        role,
                        message,
                        agent_id or "",
                        agent_name or "",
                        json.dumps({"request_id": request_id}) if request_id else None,
                        datetime.utcnow(),
                    ),
                )
        logger.info("conversation_saved", session_id=session_id, role=role)
    except Exception as e:
        logger.error("conversation_save_failed", error=str(e))


def get_conversation_history(session_id: str, limit: int = 100) -> list:
    """Get conversation history for a session."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get most recent N messages, then order them chronologically for display
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
    conversation_id: int = None,
) -> None:
    """Save user feedback on a response (thumbs up/down or agent correction)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pa_web.response_feedback
                    (session_id, request_id, feedback_type, actual_agent_id, actual_agent_name,
                     intended_agent_id, intended_agent_name, conversation_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        request_id,
                        feedback_type,
                        actual_agent_id or "",
                        actual_agent_name or "",
                        intended_agent_id,
                        intended_agent_name,
                        conversation_id,
                        datetime.utcnow(),
                    ),
                )
        logger.info("response_feedback_saved", session_id=session_id, request_id=request_id, feedback_type=feedback_type)
    except Exception as e:
        logger.error("response_feedback_save_failed", error=str(e))


# HTTP client for short requests (agent list, config, etc.)
# Note: Streaming requests create their own clients to avoid concurrency issues
http_client = httpx.Client(timeout=30.0)


@app.route("/")
def index():
    """Main chat interface."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "pa-web-ui"})


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


@app.route("/api/conversations/<session_id>")
def get_conversations(session_id):
    """Get conversation history for a session."""
    try:
        limit = request.args.get("limit", 100, type=int)
        history = get_conversation_history(session_id, limit=limit)
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

    save_response_feedback(
        session_id=session_id,
        request_id=request_id,
        feedback_type=feedback_type,
        actual_agent_id=data.get("actual_agent_id"),
        actual_agent_name=data.get("actual_agent_name"),
        intended_agent_id=data.get("intended_agent_id"),
        intended_agent_name=data.get("intended_agent_name"),
        conversation_id=data.get("conversation_id"),
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

    if not message:
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

            letta_payload = {"messages": [{"role": "user", "content": augmented_message}]}
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5200"))
    logger.info("pa_web_ui_starting", port=port)
    # threaded=True enables concurrent request handling for SSE streams
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
