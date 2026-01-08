"""PA Web UI - Flask application for chat interface."""

import json
import os
import time
from typing import Generator

import httpx
import structlog
from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

# Retry configuration for transient errors
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = {502, 503, 504}

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
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

# HTTP client for backend calls
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


@app.route("/stream", methods=["POST"])
def stream():
    """
    SSE endpoint for chat messages.

    Receives a message, routes it to the appropriate agent,
    and streams the response back via Server-Sent Events.
    """
    data = request.get_json(force=True, silent=True) or {}
    message = data.get("message", "")
    agent_id = data.get("agent_id")
    session_id = data.get("session_id")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    if not session_id:
        return jsonify({"error": "Session ID is required"}), 400

    logger.info(
        "stream_request",
        session_id=session_id,
        agent_id=agent_id,
        message_length=len(message),
    )

    def generate() -> Generator[str, None, None]:
        """Generate SSE events from Letta response."""
        try:
            # Step 1: Route the message to get the appropriate agent
            route_response = http_client.post(
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

            logger.info(
                "routed_message",
                session_id=session_id,
                selected_agent_id=selected_agent_id,
                routing_method=route_data.get("routing_method"),
            )

            # Send routing event to frontend
            yield f"data: {json.dumps({'type': 'routing', 'agent_id': selected_agent_id, 'agent_name': agent_name})}\n\n"

            # Step 2: Send message to Letta agent (with retry for transient errors)
            letta_url = f"{LETTA_BASE_URL}/v1/agents/{selected_agent_id}/messages"
            letta_payload = {"messages": [{"role": "user", "content": message}]}
            letta_response = None
            last_error = None

            for attempt in range(MAX_RETRIES):
                try:
                    letta_response = http_client.post(
                        letta_url,
                        json=letta_payload,
                        timeout=120.0,
                    )

                    if letta_response.status_code == 200:
                        break  # Success

                    if letta_response.status_code in RETRYABLE_STATUS_CODES:
                        last_error = f"Letta returned {letta_response.status_code}"
                        logger.warning(
                            "letta_transient_error",
                            status_code=letta_response.status_code,
                            attempt=attempt + 1,
                            max_retries=MAX_RETRIES,
                            response_text=letta_response.text[:500] if letta_response.text else None,
                        )
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                            continue
                    else:
                        # Non-retryable error
                        last_error = f"Letta returned {letta_response.status_code}"
                        logger.error(
                            "letta_error",
                            status_code=letta_response.status_code,
                            response_text=letta_response.text[:500] if letta_response.text else None,
                        )
                        break

                except httpx.TimeoutException as e:
                    last_error = f"Letta timeout: {str(e)}"
                    logger.warning(
                        "letta_timeout",
                        attempt=attempt + 1,
                        max_retries=MAX_RETRIES,
                        error=str(e),
                    )
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                        continue

            if letta_response is None or letta_response.status_code != 200:
                error_msg = last_error or "Failed to get response from Letta"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return

            # Parse Letta JSON response
            letta_data = letta_response.json()

            # Extract assistant messages from response
            for msg in letta_data.get("messages", []):
                if msg.get("message_type") == "assistant_message":
                    content = msg.get("content", "")
                    if content:
                        yield f"data: {json.dumps({'type': 'text', 'content': content})}\n\n"

                elif msg.get("message_type") == "tool_call_message":
                    tool_call = msg.get("tool_call", {})
                    tool_name = tool_call.get("name", "tool")
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

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
    app.run(host="0.0.0.0", port=port, debug=False)
