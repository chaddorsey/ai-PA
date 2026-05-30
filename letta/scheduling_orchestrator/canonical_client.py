"""
Canonical (Gitea) client for orchestrator.

Replaces Letta /v1/identities/ as the source of truth for staff
metadata (display names, working hours, timezones, slack/calendar
mappings). Reads from agents-canonical Gitea repo via HTTP, with
an in-memory cache to avoid hammering Gitea on every scheduling
call.

Data schema (per-person YAML frontmatter):
  description: "<Full Name> — <Title>"
  emails:
    primary: <email>
  calendar_ids:
    primary: <email>
  slack:
    user_id: U...
    display_name: <slug>
  aliases: ["<slug>"]
  timezone: <IANA tz>
  working_hours:                # optional
    monday: {start: "09:00", end: "17:00"}
    tuesday: {start: "09:00", end: "17:00"}
    ...
    saturday: null
    sunday: null
  scheduling_prefs:             # optional
    preferred_times: ["morning"]
    preferred_days: ["Monday", "Tuesday"]
    avoid_times: []
    avoid_days: []

Source of truth: agents-canonical Gitea repo, dirs:
  reference/people/work/
  reference/people/external/
  reference/people/board/
  reference/people/family/
  reference/people/personal/
"""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "http://gitea:3000")
GITEA_TOKEN = os.getenv("GITEA_MEMFS_TOKEN", "")
CANONICAL_REPO = "agents/agents-canonical"
CANONICAL_BRANCH = "main"

# Buckets to scan for people, in priority order. "work" first since that's
# the most common lookup target for scheduling.
PEOPLE_BUCKETS = ["work", "external", "board", "family", "personal", "board-alumni", "work-alumni"]

# Cache TTL in seconds. The orchestrator is a long-running service;
# refresh every few minutes is plenty.
CACHE_TTL_SECONDS = 300

# Cache state — module-level singleton, guarded by lock.
_cache_lock = threading.Lock()
_cache_data: Optional[Dict[str, Any]] = None
_cache_expires_at: float = 0.0


def _gitea_url(path: str) -> str:
    """Build a Gitea API URL relative to the canonical repo."""
    return f"{GITEA_BASE_URL}/api/v1/repos/{CANONICAL_REPO}/{path}"


def _gitea_raw_url(path: str) -> str:
    """Build a Gitea raw-file URL relative to the canonical repo's main branch."""
    return f"{GITEA_BASE_URL}/api/v1/repos/{CANONICAL_REPO}/raw/{CANONICAL_BRANCH}/{path}"


def _auth_headers() -> Dict[str, str]:
    if not GITEA_TOKEN:
        logger.warning(
            "GITEA_MEMFS_TOKEN not set; canonical reads will likely 401"
        )
        return {}
    return {"Authorization": f"token {GITEA_TOKEN}"}


def _parse_frontmatter(body: str) -> Dict[str, Any]:
    """
    Parse the YAML frontmatter block of a canonical .md file.

    Returns {} if no frontmatter or parse error.
    """
    if not body.startswith("---"):
        return {}

    end_marker = body.find("\n---", 3)
    if end_marker < 0:
        return {}

    fm_text = body[3:end_marker].strip()

    if yaml is None:
        logger.warning("PyYAML not installed; cannot parse frontmatter")
        return {}

    try:
        data = yaml.safe_load(fm_text)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        logger.warning(f"YAML parse error in canonical frontmatter: {e}")
        return {}


def _fetch_directory_entries(bucket: str, timeout: float = 10.0) -> List[str]:
    """Return the list of .md file names in a people bucket."""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                _gitea_url(f"contents/reference/people/{bucket}"),
                headers=_auth_headers(),
            )
            if r.status_code == 404:
                return []
            r.raise_for_status()
            entries = r.json()
            return [
                e["name"] for e in entries
                if isinstance(e, dict)
                and e.get("type") == "file"
                and e.get("name", "").endswith(".md")
            ]
    except Exception as e:
        logger.warning(f"Failed to list bucket {bucket}: {e}")
        return []


