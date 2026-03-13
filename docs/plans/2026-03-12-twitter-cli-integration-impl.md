# Twitter CLI Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor jackwener/twitter-cli into `twitter-cli/` as a Poetry package, replace curator-radar's hand-rolled TwitterClient, and expose a `run_twitter` Letta tool for agent access.

**Architecture:** Fork-and-adapt. twitter-cli becomes a local Poetry package with `curl_cffi` for TLS fingerprinting and Smaug cookie auth. Curator-radar imports the client directly. Agent access goes through new curator-radar HTTP routes, called by the `run_twitter` Letta tool (matching `query_curator_radar` pattern).

**Tech Stack:** Python 3.12, curl_cffi, Click, FastAPI, SQLAlchemy (async), Poetry

**Spec:** `docs/plans/2026-03-12-twitter-cli-integration-design.md`

---

## File Map

### New files (twitter-cli package)

| File | Responsibility |
|------|----------------|
| `twitter-cli/pyproject.toml` | Poetry config, deps (curl_cffi, click), entry point |
| `twitter-cli/src/twitter_cli/__init__.py` | Package init, version |
| `twitter-cli/src/twitter_cli/constants.py` | Bearer token, GraphQL query IDs, feature flags |
| `twitter-cli/src/twitter_cli/auth.py` | Cookie loading from Smaug config path |
| `twitter-cli/src/twitter_cli/client.py` | curl_cffi session with Chrome TLS fingerprint, inline parsing |
| `twitter-cli/src/twitter_cli/cli.py` | Click CLI: read/write command groups |
| `twitter-cli/src/twitter_cli/formatters.py` | JSON/human output formatting |
| `twitter-cli/tests/__init__.py` | Test package init |
| `twitter-cli/tests/test_auth.py` | Auth unit tests |
| `twitter-cli/tests/test_cli.py` | CLI integration tests |

### New files (Letta tool)

| File | Responsibility |
|------|----------------|
| `letta/twitter_tools.py` | `run_twitter` Letta tool (HTTP calls to curator-radar) |
| `letta/register_twitter_tools.py` | Register tool with Letta API |

### Modified files

| File | Change |
|------|--------|
| `curator-radar/curator_radar/twitter_client.py` | Delete (replaced by twitter_cli.client) |
| `curator-radar/curator_radar/twitter_backfill.py` | Update imports, wrap sync calls with asyncio.to_thread |
| `curator-radar/curator_radar/twitter_list_sync.py` | Update imports, wrap sync calls with asyncio.to_thread |
| `curator-radar/curator_radar/routes.py` | Add agent-access routes, update TwitterClient imports |
| `curator-radar/Dockerfile` | Add COPY + pip install for twitter-cli |
| `curator-radar/requirements.txt` | Add twitter-cli path dependency |
| `docker-compose.yml` | Add twitter-cli volume/copy context to curator-radar build |

---

## Chunk 1: Package Scaffolding, Auth, and Constants

### Task 1: Create Poetry package scaffold

**Files:**
- Create: `twitter-cli/pyproject.toml`
- Create: `twitter-cli/src/twitter_cli/__init__.py`

- [ ] **Step 1: Create package directory structure**

```bash
mkdir -p /Volumes/main-drive/ai-PA/twitter-cli/src/twitter_cli
mkdir -p /Volumes/main-drive/ai-PA/twitter-cli/tests
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[tool.poetry]
name = "twitter-cli"
version = "0.1.0"
description = "Twitter CLI with TLS fingerprinting for agent and batch use"
authors = ["ai-PA"]
packages = [{include = "twitter_cli", from = "src"}]

[tool.poetry.dependencies]
python = "^3.12"
curl-cffi = ">=0.7.0"
click = "^8.1"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^5.0"

[tool.poetry.scripts]
twitter-cli = "twitter_cli.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 3: Write __init__.py**

```python
"""Twitter CLI — cookie-based Twitter client with TLS fingerprinting."""
__version__ = "0.1.0"
```

- [ ] **Step 4: Install dependencies**

```bash
cd /Volumes/main-drive/ai-PA/twitter-cli && poetry install
```

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add twitter-cli/pyproject.toml twitter-cli/src/twitter_cli/__init__.py
git commit -m "feat: scaffold twitter-cli Poetry package"
```

---

### Task 2: Constants — bearer token, query IDs, feature flags

**Files:**
- Create: `twitter-cli/src/twitter_cli/constants.py`

- [ ] **Step 1: Write constants.py**

Port the bearer token and GraphQL query IDs from curator-radar's `twitter_client.py` and add new ones from upstream twitter-cli. Feature flags come from the upstream repo's `graphql.py`.

```python
"""Twitter API constants: bearer token, GraphQL query IDs, feature flags."""

# Public bearer token used by Twitter's web client (not a secret)
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# GraphQL operation query IDs (from x.com JS bundles)
QUERY_IDS = {
    "Retweeters": "qVWT1Tn1FiklyVDqYiOhLg",
    "CreateList": "nHFMQuE0r6yVEGmPSSbDdg",
    "ListAddMember": "sw71TVciw0CoWPcFfIhrnA",
    "ListRemoveMember": "cvl5jMbF1DqPRJalJTkNzA",
    "UserByScreenName": "xmU6X_CKVnQ5lSrCbAmJsg",
    "HomeTimeline": "HJFjzBgCs16TqxewQOeLNg",
    "UserTweets": "E3opETHurmVJflFsUBVuUQ",
    "Bookmarks": "j5KExFXtSqHHgK3MBfOuBw",
    "SearchTimeline": "gkjsKepM6gl_HmFWoWKfgg",
    "TweetDetail": "nBS-WpgA6ZG0CyNHD517JQ",
    "Favorites": "eSSNbhECHHWWALkkQq-YTA",
    "ListMembers": "BQp2IEYkgxuSxqbTAr1e1g",
    "CreateBookmark": "aoDbu3RHznuiSkQ9aNM67Q",
}

GRAPHQL_BASE = "https://x.com/i/api/graphql"

# Feature flags sent with most GraphQL requests
TIMELINE_FEATURES = {
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

USER_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
```

