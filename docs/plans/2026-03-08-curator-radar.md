# Curator Radar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Identify GitHub users who share your starring patterns, monitor their future stars, and surface interesting new repos via weekly Slack digests — with zero LLM calls in the pipeline.

**Architecture:** A FastAPI microservice (`curator-radar`, port 5145) running in Docker on `pa-internal`. Backfills stargazer data from GitHub API into Supabase PostgreSQL, computes overlap/earlyness scores, monitors top curators' WatchEvents daily, and generates weekly Markdown digests delivered via the slackbot notify endpoint. A Letta tool (`query_curator_radar`) provides agent access for both standard and Letta Code agents.

**Tech Stack:** Python 3.12, FastAPI, httpx (async GitHub API), SQLAlchemy (async + asyncpg), Supabase PostgreSQL, scheduler-service for cron jobs.

---

## Context for Implementer

### Key Files to Reference
- **Service pattern:** `sports-and-media-tools/sports-service/sports_api.py` (simple Flask), `scheduler-service/src/scheduler_service/main.py` (FastAPI with async DB)
- **Docker setup:** `docker-compose.yml` — follow existing service conventions
- **Letta tool pattern:** `letta/omnifocus_tools.py`, `letta/register_gmail_tools.py`
- **Scheduler job registration:** `POST http://scheduler-service:8087/v1/jobs`
- **Slack notify:** `POST http://slackbot:8081/api/notify` with `{text, detail, user_slack_id}`
- **DB connection:** `postgresql+asyncpg://curator_radar:curator_radar_secret@supabase-db:5432/curator_radar`

### GitHub API Notes
- **Stars with timestamps:** `GET /users/{login}/starred?per_page=100` with `Accept: application/vnd.github.v3.star+json`
- **Stargazers with timestamps:** `GET /repos/{owner}/{repo}/stargazers?per_page=100` with same Accept header
- **User public events:** `GET /users/{login}/events/public` (last 90 days, max 300 events, 10 pages)
- **Rate limit:** 5,000 req/hr with PAT. Track via `X-RateLimit-Remaining` / `X-RateLimit-Reset` headers.
- **~144 total starred repos** for @chaddorsey. Backfill scope is manageable (~1-2 hours).

### Port Assignment
- `5145` (unused, in the 5100s range with other services)

---

## Task 1: Database Schema and Service Skeleton

**Files:**
- Create: `curator-radar/curator_radar/__init__.py`
- Create: `curator-radar/curator_radar/main.py`
- Create: `curator-radar/curator_radar/settings.py`
- Create: `curator-radar/curator_radar/database.py`
- Create: `curator-radar/curator_radar/models.py`
- Create: `curator-radar/curator_radar/schema.sql`
- Create: `curator-radar/requirements.txt`
- Create: `curator-radar/Dockerfile`

**Step 1: Create the directory structure**

```bash
mkdir -p curator-radar/curator_radar
touch curator-radar/curator_radar/__init__.py
```

**Step 2: Write `requirements.txt`**

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx>=0.27.0
sqlalchemy[asyncio]>=2.0.30
asyncpg>=0.29.0
pydantic-settings>=2.3.0
```

**Step 3: Write `settings.py`**

```python
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://curator_radar:curator_radar_secret@supabase-db:5432/curator_radar",
        alias="DATABASE_URL",
    )
    github_token: str = Field(alias="GITHUB_TOKEN")
    github_username: str = Field(default="chaddorsey", alias="GITHUB_USERNAME")
    top_curators_k: int = Field(default=20, alias="TOP_CURATORS_K")
    rate_limit_guard: int = Field(default=200, alias="RATE_LIMIT_GUARD")
    slackbot_notify_url: str = Field(
        default="http://slackbot:8081/api/notify",
        alias="SLACKBOT_NOTIFY_URL",
    )
    slack_user_id: str = Field(default="", alias="SLACK_USER_ID")

    model_config = {"env_file": ".env", "extra": "ignore"}
```

**Step 4: Write `database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator
from .settings import Settings

