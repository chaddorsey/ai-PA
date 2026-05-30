"""
Canonical-backed lookups for participant name resolution and
scheduling preferences.

Drop-in replacement for identity_lookup.py. Same public API
signatures, but reads from agents-canonical Gitea repo instead of
Letta /v1/identities/.

Public API:
    lookup_participant_names(emails, ...) -> Dict[email, display_name]
    get_user_preferences_from_identity(identity_id, ...) -> Optional[Dict]
    lookup_identity_by_property(key, value, ...) -> Optional[dict]
    resolve_participant_identifier(identifier, ...) -> Optional[email]

Note: "identity_id" in this module means a canonical slug
(e.g., "cdorsey", "kmiller"), not a Letta identity UUID. Same
parameter name is preserved for callsite compatibility.
"""

import logging
from typing import Dict, List, Optional

try:
    from .canonical_client import (
        get_person_by_email,
        get_person_by_slug,
        get_person_by_slack_id,
        get_cache,
    )
except ImportError:
    from canonical_client import (
        get_person_by_email,
        get_person_by_slug,
        get_person_by_slack_id,
        get_cache,
    )

logger = logging.getLogger(__name__)


def lookup_participant_names(
    participant_emails: List[str],
    letta_base_url: Optional[str] = None,  # ignored; kept for API compat
    timeout: float = 5.0,                  # ignored; cache handles it
) -> Dict[str, str]:
    """
    Resolve email addresses to colloquial first names from canonical.

    Drop-in replacement for identity_lookup.lookup_participant_names.
    """
    if not participant_emails:
        return {}

    result: Dict[str, str] = {}
    for email in participant_emails:
        person = get_person_by_email(email)
        if person:
            result[email] = _extract_display_name(person)
        else:
            result[email] = _email_to_fallback_name(email)
    return result


def get_user_preferences_from_identity(
    identity_id: str,
    letta_base_url: Optional[str] = None,  # ignored
    timeout: float = 5.0,                  # ignored
) -> Optional[Dict[str, List[str]]]:
    """
    Fetch scheduling preferences from canonical for a given slug.

    Drop-in replacement for identity_lookup.get_user_preferences_from_identity.
    Accepts a canonical slug instead of a Letta identity UUID.

    Returns a dict with keys from {preferred_times, preferred_days,
    avoid_times, avoid_days} (only keys with data), or None if no
    person record found.
    """
    if not identity_id:
        return None

    person = get_person_by_slug(identity_id)
    if person is None:
        return None

    fm = person.get("frontmatter") or {}
    prefs = fm.get("scheduling_prefs") or {}

    if not isinstance(prefs, dict) or not prefs:
        return None

    result: Dict[str, List[str]] = {}
    for key in ("preferred_times", "preferred_days", "avoid_times", "avoid_days"):
        value = prefs.get(key)
        if isinstance(value, list) and value:
            result[key] = [str(v).strip() for v in value if str(v).strip()]
    return result if result else None


def lookup_identity_by_property(
    property_key: str,
    property_value: str,
    letta_base_url: Optional[str] = None,  # ignored
    timeout: float = 5.0,                  # ignored
) -> Optional[dict]:
    """
    Find a canonical person by an arbitrary property key/value pair.

    Drop-in replacement for identity_lookup.lookup_identity_by_property.
    Returns a synthesized identity-shaped dict for compatibility with
    callers expecting the old shape.

    Supported keys: "email", "identifier_key", "slack_id", "calendar_id",
    plus anything that happens to live in the frontmatter.
    """
    if not property_key or not property_value:
        return None

    person = None

    if property_key in ("email", "identifier_key"):
        person = get_person_by_email(property_value)
    elif property_key == "slack_id":
        person = get_person_by_slack_id(property_value)
    elif property_key == "calendar_id":
        # calendar_id is indexed alongside email
        cache = get_cache()
        slug = cache["by_calendar_id"].get(property_value.lower())
        if slug:
            person = get_person_by_slug(slug)
    else:
        # Generic scan: look for the key in each person's frontmatter
        cache = get_cache()
        for record in cache["people"].values():
            fm = record.get("frontmatter") or {}
            if _frontmatter_field_matches(fm, property_key, property_value):
                person = record
                break

    if person is None:
        return None

    return _to_identity_shape(person)


