"""Parse SUMMARY lines from agent responses for session context tracking.

Sub-agents are instructed to end responses with SUMMARY: <action taken> #topic #tags.
This module extracts summaries and topic hashtags for archival tagging.
"""

import re
from dataclasses import dataclass

# Pattern to match SUMMARY line (case-insensitive, multiline)
SUMMARY_PATTERN = re.compile(r"^SUMMARY:\s*(.+)$", re.MULTILINE | re.IGNORECASE)

# Pattern to extract hashtags from summary
HASHTAG_PATTERN = re.compile(r"#(\w+)")

# Maximum length for truncated summaries
MAX_SUMMARY_LENGTH = 80


@dataclass
class ParsedSummary:
    """Parsed summary with extracted topic tags."""

    text: str  # Summary text without hashtags
    topics: list[str]  # Extracted topic tags (without # prefix)


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


def extract_summary_with_topics(
    response_text: str,
    agent_name: str,
    tool_calls: list[str] | None = None,
) -> ParsedSummary:
    """
    Extract SUMMARY line and parse hashtags as topic tags.

    Args:
        response_text: Full response from agent
        agent_name: Name of the responding agent (for fallback)
        tool_calls: List of tool names called (optional)

    Returns:
        ParsedSummary with text (hashtags stripped) and topics list
    """
    raw_summary = extract_summary(response_text, agent_name, tool_calls)

    # Extract hashtags
    topics = HASHTAG_PATTERN.findall(raw_summary)

    # Remove hashtags from summary text for clean display
    clean_text = HASHTAG_PATTERN.sub("", raw_summary).strip()
    # Clean up any double spaces left after hashtag removal
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    return ParsedSummary(text=clean_text, topics=topics)


def clean_response_for_user(response_text: str) -> str:
    """
    Strip SUMMARY line from user-facing response.

    The SUMMARY line is for internal context tracking and shouldn't
    be shown to users.

    Args:
        response_text: Full response from agent

    Returns:
        Response with SUMMARY line removed
    """
    if not response_text:
        return ""

    cleaned = SUMMARY_PATTERN.sub("", response_text)
    return cleaned.strip()
