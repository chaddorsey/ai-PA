"""OpenAI embeddings with batching and rate limiting.

This module handles embedding generation for document chunks:
- Batch embedding requests for efficiency
- Rate limiting with exponential backoff
- Caching for repeated texts (optional)
"""

import asyncio
from typing import Optional

import structlog
from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from drive_rag.settings import get_settings

logger = structlog.get_logger()


class Embedder:
    """OpenAI embeddings client with batching support."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        """Initialize the embedder.

        Args:
            api_key: OpenAI API key (defaults to settings)
            model: Embedding model name (defaults to settings)
            batch_size: Max texts per API call (defaults to settings)
        """
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self.model = model or settings.embedding_model
        self.batch_size = batch_size or settings.embedding_batch_size
        self.dimensions = settings.embedding_dimensions

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=lambda retry_state: logger.warning(
            "embedding_retry",
            attempt=retry_state.attempt_number,
            error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
        ),
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a single batch of texts with retry logic.

        Args:
            texts: List of texts to embed (max batch_size)

        Returns:
            List of embedding vectors
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
        )

        # Sort by index to ensure order matches input
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts, handling batching automatically.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (same order as input)
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

            # Small delay between batches to avoid rate limits
            if i + self.batch_size < len(texts):
                await asyncio.sleep(0.1)

        logger.info(
            "embedded_texts",
            count=len(texts),
            batches=(len(texts) + self.batch_size - 1) // self.batch_size,
            model=self.model,
        )

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        embeddings = await self.embed([text])
        return embeddings[0]


# Module-level singleton for convenience
_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    """Get or create the global embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Convenience function to embed texts using the global embedder."""
    embedder = get_embedder()
    return await embedder.embed(texts)


async def embed_text(text: str) -> list[float]:
    """Convenience function to embed a single text."""
    embedder = get_embedder()
    return await embedder.embed_single(text)