- [ ] **Step 2: Commit**

```bash
git add twitter-cli/src/twitter_cli/constants.py
git commit -m "feat(twitter-cli): add API constants, query IDs, and feature flags"
```

---

### Task 3: Auth — Smaug cookie loading

**Files:**
- Create: `twitter-cli/src/twitter_cli/auth.py`
- Create: `twitter-cli/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# twitter-cli/tests/test_auth.py
import json
import tempfile
from pathlib import Path
from twitter_cli.auth import load_cookies


def test_load_cookies_from_smaug_config():
    """Load auth_token and ct0 from Smaug config JSON."""
    config = {"twitter": {"authToken": "test_auth_token", "ct0": "test_ct0"}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        cookies = load_cookies(f.name)
    assert cookies["auth_token"] == "test_auth_token"
    assert cookies["ct0"] == "test_ct0"


def test_load_cookies_missing_file():
    """Return empty cookies when config file doesn't exist."""
    cookies = load_cookies("/nonexistent/path.json")
    assert cookies["auth_token"] == ""
    assert cookies["ct0"] == ""


def test_load_cookies_env_override(monkeypatch):
    """Environment variables take precedence over config file."""
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "env_auth")
    monkeypatch.setenv("TWITTER_CT0", "env_ct0")
    cookies = load_cookies("/nonexistent/path.json")
    assert cookies["auth_token"] == "env_auth"
    assert cookies["ct0"] == "env_ct0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Volumes/main-drive/ai-PA/twitter-cli && poetry run pytest tests/test_auth.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'twitter_cli.auth'`

- [ ] **Step 3: Write auth.py**

```python
"""Cookie-based authentication for Twitter API.

Priority: environment variables > Smaug config file.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def load_cookies(config_path: str) -> dict[str, str]:
    """Load Twitter auth cookies.

    Args:
        config_path: Path to Smaug's smaug.config.json.

    Returns:
        Dict with 'auth_token' and 'ct0' keys.
    """
    # Environment variables take precedence
    env_auth = os.environ.get("TWITTER_AUTH_TOKEN", "")
    env_ct0 = os.environ.get("TWITTER_CT0", "")
    if env_auth and env_ct0:
        return {"auth_token": env_auth, "ct0": env_ct0}

    # Fall back to Smaug config file
    path = Path(config_path)
    if not path.exists():
        logger.warning("Smaug config not found: %s", config_path)
        return {"auth_token": "", "ct0": ""}

    try:
        config = json.loads(path.read_text())
        twitter = config.get("twitter", {})
        return {
            "auth_token": twitter.get("authToken", ""),
            "ct0": twitter.get("ct0", ""),
        }
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to read Smaug config: %s", e)
        return {"auth_token": "", "ct0": ""}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Volumes/main-drive/ai-PA/twitter-cli && poetry run pytest tests/test_auth.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add twitter-cli/src/twitter_cli/auth.py twitter-cli/tests/test_auth.py
git commit -m "feat(twitter-cli): add Smaug cookie auth with env var override"
```

---

### Task 4: Client — curl_cffi session with TLS fingerprinting

**Files:**
- Create: `twitter-cli/src/twitter_cli/client.py`

This is the core value-add. The client wraps `curl_cffi` with Chrome TLS impersonation, rate limiting, and GraphQL request helpers. It's synchronous (curl_cffi native), matching CLI usage. Curator-radar wraps calls with `asyncio.to_thread()`.

- [ ] **Step 1: Write client.py**