settings = Settings()
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session
```

**Step 5: Write `models.py`**

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Boolean, DateTime, JSON, Text
from datetime import datetime


class Base(DeclarativeBase):
    pass


class StarredRepo(Base):
    __tablename__ = "starred_repos"

    repo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    topics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stargazers_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    starred_at_by_chad: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RepoStargazer(Base):
    __tablename__ = "repo_stargazers"

    repo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_login: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    starred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Curator(Base):
    __tablename__ = "curators"

    user_login: Mapped[str] = mapped_column(String(100), primary_key=True)
    overlap_count: Mapped[int] = mapped_column(Integer, default=0)
    overlap_score: Mapped[float] = mapped_column(Float, default=0.0)
    earlyness_mean: Mapped[float] = mapped_column(Float, default=0.0)
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class CuratorEvent(Base):
    __tablename__ = "curator_events"

    event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_login: Mapped[str] = mapped_column(String(100), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(255))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class BackfillCheckpoint(Base):
    __tablename__ = "backfill_checkpoints"

    job_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

**Step 6: Write `main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine
from .models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Curator Radar", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "curator-radar"}
```

**Step 7: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY curator_radar/ ./curator_radar/

EXPOSE 5145

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5145/health || exit 1

CMD ["uvicorn", "curator_radar.main:app", "--host", "0.0.0.0", "--port", "5145"]
```

**Step 8: Write `schema.sql`** (reference only — tables created by SQLAlchemy)

```sql
-- Reference schema for curator-radar
-- Tables are auto-created by SQLAlchemy models on startup.
-- This file exists for documentation and manual recovery.

CREATE DATABASE curator_radar;
CREATE USER curator_radar WITH PASSWORD 'curator_radar_secret';
GRANT ALL PRIVILEGES ON DATABASE curator_radar TO curator_radar;
```

**Step 9: Commit**

```bash
git add curator-radar/
git commit -m "feat: curator-radar service skeleton with DB models"
```

---

## Task 2: GitHub API Client with Rate Limiting

**Files:**
- Create: `curator-radar/curator_radar/github_client.py`
- Create: `curator-radar/tests/test_github_client.py`

**Step 1: Write `github_client.py`**

An async httpx-based client that handles pagination, rate limits, and the star+json Accept header.

```python
import asyncio
import time
import httpx
from dataclasses import dataclass
from typing import AsyncIterator
from .settings import Settings


STAR_ACCEPT = "application/vnd.github.v3.star+json"
DEFAULT_ACCEPT = "application/vnd.github.v3+json"


@dataclass
class RateLimitState:
    remaining: int = 5000
    reset_at: float = 0.0


class GitHubClient:
    def __init__(self, settings: Settings):
        self.token = settings.github_token
        self.username = settings.github_username
        self.guard = settings.rate_limit_guard
        self.rate = RateLimitState()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _update_rate(self, headers: httpx.Headers):
        if "x-ratelimit-remaining" in headers:
            self.rate.remaining = int(headers["x-ratelimit-remaining"])
        if "x-ratelimit-reset" in headers:
            self.rate.reset_at = float(headers["x-ratelimit-reset"])

    async def _wait_if_limited(self):
        if self.rate.remaining < self.guard:
            wait = max(0, self.rate.reset_at - time.time()) + 1
            await asyncio.sleep(wait)

    async def _get(self, url: str, accept: str = DEFAULT_ACCEPT) -> httpx.Response:
        await self._wait_if_limited()
        client = await self._get_client()
        for attempt in range(3):
            resp = await client.get(url, headers={"Accept": accept})
            self._update_rate(resp.headers)
            if resp.status_code in (403, 429):
                wait = max(0, self.rate.reset_at - time.time()) + 2 ** attempt
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                await asyncio.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp  # unreachable but satisfies type checker

    async def paginate(self, url: str, accept: str = DEFAULT_ACCEPT) -> AsyncIterator[list]:
        """Yield pages of results, following Link: next headers."""
        next_url: str | None = url
        while next_url:
            resp = await self._get(next_url, accept=accept)
            data = resp.json()
            if isinstance(data, list) and data:
                yield data
            elif not isinstance(data, list):
                yield [data]
                return
            else:
                return
            # Parse Link header for next page
            link = resp.headers.get("link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")

    async def get_user_stars(self) -> AsyncIterator[list]:
        """Get all starred repos with timestamps."""
        url = f"/users/{self.username}/starred?per_page=100"
        async for page in self.paginate(url, accept=STAR_ACCEPT):
            yield page

    async def get_repo_stargazers(self, full_name: str) -> AsyncIterator[list]:
        """Get stargazers with timestamps for a repo."""
        url = f"/repos/{full_name}/stargazers?per_page=100"
        async for page in self.paginate(url, accept=STAR_ACCEPT):
            yield page

    async def get_repo_info(self, full_name: str) -> dict:
        """Get repo metadata."""
        resp = await self._get(f"/repos/{full_name}")
        return resp.json()

    async def get_user_events(self, login: str) -> AsyncIterator[list]:
        """Get a user's public events (max 10 pages / 300 events)."""
        url = f"/users/{login}/events/public?per_page=100"
        page_count = 0
        async for page in self.paginate(url):
            yield page
            page_count += 1
            if page_count >= 10:
                break
```

