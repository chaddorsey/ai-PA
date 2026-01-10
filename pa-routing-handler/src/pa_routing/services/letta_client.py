"""Letta API client for archival memory operations.

Provides methods for:
- Pattern 3: Writing passages to archival memory (fire-and-forget)
- Pattern 4: Querying passages for briefing injection
"""

import httpx
import structlog
from datetime import datetime
from typing import Optional

logger = structlog.get_logger()

# Metatag identifying session memory passages
SESSION_MEMORY_TAG = "memory:session"


class LettaClient:
    """
    Client for Letta archival memory operations.

    Used by the orchestrator to:
    - Write session summaries to Main Agent's archival (Pattern 3)
    - Query recent passages for briefing injection (Pattern 4)

    Note: Archival operations require Letta to have a working embedding model.
    If embeddings fail, operations degrade gracefully (empty results, skipped writes).
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        """Initialize with short timeout to avoid blocking on slow embedding calls."""
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)

    async def create_passage(
        self,
        agent_id: str,
        text: str,
        tags: list[str] | None = None,
    ) -> dict | None:
        """
        Write passage to agent's archival memory.

        Pattern 3: Fire-and-forget persistence. Caller should use
        asyncio.create_task() to avoid blocking.

        Args:
            agent_id: The agent whose archival to write to (typically main agent)
            text: The passage text to store
            tags: List of tags for filtering (e.g., ["session:2026-01-09", "agent:calendar"])

        Returns:
            Created passage dict on success, None on failure
        """
        # Always include session memory metatag
        all_tags = [SESSION_MEMORY_TAG] + (tags or [])

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/agents/{agent_id}/archival-memory",
                    json={"text": text, "tags": all_tags}
                )
                response.raise_for_status()
                result = response.json()

                logger.info(
                    "passage_created",
                    agent_id=agent_id,
                    text_preview=text[:50],
                    tags=all_tags,
                )
                return result

        except httpx.HTTPStatusError as e:
            logger.warning(
                "passage_create_failed",
                agent_id=agent_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.warning(
                "passage_create_error",
                agent_id=agent_id,
                error=str(e),
            )
            return None

    async def list_passages(
        self,
        agent_id: str,
        tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Query passages from agent's archival memory.

        Pattern 4: Called once before main agent to get session briefing.
        Adds ~50-100ms latency.

        Args:
            agent_id: The agent whose archival to query
            tags: Filter tags (e.g., ["session:2026-01-09"])
            limit: Max passages to return

        Returns:
            List of passage dicts, empty list on failure
        """
        # Always filter to session memory
        filter_tags = [SESSION_MEMORY_TAG] + (tags or [])

        # Build query params for search endpoint
        params = {
            "query": "session",  # Required query string
            "top_k": limit,
        }
        # Add tags as list parameter
        if filter_tags:
            params["tags"] = filter_tags

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/v1/agents/{agent_id}/archival-memory/search",
                    params=params
                )
                response.raise_for_status()
                data = response.json()

                # Handle various response formats from Letta API
                if isinstance(data, list):
                    passages = data
                else:
                    # Search endpoint returns "results", list endpoint may return "passages" or "items"
                    passages = data.get("results", data.get("passages", data.get("items", [])))

                logger.info(
                    "passages_retrieved",
                    agent_id=agent_id,
                    count=len(passages),
                    tags=filter_tags,
                )
                return passages

        except httpx.HTTPStatusError as e:
            logger.warning(
                "passages_list_failed",
                agent_id=agent_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            return []
        except Exception as e:
            logger.warning(
                "passages_list_error",
                agent_id=agent_id,
                error=str(e),
            )
            return []

    def format_briefing(self, passages: list[dict]) -> str:
        """
        Format retrieved passages as briefing string for injection.

        Returns empty string if no passages (zero overhead for empty case).

        Args:
            passages: List of passage dicts from list_passages()

        Returns:
            Formatted briefing string or empty string
        """
        if not passages:
            return ""

        lines = ["[Today's session briefing:]"]
        for p in passages:
            # Handle both formats: search returns "content", list returns "text"
            text = p.get("content", p.get("text", ""))
            # Truncate long passages for briefing
            if len(text) > 100:
                text = text[:97] + "..."
            lines.append(f"  • {text}")

        return "\n".join(lines)

    def build_session_tags(
        self,
        agent_name: str,
        topics: list[str] | None = None,
        user_id: str | None = None,
    ) -> list[str]:
        """
        Build standard tag set for a session passage.

        Args:
            agent_name: Name of the responding agent
            topics: Topic tags extracted from SUMMARY hashtags
            user_id: User identifier (optional)

        Returns:
            List of tags following flat convention
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")

        tags = [
            f"session:{today}",
            f"agent:{agent_name}",
        ]

        # Add topic tags
        if topics:
            for topic in topics:
                tags.append(f"topic:{topic}")

        # Add user tag if provided
        if user_id:
            tags.append(f"user:{user_id}")

        return tags
