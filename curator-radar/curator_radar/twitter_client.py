"""
Lightweight async client for Twitter's GraphQL API.
Uses browser auth cookies from Smaug's config file.
"""
import asyncio
import json
import logging
import httpx
from dataclasses import dataclass
from pathlib import Path
from .settings import Settings

logger = logging.getLogger(__name__)

RETWEETERS_QUERY_ID = "qVWT1Tn1FiklyVDqYiOhLg"
CREATE_LIST_QUERY_ID = "nHFMQuE0r6yVEGmPSSbDdg"
LIST_ADD_MEMBER_QUERY_ID = "sw71TVciw0CoWPcFfIhrnA"
LIST_REMOVE_MEMBER_QUERY_ID = "cvl5jMbF1DqPRJalJTkNzA"
USER_BY_SCREEN_NAME_QUERY_ID = "xmU6X_CKVnQ5lSrCbAmJsg"

GRAPHQL_BASE = "https://x.com/i/api/graphql"

FAVORITERS_FEATURES = {
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

# Bearer token used by Twitter's web client (public, not a secret)
BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"


@dataclass
class TwitterAuth:
    auth_token: str = ""
    ct0: str = ""


@dataclass
class TwitterRateState:
    remaining: int = 500
    reset_at: float = 0.0
    consecutive_429s: int = 0
    base_delay: float = 2.0
    current_delay: float = 2.0


class TwitterClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth = self._load_auth()
        self.rate = TwitterRateState()
        self._client: httpx.AsyncClient | None = None

    def _load_auth(self) -> TwitterAuth:
        """Load Twitter auth cookies from Smaug's config file."""
        config_path = Path(self.settings.smaug_config_path)
        if not config_path.exists():
            logger.error(f"Smaug config not found: {config_path}")
            return TwitterAuth()
        config = json.loads(config_path.read_text())
        twitter = config.get("twitter", {})
        return TwitterAuth(
            auth_token=twitter.get("authToken", ""),
            ct0=twitter.get("ct0", ""),
        )

    def reload_auth(self):
        """Reload auth cookies (call if cookies were refreshed)."""
        self.auth = self._load_auth()
        self._client = None  # Force new client with fresh headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {BEARER_TOKEN}",
                    "x-csrf-token": self.auth.ct0,
                    "x-twitter-auth-type": "OAuth2Session",
                    "x-twitter-active-user": "yes",
                    "Cookie": f"auth_token={self.auth.auth_token}; ct0={self.auth.ct0}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _wait(self):
        await asyncio.sleep(self.rate.current_delay)

    async def _handle_rate_limit(self, resp: httpx.Response):
        if "x-rate-limit-remaining" in resp.headers:
            self.rate.remaining = int(resp.headers["x-rate-limit-remaining"])
        if "x-rate-limit-reset" in resp.headers:
            self.rate.reset_at = float(resp.headers["x-rate-limit-reset"])

        if resp.status_code == 429:
            self.rate.consecutive_429s += 1
            wait = min(self.rate.base_delay * (2 ** self.rate.consecutive_429s), 120)
            self.rate.current_delay = wait
            logger.warning(f"Rate limited (429). Waiting {wait:.0f}s. Consecutive: {self.rate.consecutive_429s}")
            await asyncio.sleep(wait)
        else:
            if self.rate.consecutive_429s > 0:
                self.rate.consecutive_429s = 0
                self.rate.current_delay = self.rate.base_delay

    async def get_retweeters(self, tweet_id: str) -> list[dict]:
        """Fetch all users who retweeted a tweet. Returns list of {handle, name}."""
        all_users = []
        cursor = None

        while True:
            await self._wait()
            client = await self._get_client()

            variables = {
                "tweetId": tweet_id,
                "count": 100,
                "includePromotedContent": False,
                "withDownvotePerspective": False,
                "withReactionsMetadata": False,
                "withReactionsPerspective": False,
                "withSuperFollowsTweetFields": False,
                "withSuperFollowsUserFields": False,
            }
            if cursor:
                variables["cursor"] = cursor

            params = {
                "variables": json.dumps(variables),
                "features": json.dumps(FAVORITERS_FEATURES),
            }

            resp = await client.get(
                f"{GRAPHQL_BASE}/{RETWEETERS_QUERY_ID}/Retweeters",
                params=params,
            )
            await self._handle_rate_limit(resp)

            if resp.status_code == 429:
                continue
            if resp.status_code != 200:
                print(f"Retweeters API error {resp.status_code} for tweet {tweet_id}: {resp.text[:200]}", flush=True)
                break

            data = resp.json()
            timeline = (
                data.get("data", {})
                .get("retweeters_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )

            found_users = False
            next_cursor = None

            for instruction in timeline:
                entries = instruction.get("entries", [])
                for entry in entries:
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

        logger.info(f"Tweet {tweet_id}: {len(all_users)} retweeters")
        return all_users

    async def create_list(self, name: str, description: str = "", private: bool = True) -> str | None:
        """Create a Twitter list. Returns list_id or None on failure."""
        await self._wait()
        client = await self._get_client()

        resp = await client.post(
            f"{GRAPHQL_BASE}/{CREATE_LIST_QUERY_ID}/CreateList",
            json={"variables": {"isPrivate": private, "name": name, "description": description}, "features": {}},
        )
        await self._handle_rate_limit(resp)

        if resp.status_code != 200:
            logger.error(f"CreateList error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        list_data = data.get("data", {}).get("list", {})
        list_id = list_data.get("id_str") or list_data.get("id")
        logger.info(f"Created Twitter list '{name}': {list_id}")
        return str(list_id) if list_id else None

    async def add_list_member(self, list_id: str, user_id: str) -> bool:
        """Add a user to a Twitter list by user REST ID."""
        await self._wait()
        client = await self._get_client()
        resp = await client.post(
            f"{GRAPHQL_BASE}/{LIST_ADD_MEMBER_QUERY_ID}/ListAddMember",
            json={"variables": {"listId": list_id, "userId": user_id}, "features": {}},
        )
        await self._handle_rate_limit(resp)
        return resp.status_code == 200

    async def remove_list_member(self, list_id: str, user_id: str) -> bool:
        """Remove a user from a Twitter list by user REST ID."""
        await self._wait()
        client = await self._get_client()
        resp = await client.post(
            f"{GRAPHQL_BASE}/{LIST_REMOVE_MEMBER_QUERY_ID}/ListRemoveMember",
            json={"variables": {"listId": list_id, "userId": user_id}, "features": {}},
        )
        await self._handle_rate_limit(resp)
        return resp.status_code == 200

    async def get_user_rest_id(self, screen_name: str) -> str | None:
        """Look up a user's REST ID by screen name."""
        await self._wait()
        client = await self._get_client()

        variables = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        resp = await client.get(
            f"{GRAPHQL_BASE}/{USER_BY_SCREEN_NAME_QUERY_ID}/UserByScreenName",
            params={"variables": json.dumps(variables), "features": json.dumps(USER_FEATURES)},
        )
        await self._handle_rate_limit(resp)

        if resp.status_code != 200:
            return None

        data = resp.json()
        return data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")
