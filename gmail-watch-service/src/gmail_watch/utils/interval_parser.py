"""Utilities for parsing and formatting follow-up interval strings."""

from __future__ import annotations

import re
from typing import Any, Optional

DEFAULT_FOLLOWUP_SECONDS: int = 259200  # 3 days

_UNIT_MULTIPLIERS: dict[str, int] = {
    "h": 3600,
    "d": 86400,
    "w": 604800,
}

_INTERVAL_RE = re.compile(r"^(\d+)(h|d|w)$", re.IGNORECASE)


def parse_interval(s: Optional[str]) -> int:
    """Parse a human-readable interval string to seconds.

    Accepts strings like '3d', '12h', '1w'. Returns DEFAULT_FOLLOWUP_SECONDS
    for None, empty, or invalid input.
    """
    if not s:
        return DEFAULT_FOLLOWUP_SECONDS

    s = s.strip()
    match = _INTERVAL_RE.match(s)
    if not match:
        return DEFAULT_FOLLOWUP_SECONDS

    amount = int(match.group(1))
    unit = match.group(2).lower()
    return amount * _UNIT_MULTIPLIERS[unit]


def format_interval(seconds: int) -> str:
    """Format seconds to a human-readable interval string.

    Prefers weeks > days > hours. Falls back to hours for values that
    don't divide evenly into days.
    """
    if seconds % _UNIT_MULTIPLIERS["w"] == 0:
        return f"{seconds // _UNIT_MULTIPLIERS['w']}w"
    if seconds % _UNIT_MULTIPLIERS["d"] == 0:
        return f"{seconds // _UNIT_MULTIPLIERS['d']}d"
    return f"{seconds // _UNIT_MULTIPLIERS['h']}h"


def extract_interval_from_address(
    address: str, bcc_prefix: str
) -> Optional[int]:
    """Extract a follow-up interval from a BCC plus-address.

    Given an address like 'cdorsey+watch3d@concord.org' and prefix
    'cdorsey+watch', extracts '3d' and parses it to 259200 seconds.

    Returns None if the address does not match the prefix.
    Returns DEFAULT_FOLLOWUP_SECONDS if the prefix matches but no
    interval suffix is present.
    """
    params = extract_watch_params_from_address(address, bcc_prefix)
    if params is None:
        return None
    return params["interval_seconds"]


def extract_watch_params_from_address(
    address: str, bcc_prefix: str
) -> Optional[dict[str, Any]]:
    """Extract watch parameters from a BCC plus-address.

    Supports optional 'ext' prefix for external_only flag.
    Examples:
        cdorsey+watch5d@concord.org   → interval=432000, external_only=False
        cdorsey+watchext5d@concord.org → interval=432000, external_only=True
        cdorsey+watchext@concord.org   → interval=259200, external_only=True

    Returns None if the address does not match the prefix.
    """
    local_part = address.split("@")[0]
    if not local_part.lower().startswith(bcc_prefix.lower()):
        return None

    suffix = local_part[len(bcc_prefix):]
    external_only = False

    if suffix.lower().startswith("ext"):
        external_only = True
        suffix = suffix[3:]

    interval_seconds = parse_interval(suffix) if suffix else DEFAULT_FOLLOWUP_SECONDS

    return {
        "interval_seconds": interval_seconds,
        "external_only": external_only,
    }