```python
"""Twitter GraphQL client with curl_cffi TLS fingerprinting.

Synchronous client — use asyncio.to_thread() for async contexts.
"""
import json
import logging
import time
import random
from dataclasses import dataclass, field

from curl_cffi.requests import Session

from .auth import load_cookies
from .constants import BEARER_TOKEN, GRAPHQL_BASE, QUERY_IDS, TIMELINE_FEATURES, USER_FEATURES

logger = logging.getLogger(__name__)

# Chrome impersonation target for curl_cffi
IMPERSONATE = "chrome133"

BASE_DELAY = 2.0
MAX_DELAY = 120.0
MAX_CONSECUTIVE_429S = 10


@dataclass
class RateState:
    remaining: int = 500
    reset_at: float = 0.0
    consecutive_429s: int = 0
    delay: float = BASE_DELAY


class TwitterClient:
    """Twitter GraphQL client with TLS fingerprinting and rate limiting.

    Usage:
        client = TwitterClient(config_path="/path/to/smaug.config.json")
        tweets = client.get_user_tweets("elonmusk", count=20)
        client.close()
    """

    def __init__(self, config_path: str):
        cookies = load_cookies(config_path)
        self._auth_token = cookies["auth_token"]
        self._ct0 = cookies["ct0"]
        self._rate = RateState()
        self._session: Session | None = None

    def _get_session(self) -> Session:
        if self._session is None:
            self._session = Session(impersonate=IMPERSONATE)
            self._session.headers.update({
                "Authorization": f"Bearer {BEARER_TOKEN}",
                "x-csrf-token": self._ct0,
                "x-twitter-auth-type": "OAuth2Session",
                "x-twitter-active-user": "yes",
                "Content-Type": "application/json",
            })
            self._session.cookies.set("auth_token", self._auth_token, domain=".x.com")
            self._session.cookies.set("ct0", self._ct0, domain=".x.com")
        return self._session

    def close(self):
        if self._session:
            self._session.close()
            self._session = None

    def _wait(self):
        jitter = random.uniform(0.8, 1.2)
        time.sleep(self._rate.delay * jitter)

    def _handle_rate_limit(self, resp) -> bool:
        """Update rate state from response. Returns True if rate-limited (should retry)."""
        if "x-rate-limit-remaining" in resp.headers:
            self._rate.remaining = int(resp.headers["x-rate-limit-remaining"])
        if "x-rate-limit-reset" in resp.headers:
            self._rate.reset_at = float(resp.headers["x-rate-limit-reset"])

        if resp.status_code == 429:
            self._rate.consecutive_429s += 1
            wait = min(BASE_DELAY * (2 ** self._rate.consecutive_429s), MAX_DELAY)
            self._rate.delay = wait
            logger.warning("Rate limited (429). Waiting %.0fs. Consecutive: %d",
                           wait, self._rate.consecutive_429s)
            time.sleep(wait)
            return True

        if self._rate.consecutive_429s > 0:
            self._rate.consecutive_429s = 0
            self._rate.delay = BASE_DELAY
        return False

    def _graphql_get(self, operation: str, variables: dict,
                     features: dict | None = None) -> dict:
        """Execute a GraphQL GET request."""
        query_id = QUERY_IDS.get(operation)
        if not query_id:
            raise ValueError(f"Unknown GraphQL operation: {operation}")

        if features is None:
            features = TIMELINE_FEATURES

        session = self._get_session()
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features),
        }

        for attempt in range(MAX_CONSECUTIVE_429S):
            self._wait()
            resp = session.get(f"{GRAPHQL_BASE}/{query_id}/{operation}", params=params)
            if not self._handle_rate_limit(resp):
                break
        else:
            raise RuntimeError(f"Rate limited after {MAX_CONSECUTIVE_429S} retries")

        if resp.status_code != 200:
            raise RuntimeError(
                f"{operation} API error {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def _graphql_post(self, operation: str, variables: dict,
                      features: dict | None = None) -> dict:
        """Execute a GraphQL POST request (for write operations)."""
        query_id = QUERY_IDS.get(operation)
        if not query_id:
            raise ValueError(f"Unknown GraphQL operation: {operation}")

        session = self._get_session()
        payload = {
            "variables": variables,
            "features": features or {},
            "queryId": query_id,
        }

        self._wait()
        # Extra delay for write operations (anti-detection)
        time.sleep(random.uniform(1.5, 4.0))

        resp = session.post(
            f"{GRAPHQL_BASE}/{query_id}/{operation}",
            json=payload,
        )
        self._handle_rate_limit(resp)

        if resp.status_code != 200:
            raise RuntimeError(
                f"{operation} API error {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    # --- Read operations ---

    def get_retweeters(self, tweet_id: str) -> list[dict]:
        """Fetch all retweeters of a tweet. Returns list of {handle, name}."""
        all_users = []
        cursor = None

        while True:
            variables = {
                "tweetId": tweet_id,
                "count": 100,
                "includePromotedContent": False,
            }
            if cursor:
                variables["cursor"] = cursor

            data = self._graphql_get("Retweeters", variables)
            timeline = (
                data.get("data", {})
                .get("retweeters_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )

            found_users = False
            next_cursor = None

            for instruction in timeline:
                for entry in instruction.get("entries", []):
                    content = entry.get("content", {})
                    if content.get("entryType") == "TimelineTimelineItem":
                        user_result = (
                            content.get("itemContent", {})
                            .get("user_results", {})
                            .get("result", {})
                        )
                        legacy = user_result.get("legacy", {})
                        if legacy.get("screen_name"):
                            all_users.append({
                                "handle": legacy["screen_name"],
                                "name": legacy.get("name", ""),
                            })
                            found_users = True
                    if content.get("entryType") == "TimelineTimelineCursor":
                        if content.get("cursorType") == "Bottom":
                            next_cursor = content.get("value")

            if not found_users or not next_cursor:
                break
            cursor = next_cursor

        return all_users

    def get_user_rest_id(self, screen_name: str) -> str | None:
        """Look up a user's REST ID by screen name."""
        data = self._graphql_get(
            "UserByScreenName",
            {"screen_name": screen_name, "withSafetyModeUserFields": True},
            features=USER_FEATURES,
        )
        return data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")

    def get_user_tweets(self, screen_name: str, count: int = 20) -> list[dict]:
        """Fetch a user's recent tweets. Returns raw GraphQL tweet entries."""
        user_id = self.get_user_rest_id(screen_name)
        if not user_id:
            return []
        data = self._graphql_get("UserTweets", {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        })
        return self._extract_timeline_tweets(data)

    def get_home_timeline(self, count: int = 20) -> list[dict]:
        """Fetch the home timeline."""
        data = self._graphql_get("HomeTimeline", {
            "count": count,
            "includePromotedContent": False,
            "latestControlAvailable": True,
            "withCommunity": True,
        })
        return self._extract_timeline_tweets(data)

    def get_bookmarks(self, count: int = 20) -> list[dict]:
        """Fetch bookmarked tweets via API."""
        data = self._graphql_get("Bookmarks", {
            "count": count,
            "includePromotedContent": False,
        })
        return self._extract_timeline_tweets(data)

    def search_tweets(self, query: str, count: int = 20) -> list[dict]:
        """Search tweets."""
        data = self._graphql_get("SearchTimeline", {
            "rawQuery": query,
            "count": count,
            "querySource": "typed_query",
            "product": "Latest",
        })
        # Search has a different nesting: data.search_by_raw_query.search_timeline
        search_timeline = (
            data.get("data", {})
            .get("search_by_raw_query", {})
            .get("search_timeline", {})
            .get("timeline", {})
        )
        return self._extract_instructions_tweets(search_timeline.get("instructions", []))

    def get_tweet_detail(self, tweet_id: str) -> dict:
        """Fetch a tweet and its replies."""
        data = self._graphql_get("TweetDetail", {
            "focalTweetId": tweet_id,
            "rankingMode": "Relevance",
            "includePromotedContent": False,
            "withCommunity": True,
            "withVoice": True,
            "withBirdwatchNotes": True,
        })
        return data

    def get_list_members(self, list_id: str, count: int = 100) -> list[dict]:
        """Fetch members of a Twitter list."""
        data = self._graphql_get("ListMembers", {
            "listId": list_id,
            "count": count,
        })
        members = []
        instructions = (
            data.get("data", {})
            .get("list", {})
            .get("members_timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        for instruction in instructions:
            for entry in instruction.get("entries", []):
                content = entry.get("content", {})
                if content.get("entryType") == "TimelineTimelineItem":
                    user_result = (
                        content.get("itemContent", {})
                        .get("user_results", {})
                        .get("result", {})
                    )
                    legacy = user_result.get("legacy", {})
                    if legacy.get("screen_name"):
                        members.append({
                            "handle": legacy["screen_name"],
                            "name": legacy.get("name", ""),
                            "id": user_result.get("rest_id", ""),
                        })
        return members

    # --- Write operations ---

    def create_list(self, name: str, description: str = "",
                    private: bool = True) -> str | None:
        """Create a Twitter list. Returns list_id or None."""
        data = self._graphql_post("CreateList", {
            "isPrivate": private,
            "name": name,
            "description": description,
        })
        list_data = data.get("data", {}).get("list", {})
        list_id = list_data.get("id_str") or list_data.get("id")
        return str(list_id) if list_id else None

    def add_list_member(self, list_id: str, user_id: str) -> bool:
        """Add a user to a Twitter list by REST ID."""
        try:
            self._graphql_post("ListAddMember", {
                "listId": list_id, "userId": user_id,
            })
            return True
        except RuntimeError:
            return False

    def remove_list_member(self, list_id: str, user_id: str) -> bool:
        """Remove a user from a Twitter list by REST ID."""
        try:
            self._graphql_post("ListRemoveMember", {
                "listId": list_id, "userId": user_id,
            })
            return True
        except RuntimeError:
            return False

    def add_bookmark(self, tweet_id: str) -> bool:
        """Bookmark a tweet."""
        try:
            self._graphql_post("CreateBookmark", {
                "tweet_id": tweet_id,
            })
            return True
        except RuntimeError:
            return False

    # --- Internal helpers ---

    def _extract_timeline_tweets(self, data: dict) -> list[dict]:
        """Extract tweet entries from a standard timeline response."""
        instructions = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline_v2", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        # Some endpoints nest differently
        if not instructions:
            for key in ("home_timeline_urt", "bookmark_timeline_v2", "timeline_v2"):
                nested = data.get("data", {}).get(key, {})
                if nested:
                    instructions = nested.get("timeline", {}).get("instructions", [])
                    if instructions:
                        break
        return self._extract_instructions_tweets(instructions)

    def _extract_instructions_tweets(self, instructions: list) -> list[dict]:
        """Extract tweets from timeline instructions."""
        tweets = []
        for instruction in instructions:
            if instruction.get("type") not in ("TimelineAddEntries", None):
                continue
            for entry in instruction.get("entries", []):
                content = entry.get("content", {})
                if content.get("entryType") != "TimelineTimelineItem":
                    continue
                tweet_result = (
                    content.get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", {})
                if not tweet_result or tweet_result.get("__typename") == "TweetTombstone":
                    continue

                legacy = tweet_result.get("legacy", {})
                user = tweet_result.get("core", {}).get("user_results", {}).get("result", {})
                user_legacy = user.get("legacy", {})

                tweets.append({
                    "id": legacy.get("id_str", tweet_result.get("rest_id", "")),
                    "text": legacy.get("full_text", ""),
                    "author_handle": user_legacy.get("screen_name", ""),
                    "author_name": user_legacy.get("name", ""),
                    "created_at": legacy.get("created_at", ""),
                    "retweet_count": legacy.get("retweet_count", 0),
                    "favorite_count": legacy.get("favorite_count", 0),
                    "reply_count": legacy.get("reply_count", 0),
                    "url": f"https://x.com/{user_legacy.get('screen_name', '_')}/status/{legacy.get('id_str', '')}",
                })
        return tweets
```

