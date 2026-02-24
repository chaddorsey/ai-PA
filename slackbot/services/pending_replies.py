"""
Pending agent replies service.

Manages the pending_agent_replies table in Supabase for tracking
agent-initiated notifications and routing user replies back to the
originating agent.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TABLE = "pending_agent_replies"

logger = logging.getLogger(__name__)


def _headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def create_pending_reply(
    thread_ts: str,
    channel_id: str,
    agent_id: str,
    reply_context: Dict[str, Any],
    notification_data: Dict[str, Any],
) -> Optional[str]:
    """
    Store a pending agent reply record in Supabase.

    Returns the row ID (UUID) on success, None on failure.
    """
    try:
        url = f"{SUPABASE_URL}/{TABLE}"
        body = {
            "thread_ts": thread_ts,
            "channel_id": channel_id,
            "agent_id": agent_id,
            "reply_context": reply_context,
            "notification_data": notification_data,
        }
        resp = requests.post(
            url,
            json=body,
            headers={**_headers(), "Prefer": "return=representation"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            row_id = data[0].get("id")
            logger.info("Created pending_agent_reply %s for thread %s", row_id, thread_ts)
            return row_id
        return None
    except Exception as e:
        logger.error("Failed to create pending_agent_reply: %s", e)
        return None


def get_pending_reply_by_thread(thread_ts: str) -> Optional[Dict[str, Any]]:
    """Look up a pending reply by Slack thread_ts."""
    try:
        url = f"{SUPABASE_URL}/{TABLE}"
        params = {
            "thread_ts": f"eq.{thread_ts}",
            "status": "eq.pending",
            "limit": "1",
        }
        resp = requests.get(url, params=params, headers=_headers(), timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        logger.error("Failed to look up pending_agent_reply by thread: %s", e)
        return None


def get_pending_reply_by_id(reply_id: str) -> Optional[Dict[str, Any]]:
    """Look up a pending reply by its UUID."""
    try:
        url = f"{SUPABASE_URL}/{TABLE}"
        params = {"id": f"eq.{reply_id}", "limit": "1"}
        resp = requests.get(url, params=params, headers=_headers(), timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        logger.error("Failed to look up pending_agent_reply by id: %s", e)
        return None


def resolve_pending_reply(reply_id: str) -> bool:
    """Mark a pending reply as resolved."""
    try:
        url = f"{SUPABASE_URL}/{TABLE}"
        params = {"id": f"eq.{reply_id}"}
        body = {
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = requests.patch(
            url,
            params=params,
            json=body,
            headers={**_headers(), "Prefer": "return=minimal"},
            timeout=5.0,
        )
        resp.raise_for_status()
        logger.info("Resolved pending_agent_reply %s", reply_id)
        return True
    except Exception as e:
        logger.error("Failed to resolve pending_agent_reply: %s", e)
        return False