**Step 2: Write basic test**

```python
# tests/test_github_client.py
import pytest
from curator_radar.github_client import RateLimitState

def test_rate_limit_state_defaults():
    state = RateLimitState()
    assert state.remaining == 5000
    assert state.reset_at == 0.0
```

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/github_client.py curator-radar/tests/
git commit -m "feat: async GitHub API client with rate limiting and pagination"
```

---

## Task 3: Backfill Pipeline

**Files:**
- Create: `curator-radar/curator_radar/backfill.py`
- Create: `curator-radar/curator_radar/routes.py`
- Modify: `curator-radar/curator_radar/main.py` (add routes)

**Step 1: Write `backfill.py`**

```python
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import StarredRepo, RepoStargazer, BackfillCheckpoint
from .github_client import GitHubClient

logger = logging.getLogger(__name__)

TWELVE_MONTHS_AGO = datetime.now(timezone.utc) - timedelta(days=365)


async def backfill_stars(session: AsyncSession, client: GitHubClient, since_days: int = 365):
    """Fetch user's starred repos from the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    count = 0

    async for page in client.get_user_stars():
        for item in page:
            starred_at = datetime.fromisoformat(item["starred_at"].replace("Z", "+00:00"))
            if starred_at < cutoff:
                logger.info(f"Reached cutoff at {starred_at}, stopping. Fetched {count} repos.")
                await session.commit()
                return count
            repo = item["repo"]
            stmt = pg_insert(StarredRepo).values(
                repo_id=repo["id"],
                full_name=repo["full_name"],
                owner=repo["owner"]["login"],
                name=repo["name"],
                language=repo.get("language"),
                topics=repo.get("topics", []),
                stargazers_count=repo.get("stargazers_count", 0),
                created_at=repo.get("created_at"),
                pushed_at=repo.get("pushed_at"),
                starred_at_by_chad=starred_at,
            ).on_conflict_do_update(
                index_elements=["repo_id"],
                set_={"stargazers_count": repo.get("stargazers_count", 0), "pushed_at": repo.get("pushed_at")},
            )
            await session.execute(stmt)
            count += 1
        await session.commit()

    logger.info(f"Fetched all {count} starred repos.")
    return count


async def backfill_stargazers(session: AsyncSession, client: GitHubClient, max_pages_per_repo: int = 100):
    """Fetch stargazers for all starred repos. Resumable via checkpoint."""
    # Get checkpoint
    cp_result = await session.execute(
        select(BackfillCheckpoint).where(BackfillCheckpoint.job_name == "stargazers")
    )
    checkpoint = cp_result.scalar_one_or_none()
    completed_repos: set = set(checkpoint.checkpoint.get("completed", [])) if checkpoint else set()

    # Get all repos
    repos_result = await session.execute(select(StarredRepo))
    repos = repos_result.scalars().all()

    # Sort smallest first (fastest to complete, best for rate-limit budgeting)
    repos = sorted(repos, key=lambda r: r.stargazers_count)

    for repo in repos:
        if repo.full_name in completed_repos:
            continue

        logger.info(f"Fetching stargazers for {repo.full_name} ({repo.stargazers_count} stars)")
        page_count = 0

        try:
            async for page in client.get_repo_stargazers(repo.full_name):
                for item in page:
                    user = item.get("user", {})
                    if not user or not user.get("login"):
                        continue
                    starred_at = item.get("starred_at")
                    if starred_at:
                        starred_at = datetime.fromisoformat(starred_at.replace("Z", "+00:00"))

                    stmt = pg_insert(RepoStargazer).values(
                        repo_id=repo.repo_id,
                        user_login=user["login"],
                        starred_at=starred_at,
                    ).on_conflict_do_nothing()
                    await session.execute(stmt)

                page_count += 1
                if page_count >= max_pages_per_repo:
                    logger.info(f"  Hit page limit ({max_pages_per_repo}) for {repo.full_name}")
                    break

            await session.commit()
        except Exception as e:
            logger.error(f"Error fetching stargazers for {repo.full_name}: {e}")
            await session.rollback()
            continue

        # Update checkpoint
        completed_repos.add(repo.full_name)
        cp_stmt = pg_insert(BackfillCheckpoint).values(
            job_name="stargazers",
            checkpoint={"completed": list(completed_repos)},
            updated_at=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["job_name"],
            set_={"checkpoint": {"completed": list(completed_repos)}, "updated_at": datetime.now(timezone.utc)},
        )
        await session.execute(cp_stmt)
        await session.commit()

    return len(completed_repos)


async def get_backfill_status(session: AsyncSession) -> dict:
    """Return current backfill progress."""
    total = await session.scalar(select(func.count()).select_from(StarredRepo))
    cp_result = await session.execute(
        select(BackfillCheckpoint).where(BackfillCheckpoint.job_name == "stargazers")
    )
    checkpoint = cp_result.scalar_one_or_none()
    completed = len(checkpoint.checkpoint.get("completed", [])) if checkpoint else 0
    stargazer_count = await session.scalar(select(func.count()).select_from(RepoStargazer))

    return {
        "starred_repos": total or 0,
        "repos_with_stargazers_fetched": completed,
        "total_stargazer_rows": stargazer_count or 0,
        "complete": completed >= (total or 0),
    }
```

**Step 2: Write `routes.py`**

```python
import asyncio
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_session
from .settings import Settings
from .github_client import GitHubClient
from .backfill import backfill_stars, backfill_stargazers, get_backfill_status
from .scoring import score_curators, get_top_curators
from .monitor import refresh_curator_events, get_discoveries
from .digest import generate_digest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")
settings = Settings()


async def _run_backfill(since_days: int):
    """Run full backfill in background."""
    from .database import AsyncSessionFactory
    client = GitHubClient(settings)
    try:
        async with AsyncSessionFactory() as session:
            logger.info("Starting stars backfill...")
            await backfill_stars(session, client, since_days=since_days)
            logger.info("Starting stargazers backfill...")
            await backfill_stargazers(session, client)
            logger.info("Scoring curators...")
            await score_curators(session)
            logger.info("Backfill complete.")
    finally:
        await client.close()


@router.post("/backfill")
async def start_backfill(background_tasks: BackgroundTasks, since_days: int = 365):
    background_tasks.add_task(_run_backfill, since_days)
    return {"status": "started", "since_days": since_days}


@router.get("/backfill/status")
async def backfill_status(session: AsyncSession = Depends(get_session)):
    return await get_backfill_status(session)


@router.post("/score")
async def run_scoring(session: AsyncSession = Depends(get_session)):
    count = await score_curators(session)
    return {"status": "ok", "curators_scored": count}


@router.get("/curators")
async def list_curators(top_k: int = 20, session: AsyncSession = Depends(get_session)):
    return await get_top_curators(session, top_k)


@router.post("/monitor/refresh")
async def monitor_refresh(session: AsyncSession = Depends(get_session)):
    client = GitHubClient(settings)
    try:
        count = await refresh_curator_events(session, client)
        return {"status": "ok", "new_events": count}
    finally:
        await client.close()


@router.get("/discoveries")
async def discoveries(since_days: int = 7, session: AsyncSession = Depends(get_session)):
    return await get_discoveries(session, since_days)


@router.get("/digest")
async def digest(since_days: int = 7, session: AsyncSession = Depends(get_session)):
    md = await generate_digest(session, since_days)
    return {"status": "ok", "digest": md}


@router.post("/digest/deliver")
async def deliver_digest(since_days: int = 7, session: AsyncSession = Depends(get_session)):
    """Generate digest and post to Slack."""
    import httpx
    md = await generate_digest(session, since_days)
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            settings.slackbot_notify_url,
            json={
                "text": "Weekly Curator Radar Digest",
                "detail": md,
                "user_slack_id": settings.slack_user_id,
            },
        )
    return {"status": "ok", "slack_response": resp.status_code}
```

**Step 3: Update `main.py` to include routes**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine
from .models import Base
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Curator Radar", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "curator-radar"}
```

**Step 4: Commit**

```bash
git add curator-radar/
git commit -m "feat: backfill pipeline with star fetching, stargazer collection, and API routes"
```

---

## Task 4: Scoring Engine

**Files:**
- Create: `curator-radar/curator_radar/scoring.py`

**Step 1: Write `scoring.py`**

The core math: for each user who starred any of your repos, compute an overlap score weighted by repo popularity (IDF) and earlyness (how early they starred relative to others).

```python
import math
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import StarredRepo, RepoStargazer, Curator

logger = logging.getLogger(__name__)


async def score_curators(session: AsyncSession) -> int:
    """Score all candidate curators based on overlap, popularity weighting, and earlyness."""

    # 1. Get all starred repos with their stargazer counts
    repos_result = await session.execute(select(StarredRepo))
    repos = {r.repo_id: r for r in repos_result.scalars().all()}

    if not repos:
        logger.warning("No starred repos found. Run backfill first.")
        return 0

    # 2. For each repo, compute earlyness percentiles for all stargazers
    #    earlyness = 1 - percentile (1.0 = earliest, 0.0 = latest)
    #    We do this in SQL for efficiency: rank within each repo's stargazers.

    # 3. Aggregate per user: sum of (idf_weight * (1.0 + 0.7 * earlyness)) across overlapping repos
    #    IDF weight: log(1 + 100000 / (1 + stargazers_count))

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

    result = await session.execute(scoring_sql, {"username": "chaddorsey"})
    rows = result.fetchall()

    # Upsert all curator scores
    now = datetime.now(timezone.utc)
    count = 0
    for row in rows:
        stmt = pg_insert(Curator).values(
            user_login=row.user_login,
            overlap_count=row.overlap_count,
            overlap_score=round(row.overlap_score, 4),
            earlyness_mean=round(row.earlyness_mean, 4),
            last_scored_at=now,
            blocked=False,
        ).on_conflict_do_update(
            index_elements=["user_login"],
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
    logger.info(f"Scored {count} curators (from {len(rows)} candidates with >= 2 overlaps)")
    return count


async def get_top_curators(session: AsyncSession, top_k: int = 20) -> list[dict]:
    """Return top-K curators by score."""
    result = await session.execute(
        select(Curator)
        .where(Curator.blocked == False)
        .order_by(Curator.overlap_score.desc())
        .limit(top_k)
    )
    curators = result.scalars().all()
    return [
        {
            "user_login": c.user_login,
            "overlap_count": c.overlap_count,
            "overlap_score": c.overlap_score,
            "earlyness_mean": c.earlyness_mean,
            "github_url": f"https://github.com/{c.user_login}",
        }
        for c in curators
    ]
```

**Step 2: Commit**

```bash
git add curator-radar/curator_radar/scoring.py
git commit -m "feat: curator scoring engine with IDF weighting and earlyness percentiles"
```

---

## Task 5: Daily Monitor and Digest

**Files:**
- Create: `curator-radar/curator_radar/monitor.py`
- Create: `curator-radar/curator_radar/digest.py`

**Step 1: Write `monitor.py`**

```python
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from .models import Curator, CuratorEvent, StarredRepo
from .github_client import GitHubClient

logger = logging.getLogger(__name__)


async def refresh_curator_events(session: AsyncSession, client: GitHubClient, top_k: int = 20) -> int:
    """Fetch WatchEvents from top-K curators and store new ones."""
    result = await session.execute(
        select(Curator)
        .where(Curator.blocked == False)
        .order_by(Curator.overlap_score.desc())
        .limit(top_k)
    )
    curators = result.scalars().all()

    # Get repos Chad already starred (to flag novelty)
    chad_repos = await session.execute(select(StarredRepo.full_name))
    chad_repo_set = {r[0] for r in chad_repos.fetchall()}

    new_events = 0
    for curator in curators:
        logger.info(f"Checking events for {curator.user_login}")
        try:
            async for page in client.get_user_events(curator.user_login):
                for event in page:
                    if event.get("type") != "WatchEvent":
                        continue
                    repo_name = event.get("repo", {}).get("name", "")
                    if repo_name in chad_repo_set:
                        continue  # Skip repos Chad already starred

                    event_time = datetime.fromisoformat(
                        event["created_at"].replace("Z", "+00:00")
                    )
                    stmt = pg_insert(CuratorEvent).values(
                        event_id=str(event["id"]),
                        user_login=curator.user_login,
                        repo_full_name=repo_name,
                        event_time=event_time,
                        processed=False,
                    ).on_conflict_do_nothing()
                    result = await session.execute(stmt)
                    if result.rowcount > 0:
                        new_events += 1
        except Exception as e:
            logger.error(f"Error fetching events for {curator.user_login}: {e}")
            continue

    await session.commit()
    logger.info(f"Found {new_events} new WatchEvents from top-{top_k} curators")
    return new_events


async def get_discoveries(session: AsyncSession, since_days: int = 7) -> list[dict]:
    """Get repos discovered by curators in the last N days, ranked by curator count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    result = await session.execute(
        select(
            CuratorEvent.repo_full_name,
            Curator.overlap_score,
            CuratorEvent.user_login,
            CuratorEvent.event_time,
        )
        .join(Curator, Curator.user_login == CuratorEvent.user_login)
        .where(CuratorEvent.event_time >= cutoff)
        .order_by(CuratorEvent.event_time.desc())
    )
    rows = result.fetchall()

    # Group by repo, count unique curators, sum their scores
    repo_map: dict[str, dict] = {}
    for row in rows:
        repo = row.repo_full_name
        if repo not in repo_map:
            repo_map[repo] = {"repo": repo, "curators": [], "total_score": 0.0, "latest": row.event_time}
        if row.user_login not in [c["login"] for c in repo_map[repo]["curators"]]:
            repo_map[repo]["curators"].append({"login": row.user_login, "score": row.overlap_score})
            repo_map[repo]["total_score"] += row.overlap_score
        if row.event_time > repo_map[repo]["latest"]:
            repo_map[repo]["latest"] = row.event_time

    # Sort by number of curators (social proof), then total score
    ranked = sorted(repo_map.values(), key=lambda r: (len(r["curators"]), r["total_score"]), reverse=True)

    return [
        {
            "repo": r["repo"],
            "github_url": f"https://github.com/{r['repo']}",
            "curator_count": len(r["curators"]),
            "curators": [c["login"] for c in r["curators"]],
            "total_curator_score": round(r["total_score"], 2),
            "latest_event": r["latest"].isoformat(),
        }
        for r in ranked[:50]
    ]