def _fetch_person_file(bucket: str, filename: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """
    Fetch one person's canonical record and parse its frontmatter.

    Returns a dict shaped like:
      {
        "slug": "kmiller",
        "bucket": "work",
        "path": "reference/people/work/kmiller.md",
        "frontmatter": {...},        # parsed YAML
        "raw_body": "<full markdown body, including frontmatter>",
      }
    Returns None on fetch failure.
    """
    path = f"reference/people/{bucket}/{filename}"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(_gitea_raw_url(path), headers=_auth_headers())
            if r.status_code == 404:
                return None
            r.raise_for_status()
            body = r.text
    except Exception as e:
        logger.warning(f"Failed to fetch {path}: {e}")
        return None

    fm = _parse_frontmatter(body)
    slug = filename[:-3] if filename.endswith(".md") else filename
    return {
        "slug": slug,
        "bucket": bucket,
        "path": path,
        "frontmatter": fm,
        "raw_body": body,
    }


def _build_cache() -> Dict[str, Any]:
    """
    Walk all people buckets, fetch each person file, build lookup indices.

    Returns:
      {
        "people": {slug: person_record},
        "by_email": {email_lower: slug},
        "by_slack_id": {slack_user_id: slug},
        "by_calendar_id": {calendar_id_lower: slug},
        "built_at": <unix timestamp>,
      }
    """
    people: Dict[str, Dict[str, Any]] = {}
    by_email: Dict[str, str] = {}
    by_slack_id: Dict[str, str] = {}
    by_calendar_id: Dict[str, str] = {}

    for bucket in PEOPLE_BUCKETS:
        filenames = _fetch_directory_entries(bucket)
        for filename in filenames:
            record = _fetch_person_file(bucket, filename)
            if record is None:
                continue

            slug = record["slug"]
            fm = record["frontmatter"]

            # Skip duplicate slugs across buckets (first wins per
            # PEOPLE_BUCKETS order — work has priority).
            if slug in people:
                continue
            people[slug] = record

            # Index by primary email
            emails = fm.get("emails") or {}
            primary_email = emails.get("primary") if isinstance(emails, dict) else None
            if primary_email:
                by_email[primary_email.lower()] = slug

            # Index by primary calendar id (often same as primary email)
            calendar_ids = fm.get("calendar_ids") or {}
            primary_cal = calendar_ids.get("primary") if isinstance(calendar_ids, dict) else None
            if primary_cal:
                by_calendar_id[primary_cal.lower()] = slug

            # Index by slack user_id
            slack = fm.get("slack") or {}
            slack_user = slack.get("user_id") if isinstance(slack, dict) else None
            if slack_user:
                by_slack_id[slack_user] = slug

    cache = {
        "people": people,
        "by_email": by_email,
        "by_slack_id": by_slack_id,
        "by_calendar_id": by_calendar_id,
        "built_at": time.time(),
    }

    logger.info(
        f"Canonical cache built: {len(people)} people, "
        f"{len(by_email)} emails, {len(by_slack_id)} slack ids"
    )
    return cache


def get_cache(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Return the canonical lookup cache, refreshing if expired.

    Thread-safe; multiple concurrent callers will block on a single
    refresh.
    """
    global _cache_data, _cache_expires_at

    now = time.time()

    with _cache_lock:
        if (
            not force_refresh
            and _cache_data is not None
            and now < _cache_expires_at
        ):
            return _cache_data

        try:
            _cache_data = _build_cache()
            _cache_expires_at = now + CACHE_TTL_SECONDS
        except Exception as e:
            logger.error(f"Canonical cache build failed: {e}")
            # Return last good cache if we have one; otherwise empty
            if _cache_data is None:
                _cache_data = {
                    "people": {},
                    "by_email": {},
                    "by_slack_id": {},
                    "by_calendar_id": {},
                    "built_at": 0.0,
                }

    return _cache_data


def get_person_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Return the person record for a given email, or None if not found."""
    if not email:
        return None
    cache = get_cache()
    slug = cache["by_email"].get(email.lower())
    if not slug:
        return None
    return cache["people"].get(slug)


def get_person_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Return the person record for a given canonical slug, or None."""
    if not slug:
        return None
    cache = get_cache()
    return cache["people"].get(slug)


def get_person_by_slack_id(slack_user_id: str) -> Optional[Dict[str, Any]]:
    """Return the person record for a given slack user_id, or None."""
    if not slack_user_id:
        return None
    cache = get_cache()
    slug = cache["by_slack_id"].get(slack_user_id)
    if not slug:
        return None
    return cache["people"].get(slug)


def list_all_people() -> List[Dict[str, Any]]:
    """Return all known person records (work, external, board, etc.)."""
    cache = get_cache()
    return list(cache["people"].values())