def resolve_participant_identifier(
    identifier: str,
    letta_base_url: Optional[str] = None,  # ignored
    timeout: float = 5.0,                  # ignored
) -> Optional[str]:
    """
    Resolve any participant identifier to an email address.

    Drop-in replacement for identity_lookup.resolve_participant_identifier.
    """
    if not identifier:
        return None

    # If it already looks like an email, return it directly
    if "@" in identifier:
        return identifier

    # Slack user ID pattern (starts with U, length 9+)
    if identifier.startswith("U") and len(identifier) >= 9:
        person = get_person_by_slack_id(identifier)
        if person:
            return _primary_email(person)

    # Try as a canonical slug
    person = get_person_by_slug(identifier)
    if person:
        return _primary_email(person)

    return None


# ---------------------------------------------------------------------------
# Internal helpers


def _extract_display_name(person: Dict) -> str:
    """
    Pick the best display name for a person record.

    Priority:
      1. scheduling_prefs.colloquial_name if explicitly set
      2. First word of the description before " — "
         (e.g. "Kate Miller — Research Associate" → "Kate")
      3. First word of `name:` field if present
      4. Slug
    """
    fm = person.get("frontmatter") or {}

    prefs = fm.get("scheduling_prefs") or {}
    if isinstance(prefs, dict):
        explicit = prefs.get("colloquial_name")
        if explicit:
            return str(explicit).strip()

    description = fm.get("description") or ""
    if " — " in description:
        full_name = description.split(" — ")[0].strip()
    elif " - " in description:
        full_name = description.split(" - ")[0].strip()
    else:
        full_name = description.strip()

    if full_name:
        first = full_name.split()[0]
        if first:
            return first

    name_field = fm.get("name") or ""
    if name_field:
        first = name_field.split()[0]
        if first:
            return first

    return person.get("slug", "unknown")


def _email_to_fallback_name(email: str) -> str:
    """Fall back to email prefix when canonical has no record."""
    if not email or "@" not in email:
        return email or "unknown"
    prefix = email.split("@")[0]
    if "." in prefix:
        return prefix.split(".")[0]
    return prefix


def _primary_email(person: Dict) -> Optional[str]:
    fm = person.get("frontmatter") or {}
    emails = fm.get("emails") or {}
    if isinstance(emails, dict):
        primary = emails.get("primary")
        if primary:
            return primary
    return None


def _to_identity_shape(person: Dict) -> Dict:
    """
    Convert a canonical person record to a Letta-identity-shaped dict
    for compatibility with callers that still iterate `.get('properties')`.

    Produces:
      {
        "id": "<slug>",
        "identifier_key": "<primary_email>",
        "name": "<full name from description>",
        "properties": [{"key": "...", "value": "..."}, ...]
      }
    """
    fm = person.get("frontmatter") or {}
    primary_email = _primary_email(person) or ""
    description = fm.get("description") or ""
    full_name = description.split(" — ")[0].strip() if " — " in description else description.strip()

    properties = []

    # Flatten common fields into properties[] for legacy callers
    if fm.get("timezone"):
        properties.append({"key": "timezone", "value": fm["timezone"]})

    slack = fm.get("slack") or {}
    if isinstance(slack, dict) and slack.get("user_id"):
        properties.append({"key": "slack_id", "value": slack["user_id"]})

    cal = fm.get("calendar_ids") or {}
    if isinstance(cal, dict) and cal.get("primary"):
        properties.append({"key": "calendar_id", "value": cal["primary"]})

    prefs = fm.get("scheduling_prefs") or {}
    if isinstance(prefs, dict):
        for key, value in prefs.items():
            if isinstance(value, list):
                properties.append({"key": key, "value": ",".join(str(v) for v in value)})
            elif value is not None:
                properties.append({"key": key, "value": str(value)})

    return {
        "id": person.get("slug"),
        "identifier_key": primary_email,
        "name": full_name,
        "properties": properties,
    }


def _frontmatter_field_matches(fm: Dict, key: str, value: str) -> bool:
    """Generic field equality check for unfamiliar property keys."""
    target = fm.get(key)
    if target is None:
        return False
    if isinstance(target, str):
        return target.lower() == value.lower()
    if isinstance(target, list):
        return any(str(item).lower() == value.lower() for item in target)
    if isinstance(target, dict):
        return any(str(v).lower() == value.lower() for v in target.values())
    return str(target).lower() == value.lower()