```

**Step 2: Write `digest.py`**

```python
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from .scoring import get_top_curators
from .monitor import get_discoveries


async def generate_digest(session: AsyncSession, since_days: int = 7) -> str:
    """Generate a Markdown weekly digest."""
    curators = await get_top_curators(session, top_k=10)
    discoveries = await get_discoveries(session, since_days)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=since_days)

    lines = [
        f"# Curator Radar — Weekly Digest",
        f"**Period:** {start.strftime('%b %d')} — {now.strftime('%b %d, %Y')}",
        "",
    ]

    # Top curators section
    lines.append("## Top Curators")
    lines.append("| Rank | User | Overlap | Earlyness | Score |")
    lines.append("|------|------|---------|-----------|-------|")
    for i, c in enumerate(curators, 1):
        lines.append(
            f"| {i} | [{c['user_login']}]({c['github_url']}) | "
            f"{c['overlap_count']} repos | {c['earlyness_mean']:.2f} | {c['overlap_score']:.1f} |"
        )
    lines.append("")

    # Discoveries section
    if discoveries:
        lines.append(f"## New Discoveries ({len(discoveries)} repos)")
        lines.append("")
        for d in discoveries[:20]:
            curator_list = ", ".join(d["curators"][:5])
            lines.append(f"- **[{d['repo']}]({d['github_url']})** — {d['curator_count']} curator(s): {curator_list}")
        lines.append("")
    else:
        lines.append("## New Discoveries")
        lines.append("No new discoveries this period.")
        lines.append("")

    return "\n".join(lines)
