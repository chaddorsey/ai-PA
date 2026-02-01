"""Normalize Google Docs API content to stable text with structure blocks.

This module converts the complex JSON structure from the Google Docs API
into a normalized text format suitable for chunking and embedding.

Key responsibilities:
- Walk the Docs API document structure
- Extract text from paragraphs, headings, lists, and tables
- Track heading hierarchy for outline_path
- Normalize whitespace and characters
- Generate stable hashes for change detection
"""

import hashlib
import re
import unicodedata
from typing import Any, Optional

import structlog

from drive_rag.models import NormalizedSnapshot, StructureBlock

logger = structlog.get_logger()


def sha256_hex(text: str) -> str:
    """Generate SHA-256 hash of text as hex string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    """Normalize a block of text for stable comparison.

    - Unicode NFC normalization
    - Unified newlines
    - Collapse multiple spaces
    - Trim trailing whitespace per line
    """
    # Unicode normalize (NFC)
    nfc = unicodedata.normalize("NFC", text)

    # Unify newlines
    unified = nfc.replace("\r\n", "\n").replace("\r", "\n")

    # Process line by line
    lines = []
    for line in unified.split("\n"):
        # Collapse multiple spaces/tabs to single space
        collapsed = re.sub(r"[ \t]+", " ", line)
        # Trim trailing whitespace
        trimmed = collapsed.rstrip()
        lines.append(trimmed)

    return "\n".join(lines).strip()


def normalize_global_text(text: str) -> str:
    """Final normalization of the complete document text.

    - Collapse 3+ newlines to 2 (preserve paragraph breaks)
    - Trim
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    collapsed = re.sub(r"\n{3,}", "\n\n", unified)
    return collapsed.strip()


def heading_level_from_named_style(named_style_type: Optional[str]) -> Optional[int]:
    """Extract heading level from Google Docs named style type.

    Examples: HEADING_1 -> 1, HEADING_2 -> 2, NORMAL_TEXT -> None
    """
    if not named_style_type:
        return None

    match = re.match(r"^HEADING_(\d)$", named_style_type)
    if match:
        return int(match.group(1))
    return None


def is_list_item(paragraph: dict[str, Any]) -> bool:
    """Check if a paragraph is a list item."""
    return bool(paragraph.get("bullet"))


def list_level_from_paragraph(paragraph: dict[str, Any]) -> Optional[int]:
    """Get the nesting level of a list item."""
    bullet = paragraph.get("bullet", {})
    nesting_level = bullet.get("nestingLevel")
    if nesting_level is not None:
        return int(nesting_level)
    return None


def extract_inline_text(elements: list[dict[str, Any]]) -> str:
    """Extract text from inline elements (textRun, inlineObjects, etc.)."""
    parts = []
    for element in elements:
        if "textRun" in element:
            content = element["textRun"].get("content", "")
            parts.append(content)
        elif "inlineObjectElement" in element:
            parts.append(" [IMAGE] ")
        elif "horizontalRule" in element:
            parts.append("\n")
        # Add more element types as needed

    return "".join(parts)


def extract_table_row_text(row: dict[str, Any]) -> str:
    """Extract text from a table row as pipe-separated cells."""
    cells = row.get("tableCells", [])
    cell_texts = []

    for cell in cells:
        cell_content = cell.get("content", [])
        cell_text = ""
        for element in cell_content:
            if "paragraph" in element:
                para_elements = element["paragraph"].get("elements", [])
                cell_text += extract_inline_text(para_elements)
        cell_texts.append(normalize_text(cell_text.strip()))

    return f"| {' | '.join(cell_texts)} |"


