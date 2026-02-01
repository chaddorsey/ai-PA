"""Structure-aware text chunking for document embeddings.

This module creates chunks from normalized text, respecting document structure:
- Keeps heading boundaries intact
- Groups related blocks together
- Generates stable chunk IDs for incremental updates
- Targets optimal chunk sizes for embedding models
"""

import hashlib
from typing import Optional

import structlog

from drive_rag.models import ChunkRecord, StructureBlock
from drive_rag.settings import get_settings

logger = structlog.get_logger()


def sha256_hex(text: str) -> str:
    """Generate SHA-256 hash of text as hex string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_from_normalized(
    file_id: str,
    revision_id: str,
    title: str,
    normalized_text: str,
    blocks: list[StructureBlock],
    max_chunk_chars: Optional[int] = None,
    min_chunk_chars: Optional[int] = None,
) -> list[ChunkRecord]:
    """Create chunks from normalized text and structure blocks.

    Strategy:
    - Group consecutive blocks by outline_path
    - Respect heading boundaries when possible
    - Target chunk size between min and max chars
    - Generate stable chunk IDs from file + outline + block range

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID
        title: Document title
        normalized_text: Full normalized document text
        blocks: Structure blocks from normalization
        max_chunk_chars: Maximum characters per chunk
        min_chunk_chars: Minimum characters per chunk (soft limit)

    Returns:
        List of ChunkRecord ready for embedding
    """
    settings = get_settings()
    max_chars = max_chunk_chars or settings.max_chunk_chars
    min_chars = min_chunk_chars or settings.min_chunk_chars

    if not blocks:
        logger.warning("no_blocks_to_chunk", file_id=file_id)
        return []

    chunks: list[ChunkRecord] = []
    i = 0

    while i < len(blocks):
        start_block = blocks[i]
        start_outline = "/".join(start_block.outline_path)

        # Get character positions
        char_start = start_block.char_start or 0
        char_end = start_block.char_end or char_start
        end_index = i

        # Try to extend chunk with more blocks
        while end_index + 1 < len(blocks):
            next_block = blocks[end_index + 1]
            next_outline = "/".join(next_block.outline_path)

            # Would we cross a major section boundary?
            would_cross_section = next_outline != start_outline

            # Calculate proposed size
            next_end = next_block.char_end or char_end
            proposed_size = next_end - char_start

            # Stop if we'd exceed max size
            if proposed_size > max_chars:
                break

            # If crossing section and we already have enough content, stop
            if would_cross_section and (char_end - char_start) >= min_chars:
                break

            # Include the next block
            char_end = next_end
            end_index += 1

        # If chunk is too small, try to grab one more block
        if (char_end - char_start) < min_chars and end_index + 1 < len(blocks):
            next_block = blocks[end_index + 1]
            next_end = next_block.char_end or char_end
            if (next_end - char_start) <= max_chars:
                char_end = next_end
                end_index += 1

        # Get the block range
        block_start_id = blocks[i].block_id
        block_end_id = blocks[end_index].block_id
        outline_path = blocks[i].outline_path

        # Extract chunk text from normalized text
        chunk_text = normalized_text[char_start:char_end]
        chunk_hash = sha256_hex(chunk_text)

        # Generate stable chunk ID
        chunk_id = sha256_hex(
            f"{file_id}:{'/'.join(outline_path)}:{block_start_id}:{block_end_id}"
        )

        chunks.append(
            ChunkRecord(
                drive_file_id=file_id,
                revision_id=revision_id,
                title=title,
                chunk_id=chunk_id,
                outline_path=outline_path,
                block_start_id=block_start_id,
                block_end_id=block_end_id,
                char_start=char_start,
                char_end=char_end,
                chunk_text=chunk_text,
                chunk_hash=chunk_hash,
            )
        )

        # Move to next unprocessed block
        i = end_index + 1

    logger.info(
        "chunked_document",
        file_id=file_id,
        blocks_count=len(blocks),
        chunks_count=len(chunks),
        avg_chunk_size=sum(c.char_end - c.char_start for c in chunks) // max(len(chunks), 1),
    )

    return chunks


def diff_chunks(
    prev_chunks: list[ChunkRecord],
    new_chunks: list[ChunkRecord],
) -> tuple[list[ChunkRecord], list[ChunkRecord], list[ChunkRecord]]:
    """Compare previous and new chunks to find what changed.

    Returns:
        Tuple of (to_add, to_update, to_delete) chunk lists
    """
    prev_by_id = {c.chunk_id: c for c in prev_chunks}
    new_by_id = {c.chunk_id: c for c in new_chunks}

    to_add: list[ChunkRecord] = []
    to_update: list[ChunkRecord] = []
    to_delete: list[ChunkRecord] = []

    # Check new chunks
    for chunk in new_chunks:
        prev = prev_by_id.get(chunk.chunk_id)
        if prev is None:
            to_add.append(chunk)
        elif prev.chunk_hash != chunk.chunk_hash:
            to_update.append(chunk)
        # If hash matches, no change needed

    # Find deleted chunks
    for chunk in prev_chunks:
        if chunk.chunk_id not in new_by_id:
            to_delete.append(chunk)

    logger.info(
        "chunk_diff",
        to_add=len(to_add),
        to_update=len(to_update),
        to_delete=len(to_delete),
        unchanged=len(new_chunks) - len(to_add) - len(to_update),
    )

    return to_add, to_update, to_delete