```

**Step 3: Commit**

```bash
git add curator-radar/curator_radar/monitor.py curator-radar/curator_radar/digest.py
git commit -m "feat: daily curator monitor and weekly digest generator"
```

---

## Task 6: Docker Compose Integration and Database Setup

**Files:**
- Modify: `docker-compose.yml` (add curator-radar service)
- Modify: `.env` (add GITHUB_TOKEN)

**Step 1: Create the database in Supabase**

```bash
docker exec supabase-db psql -U postgres -c "CREATE DATABASE curator_radar;"
docker exec supabase-db psql -U postgres -c "CREATE USER curator_radar WITH PASSWORD 'curator_radar_secret';"
docker exec supabase-db psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE curator_radar TO curator_radar;"
docker exec supabase-db psql -U postgres -d curator_radar -c "GRANT ALL ON SCHEMA public TO curator_radar;"
```

**Step 2: Add GITHUB_TOKEN to `.env`**

```
# Curator Radar
GITHUB_TOKEN=ghp_your_personal_access_token_here
```

**Step 3: Add service to `docker-compose.yml`**

Add after the last service block (before `volumes:` or `networks:`):

```yaml
  # --- Curator Radar: GitHub star overlap monitoring ---
  curator-radar:
    build:
      context: ./curator-radar
    container_name: curator-radar
    restart: unless-stopped
    networks: [pa-internal]
    depends_on:
      supabase-db:
        condition: service_healthy
    environment:
      DATABASE_URL: "postgresql+asyncpg://curator_radar:curator_radar_secret@supabase-db:5432/curator_radar"
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_USERNAME: "chaddorsey"
      TOP_CURATORS_K: "20"
      SLACKBOT_NOTIFY_URL: "http://slackbot:8081/api/notify"
      SLACK_USER_ID: "${SLACK_USER_ID:-U02V91KU8}"
    ports:
      - "5145:5145"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5145/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

