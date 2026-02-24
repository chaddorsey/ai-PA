#!/usr/bin/env python3
"""
Health check and API server for Slackbot.

Provides:
- GET /health — Docker health check endpoint
- POST /api/notify — Agent outbound notification endpoint
"""

import os
import sys
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default owner Slack user ID — used when no user_slack_id is provided
OWNER_SLACK_USER_ID = os.getenv("OWNER_SLACK_USER_ID", "")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check and API endpoints."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self.send_health_response()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/api/notify':
            self._handle_notify()
        else:
            self.send_error(404, "Not Found")

    def _handle_notify(self):
        """
        Handle POST /api/notify — agent outbound notification.

        Accepts JSON body with structured notification data, posts a Slack DM
        with interactive Block Kit buttons, and stores a pending_agent_reply
        record in Supabase for reply routing.
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_json(400, {"ok": False, "error": "Empty request body"})
                return

            body = json.loads(self.rfile.read(content_length))

            text = body.get("text", "")
            agent_id = body.get("originating_agent_id", "")
            reply_context = body.get("reply_context", {})
            user_slack_id = body.get("user_slack_id", "") or OWNER_SLACK_USER_ID

            if not text:
                self._send_json(400, {"ok": False, "error": "text is required"})
                return
            if not agent_id:
                self._send_json(400, {"ok": False, "error": "originating_agent_id is required"})
                return
            if not user_slack_id:
                self._send_json(400, {"ok": False, "error": "No user_slack_id provided and OWNER_SLACK_USER_ID not set"})
                return

            # Build notification_data from the request
            notification_data = {
                "text": text,
                "detail": body.get("detail", ""),
                "suggested_reply": body.get("suggested_reply", ""),
                "footer": body.get("footer", ""),
            }

            # Create Slack client
            from slack_sdk import WebClient
            slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
            if not slack_token:
                self._send_json(500, {"ok": False, "error": "SLACK_BOT_TOKEN not configured"})
                return

            client = WebClient(token=slack_token)

            # Open DM channel with user
            dm_resp = client.conversations_open(users=[user_slack_id])
            if not dm_resp.get("ok"):
                self._send_json(500, {"ok": False, "error": f"Failed to open DM: {dm_resp.get('error')}"})
                return

            channel_id = dm_resp["channel"]["id"]

            # Store pending reply in Supabase first (need the ID for button values)
            from services.pending_replies import create_pending_reply
            # Use a placeholder thread_ts; we'll update after posting
            import uuid as uuid_mod
            temp_id = str(uuid_mod.uuid4())

            pending_id = create_pending_reply(
                thread_ts=temp_id,  # temporary, updated after posting
                channel_id=channel_id,
                agent_id=agent_id,
                reply_context=reply_context,
                notification_data=notification_data,
            )

            if not pending_id:
                self._send_json(500, {"ok": False, "error": "Failed to store pending reply"})
                return

            # Render Block Kit blocks
            from adapters.notification_blocks import (
                render_notification_blocks,
                render_notification_fallback_text,
            )
            blocks = render_notification_blocks(notification_data, pending_id)
            fallback = render_notification_fallback_text(notification_data)

            # Post the notification message
            post_resp = client.chat_postMessage(
                channel=channel_id,
                text=fallback,
                blocks=blocks,
            )

            if not post_resp.get("ok"):
                self._send_json(500, {"ok": False, "error": f"Failed to post message: {post_resp.get('error')}"})
                return

            thread_ts = post_resp["ts"]

            # Update the pending reply with the real thread_ts
            import requests as http_requests
            supabase_url = os.getenv("SUPABASE_URL", "")
            supabase_key = os.getenv("SUPABASE_SERVICE_KEY", "")
            if supabase_url and supabase_key:
                http_requests.patch(
                    f"{supabase_url}/pending_agent_replies",
                    params={"id": f"eq.{pending_id}"},
                    json={"thread_ts": thread_ts},
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    timeout=5.0,
                )

            logger.info(
                "Notification posted: channel=%s thread_ts=%s agent=%s pending_id=%s",
                channel_id, thread_ts, agent_id, pending_id,
            )

            self._send_json(200, {
                "ok": True,
                "thread_ts": thread_ts,
                "channel_id": channel_id,
                "pending_reply_id": pending_id,
            })

        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Invalid JSON"})
        except Exception as e:
            logger.error("Error in /api/notify: %s", e, exc_info=True)
            self._send_json(500, {"ok": False, "error": str(e)})

    def send_health_response(self):
        """Send health check response."""
        try:
            required_vars = ['SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN', 'LETTA_AGENT_ID']
            missing_vars = [var for var in required_vars if not os.getenv(var)]

            if missing_vars:
                self.send_error(503, f"Missing required environment variables: {', '.join(missing_vars)}")
                return

            health_status = {
                "status": "healthy",
                "timestamp": time.time(),
                "service": "slackbot-mcp",
                "version": "1.0.0"
            }

            self._send_json(200, health_status)

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.send_error(503, f"Health check failed: {str(e)}")

    def _send_json(self, status_code: int, data: dict):
        """Send a JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """Override to reduce log noise from health checks."""
        # Log API calls but not health checks
        if self.path != '/health':
            logger.info(format, *args)

def start_health_server(port=8081):
    """Start the health check HTTP server."""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server started on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start health check server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Start health check server in a separate thread
    health_port = int(os.getenv('HEALTH_CHECK_PORT', '8081'))
    health_thread = Thread(target=start_health_server, args=(health_port,), daemon=True)
    health_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Health check server stopped")
        sys.exit(0)