def normalize_docs_document(
    file_id: str,
    revision_id: str,
    doc: dict[str, Any],
) -> NormalizedSnapshot:
    """Convert a Google Docs API document to normalized text with structure blocks.

    Args:
        file_id: Google Drive file ID
        revision_id: Document revision ID
        doc: Google Docs API document response

    Returns:
        NormalizedSnapshot with normalized text and structure blocks
    """
    blocks: list[StructureBlock] = []
    text_parts: list[str] = []

    # Track heading hierarchy for outline_path
    outline_stack: list[tuple[str, int]] = []  # (heading_text, level)

    cursor = 0  # Character position in normalized text

    body = doc.get("body", {})
    content = body.get("content", [])

    for element in content:
        # Handle paragraphs
        if "paragraph" in element:
            para = element["paragraph"]
            style = para.get("paragraphStyle", {})
            named_style = style.get("namedStyleType")
            heading_level = heading_level_from_named_style(named_style)

            # Extract text from paragraph elements
            para_elements = para.get("elements", [])
            raw_text = extract_inline_text(para_elements)
            trimmed = raw_text.strip()

            # Skip empty paragraphs
            if not trimmed:
                continue

            # Determine block type
            if heading_level is not None:
                block_type = "heading"
            elif is_list_item(para):
                block_type = "list_item"
            else:
                block_type = "paragraph"

            # Update outline stack for headings
            if block_type == "heading" and heading_level is not None:
                # Pop headings at same or higher level
                outline_stack = [
                    (text, level) for text, level in outline_stack if level < heading_level
                ]
                outline_stack.append((trimmed, heading_level))

            outline_path = [text for text, _ in outline_stack]

            # Normalize the paragraph text
            normalized_para = normalize_text(trimmed)

            # Calculate character positions
            separator = "" if not text_parts else "\n\n"
            char_start = cursor + len(separator)
            text_chunk = separator + normalized_para
            text_parts.append(text_chunk)
            cursor += len(text_chunk)
            char_end = cursor

            # Generate stable block ID
            text_hash = sha256_hex(normalized_para)
            block_id = sha256_hex(
                f"{block_type}:{':'.join(outline_path)}:{heading_level}:{text_hash}"
            )

            blocks.append(
                StructureBlock(
                    block_id=block_id,
                    type=block_type,
                    outline_path=outline_path,
                    heading_level=heading_level,
                    list_level=list_level_from_paragraph(para),
                    text_hash=text_hash,
                    char_start=char_start,
                    char_end=char_end,
                    text=normalized_para,
                )
            )

        # Handle tables
        elif "table" in element:
            table = element["table"]
            table_rows = table.get("tableRows", [])

            for row in table_rows:
                row_text = extract_table_row_text(row)

                # Skip empty rows
                if not row_text or row_text == "|  |":
                    continue

                outline_path = [text for text, _ in outline_stack]

                # Calculate character positions
                separator = "" if not text_parts else "\n\n"
                char_start = cursor + len(separator)
                text_chunk = separator + row_text
                text_parts.append(text_chunk)
                cursor += len(text_chunk)
                char_end = cursor

                text_hash = sha256_hex(row_text)
                block_id = sha256_hex(f"table_row:{':'.join(outline_path)}:{text_hash}")

                blocks.append(
                    StructureBlock(
                        block_id=block_id,
                        type="table_row",
                        outline_path=outline_path,
                        text_hash=text_hash,
                        char_start=char_start,
                        char_end=char_end,
                        text=row_text,
                    )
                )

        # Other element types (sectionBreak, tableOfContents, etc.) are skipped

    # Combine all text and do final normalization
    full_text = "".join(text_parts)
    normalized_text = normalize_global_text(full_text)

    # Generate content hash for the entire document
    normalized_hash = sha256_hex(normalized_text)

    logger.info(
        "normalized_document",
        file_id=file_id,
        revision_id=revision_id,
        blocks_count=len(blocks),
        text_length=len(normalized_text),
        content_hash=normalized_hash[:16],
    )

    return NormalizedSnapshot(
        normalized_text=normalized_text,
        normalized_hash=normalized_hash,
        blocks=blocks,
    )
