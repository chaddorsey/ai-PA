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
