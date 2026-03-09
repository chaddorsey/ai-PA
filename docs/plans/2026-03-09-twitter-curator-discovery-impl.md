# Twitter Curator Discovery — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend Curator Radar to discover Twitter users who consistently like the same tweets you bookmark, rank them by IDF-weighted overlap, and auto-manage a private Twitter List of top curators.

**Architecture:** Adds a Twitter platform module to the existing Curator Radar service (port 5145). Reads bookmarked tweet IDs from Smaug's output files, fetches likers via Twitter's GraphQL Favoriters endpoint, scores overlap using the same IDF algorithm as GitHub, and syncs a private Twitter List daily. No new Docker containers.

**Tech Stack:** Python 3.12, FastAPI, httpx (async Twitter GraphQL), SQLAlchemy (async + asyncpg), Supabase PostgreSQL, Smaug (bookmark source)

**Design doc:** [2026-03-09-twitter-curator-discovery-design.md](2026-03-09-twitter-curator-discovery-design.md)

---

### Context for Implementer

**Key files to reference:**
- **Existing service:** `/Volumes/main-drive/ai-PA/curator-radar/curator_radar/` — all modules
- **Scoring pattern:** `curator_radar/scoring.py` — IDF + earlyness SQL, `score_curators()` function
- **GitHub client pattern:** `curator_radar/github_client.py` — rate-limited async HTTP client with pagination
- **Backfill pattern:** `curator_radar/backfill.py` — checkpoint-based resumable fetch
- **Models:** `curator_radar/models.py` — SQLAlchemy ORM with `Base` declarative base
- **Smaug config:** `/Volumes/main-drive/ai-PA/smaug/smaug.config.json` — Twitter auth cookies (`twitter.authToken`, `twitter.ct0`)
- **Smaug archive:** `/Volumes/main-drive/ai-PA/smaug-data/bookmarks.md` — contains tweet URLs as `x.com/{author}/status/{id}`
- **Smaug state:** `/Volumes/main-drive/ai-PA/smaug-data/.state/bookmarks-state.json`

**Twitter GraphQL Favoriters endpoint:**
- URL: `https://x.com/i/api/graphql/{queryId}/Favoriters`
- Method: GET with `variables` and `features` query params (URL-encoded JSON)
- Auth headers: `Cookie: auth_token={authToken}; ct0={ct0}` and `x-csrf-token: {ct0}`
- Returns paginated user list with `screen_name`, `name`, `rest_id`
- The queryId for Favoriters needs to be discovered from Twitter's main.js bundle (changes periodically)

**Important patterns from existing code:**
- All DB operations use `pg_insert().on_conflict_do_update()` or `.on_conflict_do_nothing()` for idempotency
- Background tasks via FastAPI `BackgroundTasks`
- Settings via Pydantic `BaseSettings` with env var aliases
- Logging via `logging.getLogger(__name__)`

---

### Task 1: Add Twitter models to schema

**Files:**
- Modify: `curator-radar/curator_radar/models.py`

**Step 1: Add platform column to Curator and new Twitter tables**

Add these models after the existing `BackfillCheckpoint` class in `models.py`:

```python
# In models.py, modify Curator class:
# Change primary_key from just user_login to composite (user_login, platform)

class Curator(Base):
    __tablename__ = "curators"

    user_login: Mapped[str] = mapped_column(String(100), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), primary_key=True, default="github")
    overlap_count: Mapped[int] = mapped_column(Integer, default=0)
    overlap_score: Mapped[float] = mapped_column(Float, default=0.0)
    earlyness_mean: Mapped[float] = mapped_column(Float, default=0.0)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)


# Add new Twitter tables after BackfillCheckpoint:

class BookmarkedTweet(Base):
    __tablename__ = "bookmarked_tweets"

    tweet_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    author_handle: Mapped[str] = mapped_column(String(100))
    author_name: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    tweet_url: Mapped[str] = mapped_column(String(300))
    bookmarked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    likers_fetched: Mapped[bool] = mapped_column(Boolean, default=False)


class TweetLiker(Base):
    __tablename__ = "tweet_likers"

    tweet_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_handle: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    user_name: Mapped[str] = mapped_column(String(200), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TwitterList(Base):
    __tablename__ = "twitter_lists"

    list_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    list_name: Mapped[str] = mapped_column(String(100))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TwitterListMember(Base):
    __tablename__ = "twitter_list_members"

    list_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_handle: Mapped[str] = mapped_column(String(100), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**Step 2: Update Settings for Smaug config path**

Add to `curator_radar/settings.py`:

```python
    smaug_config_path: str = Field(
        default="/Volumes/main-drive/ai-PA/smaug/smaug.config.json",
        alias="SMAUG_CONFIG_PATH",
    )
    smaug_data_path: str = Field(
        default="/Volumes/main-drive/ai-PA/smaug-data",
        alias="SMAUG_DATA_PATH",
    )
    twitter_list_name: str = Field(
        default="Curator Radar",
        alias="TWITTER_LIST_NAME",
    )
    twitter_list_size: int = Field(
        default=50,
        alias="TWITTER_LIST_SIZE",
    )