- [ ] **Step 2: Verify import works**

```bash
cd /Volumes/main-drive/ai-PA/twitter-cli && poetry run python -c "from twitter_cli.client import TwitterClient; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add twitter-cli/src/twitter_cli/client.py
git commit -m "feat(twitter-cli): add TwitterClient with curl_cffi TLS fingerprinting"
```

---

## Chunk 2: CLI Layer and Formatters

### Task 5: Formatters — JSON and human-readable output

**Files:**
- Create: `twitter-cli/src/twitter_cli/formatters.py`

- [ ] **Step 1: Write formatters.py**

```python
"""Output formatting for twitter-cli."""
import json
import sys


def format_output(data, fmt: str = "json") -> str:
    """Format data for output.

    Args:
        data: Dict or list to format.
        fmt: 'json' or 'text'.
    """
    if fmt == "json":
        indent = 2 if sys.stdout.isatty() else None
        return json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    if fmt == "text":
        return _format_text(data)
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _format_text(data) -> str:
    """Human-readable text output."""
    if isinstance(data, list):
        return "\n---\n".join(_format_item(item) for item in data)
    if isinstance(data, dict):
        return _format_item(data)
    return str(data)


def _format_item(item: dict) -> str:
    """Format a single item as key: value lines."""
    lines = []
    for key, value in item.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str, ensure_ascii=False)
        lines.append(f"{key}: {value}")
    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add twitter-cli/src/twitter_cli/formatters.py
git commit -m "feat(twitter-cli): add JSON/text output formatters"
```

---

### Task 6: CLI — Click commands with read/write groups

**Files:**
- Create: `twitter-cli/src/twitter_cli/cli.py`
- Create: `twitter-cli/tests/test_cli.py`

- [ ] **Step 1: Write cli.py**

