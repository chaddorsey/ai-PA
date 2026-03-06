"""
Direct scheduling orchestrator client.

Calls the scheduling-orchestrator-api HTTP service directly,
bypassing Letta LLM inference for ~10x faster responses.

Handles:
- Participant name → email resolution via Letta identities
- Default context_json construction (timeframe, timezone)
- Orchestrator HTTP call
- Result formatting for proposal parsing
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from ai.identity import _get_identities, _find_property

logger = logging.getLogger(__name__)

ORCHESTRATOR_URL = os.getenv(
    "SCHEDULING_ORCHESTRATOR_URL", "http://scheduling-orchestrator-api:8095"
).rstrip("/")
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://letta:8283").rstrip("/")

# Scheduling keyword patterns for auto-detection in DMs
_SCHEDULING_PATTERNS = [
    r"\bschedule\b.*\b(?:meeting|call|sync|session|time)\b",
    r"\bfind\b.*\b(?:time|slot|opening|availability|min|minutes|hour)\b",
    r"\bfind\b.*\b(?:with)\b",  # "find 30 min with Alex"
    r"\bwhen\s+(?:can|could|should)\b.*\bmeet\b",  # "when can Leslie and I meet"
    r"\bset\s+up\b.*\b(?:meeting|call|sync)\b",
    r"\bbook\b.*\b(?:meeting|call|time|slot)\b",
    r"\bblock\s+(?:off|out)\b.*\b(?:time|calendar)\b",
    r"\breschedule\b",
    r"\bfind\s+(?:a\s+)?(?:new\s+)?time\b",
    r"\bavailability\b.*\bfor\b",
    r"\bcalendar\b.*\b(?:check|open|free|available)\b",
    r"\bmeeting\b.*\bwith\b.*\b(?:next|this|tomorrow|monday|tuesday|wednesday|thursday|friday)\b",
    r"\b\d+\s*(?:min|minute|hour|hr)\b.*\bwith\b",  # "30 min with Alex"
    r"\bmeet\b.*\bfor\b.*\b(?:min|minute|hour|hr)\b",  # "meet for 30 minutes"
    r"\bmeet\b.*\b(?:next|this)\s+(?:week|monday|tuesday|wednesday|thursday|friday)\b",  # "meet next week"
]
_SCHEDULING_RE = re.compile("|".join(_SCHEDULING_PATTERNS), re.IGNORECASE)

# Phrases that look like scheduling but aren't (queries, status checks)
_NON_SCHEDULING_PATTERNS = [
    r"\bwhat(?:'s| is)\b.*\bon\s+my\s+calendar\b",
    r"\bwhat\s+do\s+i\s+have\b",
    r"\bshow\s+(?:me\s+)?my\b.*\bcalendar\b",
    r"\blist\b.*\b(?:meetings|events|appointments)\b",
    r"\bwhat\b.*\b(?:meetings|events)\b.*\btoday\b",
    r"\bdo\s+i\s+have\b.*\b(?:meeting|event|anything)\b",
]
_NON_SCHEDULING_RE = re.compile("|".join(_NON_SCHEDULING_PATTERNS), re.IGNORECASE)


def is_scheduling_request(text: str) -> bool:
    """Detect if a message is a scheduling request suitable for direct orchestration."""
    if not text or len(text) < 10:
        return False
    # Exclude calendar queries (checking what's on the calendar)
    if _NON_SCHEDULING_RE.search(text):
        return False
    return bool(_SCHEDULING_RE.search(text))


def resolve_user_email(slack_user_id: str) -> Optional[str]:
    """Resolve a Slack user ID to their email via Letta identities."""
    identities = _get_identities()
    for identity in identities:
        if _find_property(identity, "slack_id") == slack_user_id:
            return identity.get("identifier_key")
    return None


def resolve_participants_from_utterance(utterance: str) -> List[str]:
    """
    Extract participant names from utterance and resolve to emails.

    Looks for patterns like "with Alex and Priya", "meeting with Dan",
    then matches against Letta identity names/colloquial names.

    Returns list of resolved email addresses.
    """
    identities = _get_identities()
    if not identities:
        return []

    # Build name → email index from identities
    name_to_email: Dict[str, str] = {}
    for identity in identities:
        email = identity.get("identifier_key", "")
        if not email:
            continue
        # Full name
        full_name = identity.get("name", "").strip()
        if full_name:
            name_to_email[full_name.lower()] = email
            # First name
            first = full_name.split()[0]
            if first and len(first) > 1:
                # Only add if unique first name (avoid ambiguity)
                name_to_email.setdefault(first.lower(), email)
        # Colloquial name
        colloquial = _find_property(identity, "colloquial_name")
        if colloquial and colloquial.strip():
            name_to_email[colloquial.strip().lower()] = email

    # Extract names from utterance using "with X and Y" pattern
    # Also handle "X and Y's meeting", "X, Y, and Z"
    utterance_lower = utterance.lower()
    resolved = []

    for name, email in name_to_email.items():
        # Check if the name appears as a word boundary in the utterance
        if re.search(r'\b' + re.escape(name) + r'\b', utterance_lower):
            if email not in resolved:
                resolved.append(email)

    return resolved


def build_context_json(
    participant_emails: List[str],
    timezone: str = "America/New_York",
    days_ahead: int = 14,
) -> str:
    """Build context_json with default timeframe and participant metadata."""
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Build participant list with metadata from identities
    identities = _get_identities()
    email_to_identity = {
        id_.get("identifier_key", "").lower(): id_
        for id_ in identities
        if id_.get("identifier_key")
    }

    participants = []
    for email in participant_emails:
        identity = email_to_identity.get(email.lower(), {})
        name = identity.get("name", email.split("@")[0])
        colloquial = _find_property(identity, "colloquial_name") if identity else None
        work_hours = _find_property(identity, "work_hours") if identity else None

        entry = {
            "id": email.split("@")[0],
            "email": email,
            "name": colloquial or name,
        }
        if work_hours:
            entry["work_hours"] = work_hours
        participants.append(entry)

    context = {
        "timeframe": {
            "from": today,
            "to": end_date,
            "tz": timezone,
        },
        "participants": participants,
    }
    return json.dumps(context)


def call_orchestrator(
    utterance: str,
    user_email: str,
    participant_ids: Optional[List[str]] = None,
    context_json: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call the scheduling orchestrator directly via HTTP.

    Returns the orchestrator result dict (same format as the Letta tool return).
    """
    # Resolve participants from utterance if not provided
    if participant_ids is None:
        resolved = resolve_participants_from_utterance(utterance)
        # Always include the requester
        if user_email and user_email not in resolved:
            resolved.insert(0, user_email)
        participant_ids = resolved if resolved else [user_email]

    # Build context if not provided
    if context_json is None:
        context_json = build_context_json(participant_ids)

    payload = {
        "utterance": utterance,
        "participant_ids": participant_ids,
        "user_id": user_email,
        "context_json": context_json,
    }
    if event_id:
        payload["event_id"] = event_id

    start = time.time()
    logger.info("Direct orchestrator call: %s", utterance[:80])

    try:
        resp = requests.post(
            f"{ORCHESTRATOR_URL}/schedule",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.exceptions.ConnectionError:
        logger.error("Orchestrator service unreachable at %s", ORCHESTRATOR_URL)
        return {
            "status": "error",
            "error_message": "Scheduling service temporarily unavailable. Try again shortly.",
        }
    except Exception as e:
        logger.error("Orchestrator call failed: %s", e, exc_info=True)
        return {
            "status": "error",
            "error_message": f"Scheduling error: {e}",
        }

    elapsed_ms = int((time.time() - start) * 1000)
    logger.info("Orchestrator responded: status=%s elapsed=%dms",
                result.get("status"), elapsed_ms)

    # Inject resolved participants into result so extract_participant_metadata
    # can find them (the orchestrator response doesn't include them).
    if "agent_data" not in result or result["agent_data"] is None:
        result["agent_data"] = {}
    if "participants" not in result["agent_data"]:
        # Build participant list with name resolution from identities
        identities = _get_identities()
        email_to_identity = {
            id_.get("identifier_key", "").lower(): id_
            for id_ in identities
            if id_.get("identifier_key")
        }
        participant_entries = []
        for email in participant_ids:
            identity = email_to_identity.get(email.lower(), {})
            name = _find_property(identity, "colloquial_name") if identity else None
            if not name:
                name = identity.get("name", "") if identity else ""
            participant_entries.append({
                "email": email,
                "name": name or email.split("@")[0].replace(".", " ").replace("_", " ").title(),
            })
        result["agent_data"]["participants"] = participant_entries

    return result


def extract_display_content(result: Dict[str, Any]) -> Optional[str]:
    """
    Extract the user-facing display content from an orchestrator result.

    Returns the verbatim output string suitable for proposal parsing,
    or None if the result has no displayable content.
    """
    # Try top-level verbatim_user_output first
    verbatim = result.get("verbatim_user_output")
    if verbatim:
        return verbatim

    # Try user_display.verbatim_user_output
    user_display = result.get("user_display")
    if isinstance(user_display, dict):
        verbatim = user_display.get("verbatim_user_output")
        if verbatim:
            return verbatim

    # Fallback to explanation
    explanation = result.get("explanation")
    if explanation:
        return explanation

    return None


def extract_participant_metadata(result: Dict[str, Any]) -> Tuple[List[str], Dict[str, str]]:
    """
    Extract participant emails and names from orchestrator result.

    Returns (participant_emails, participant_names_map).
    """
    participants: List[str] = []
    names: Dict[str, str] = {}

    # Try agent_data.participants
    agent_data = result.get("agent_data")
    if isinstance(agent_data, dict):
        for p in agent_data.get("participants", []):
            if isinstance(p, dict):
                email = p.get("email") or p.get("id", "")
                name = p.get("display_name") or p.get("name", "")
                if email:
                    participants.append(email)
                    if name:
                        names[email] = name

    # Fallback: parse from user_display metadata markers
    user_display = result.get("user_display")
    if isinstance(user_display, dict) and not participants:
        verbatim = user_display.get("verbatim_output", "")
        match = re.search(r'\[PARTICIPANTS:([^\]]+)\]', verbatim)
        if match:
            participants = [p.strip() for p in match.group(1).split(",") if p.strip()]
        names_match = re.search(r'\[PARTICIPANT_NAMES:([^\]]+)\]', verbatim)
        if names_match:
            for pair in names_match.group(1).split(","):
                if "=" in pair:
                    email, name = pair.split("=", 1)
                    names[email.strip()] = name.strip()

    return participants, names
