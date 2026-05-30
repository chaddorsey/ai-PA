"""Parse SUMMARY and REFS lines from agent responses for session context tracking.

Sub-agents are instructed to end responses with:
  SUMMARY: <action taken> #topic #tags
  REFS: {"key": "value", ...}  (optional, for actionable references)

This module extracts summaries, topic hashtags, and structured refs for:
- Cross-agent context awareness (Pattern 2)
- Archival tagging (Pattern 3)
- Actionable follow-up support (e.g., updating a just-created calendar event)
"""

import json
import re
from dataclasses import dataclass, field

# Pattern to match SUMMARY line (case-insensitive, multiline)
SUMMARY_PATTERN = re.compile(r"^SUMMARY:\s*(.+)$", re.MULTILINE | re.IGNORECASE)

# Pattern to match REFS line with JSON (case-insensitive, multiline)
REFS_PATTERN = re.compile(r"^REFS:\s*(\{.+\})\s*$", re.MULTILINE | re.IGNORECASE)

# Pattern to extract hashtags from summary
HASHTAG_PATTERN = re.compile(r"#(\w+)")

# Maximum length for truncated summaries
MAX_SUMMARY_LENGTH = 80


@dataclass
class ParsedSummary:
    """Parsed summary with extracted topic tags and actionable refs."""

    text: str  # Summary text without hashtags
    topics: list[str]  # Extracted topic tags (without # prefix)
    refs: dict = field(default_factory=dict)  # Actionable references (IDs, titles, etc.)


def extract_summary(
    response_text: str,
    agent_name: str,
    tool_calls: list[str] | None = None,
) -> str:
    """
    Extract SUMMARY line from agent response with fallback chain.

    Priority:
    1. Explicit SUMMARY: line from agent
    2. Tool name if tools were called
    3. First sentence of response, truncated

    Args:
        response_text: Full response from agent
        agent_name: Name of the responding agent (for fallback)
        tool_calls: List of tool names called (optional)

    Returns:
        Summary string for session context (includes hashtags if present)
    """
    if not response_text:
        return f"{agent_name} responded"

    # Try explicit SUMMARY line first
    match = SUMMARY_PATTERN.search(response_text)
    if match:
        return match.group(1).strip()

    # Fallback 1: Use tool name if tools were called
    if tool_calls:
        tool_name = tool_calls[0]
        return f"Called {tool_name}"

    # Fallback 2: First line, truncated
    first_line = response_text.split("\n")[0].strip()

    if not first_line:
        return f"{agent_name} responded"

    if len(first_line) > MAX_SUMMARY_LENGTH:
        return first_line[: MAX_SUMMARY_LENGTH - 3] + "..."

    return first_line


def extract_refs(response_text: str) -> dict:
    """
    Extract REFS JSON from agent response.

    Args:
        response_text: Full response from agent

    Returns:
        Dict of actionable references, empty dict if none or parse error
    """
    if not response_text:
        return {}

    match = REFS_PATTERN.search(response_text)
    if not match:
        return {}

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        # Invalid JSON - log would be nice but return empty for graceful degradation
        return {}


def extract_summary_with_topics(
    response_text: str,
    agent_name: str,
    tool_calls: list[str] | None = None,
) -> ParsedSummary:
    """
    Extract SUMMARY line, parse hashtags as topic tags, and extract REFS.

    Args:
        response_text: Full response from agent
        agent_name: Name of the responding agent (for fallback)
        tool_calls: List of tool names called (optional)

    Returns:
        ParsedSummary with text (hashtags stripped), topics list, and refs dict
    """
    raw_summary = extract_summary(response_text, agent_name, tool_calls)

    # Extract hashtags
    topics = HASHTAG_PATTERN.findall(raw_summary)

    # Remove hashtags from summary text for clean display
    clean_text = HASHTAG_PATTERN.sub("", raw_summary).strip()
    # Clean up any double spaces left after hashtag removal
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    # Extract refs
    refs = extract_refs(response_text)

    return ParsedSummary(text=clean_text, topics=topics, refs=refs)


def clean_response_for_user(response_text: str) -> str:
    """
    Strip SUMMARY and REFS lines from user-facing response.

    These lines are for internal context tracking and shouldn't
    be shown to users.

    Args:
        response_text: Full response from agent

    Returns:
        Response with SUMMARY and REFS lines removed
    """
    if not response_text:
        return ""

    cleaned = SUMMARY_PATTERN.sub("", response_text)
    cleaned = REFS_PATTERN.sub("", cleaned)
    # Clean up any extra blank lines left behind
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