```python
"""Click-based CLI for Twitter operations."""
import json
import sys

import click

from .formatters import format_output

# Default Smaug config path (overridable via env or --config)
DEFAULT_CONFIG_PATH = "/app/smaug-config/smaug.config.json"


def _get_client(config_path: str):
    """Lazy-import and create client to keep CLI startup fast."""
    from .client import TwitterClient
    return TwitterClient(config_path)


def _output(data, fmt: str):
    """Print formatted output and exit."""
    click.echo(format_output(data, fmt))


def _error(message: str, code: int = 1):
    """Print error as JSON to stdout (agent-parseable) and exit."""
    click.echo(json.dumps({"status": "error", "error": message}))
    sys.exit(code)


@click.group()
@click.option("--config", envvar="TWITTER_CONFIG_PATH",
              default=DEFAULT_CONFIG_PATH,
              help="Path to Smaug config JSON.")
@click.pass_context
def cli(ctx, config):
    """Twitter CLI — read and write Twitter with TLS fingerprinting."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# --- Schema discovery ---

COMMAND_SCHEMA = {
    "read": {
        "feed": {"description": "Your home timeline", "params": {"count": "int (default 20)"}},
        "user": {"description": "A user's recent tweets", "params": {"handle": "required", "count": "int (default 20)"}},
        "bookmarks": {"description": "Your bookmarked tweets", "params": {"count": "int (default 20)"}},
        "search": {"description": "Search tweets", "params": {"query": "required", "count": "int (default 20)"}},
        "list": {"description": "Members of a Twitter list", "params": {"list_id": "required"}},
        "tweet": {"description": "A tweet and its replies (flat)", "params": {"tweet_id": "required"}},
    },
    "write": {
        "bookmark": {"description": "Bookmark a tweet", "params": {"tweet_id": "required"}},
        "list-add": {"description": "Add user to a list", "params": {"list_id": "required", "handle": "required"}},
        "list-remove": {"description": "Remove user from a list", "params": {"list_id": "required", "handle": "required"}},
    },
}


@cli.command()
@click.argument("command", required=False)
def schema(command):
    """List available commands, or details for a specific command."""
    if not command:
        output = {}
        for group, cmds in COMMAND_SCHEMA.items():
            output[group] = [
                {"command": f"{group} {name}", "description": meta["description"]}
                for name, meta in cmds.items()
            ]
        click.echo(format_output(output, "json"))
        return

    # Look up specific command
    parts = command.split(" ", 1)
    group = parts[0] if parts else ""
    name = parts[1] if len(parts) > 1 else ""

    if group in COMMAND_SCHEMA and name in COMMAND_SCHEMA[group]:
        meta = COMMAND_SCHEMA[group][name]
        click.echo(format_output({
            "command": f"{group} {name}",
            "description": meta["description"],
            "params": meta["params"],
        }, "json"))
    else:
        _error(f"Unknown command: {command}. Run 'twitter-cli schema' to list all.")


# --- Read commands ---

@cli.group()
def read():
    """Read operations: feed, user, bookmarks, search, list, tweet."""
    pass


@read.command()
@click.option("--count", default=20, help="Number of tweets to fetch.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def feed(ctx, count, fmt):
    """Fetch your home timeline."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.get_home_timeline(count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command()
@click.argument("handle")
@click.option("--count", default=20, help="Number of tweets to fetch.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def user(ctx, handle, count, fmt):
    """Fetch a user's recent tweets."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.get_user_tweets(handle, count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command()
@click.option("--count", default=20, help="Number of bookmarks to fetch.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def bookmarks(ctx, count, fmt):
    """Fetch your bookmarked tweets."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.get_bookmarks(count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command()
@click.argument("query")
@click.option("--count", default=20, help="Number of results.")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def search(ctx, query, count, fmt):
    """Search tweets."""
    client = _get_client(ctx.obj["config_path"])
    try:
        tweets = client.search_tweets(query, count=count)
        _output(tweets, fmt)
    finally:
        client.close()


@read.command("list")
@click.argument("list_id")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def read_list(ctx, list_id, fmt):
    """Fetch members of a Twitter list."""
    client = _get_client(ctx.obj["config_path"])
    try:
        members = client.get_list_members(list_id)
        _output(members, fmt)
    finally:
        client.close()


@read.command()
@click.argument("tweet_id")
@click.option("--json", "fmt", flag_value="json", default=True)
@click.option("--text", "fmt", flag_value="text")
@click.pass_context
def tweet(ctx, tweet_id, fmt):
    """Fetch a tweet and its replies."""
    client = _get_client(ctx.obj["config_path"])
    try:
        data = client.get_tweet_detail(tweet_id)
        _output(data, fmt)
    finally:
        client.close()


# --- Write commands ---

@cli.group()
def write():
    """Write operations: bookmark, list-add, list-remove."""
    pass


@write.command()
@click.argument("tweet_id")
@click.pass_context
def bookmark(ctx, tweet_id):
    """Bookmark a tweet."""
    client = _get_client(ctx.obj["config_path"])
    try:
        ok = client.add_bookmark(tweet_id)
        _output({"status": "ok" if ok else "error", "tweet_id": tweet_id}, "json")
    finally:
        client.close()


@write.command("list-add")
@click.argument("list_id")
@click.argument("handle")
@click.pass_context
def list_add(ctx, list_id, handle):
    """Add a user to a Twitter list."""
    client = _get_client(ctx.obj["config_path"])
    try:
        user_id = client.get_user_rest_id(handle)
        if not user_id:
            _error(f"User not found: {handle}")
        ok = client.add_list_member(list_id, user_id)
        _output({"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}, "json")
    finally:
        client.close()


@write.command("list-remove")
@click.argument("list_id")
@click.argument("handle")
@click.pass_context
def list_remove(ctx, list_id, handle):
    """Remove a user from a Twitter list."""
    client = _get_client(ctx.obj["config_path"])
    try:
        user_id = client.get_user_rest_id(handle)
        if not user_id:
            _error(f"User not found: {handle}")
        ok = client.remove_list_member(list_id, user_id)
        _output({"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}, "json")
    finally:
        client.close()
```

- [ ] **Step 2: Write basic CLI tests**

```python
# twitter-cli/tests/test_cli.py
import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from twitter_cli.cli import cli


def test_schema_lists_all_commands():
    """Schema command returns all read and write commands."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "read" in data
    assert "write" in data
    read_cmds = [c["command"] for c in data["read"]]
    assert "read feed" in read_cmds
    assert "read user" in read_cmds


def test_schema_specific_command():
    """Schema for a specific command returns its details."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "read feed"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["command"] == "read feed"
    assert "count" in data["params"]


def test_schema_unknown_command():
    """Schema for unknown command returns error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "read nonexistent"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["status"] == "error"
```

- [ ] **Step 3: Run tests**

```bash
cd /Volumes/main-drive/ai-PA/twitter-cli && poetry run pytest tests/test_cli.py -v
```
Expected: 3 passed