**Step 4: Build and start**

```bash
docker-compose up -d --build curator-radar
```

**Step 5: Verify health**

```bash
curl http://localhost:5145/health
```

**Step 6: Commit**

```bash
git add docker-compose.yml curator-radar/
git commit -m "feat: curator-radar Docker service with Supabase integration"
```

---

## Task 7: Register Scheduler Jobs

**Files:** None (API calls only)

**Step 1: Register daily monitor job**

```bash
curl -X POST http://localhost:8087/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SCHEDULER_API_KEY}" \
  -d '{
    "name": "curator-radar-daily-monitor",
    "description": "Refresh top curator WatchEvents daily",
    "expression": {"cron": "0 6 * * *"},
    "timezone": "America/New_York",
    "action": {
      "type": "webhook",
      "url": "http://curator-radar:5145/v1/monitor/refresh",
      "method": "POST"
    }
  }'
```

**Step 2: Register weekly digest job**

```bash
curl -X POST http://localhost:8087/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${SCHEDULER_API_KEY}" \
  -d '{
    "name": "curator-radar-weekly-digest",
    "description": "Generate and deliver weekly curator radar digest to Slack",
    "expression": {"cron": "0 15 * * 5"},
    "timezone": "America/New_York",
    "action": {
      "type": "webhook",
      "url": "http://curator-radar:5145/v1/digest/deliver",
      "method": "POST"
    }
  }'
```