```

**Step 3: Verify models load**

```bash
cd /Volumes/main-drive/ai-PA/curator-radar
python -c "from curator_radar.models import BookmarkedTweet, TweetLiker, TwitterList, TwitterListMember, Curator; print('Models OK')"
```

Expected: `Models OK`

**Step 4: Commit**

```bash
git add curator-radar/curator_radar/models.py curator-radar/curator_radar/settings.py
git commit -m "feat: add Twitter curator models and settings to Curator Radar"
```

---

### Task 2: Handle Curator table migration

The existing `Curator` table has `user_login` as sole PK. We're adding `platform` as a composite PK. Since Curator Radar's DB may or may not be running yet, we need to handle both cases.

**Files:**
- Create: `curator-radar/curator_radar/migrate_curator_platform.py`

**Step 1: Write migration script**

```python
"""
One-time migration: add platform column to curators table.
Safe to run multiple times (idempotent).
Run before starting the service after the model change.
"""
import asyncio
import logging
from sqlalchemy import text
from curator_radar.database import engine

logger = logging.getLogger(__name__)


async def migrate():
    async with engine.begin() as conn:
        # Check if platform column exists
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'curators' AND column_name = 'platform'
        """))
        if result.fetchone():
            print("Migration already applied: platform column exists.")
            return

        print("Adding platform column to curators table...")

        # Add column with default
        await conn.execute(text("""
            ALTER TABLE curators ADD COLUMN platform VARCHAR(20) NOT NULL DEFAULT 'github'
        """))

        # Drop old primary key and create new composite one
        await conn.execute(text("""
            ALTER TABLE curators DROP CONSTRAINT curators_pkey
        """))
        await conn.execute(text("""
            ALTER TABLE curators ADD PRIMARY KEY (user_login, platform)
        """))

        print("Migration complete: curators table now has composite PK (user_login, platform).")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
```

**Step 2: Verify it runs (dry — will fail if DB not up, that's OK)**

```bash
python -c "from curator_radar.migrate_curator_platform import migrate; print('Import OK')"
```

Expected: `Import OK`

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/migrate_curator_platform.py
git commit -m "feat: add Curator table migration for platform column"
```

---

### Task 3: Update scoring for platform awareness

**Files:**
- Modify: `curator-radar/curator_radar/scoring.py`

**Step 1: Parameterize `score_curators()` with platform**

The existing function hardcodes GitHub-specific logic. Refactor to accept a `platform` parameter and handle both GitHub and Twitter scoring:

```python
# scoring.py — replace the full file

import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import StarredRepo, RepoStargazer, Curator, BookmarkedTweet, TweetLiker

logger = logging.getLogger(__name__)


async def score_github_curators(session: AsyncSession, username: str = "chaddorsey") -> int:
    """Score GitHub curators based on repo overlap, IDF weighting, and earlyness."""

    scoring_sql = text("""
        WITH repo_earlyness AS (
            SELECT
                rs.repo_id,
                rs.user_login,
                rs.starred_at,
                CASE
                    WHEN COUNT(*) OVER (PARTITION BY rs.repo_id) <= 1 THEN 0.5
                    ELSE 1.0 - (
                        RANK() OVER (PARTITION BY rs.repo_id ORDER BY COALESCE(rs.starred_at, '2099-01-01'::timestamp))::float
                        / NULLIF(COUNT(*) OVER (PARTITION BY rs.repo_id), 0)
                    )
                END AS earlyness
            FROM repo_stargazers rs
        ),
        user_scores AS (
            SELECT
                re.user_login,
                COUNT(DISTINCT re.repo_id) AS overlap_count,
                SUM(
                    LN(1 + 100000.0 / (1 + sr.stargazers_count))
                    * (1.0 + 0.7 * re.earlyness)
                ) AS overlap_score,
                AVG(re.earlyness) AS earlyness_mean
            FROM repo_earlyness re
            JOIN starred_repos sr ON sr.repo_id = re.repo_id
            WHERE re.user_login != :username
            GROUP BY re.user_login
            HAVING COUNT(DISTINCT re.repo_id) >= 2
        )
        SELECT user_login, overlap_count, overlap_score, earlyness_mean
        FROM user_scores
        ORDER BY overlap_score DESC
    """)

    result = await session.execute(scoring_sql, {"username": username})
    rows = result.fetchall()

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        stmt = pg_insert(Curator).values(
            user_login=row.user_login,
            platform="github",
            overlap_count=row.overlap_count,
            overlap_score=round(row.overlap_score, 4),
            earlyness_mean=round(row.earlyness_mean, 4),
            last_scored_at=now,
            blocked=False,
        ).on_conflict_do_update(
            index_elements=["user_login", "platform"],
            set_={
                "overlap_count": row.overlap_count,
                "overlap_score": round(row.overlap_score, 4),
                "earlyness_mean": round(row.earlyness_mean, 4),
                "last_scored_at": now,
            },
        )
        await session.execute(stmt)
        count += 1
        if count % 1000 == 0:
            await session.commit()

    await session.commit()
    logger.info(f"Scored {count} GitHub curators")
    return count


async def score_twitter_curators(session: AsyncSession) -> int:
    """Score Twitter curators based on tweet-like overlap with IDF weighting.

    IDF formula: LN(1 + C / (1 + likers_count))
    No earlyness component (Twitter likes have no meaningful temporal ordering).
    Minimum threshold: >= 2 overlapping tweets.
    """

    scoring_sql = text("""
        WITH tweet_liker_counts AS (
            SELECT
                tl.tweet_id,
                tl.user_handle,
                COUNT(*) OVER (PARTITION BY tl.tweet_id) AS likers_count
            FROM tweet_likers tl
        ),
        user_scores AS (
            SELECT
                tlc.user_handle AS user_login,
                COUNT(DISTINCT tlc.tweet_id) AS overlap_count,
                SUM(
                    LN(1 + 100000.0 / (1 + tlc.likers_count))
                ) AS overlap_score
            FROM tweet_liker_counts tlc
            GROUP BY tlc.user_handle
            HAVING COUNT(DISTINCT tlc.tweet_id) >= 2
        )
        SELECT user_login, overlap_count, overlap_score
        FROM user_scores
        ORDER BY overlap_score DESC
    """)

    result = await session.execute(scoring_sql)
    rows = result.fetchall()

    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        stmt = pg_insert(Curator).values(
            user_login=row.user_login,
            platform="twitter",
            overlap_count=row.overlap_count,
            overlap_score=round(row.overlap_score, 4),
            earlyness_mean=0.0,
            last_scored_at=now,
            blocked=False,
        ).on_conflict_do_update(
            index_elements=["user_login", "platform"],
            set_={
                "overlap_count": row.overlap_count,
                "overlap_score": round(row.overlap_score, 4),
                "last_scored_at": now,
            },
        )
        await session.execute(stmt)
        count += 1
        if count % 1000 == 0:
            await session.commit()

    await session.commit()
    logger.info(f"Scored {count} Twitter curators")
    return count


async def score_curators(session: AsyncSession, platform: str = "github") -> int:
    """Score curators for a given platform."""
    if platform == "twitter":
        return await score_twitter_curators(session)
    return await score_github_curators(session)


async def get_top_curators(session: AsyncSession, top_k: int = 20, platform: str = "github") -> list[dict]:
    """Return top-K curators by score for a given platform."""
    result = await session.execute(
        select(Curator)
        .where(Curator.blocked == False, Curator.platform == platform)
        .order_by(Curator.overlap_score.desc())
        .limit(top_k)
    )
    curators = result.scalars().all()

    url_prefix = "https://github.com" if platform == "github" else "https://x.com"
    return [
        {
            "user_login": c.user_login,
            "platform": c.platform,
            "overlap_count": c.overlap_count,
            "overlap_score": c.overlap_score,
            "earlyness_mean": c.earlyness_mean,
            "profile_url": f"{url_prefix}/{c.user_login}",
        }
        for c in curators
    ]
```

**Step 2: Update existing references**

Update `routes.py` to pass `platform` parameter to `score_curators()` and `get_top_curators()`. The existing `/v1/score` and `/v1/curators` endpoints should accept an optional `platform` query param defaulting to `"github"`:

In `routes.py`, update:
- `run_scoring()`: add `platform: str = "github"` param, pass to `score_curators(session, platform)`
- `list_curators()`: add `platform: str = "github"` param, pass to `get_top_curators(session, top_k, platform)`

**Step 3: Update monitor.py**

Add `platform="github"` filter to the curator query in `refresh_curator_events()`:

```python
# In monitor.py, line ~17, update the select:
result = await session.execute(
    select(Curator)
    .where(Curator.blocked == False, Curator.platform == "github")
    .order_by(Curator.overlap_score.desc())
    .limit(top_k)
)
```

**Step 4: Update digest.py**

Add `platform` parameter to `generate_digest()`. For now, keep GitHub-only digest working. Twitter digest section will be added in Task 7.

**Step 5: Verify imports**

```bash
cd /Volumes/main-drive/ai-PA/curator-radar
python -c "from curator_radar.scoring import score_curators, score_twitter_curators, get_top_curators; print('Scoring OK')"
```

Expected: `Scoring OK`

**Step 6: Commit**

```bash
git add curator-radar/curator_radar/scoring.py curator-radar/curator_radar/routes.py curator-radar/curator_radar/monitor.py curator-radar/curator_radar/digest.py
git commit -m "feat: parameterize scoring engine for multi-platform curator support"
```

---

### Task 4: Twitter GraphQL client

**Files:**
- Create: `curator-radar/curator_radar/twitter_client.py`

**Step 1: Write the Twitter client**

```python
"""
Lightweight async client for Twitter's GraphQL API.
Uses browser auth cookies from Smaug's config file.
"""
import asyncio
import json
import logging
import re
import httpx
from dataclasses import dataclass, field
from pathlib import Path
from .settings import Settings

logger = logging.getLogger(__name__)

# Known GraphQL query IDs — these change when Twitter deploys.
# If they break, re-extract from https://x.com main JS bundle.
FAVORITERS_QUERY_ID = "LLkk5EcVutJL6y-2gkz22A"
CREATE_LIST_QUERY_ID = "nHFMQuE0r6yVEGmPSSbDdg"
LIST_ADD_MEMBER_QUERY_ID = "sw71TVciw0CoWPcFfIhrnA"
LIST_REMOVE_MEMBER_QUERY_ID = "cvl5jMbF1DqPRJalJTkNzA"

GRAPHQL_BASE = "https://x.com/i/api/graphql"

# Standard features param for Favoriters
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

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
                    "x-csrf-token": self.auth.ct0,
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
        """Adaptive delay between requests."""
        await asyncio.sleep(self.rate.current_delay)

    async def _handle_rate_limit(self, resp: httpx.Response):
        """Update rate state from response."""
        if "x-rate-limit-remaining" in resp.headers:
            self.rate.remaining = int(resp.headers["x-rate-limit-remaining"])
        if "x-rate-limit-reset" in resp.headers:
            self.rate.reset_at = float(resp.headers["x-rate-limit-reset"])

        if resp.status_code == 429:
            self.rate.consecutive_429s += 1
            # Exponential backoff
            wait = min(self.rate.base_delay * (2 ** self.rate.consecutive_429s), 120)
            self.rate.current_delay = wait
            logger.warning(f"Rate limited (429). Waiting {wait:.0f}s. Consecutive: {self.rate.consecutive_429s}")
            await asyncio.sleep(wait)
        else:
            if self.rate.consecutive_429s > 0:
                self.rate.consecutive_429s = 0
                self.rate.current_delay = self.rate.base_delay

    async def get_favoriters(self, tweet_id: str) -> list[dict]:
        """Fetch all users who liked a tweet. Returns list of {handle, name}."""
        all_users = []
        cursor = None

        while True:
            await self._wait()
            client = await self._get_client()

            variables = {"tweetId": tweet_id, "count": 100}
            if cursor:
                variables["cursor"] = cursor

            params = {
                "variables": json.dumps(variables),
                "features": json.dumps(FAVORITERS_FEATURES),
            }

            resp = await client.get(
                f"{GRAPHQL_BASE}/{FAVORITERS_QUERY_ID}/Favoriters",
                params=params,
            )
            await self._handle_rate_limit(resp)

            if resp.status_code == 429:
                continue  # Retry after backoff
            if resp.status_code != 200:
                logger.error(f"Favoriters API error {resp.status_code} for tweet {tweet_id}: {resp.text[:200]}")
                break

            data = resp.json()

            # Parse the nested GraphQL response
            timeline = (
                data.get("data", {})
                .get("favoriters_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )

            found_users = False
            next_cursor = None

            for instruction in timeline:
                entries = instruction.get("entries", [])
                for entry in entries:
                    content = entry.get("content", {})

                    # User entries
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

                    # Cursor entries
                    if content.get("entryType") == "TimelineTimelineCursor":
                        if content.get("cursorType") == "Bottom":
                            next_cursor = content.get("value")

            if not found_users or not next_cursor:
                break
            cursor = next_cursor

        logger.info(f"Tweet {tweet_id}: {len(all_users)} likers")
        return all_users

    async def create_list(self, name: str, description: str = "", private: bool = True) -> str | None:
        """Create a Twitter list. Returns list_id or None on failure."""
        await self._wait()
        client = await self._get_client()

        variables = {
            "isPrivate": private,
            "name": name,
            "description": description,
        }

        resp = await client.post(
            f"{GRAPHQL_BASE}/{CREATE_LIST_QUERY_ID}/CreateList",
            json={"variables": variables, "features": {}},
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
        """Look up a user's REST ID by screen name. Needed for list operations."""
        await self._wait()
        client = await self._get_client()

        # Use the UserByScreenName endpoint
        variables = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        features = {
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
        resp = await client.get(
            f"{GRAPHQL_BASE}/xmU6X_CKVnQ5lSrCbAmJsg/UserByScreenName",
            params={"variables": json.dumps(variables), "features": json.dumps(features)},
        )
        await self._handle_rate_limit(resp)

        if resp.status_code != 200:
            return None

        data = resp.json()
        return data.get("data", {}).get("user", {}).get("result", {}).get("rest_id")
```

**Step 2: Verify import**

```bash
cd /Volumes/main-drive/ai-PA/curator-radar
python -c "from curator_radar.twitter_client import TwitterClient; print('Twitter client OK')"
```

Expected: `Twitter client OK`

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/twitter_client.py
git commit -m "feat: add Twitter GraphQL client for Favoriters and List management"
```

---

### Task 5: Bookmark ingestion from Smaug

**Files:**
- Create: `curator-radar/curator_radar/twitter_ingest.py`

**Step 1: Write the ingestion module**

```python
"""
Ingest bookmarked tweet IDs from Smaug's output files.
Reads bookmarks.md and extracts tweet IDs + metadata.
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import BookmarkedTweet
from .settings import Settings

logger = logging.getLogger(__name__)

# Matches tweet URLs in bookmarks.md: https://x.com/{author}/status/{id}
TWEET_URL_RE = re.compile(r"https://x\.com/(\w+)/status/(\d+)")

# Matches bookmark entries: ## @author - title
ENTRY_RE = re.compile(r"^## @(\w+) - (.+)$", re.MULTILINE)

# Matches date headers: # Thursday, March 5, 2026
DATE_RE = re.compile(r"^# (.+)$", re.MULTILINE)


async def ingest_bookmarks(session: AsyncSession, settings: Settings) -> int:
    """Read Smaug's bookmarks.md and ingest any new tweet IDs."""
    archive_path = Path(settings.smaug_data_path) / "bookmarks.md"
    if not archive_path.exists():
        logger.warning(f"Archive file not found: {archive_path}")
        return 0

    content = archive_path.read_text(encoding="utf-8")

    # Get existing tweet IDs to skip
    result = await session.execute(select(BookmarkedTweet.tweet_id))
    existing_ids = {row[0] for row in result.fetchall()}

    # Parse bookmarks.md — extract tweet URLs from **Tweet:** lines
    # Format: - **Tweet:** https://x.com/author/status/12345
    tweet_line_re = re.compile(r"- \*\*Tweet:\*\* (https://x\.com/(\w+)/status/(\d+))")

    # Also need the date context for bookmarked_at
    lines = content.split("\n")
    current_date = None
    new_count = 0

    for line in lines:
        # Track current date section
        date_match = DATE_RE.match(line)
        if date_match:
            try:
                current_date = datetime.strptime(date_match.group(1), "%A, %B %d, %Y")
                current_date = current_date.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            continue

        # Find tweet URLs
        tweet_match = tweet_line_re.match(line.strip())
        if tweet_match:
            tweet_url = tweet_match.group(1)
            author = tweet_match.group(2)
            tweet_id = tweet_match.group(3)

            if tweet_id in existing_ids:
                continue

            stmt = pg_insert(BookmarkedTweet).values(
                tweet_id=tweet_id,
                author_handle=author,
                author_name="",
                text="",
                tweet_url=tweet_url,
                bookmarked_at=current_date or datetime.now(timezone.utc),
                likers_fetched=False,
            ).on_conflict_do_nothing()

            await session.execute(stmt)
            existing_ids.add(tweet_id)
            new_count += 1

            if new_count % 100 == 0:
                await session.commit()

    await session.commit()
    logger.info(f"Ingested {new_count} new bookmarks from Smaug archive")
    return new_count


async def get_ingest_status(session: AsyncSession) -> dict:
    """Return current ingestion and likers-fetch progress."""
    total = await session.scalar(select(func.count()).select_from(BookmarkedTweet))
    fetched = await session.scalar(
        select(func.count()).select_from(BookmarkedTweet).where(BookmarkedTweet.likers_fetched == True)
    )
    unfetched = (total or 0) - (fetched or 0)
    liker_count = await session.scalar(
        select(func.count()).select_from(
            select(func.distinct(BookmarkedTweet.tweet_id))
            .join(
                # This is just a count alias
            ).subquery()
        )
    ) if False else None  # Simplified — just count TweetLiker rows

    from .models import TweetLiker
    liker_rows = await session.scalar(select(func.count()).select_from(TweetLiker))

    return {
        "total_bookmarks": total or 0,
        "likers_fetched": fetched or 0,
        "likers_pending": unfetched,
        "total_liker_rows": liker_rows or 0,
    }
```

**Step 2: Verify import**

```bash
python -c "from curator_radar.twitter_ingest import ingest_bookmarks, get_ingest_status; print('Ingest OK')"
```

Expected: `Ingest OK`

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/twitter_ingest.py
git commit -m "feat: add bookmark ingestion from Smaug archive"
```

---

### Task 6: Twitter likers backfill

**Files:**
- Create: `curator-radar/curator_radar/twitter_backfill.py`

**Step 1: Write the backfill module**

```python
"""
Fetch likers for bookmarked tweets via Twitter's Favoriters GraphQL endpoint.
Processes newest-first. Resumable — tracks progress via likers_fetched flag.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import BookmarkedTweet, TweetLiker
from .twitter_client import TwitterClient

logger = logging.getLogger(__name__)


async def fetch_tweet_likers(session: AsyncSession, client: TwitterClient) -> dict:
    """Fetch likers for all unfetched bookmarked tweets (newest first).

    No artificial cap — adaptive rate limiting governs throughput.
    Returns stats dict with counts.
    """
    # Get unfetched tweets, newest first
    result = await session.execute(
        select(BookmarkedTweet)
        .where(BookmarkedTweet.likers_fetched == False)
        .order_by(BookmarkedTweet.bookmarked_at.desc())
    )
    tweets = result.scalars().all()

    if not tweets:
        logger.info("No unfetched tweets to process")
        return {"tweets_processed": 0, "total_likers": 0}

    logger.info(f"Fetching likers for {len(tweets)} tweets (newest first)")

    tweets_processed = 0
    total_likers = 0
    errors = 0

    for tweet in tweets:
        try:
            likers = await client.get_favoriters(tweet.tweet_id)

            now = datetime.now(timezone.utc)
            for liker in likers:
                stmt = pg_insert(TweetLiker).values(
                    tweet_id=tweet.tweet_id,
                    user_handle=liker["handle"],
                    user_name=liker.get("name", ""),
                    fetched_at=now,
                ).on_conflict_do_nothing()
                await session.execute(stmt)

            # Mark as fetched
            tweet.likers_fetched = True
            await session.commit()

            tweets_processed += 1
            total_likers += len(likers)
            logger.info(
                f"[{tweets_processed}/{len(tweets)}] Tweet {tweet.tweet_id}: "
                f"{len(likers)} likers (total: {total_likers})"
            )

        except Exception as e:
            errors += 1
            logger.error(f"Error fetching likers for tweet {tweet.tweet_id}: {e}")
            await session.rollback()

            # If too many consecutive errors, likely auth issue — stop
            if errors >= 5:
                logger.error("Too many consecutive errors, stopping backfill")
                break
            continue

    stats = {
        "tweets_processed": tweets_processed,
        "tweets_remaining": len(tweets) - tweets_processed,
        "total_likers": total_likers,
        "errors": errors,
    }
    logger.info(f"Backfill complete: {stats}")
    return stats
```

**Step 2: Verify import**

```bash
python -c "from curator_radar.twitter_backfill import fetch_tweet_likers; print('Backfill OK')"
```

Expected: `Backfill OK`

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/twitter_backfill.py
git commit -m "feat: add Twitter likers backfill with adaptive rate limiting"
```

---

### Task 7: Twitter List sync

**Files:**
- Create: `curator-radar/curator_radar/twitter_list_sync.py`

**Step 1: Write the list sync module**

```python
"""
Auto-manage a private Twitter List with top-N Twitter curators.
Creates the list if it doesn't exist, adds/removes members to stay in sync.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import Curator, TwitterList, TwitterListMember
from .twitter_client import TwitterClient
from .settings import Settings

logger = logging.getLogger(__name__)


async def sync_twitter_list(session: AsyncSession, client: TwitterClient, settings: Settings) -> dict:
    """Sync the Twitter list with top-N curators. Creates list if needed."""

    list_name = settings.twitter_list_name
    list_size = settings.twitter_list_size

    # 1. Get or create the Twitter list
    result = await session.execute(
        select(TwitterList).where(TwitterList.list_name == list_name)
    )
    twitter_list = result.scalar_one_or_none()

    if not twitter_list:
        logger.info(f"Creating Twitter list: {list_name}")
        list_id = await client.create_list(list_name, description="Auto-managed by Curator Radar", private=True)
        if not list_id:
            logger.error("Failed to create Twitter list")
            return {"status": "error", "message": "Failed to create list"}

        stmt = pg_insert(TwitterList).values(
            list_id=list_id,
            list_name=list_name,
            last_synced_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing()
        await session.execute(stmt)
        await session.commit()

        # Re-fetch
        result = await session.execute(
            select(TwitterList).where(TwitterList.list_name == list_name)
        )
        twitter_list = result.scalar_one_or_none()

    list_id = twitter_list.list_id

    # 2. Get top-N Twitter curators
    curators_result = await session.execute(
        select(Curator)
        .where(Curator.platform == "twitter", Curator.blocked == False)
        .order_by(Curator.overlap_score.desc())
        .limit(list_size)
    )
    top_curators = {c.user_login for c in curators_result.scalars().all()}

    # 3. Get current list members
    members_result = await session.execute(
        select(TwitterListMember)
        .where(TwitterListMember.list_id == list_id, TwitterListMember.removed_at == None)
    )
    current_members = {m.user_handle for m in members_result.scalars().all()}

    # 4. Compute diff
    to_add = top_curators - current_members
    to_remove = current_members - top_curators

    added = 0
    removed = 0

    # 5. Add new members
    for handle in to_add:
        user_id = await client.get_user_rest_id(handle)
        if not user_id:
            logger.warning(f"Could not resolve user ID for @{handle}")
            continue
        success = await client.add_list_member(list_id, user_id)
        if success:
            stmt = pg_insert(TwitterListMember).values(
                list_id=list_id,
                user_handle=handle,
                added_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["list_id", "user_handle"],
                set_={"removed_at": None, "added_at": datetime.now(timezone.utc)},
            )
            await session.execute(stmt)
            added += 1
            logger.info(f"Added @{handle} to list")

    # 6. Remove dropped members
    for handle in to_remove:
        user_id = await client.get_user_rest_id(handle)
        if user_id:
            await client.remove_list_member(list_id, user_id)
        # Mark as removed in DB regardless
        result = await session.execute(
            select(TwitterListMember)
            .where(TwitterListMember.list_id == list_id, TwitterListMember.user_handle == handle)
        )
        member = result.scalar_one_or_none()
        if member:
            member.removed_at = datetime.now(timezone.utc)
        removed += 1
        logger.info(f"Removed @{handle} from list")

    twitter_list.last_synced_at = datetime.now(timezone.utc)
    await session.commit()

    stats = {"added": added, "removed": removed, "total_members": len(top_curators)}
    logger.info(f"List sync complete: {stats}")
    return stats
```

**Step 2: Verify import**

```bash
python -c "from curator_radar.twitter_list_sync import sync_twitter_list; print('List sync OK')"
```

Expected: `List sync OK`

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/twitter_list_sync.py
git commit -m "feat: add Twitter List auto-sync for top curators"
```

---

### Task 8: Twitter routes and daily run orchestration

**Files:**
- Modify: `curator-radar/curator_radar/routes.py`

**Step 1: Add Twitter-specific routes**

Add these routes to the existing `routes.py` after the GitHub routes:

```python
# --- Twitter Curator Routes ---

from .twitter_client import TwitterClient
from .twitter_ingest import ingest_bookmarks, get_ingest_status
from .twitter_backfill import fetch_tweet_likers
from .twitter_list_sync import sync_twitter_list


async def _run_twitter_daily():
    """Daily Twitter curator pipeline: ingest → fetch likers → score → sync list."""
    from .database import AsyncSessionFactory
    try:
        client = TwitterClient(settings)
        async with AsyncSessionFactory() as session:
            logger.info("Twitter daily: ingesting new bookmarks...")
            ingested = await ingest_bookmarks(session, settings)
            logger.info(f"Twitter daily: ingested {ingested} new bookmarks")

            logger.info("Twitter daily: fetching likers...")
            stats = await fetch_tweet_likers(session, client)
            logger.info(f"Twitter daily: {stats}")

            logger.info("Twitter daily: scoring curators...")
            scored = await score_curators(session, platform="twitter")
            logger.info(f"Twitter daily: scored {scored} curators")

            logger.info("Twitter daily: syncing list...")
            sync_stats = await sync_twitter_list(session, client, settings)
            logger.info(f"Twitter daily: list sync {sync_stats}")

            logger.info("Twitter daily run complete.")
    except Exception as e:
        logger.error(f"Twitter daily run failed: {e}", exc_info=True)
    finally:
        await client.close()


@router.post("/twitter/run")
async def twitter_daily_run(background_tasks: BackgroundTasks):
    """Run the full daily Twitter curator pipeline in background."""
    background_tasks.add_task(_run_twitter_daily)
    return {"status": "started", "pipeline": "twitter-daily"}


@router.post("/twitter/ingest")
async def twitter_ingest(session: AsyncSession = Depends(get_session)):
    """Ingest new bookmarks from Smaug archive."""
    count = await ingest_bookmarks(session, settings)
    return {"status": "ok", "ingested": count}


@router.get("/twitter/status")
async def twitter_status(session: AsyncSession = Depends(get_session)):
    """Get Twitter ingestion and likers-fetch status."""
    return await get_ingest_status(session)


@router.post("/twitter/fetch-likers")
async def twitter_fetch_likers(background_tasks: BackgroundTasks):
    """Fetch likers for unfetched tweets in background."""
    async def _fetch():
        from .database import AsyncSessionFactory
        client = TwitterClient(settings)
        try:
            async with AsyncSessionFactory() as session:
                await fetch_tweet_likers(session, client)
        finally:
            await client.close()
    background_tasks.add_task(_fetch)
    return {"status": "started"}


@router.post("/twitter/score")
async def twitter_score(session: AsyncSession = Depends(get_session)):
    """Score Twitter curators."""
    count = await score_curators(session, platform="twitter")
    return {"status": "ok", "curators_scored": count}


@router.get("/twitter/curators")
async def twitter_curators(top_k: int = 50, session: AsyncSession = Depends(get_session)):
    """List top Twitter curators."""
    return await get_top_curators(session, top_k, platform="twitter")


@router.post("/twitter/sync-list")
async def twitter_sync_list(session: AsyncSession = Depends(get_session)):
    """Sync the Twitter list with top curators."""
    client = TwitterClient(settings)
    try:
        stats = await sync_twitter_list(session, client, settings)
        return {"status": "ok", **stats}
    finally:
        await client.close()
```

**Step 2: Verify the routes load**

```bash
python -c "from curator_radar.routes import router; print(f'Routes: {len(router.routes)}'); print('Routes OK')"
```

Expected: `Routes OK` with increased route count.

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/routes.py
git commit -m "feat: add Twitter curator API routes and daily pipeline orchestration"
```

---

### Task 9: Update digest for Twitter curators

**Files:**
- Modify: `curator-radar/curator_radar/digest.py`

**Step 1: Add Twitter section to weekly digest**

Replace `digest.py` with multi-platform version:

```python
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from .scoring import get_top_curators
from .monitor import get_discoveries


async def generate_digest(session: AsyncSession, since_days: int = 7) -> str:
    """Generate a Markdown weekly digest with both GitHub and Twitter sections."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=since_days)

    lines = [
        f"# Curator Radar — Weekly Digest",
        f"**Period:** {start.strftime('%b %d')} — {now.strftime('%b %d, %Y')}",
        "",
    ]

    # GitHub curators section
    gh_curators = await get_top_curators(session, top_k=10, platform="github")
    if gh_curators:
        lines.append("## GitHub Curators")
        lines.append("| Rank | User | Overlap | Earlyness | Score |")
        lines.append("|------|------|---------|-----------|-------|")
        for i, c in enumerate(gh_curators, 1):
            lines.append(
                f"| {i} | [{c['user_login']}]({c['profile_url']}) | "
                f"{c['overlap_count']} repos | {c['earlyness_mean']:.2f} | {c['overlap_score']:.1f} |"
            )
        lines.append("")

    # GitHub discoveries section
    discoveries = await get_discoveries(session, since_days)
    if discoveries:
        lines.append(f"## GitHub Discoveries ({len(discoveries)} repos)")
        lines.append("")
        for d in discoveries[:20]:
            curator_list = ", ".join(d["curators"][:5])
            lines.append(f"- **[{d['repo']}]({d['github_url']})** — {d['curator_count']} curator(s): {curator_list}")
        lines.append("")

    # Twitter curators section
    tw_curators = await get_top_curators(session, top_k=10, platform="twitter")
    if tw_curators:
        lines.append("## Twitter Curators")
        lines.append("| Rank | Handle | Overlap | Score |")
        lines.append("|------|--------|---------|-------|")
        for i, c in enumerate(tw_curators, 1):
            lines.append(
                f"| {i} | [@{c['user_login']}]({c['profile_url']}) | "
                f"{c['overlap_count']} tweets | {c['overlap_score']:.1f} |"
            )
        lines.append("")

    if not gh_curators and not tw_curators:
        lines.append("No curator data yet. Run backfill first.")
        lines.append("")

    return "\n".join(lines)
```

**Step 2: Verify import**

```bash
python -c "from curator_radar.digest import generate_digest; print('Digest OK')"
```

Expected: `Digest OK`

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/digest.py
git commit -m "feat: add Twitter curators section to weekly digest"
```

---

### Task 10: Docker and deployment config

**Files:**
- Modify: `docker-compose.yml` (curator-radar section)
- Modify: `curator-radar/Dockerfile`

**Step 1: Add Smaug volume mount to docker-compose.yml**

The curator-radar container needs read access to Smaug's config (for auth cookies) and data (for bookmarks.md). Add volume mounts to the existing `curator-radar` service in `docker-compose.yml`:

```yaml
    volumes:
      - ./smaug/smaug.config.json:/app/smaug-config/smaug.config.json:ro
      - ./smaug-data:/app/smaug-data:ro
    environment:
      # ... existing env vars ...
      SMAUG_CONFIG_PATH: "/app/smaug-config/smaug.config.json"
      SMAUG_DATA_PATH: "/app/smaug-data"
      TWITTER_LIST_NAME: "Curator Radar"
      TWITTER_LIST_SIZE: "50"
```

**Step 2: Verify docker-compose syntax**

```bash
cd /Volumes/main-drive/ai-PA
docker-compose config --services | grep curator
```

Expected: `curator-radar`

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Smaug volume mounts to curator-radar for Twitter integration"
```

---

### Task 11: Register scheduler job and initial test

**Step 1: Register daily Twitter curator cron job**

After the service is running, register a scheduler job:

```bash
curl -X POST http://localhost:8087/v1/jobs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SCHEDULER_API_KEY}" \
  -d '{
    "name": "curator-radar-twitter-daily",
    "description": "Daily Twitter curator pipeline: ingest bookmarks, fetch likers, score, sync list",
    "expression": {"cron": "0 8 * * *"},
    "endpoint": "http://curator-radar:5145/v1/twitter/run",
    "method": "POST",
    "enabled": true
  }'
```

**Step 2: Test the pipeline manually**

```bash
# 1. Ingest bookmarks
curl -X POST http://localhost:5145/v1/twitter/ingest
# Expected: {"status": "ok", "ingested": 993}

# 2. Check status
curl http://localhost:5145/v1/twitter/status
# Expected: {"total_bookmarks": 993, "likers_fetched": 0, "likers_pending": 993, ...}

# 3. Start likers fetch (runs in background)
curl -X POST http://localhost:5145/v1/twitter/fetch-likers
# Expected: {"status": "started"}

# 4. Monitor progress
curl http://localhost:5145/v1/twitter/status
# Expected: likers_fetched increasing over time

# 5. After some likers are fetched, score
curl -X POST http://localhost:5145/v1/twitter/score
# Expected: {"status": "ok", "curators_scored": N}

# 6. View top curators
curl http://localhost:5145/v1/twitter/curators?top_k=10
```

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: any issues found during initial testing"
```

---

### Task 12: Update WIP tracker

**Files:**
- Modify: `docs/plans/2026-02-23-wip-system-updates.md`

**Step 1: Update Curator Radar entry (Item 22) to reflect Twitter integration**

Add Twitter curator discovery to the existing Curator Radar WIP entry. Mention the new endpoints, the Twitter List feature, and the daily cron job.

**Step 2: Update Smaug entry (Item 23) to note the downstream consumer**

Add a line noting that Curator Radar reads from Smaug's output for Twitter curator discovery.

**Step 3: Commit**

```bash
git add docs/plans/2026-02-23-wip-system-updates.md
git commit -m "docs: update WIP tracker with Twitter curator discovery integration"
```