- [ ] **Step 4: Verify CLI entry point**

```bash
cd /Volumes/main-drive/ai-PA/twitter-cli && poetry run twitter-cli schema
```
Expected: JSON listing of all commands

- [ ] **Step 5: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add twitter-cli/src/twitter_cli/cli.py twitter-cli/tests/test_cli.py
git commit -m "feat(twitter-cli): add Click CLI with read/write commands and schema discovery"
```

---

## Chunk 3: Curator-Radar Migration

### Task 7: Update curator-radar to import from twitter-cli

**Files:**
- Modify: `curator-radar/curator_radar/twitter_backfill.py`
- Modify: `curator-radar/curator_radar/twitter_list_sync.py`
- Modify: `curator-radar/curator_radar/routes.py`
- Delete: `curator-radar/curator_radar/twitter_client.py`

Three categories of change:
1. **Import**: `from .twitter_client import TwitterClient` → `from twitter_cli.client import TwitterClient`
2. **Constructor**: `TwitterClient(settings)` → `TwitterClient(settings.smaug_config_path)`
3. **Async-to-sync**: `await client.method(...)` → `await asyncio.to_thread(client.method, ...)`, and `await client.close()` → `client.close()` (no await — new client is sync)

- [ ] **Step 1: Update twitter_backfill.py**

Change import (top of file):
```python
# Old: from .twitter_client import TwitterClient
from twitter_cli.client import TwitterClient
import asyncio  # add if not present
```

Call sites to wrap (the function receives client as param, doesn't instantiate):
- `await client.get_retweeters(tweet_id)` → `await asyncio.to_thread(client.get_retweeters, tweet_id)`

Note: `session.*` calls stay async (SQLAlchemy async session). Only `client.*` calls get wrapped.

- [ ] **Step 2: Update twitter_list_sync.py**

Change import:
```python
# Old: from .twitter_client import TwitterClient
from twitter_cli.client import TwitterClient
import asyncio  # add if not present
```

Call sites to wrap:
- `await client.create_list(name, desc, private)` → `await asyncio.to_thread(client.create_list, name, desc, private)`
- `await client.get_user_rest_id(handle)` → `await asyncio.to_thread(client.get_user_rest_id, handle)`
- `await client.add_list_member(list_id, user_id)` → `await asyncio.to_thread(client.add_list_member, list_id, user_id)`
- `await client.remove_list_member(list_id, user_id)` → `await asyncio.to_thread(client.remove_list_member, list_id, user_id)`

- [ ] **Step 3: Update routes.py — imports and constructor**

Change import:
```python
# Old: from .twitter_client import TwitterClient
from twitter_cli.client import TwitterClient
```

All 4 `TwitterClient` instantiation sites in routes.py:
1. `_run_twitter_daily()` (line ~147): `TwitterClient(settings)` → `TwitterClient(settings.smaug_config_path)`
2. `_fetch()` inside `twitter_fetch_likers` (line ~198): same change
3. `twitter_sync_list` route (line ~226): same change
4. Any other route that creates a `TwitterClient`

- [ ] **Step 4: Update routes.py — async-to-sync client calls**

All `await client.close()` calls become `client.close()` (7 sites in routes.py):
- `_run_twitter_daily` finally block
- `_fetch` finally block inside `twitter_fetch_likers`
- `twitter_sync_list` finally block

All `await client.method()` in routes that call the client directly:
- In `twitter_sync_list`: `await sync_twitter_list(...)` — this function itself has the client calls, already handled in Step 2

- [ ] **Step 5: Delete old twitter_client.py**

```bash
rm /Volumes/main-drive/ai-PA/curator-radar/curator_radar/twitter_client.py
```

- [ ] **Step 6: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add curator-radar/curator_radar/twitter_backfill.py \
       curator-radar/curator_radar/twitter_list_sync.py \
       curator-radar/curator_radar/routes.py
git rm curator-radar/curator_radar/twitter_client.py
git commit -m "refactor: migrate curator-radar to twitter-cli client"
```

---

### Task 8: Update Dockerfile and docker-compose

**Files:**
- Modify: `curator-radar/Dockerfile`
- Modify: `docker-compose.yml`

The current docker-compose build context is `./curator-radar`. Since `twitter-cli/` is a sibling directory, we change the build context to the repo root and update all COPY paths in the Dockerfile accordingly.

- [ ] **Step 1: Update docker-compose.yml build context**

Change the curator-radar service build section:
```yaml
curator-radar:
  build:
    context: .
    dockerfile: curator-radar/Dockerfile
```

- [ ] **Step 2: Update Dockerfile — fix existing COPY paths for new root context**

All existing COPY paths must be prefixed with `curator-radar/`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install twitter-cli first (changes less frequently)
COPY twitter-cli/ ./twitter-cli/
RUN pip install --no-cache-dir ./twitter-cli

# Install curator-radar dependencies
COPY curator-radar/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY curator-radar/curator_radar/ ./curator_radar/

EXPOSE 5145
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:5145/health || exit 1
CMD ["uvicorn", "curator_radar.main:app", "--host", "0.0.0.0", "--port", "5145"]
```

- [ ] **Step 3: Test build**

```bash
cd /Volumes/main-drive/ai-PA && docker-compose build curator-radar
```

- [ ] **Step 4: Test container starts**

```bash
docker-compose up -d curator-radar && sleep 5 && docker-compose logs --tail=20 curator-radar
```

- [ ] **Step 5: Verify health check**

```bash
curl -f http://localhost:5145/health
```

- [ ] **Step 6: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add curator-radar/Dockerfile docker-compose.yml
git commit -m "build: add twitter-cli to curator-radar container"
```

---

## Chunk 4: Agent Access Routes and Letta Tool

### Task 9: Add agent-access routes to curator-radar

**Files:**
- Modify: `curator-radar/curator_radar/routes.py`

Add new routes that expose twitter-cli's read operations via HTTP for the Letta tool to call.

- [ ] **Step 1: Add new routes to routes.py**

Append these routes after the existing twitter routes:

