"""Embedding utilities for scheduling content."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List, Optional

from scheduler_service.logging_config import get_logger
from scheduler_service.settings import settings

logger = get_logger(__name__)


try:  # pragma: no cover - optional dependency
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - handled gracefully
    SentenceTransformer = None  # type: ignore


@lru_cache(maxsize=1)
def _get_model() -> Optional["SentenceTransformer"]:
    if SentenceTransformer is None:
        logger.warning(
            "sentence-transformers not available; embeddings will be disabled",
            model=settings.embedding_model_name,
        )
        return None

    logger.info("Loading embedding model", model=settings.embedding_model_name)
    try:
        return SentenceTransformer(
            settings.embedding_model_name, cache_folder=settings.embedding_cache_dir
        )
    except Exception as exc:  # pragma: no cover - dependency load failure
        logger.error(
            "Failed to load embedding model; embeddings disabled",
            model=settings.embedding_model_name,
            error=str(exc),
        )
        return None


def embed_text(text: str) -> Optional[List[float]]:
    """Return embedding vector for the provided text."""

    model = _get_model()
    if model is None:  # pragma: no cover - dependency missing path
        return None

    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_texts(texts: Iterable[str]) -> Optional[List[float]]:
    """Embed multiple texts by concatenating them before encoding."""

    combined = "\n".join(filter(None, texts))
    if not combined.strip():
        logger.debug("No text provided for embedding")
        return None
    return embed_text(combined)


