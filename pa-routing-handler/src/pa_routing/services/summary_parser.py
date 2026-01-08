"""Parse SUMMARY lines from agent responses for session context tracking.

Sub-agents are instructed to end responses with SUMMARY: <action taken>.
This module extracts those summaries with fallback chain for non-compliant agents.
"""

import re

# Pattern to match SUMMARY line (case-insensitive, multiline)
SUMMARY_PATTERN = re.compile(r"^SUMMARY:\s*(.+)$", re.MULTILINE | re.IGNORECASE)

# Maximum length for truncated summaries
MAX_SUMMARY_LENGTH = 80


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
        Summary string for session context
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