```python
# --- Twitter Agent Access Routes ---

@router.get("/twitter/feed")
async def twitter_feed(count: int = 20):
    """Fetch home timeline for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_home_timeline, count)
        return {"status": "ok", "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/user/{handle}")
async def twitter_user_tweets(handle: str, count: int = 20):
    """Fetch a user's tweets for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_user_tweets, handle, count)
        return {"status": "ok", "handle": handle, "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/search")
async def twitter_search(q: str, count: int = 20):
    """Search tweets for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.search_tweets, q, count)
        return {"status": "ok", "query": q, "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/tweet/{tweet_id}")
async def twitter_tweet_detail(tweet_id: str):
    """Fetch a tweet and its replies for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        data = await asyncio.to_thread(client.get_tweet_detail, tweet_id)
        return {"status": "ok", "data": data}
    finally:
        client.close()


@router.get("/twitter/bookmarks")
async def twitter_bookmarks_read(count: int = 20):
    """Fetch bookmarked tweets via API for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        tweets = await asyncio.to_thread(client.get_bookmarks, count)
        return {"status": "ok", "tweets": tweets}
    finally:
        client.close()


@router.get("/twitter/list/{list_id}/members")
async def twitter_list_members(list_id: str, count: int = 100):
    """Fetch list members for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        members = await asyncio.to_thread(client.get_list_members, list_id, count)
        return {"status": "ok", "list_id": list_id, "members": members}
    finally:
        client.close()


@router.post("/twitter/bookmark/{tweet_id}")
async def twitter_bookmark_tweet(tweet_id: str):
    """Bookmark a tweet for agent access."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        ok = await asyncio.to_thread(client.add_bookmark, tweet_id)
        return {"status": "ok" if ok else "error", "tweet_id": tweet_id}
    finally:
        client.close()


@router.post("/twitter/list-add")
async def twitter_list_add(list_id: str, handle: str):
    """Add a user to a Twitter list."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        user_id = await asyncio.to_thread(client.get_user_rest_id, handle)
        if not user_id:
            return {"status": "error", "error": f"User not found: {handle}"}
        ok = await asyncio.to_thread(client.add_list_member, list_id, user_id)
        return {"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}
    finally:
        client.close()


@router.post("/twitter/list-remove")
async def twitter_list_remove(list_id: str, handle: str):
    """Remove a user from a Twitter list."""
    client = TwitterClient(settings.smaug_config_path)
    try:
        user_id = await asyncio.to_thread(client.get_user_rest_id, handle)
        if not user_id:
            return {"status": "error", "error": f"User not found: {handle}"}
        ok = await asyncio.to_thread(client.remove_list_member, list_id, user_id)
        return {"status": "ok" if ok else "error", "handle": handle, "list_id": list_id}
    finally:
        client.close()
```

Also add `import asyncio` at the top of routes.py if not already present.

- [ ] **Step 2: Rebuild and test**

```bash
cd /Volumes/main-drive/ai-PA && docker-compose up -d --build curator-radar
sleep 5
# Test a read-only endpoint
curl http://localhost:5145/v1/twitter/curators?top_k=5
```

- [ ] **Step 3: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add curator-radar/curator_radar/routes.py
git commit -m "feat: add Twitter agent-access routes to curator-radar"
```

---

### Task 10: Create run_twitter Letta tool

**Files:**
- Create: `letta/twitter_tools.py`

- [ ] **Step 1: Write the Letta tool**

Follow the `query_curator_radar` pattern — progressive disclosure, HTTP calls to curator-radar.

**Critical Letta requirement:** `ENDPOINTS` dict MUST be inside the function body (Letta extracts function source only; module-level constants cause `NameError`).

```python
from typing import Dict, Any, Optional


def run_twitter(command: str, params: Optional[str] = None) -> Dict[str, Any]:
    """
    Interact with Twitter — read feeds, search, manage lists, bookmark tweets.

    Use command="schema" to see all available commands and their parameters.
    Use command="schema <name>" to see details for a specific command.

    Quick start:
      command="feed"                         -- Your home timeline
      command="user"    params='{"handle":"elonmusk","count":10}'  -- Someone's tweets
      command="search"  params='{"q":"AI agents"}'                 -- Search
      command="curators"                     -- Top Twitter curators
      command="bookmarks"                    -- Your bookmarks
      command="schema"                       -- List all commands

    Args:
        command: Command name or "schema" for discovery (REQUIRED)
        params: Optional JSON string of parameters (e.g. '{"count": 10}')

    Returns:
        Dictionary with status and the API response.
    """
    import json
    import traceback
    import urllib.request
    import urllib.parse

    # ENDPOINTS must be inside function body (Letta extracts function source only)
    ENDPOINTS = {
        # --- Read ---
        "feed": {
            "method": "GET",
            "path": "/twitter/feed",
            "description": "Your home timeline",
            "params": {"count": "int (default 20)"},
        },
        "user": {
            "method": "GET",
            "path": "/twitter/user/{handle}",
            "description": "A user's recent tweets and retweets",
            "params": {"handle": "str (required, in path)", "count": "int (default 20)"},
        },
        "bookmarks": {
            "method": "GET",
            "path": "/twitter/bookmarks",
            "description": "Your bookmarked tweets",
            "params": {"count": "int (default 20)"},
        },
        "search": {
            "method": "GET",
            "path": "/twitter/search",
            "description": "Search tweets",
            "params": {"q": "str (required)", "count": "int (default 20)"},
        },
        "tweet": {
            "method": "GET",
            "path": "/twitter/tweet/{tweet_id}",
            "description": "A tweet and its replies",
            "params": {"tweet_id": "str (required, in path)"},
        },
        "list-members": {
            "method": "GET",
            "path": "/twitter/list/{list_id}/members",
            "description": "Members of a Twitter list",
            "params": {"list_id": "str (required, in path)", "count": "int (default 100)"},
        },
        "curators": {
            "method": "GET",
            "path": "/twitter/curators",
            "description": "Top Twitter curators by retweeter overlap score",
            "params": {"top_k": "int (default 50)"},
        },
        "status": {
            "method": "GET",
            "path": "/twitter/status",
            "description": "Twitter ingestion progress and fetch status",
            "params": {},
        },
        # --- Write ---
        "bookmark": {
            "method": "POST",
            "path": "/twitter/bookmark/{tweet_id}",
            "description": "Bookmark a tweet",
            "params": {"tweet_id": "str (required, in path)"},
        },
        "list-add": {
            "method": "POST",
            "path": "/twitter/list-add",
            "description": "Add a user to a Twitter list",
            "params": {"list_id": "str (required)", "handle": "str (required)"},
        },
        "list-remove": {
            "method": "POST",
            "path": "/twitter/list-remove",
            "description": "Remove a user from a Twitter list",
            "params": {"list_id": "str (required)", "handle": "str (required)"},
        },
    }

    try:
        clean = command.strip().strip("/")

        # Schema discovery
        if clean == "schema":
            groups = {"read": [], "write": [], "pipeline": []}
            for name, meta in ENDPOINTS.items():
                if meta["method"] == "GET":
                    group = "read"
                elif name in ("run", "score"):
                    group = "pipeline"
                else:
                    group = "write"
                groups[group].append(
                    {"command": name, "description": meta["description"]}
                )
            return {"status": "ok", "result": groups}

        if clean.startswith("schema "):
            target = clean.split(" ", 1)[1].strip()
            if target in ENDPOINTS:
                meta = ENDPOINTS[target]
                return {"status": "ok", "result": {
                    "command": target,
                    "method": meta["method"],
                    "description": meta["description"],
                    "params": meta["params"] or "(none)",
                }}
            return {"status": "error", "error_message": f"Unknown command: {target}. Use command='schema' to list all."}

        # Resolve endpoint
        meta = ENDPOINTS.get(clean)
        if not meta:
            return {"status": "error", "error_message": f"Unknown command: {clean}. Use command='schema' to list all."}

        base_url = "http://curator-radar:5145/v1"

        query_params = {}
        if params:
            query_params = json.loads(params)

        # Build URL, substituting path parameters
        path = meta["path"]
        path_params = {}
        for key in list(query_params.keys()):
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(query_params.pop(key)))
                path_params[key] = True

        url = f"{base_url}{path}"

        if meta["method"] == "GET" and query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        req = urllib.request.Request(url, method=meta["method"])
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read().decode())

        return {"status": "ok", "result": data}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

