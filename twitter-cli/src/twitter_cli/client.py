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
IMPERSONATE = "chrome136"

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
                "withDownvotePerspective": False,
                "withReactionsMetadata": False,
                "withReactionsPerspective": False,
                "withSuperFollowsTweetFields": True,
                "withSuperFollowsUserFields": True,
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
                        core = user_result.get("core", {})
                        handle = legacy.get("screen_name") or core.get("screen_name")
                        if handle:
                            all_users.append({
                                "handle": handle,
                                "name": legacy.get("name") or core.get("name", ""),
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
                    core = user_result.get("core", {})
                    handle = legacy.get("screen_name") or core.get("screen_name")
                    if handle:
                        members.append({
                            "handle": handle,
                            "name": legacy.get("name") or core.get("name", ""),
                            "id": user_result.get("rest_id", ""),
                        })
        return members

    def get_list_tweets(self, list_id: str, count: int = 20) -> list[dict]:
        """Fetch recent tweets from a Twitter list timeline."""
        data = self._graphql_get("ListLatestTweetsTimeline", {
            "listId": list_id,
            "count": count,
        })
        instructions = (
            data.get("data", {})
            .get("list", {})
            .get("tweets_timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )
        return self._extract_instructions_tweets(instructions)

    def get_my_lists(self) -> list[dict]:
        """Fetch the authenticated user's owned and followed lists via v1.1 API."""
        session = self._get_session()
        self._wait()
        resp = session.get("https://x.com/i/api/1.1/lists/list.json")
        if resp.status_code != 200:
            raise RuntimeError(f"lists/list API error {resp.status_code}: {resp.text[:300]}")
        lists = []
        for item in resp.json():
            user = item.get("user", {})
            owner = user.get("screen_name", "") if isinstance(user, dict) else ""
            lists.append({
                "id": item.get("id_str", ""),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "member_count": item.get("member_count", 0),
                "mode": item.get("mode", ""),
                "owner": owner,
            })
        return lists

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
            .get("timeline_v2", data.get("data", {}).get("user", {}).get("result", {}).get("timeline", {}))
            .get("timeline", {})
            .get("instructions", [])
        )
        # Some endpoints nest differently — try flat then one level deep
        if not instructions:
            data_root = data.get("data", {})
            # Flat: data.<key>.timeline.instructions
            for key in ("home_timeline_urt", "bookmark_timeline_v2", "timeline_v2"):
                nested = data_root.get(key, {})
                if nested:
                    instructions = nested.get("timeline", {}).get("instructions", [])
                    if not instructions:
                        # home_timeline_urt has instructions directly (no .timeline wrapper)
                        instructions = nested.get("instructions", [])
                    if instructions:
                        break
            # Nested: data.<parent>.<key> (e.g. data.home.home_timeline_urt)
            if not instructions:
                for parent_key in data_root:
                    parent = data_root[parent_key]
                    if not isinstance(parent, dict):
                        continue
                    for key in ("home_timeline_urt", "timeline", "timeline_v2"):
                        nested = parent.get(key, {})
                        if nested and isinstance(nested, dict):
                            instructions = nested.get("instructions", [])
                            if not instructions:
                                instructions = nested.get("timeline", {}).get("instructions", [])
                            if instructions:
                                break
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
                user_core = user.get("core", {})

                tweets.append({
                    "id": legacy.get("id_str", tweet_result.get("rest_id", "")),
                    "text": legacy.get("full_text", ""),
                    "author_handle": user_legacy.get("screen_name") or user_core.get("screen_name", ""),
                    "author_name": user_legacy.get("name") or user_core.get("name", ""),
                    "created_at": legacy.get("created_at", ""),
                    "retweet_count": legacy.get("retweet_count", 0),
                    "favorite_count": legacy.get("favorite_count", 0),
                    "reply_count": legacy.get("reply_count", 0),
                    "url": f"https://x.com/{user_legacy.get('screen_name') or user_core.get('screen_name', '_')}/status/{legacy.get('id_str', '')}",
                })
        return tweets