---

## Task 8: Letta Tool for Agent Access

**Files:**
- Create: `letta/curator_radar_tools.py`
- Create: `letta/register_curator_radar_tools.py`

**Step 1: Write `curator_radar_tools.py`**

```python
from typing import Dict, Any, Optional


def query_curator_radar(endpoint: str, params: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the Curator Radar service for GitHub star overlap insights.

    Available endpoints:
      endpoint="curators"             -- Top curators ranked by overlap score
      endpoint="curators", params='{"top_k": 10}'  -- Limit results
      endpoint="discoveries"          -- New repos found by curators (last 7 days)
      endpoint="discoveries", params='{"since_days": 14}'  -- Custom window
      endpoint="digest"               -- Full weekly digest as Markdown
      endpoint="backfill/status"      -- Check backfill progress
      endpoint="score"                -- Trigger curator re-scoring (POST)

    Args:
        endpoint: The API endpoint to call (e.g. "curators", "discoveries", "digest")
        params: Optional JSON string of query parameters

    Returns:
        Dictionary with status and the API response.
    """
    import json
    import traceback
    import urllib.request
    import urllib.parse

    try:
        base_url = "http://curator-radar:5145/v1"
        url = f"{base_url}/{endpoint.strip('/')}"

        query_params = {}
        if params:
            query_params = json.loads(params)

        post_endpoints = {"backfill", "score", "monitor/refresh", "digest/deliver"}
        method = "POST" if endpoint.strip("/") in post_endpoints else "GET"

        if method == "GET" and query_params:
            url += "?" + urllib.parse.urlencode(query_params)

        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")

        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())

        return {"status": "ok", "result": data}

    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

**Step 2: Write `register_curator_radar_tools.py`**

```python
#!/usr/bin/env python3
"""Register Curator Radar tools with Letta."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from letta_client import Letta
from curator_radar_tools import query_curator_radar

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")


def register():
    client = Letta(base_url=LETTA_BASE_URL)
    tool = client.tools.upsert_from_function(
        func=query_curator_radar,
        tags=["curator-radar", "github", "discovery"],
    )
    print(f"Registered: {tool.name} ({tool.id})")


if __name__ == "__main__":
    register()
```

**Step 3: Register and attach**

```bash
LETTA_BASE_URL=http://localhost:8283 python3 letta/register_curator_radar_tools.py
```

**Step 4: Commit**

```bash
git add letta/curator_radar_tools.py letta/register_curator_radar_tools.py
git commit -m "feat: Letta tool for curator-radar agent access"
```

---

## Task 9: Run Initial Backfill

**Step 1: Trigger backfill**

```bash
curl -X POST http://localhost:5145/v1/backfill?since_days=365
```

**Step 2: Monitor progress** (poll periodically)

```bash
curl http://localhost:5145/v1/backfill/status
```

Expected: `{"starred_repos": ~100-144, "repos_with_stargazers_fetched": ..., "total_stargazer_rows": ..., "complete": false}`

Backfill runs in the background. With ~144 repos averaging ~5k stars each, expect ~1-2 hours at 5,000 req/hr.

**Step 3: Once complete, check curators**

```bash
curl http://localhost:5145/v1/curators?top_k=10
```

**Step 4: Generate first digest**

```bash
curl http://localhost:5145/v1/digest
```

---

## Task 10: WIP Tracker and Documentation

**Files:**
- Modify: `docs/plans/2026-02-23-wip-system-updates.md` (add WIP entry)

**Step 1: Add WIP entry**

Add to the WIP list:

```markdown
### Item 21: Curator Radar — GitHub Star Overlap Monitoring
- **Status:** Implementation planned
- **Plan:** [2026-03-08-curator-radar.md](2026-03-08-curator-radar.md)
- **Description:** Identifies GitHub users who share starring patterns with @chaddorsey, monitors their activity, and surfaces interesting new repos via weekly Slack digests. No LLM calls — pure code pipeline. FastAPI service on port 5145, Supabase PostgreSQL, scheduler-service cron jobs.
```

**Step 2: Commit**

```bash
git add docs/plans/
git commit -m "docs: add curator-radar implementation plan and WIP entry"
```