- [ ] **Step 2: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/twitter_tools.py
git commit -m "feat: add run_twitter Letta tool with progressive disclosure"
```

---

### Task 11: Create registration script

**Files:**
- Create: `letta/register_twitter_tools.py`

- [ ] **Step 1: Write registration script**

Follow the pattern from `letta/register_gmail_tools.py` or existing registration scripts.

```python
#!/usr/bin/env python3
"""Register run_twitter tool with the Letta server."""
import os
import requests
from pathlib import Path

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def main():
    # Read the full source file (not just the function — ENDPOINTS is inside the function body)
    source_path = Path(__file__).parent / "twitter_tools.py"
    module_source = source_path.read_text()

    # Check for existing tool
    resp = requests.get(f"{LETTA_BASE_URL}/v1/tools/", params={"limit": 100}, timeout=30)
    resp.raise_for_status()
    existing = {t["name"]: t["id"] for t in resp.json()}

    tool_name = "run_twitter"
    tool_payload = {
        "name": tool_name,
        "description": "Interact with Twitter — read feeds, search, manage lists, bookmark tweets.",
        "source_code": module_source,
        "source_type": "python",
        "tags": ["twitter"],
    }

    if tool_name in existing:
        tool_id = existing[tool_name]
        resp = requests.patch(
            f"{LETTA_BASE_URL}/v1/tools/{tool_id}/",
            json=tool_payload,
            timeout=30,
        )
        resp.raise_for_status()
        print(f"Updated tool: {tool_name} ({tool_id})")
    else:
        resp = requests.post(
            f"{LETTA_BASE_URL}/v1/tools/",
            json=tool_payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"Created tool: {tool_name} ({result.get('id', 'unknown')})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register the tool**

```bash
cd /Volumes/main-drive/ai-PA/letta && LETTA_BASE_URL=http://localhost:8283 python register_twitter_tools.py
```

- [ ] **Step 3: Commit**

```bash
cd /Volumes/main-drive/ai-PA
git add letta/register_twitter_tools.py
git commit -m "feat: add run_twitter Letta tool registration script"
```

---

## Chunk 5: Integration Testing and Smoke Test

### Task 12: End-to-end smoke test

- [ ] **Step 1: Rebuild curator-radar with twitter-cli**

```bash
cd /Volumes/main-drive/ai-PA && docker-compose up -d --build curator-radar
```

- [ ] **Step 2: Verify existing pipeline still works**

```bash
# Check status (should return existing data)
curl http://localhost:5145/v1/twitter/status

# Check curators (should return existing scored curators)
curl http://localhost:5145/v1/twitter/curators?top_k=5
```

- [ ] **Step 3: Test new agent routes**

```bash
# These may fail if cookies are expired — that's expected.
# What matters is that the routes exist and return proper error format.
curl http://localhost:5145/v1/twitter/feed?count=5
curl "http://localhost:5145/v1/twitter/search?q=AI+agents&count=5"
```

- [ ] **Step 4: Test Letta tool registration**

```bash
cd /Volumes/main-drive/ai-PA/letta
LETTA_BASE_URL=http://localhost:8283 python register_twitter_tools.py
```

- [ ] **Step 5: Verify tool is available**

```bash
curl -s http://localhost:8283/v1/tools/?limit=100 | python3 -c "
import sys, json
tools = json.load(sys.stdin)
twitter = [t for t in tools if t['name'] == 'run_twitter']
print(f'Found: {len(twitter)} run_twitter tool(s)')
if twitter:
    print(f'ID: {twitter[0][\"id\"]}')
"
```

- [ ] **Step 6: Final commit (if any unstaged changes remain)**

```bash
cd /Volumes/main-drive/ai-PA
git status
# Stage only specific files that are part of this work — do NOT use git add -A
```
