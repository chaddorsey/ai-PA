#!/usr/bin/env python3
"""Extract entities from existing documents to knowledge graph.

This script processes documents that have been indexed but don't have
entity extraction yet, sending them to Graphiti for knowledge graph building.

Usage:
    python scripts/extract_entities.py --dry-run     # Preview what would be done
    python scripts/extract_entities.py --limit 10    # Process 10 documents (for testing)
    python scripts/extract_entities.py --estimate    # Estimate time/cost for all documents
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Set environment variables for local execution
if not os.environ.get("GOOGLE_CREDENTIALS_PATH"):
    os.environ["GOOGLE_CREDENTIALS_PATH"] = "/Users/dorseyhomeserver/.gmail-mcp"
if not os.environ.get("GOOGLE_TOKEN_PATH"):
    os.environ["GOOGLE_TOKEN_PATH"] = "/Users/dorseyhomeserver/.gmail-mcp/drive-docs-token.json"

import structlog

from drive_rag.auth import GoogleClient

# Override Graphiti URL for local execution
os.environ["GRAPHITI_BASE_URL"] = "http://localhost:8082"

from drive_rag.entities import extract_entities_from_document, get_graphiti_client
from drive_rag.normalizer import (
    normalize_docs_document,
    normalize_plain_text_document,
    normalize_spreadsheet_csv,
    normalize_presentation_text,
    normalize_pdf_document,
)

logger = structlog.get_logger()

# MIME type constants
GOOGLE_DOCS_MIME_TYPE = "application/vnd.google-apps.document"
GOOGLE_SHEETS_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDES_MIME_TYPE = "application/vnd.google-apps.presentation"
PDF_MIME_TYPE = "application/pdf"

# Cost estimation (GPT-4o-mini pricing per 1M tokens)
INPUT_COST_PER_1M = 0.15  # $0.15 per 1M input tokens
OUTPUT_COST_PER_1M = 0.60  # $0.60 per 1M output tokens

# Approximate tokens per character (GPT tokenization ~4 chars per token)
CHARS_PER_TOKEN = 4

# Estimated output tokens per document (entity extraction typically generates 200-500 tokens)
ESTIMATED_OUTPUT_TOKENS = 350

# Time per document for Graphiti processing (based on actual testing)
# Graphiti queues documents and processes them serially with LLM calls
# Actual processing: ~17 seconds per document (tested Feb 2026)
TIME_PER_DOC_SECONDS = 17.0


def run_db_query(query: str) -> str:
    """Run a query via docker exec psql."""
    result = subprocess.run(
        ["docker", "exec", "supabase-db", "psql", "-U", "postgres", "-d", "postgres",
         "-t", "-A", "-c", query],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Database query failed: {result.stderr}")
    return result.stdout.strip()


def get_documents_for_extraction(limit: int = None) -> list[dict]:
    """Get documents that need entity extraction.

    Returns documents with their content length for cost estimation.
    """
    # Get documents with normalized_text_length from snapshots or estimate from chunks
    query = """
        SELECT row_to_json(t) FROM (
            SELECT
                ds.drive_file_id,
                ds.title,
                ds.mime_type,
                ds.owner_email,
                ds.modified_time,
                COALESCE(snap.normalized_text_length, 0) as text_length
            FROM rag.document_state ds
            LEFT JOIN rag.document_snapshots snap
                ON ds.drive_file_id = snap.drive_file_id
            ORDER BY ds.drive_file_id
    """

    if limit:
        query += f" LIMIT {limit}"

    query += ") t;"

    output = run_db_query(query)
    if not output:
        return []

    docs = []
    for line in output.strip().split("\n"):
        if line.strip():
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    return docs


def get_document_count() -> int:
    """Get total count of documents."""
    result = run_db_query("SELECT COUNT(*) FROM rag.document_state;")
    return int(result) if result else 0


def estimate_costs(docs: list[dict]) -> dict:
    """Estimate time and token costs for entity extraction.

    Args:
        docs: List of documents with text_length

    Returns:
        Cost estimation dictionary
    """
    total_chars = sum(d.get("text_length", 5000) or 5000 for d in docs)  # Default 5k chars if unknown
    total_input_tokens = total_chars / CHARS_PER_TOKEN
    total_output_tokens = len(docs) * ESTIMATED_OUTPUT_TOKENS

    input_cost = (total_input_tokens / 1_000_000) * INPUT_COST_PER_1M
    output_cost = (total_output_tokens / 1_000_000) * OUTPUT_COST_PER_1M
    total_cost = input_cost + output_cost

    # Time estimate based on actual Graphiti processing times
    total_time_seconds = len(docs) * TIME_PER_DOC_SECONDS
    total_time_hours = total_time_seconds / 3600

    return {
        "document_count": len(docs),
        "total_characters": total_chars,
        "estimated_input_tokens": int(total_input_tokens),
        "estimated_output_tokens": int(total_output_tokens),
        "estimated_input_cost": round(input_cost, 2),
        "estimated_output_cost": round(output_cost, 2),
        "estimated_total_cost": round(total_cost, 2),
        "estimated_time_seconds": int(total_time_seconds),
        "estimated_time_hours": round(total_time_hours, 1),
    }


async def get_document_content(
    google: GoogleClient,
    file_id: str,
    mime_type: str,
) -> Optional[str]:
    """Get document content for entity extraction.

    First tries to load from snapshot, falls back to fetching from Drive.
    """
    from drive_rag.snapshots import load_snapshot

    # Try loading from snapshot first
    # Get latest revision ID from database
    query = f"SELECT last_seen_revision_id FROM rag.document_state WHERE drive_file_id = '{file_id}';"
    revision_id = run_db_query(query)

    if revision_id:
        snapshot = load_snapshot(file_id, revision_id)
        if snapshot:
            return snapshot.normalized_text

    # Fall back to fetching from Drive
    try:
        if mime_type == GOOGLE_DOCS_MIME_TYPE:
            try:
                doc = google.get_document(file_id)
                snapshot = normalize_docs_document(file_id, "temp", doc)
                return snapshot.normalized_text
            except Exception:
                plain_text = google.export_document_as_text(file_id)
                snapshot = normalize_plain_text_document(file_id, "temp", plain_text)
                return snapshot.normalized_text

        elif mime_type == GOOGLE_SHEETS_MIME_TYPE:
            csv_content = google.export_spreadsheet_as_csv(file_id)
            snapshot = normalize_spreadsheet_csv(file_id, "temp", csv_content)
            return snapshot.normalized_text

        elif mime_type == GOOGLE_SLIDES_MIME_TYPE:
            text_content = google.export_presentation_as_text(file_id)
            snapshot = normalize_presentation_text(file_id, "temp", text_content)
            return snapshot.normalized_text

        elif mime_type == PDF_MIME_TYPE:
            pdf_content = google.download_file_content(file_id)
            snapshot = normalize_pdf_document(file_id, "temp", pdf_content)
            return snapshot.normalized_text

    except Exception as e:
        logger.warning("content_fetch_failed", file_id=file_id, error=str(e))

    return None


async def extract_entities_for_document(
    google: GoogleClient,
    doc: dict,
) -> tuple[bool, str, dict]:
    """Extract entities for a single document.

    Returns:
        Tuple of (success, message, stats)
    """
    file_id = doc["drive_file_id"]
    title = doc["title"]
    mime_type = doc["mime_type"]

    stats = {
        "content_chars": 0,
        "time_seconds": 0,
        "estimated_input_tokens": 0,
    }

    start_time = time.time()

    try:
        # Get document content
        content = await get_document_content(google, file_id, mime_type)

        if not content:
            return False, f"Could not get content for {title[:40]}", stats

        stats["content_chars"] = len(content)
        stats["estimated_input_tokens"] = len(content) // CHARS_PER_TOKEN

        # Parse modified time
        modified_time = None
        if doc.get("modified_time"):
            try:
                if isinstance(doc["modified_time"], str):
                    modified_time = datetime.fromisoformat(
                        doc["modified_time"].replace("Z", "+00:00")
                    )
                else:
                    modified_time = doc["modified_time"]
            except Exception:
                pass

        # Extract entities via Graphiti
        result = await extract_entities_from_document(
            file_id=file_id,
            title=title,
            content=content,
            mime_type=mime_type,
            owner_email=doc.get("owner_email"),
            modified_time=modified_time,
        )

        stats["time_seconds"] = round(time.time() - start_time, 2)

        if result.get("status") == "ok":
            return True, f"Extracted entities for {title[:40]}", stats
        else:
            return False, f"Extraction failed for {title[:40]}: {result.get('error', 'unknown')}", stats

    except Exception as e:
        stats["time_seconds"] = round(time.time() - start_time, 2)
        return False, f"Error for {title[:40]}: {str(e)[:60]}", stats


async def main_async(args):
    """Async main function."""
    # Get documents
    print("Fetching document list...")
    docs = get_documents_for_extraction(limit=args.limit)
    total = len(docs)

    if total == 0:
        print("No documents found!")
        return

    # Estimate mode - show costs without processing
    if args.estimate or args.dry_run:
        print(f"\n{'='*60}")
        print("ENTITY EXTRACTION COST ESTIMATE")
        print(f"{'='*60}")

        if args.limit:
            # Get full count for comparison
            full_count = get_document_count()
            full_docs = get_documents_for_extraction(limit=full_count)
            full_estimate = estimate_costs(full_docs)

            print(f"\nSample size: {total} documents")
            sample_estimate = estimate_costs(docs)

            print(f"\n--- Sample ({total} docs) ---")
            print(f"  Input tokens:  ~{sample_estimate['estimated_input_tokens']:,}")
            print(f"  Output tokens: ~{sample_estimate['estimated_output_tokens']:,}")
            print(f"  Estimated cost: ${sample_estimate['estimated_total_cost']:.2f}")
            print(f"  Estimated time: {sample_estimate['estimated_time_seconds']}s ({sample_estimate['estimated_time_hours']:.1f}h)")

            print(f"\n--- Full Dataset ({full_count} docs) ---")
            print(f"  Input tokens:  ~{full_estimate['estimated_input_tokens']:,}")
            print(f"  Output tokens: ~{full_estimate['estimated_output_tokens']:,}")
            print(f"  Estimated cost: ${full_estimate['estimated_total_cost']:.2f}")
            print(f"  Estimated time: {full_estimate['estimated_time_hours']:.1f} hours")
        else:
            estimate = estimate_costs(docs)
            print(f"\nTotal documents: {estimate['document_count']:,}")
            print(f"Total characters: {estimate['total_characters']:,}")
            print(f"\nToken Estimates (GPT-4o-mini):")
            print(f"  Input tokens:  ~{estimate['estimated_input_tokens']:,}")
            print(f"  Output tokens: ~{estimate['estimated_output_tokens']:,}")
            print(f"\nCost Breakdown:")
            print(f"  Input cost:  ${estimate['estimated_input_cost']:.2f}")
            print(f"  Output cost: ${estimate['estimated_output_cost']:.2f}")
            print(f"  Total cost:  ${estimate['estimated_total_cost']:.2f}")
            print(f"\nTime Estimate:")
            print(f"  ~{estimate['estimated_time_hours']:.1f} hours")

        if args.dry_run:
            print(f"\n--- Sample Documents ---")
            for doc in docs[:10]:
                print(f"  - {doc['title'][:60]}")
            if total > 10:
                print(f"  ... and {total - 10} more")

        return

    # Initialize clients
    print("Initializing clients...")
    google = GoogleClient()

    # Check Graphiti connectivity
    client = get_graphiti_client()
    status = await client.get_status()
    if status.get("status") != "healthy":
        print(f"Warning: Graphiti not healthy: {status}")
        return

    print(f"Graphiti status: {status.get('status')}")
    print(f"\nProcessing {total} documents...")

    # Process documents
    success_count = 0
    error_count = 0
    total_time = 0
    total_input_tokens = 0
    errors = []

    for i, doc in enumerate(docs, 1):
        success, message, stats = await extract_entities_for_document(google, doc)

        total_time += stats.get("time_seconds", 0)
        total_input_tokens += stats.get("estimated_input_tokens", 0)

        if success:
            success_count += 1
            if args.verbose:
                print(f"  ✓ {message} ({stats['time_seconds']}s, ~{stats['estimated_input_tokens']} tokens)")
        else:
            error_count += 1
            errors.append(message)
            if args.verbose:
                print(f"  ✗ {message}")

        # Progress report every 10 documents or at end
        if i % 10 == 0 or i == total:
            avg_time = total_time / i
            remaining = (total - i) * avg_time
            print(f"  Progress: {i}/{total} ({i*100//total}%) - "
                  f"Success: {success_count}, Errors: {error_count}, "
                  f"Avg: {avg_time:.1f}s/doc, ETA: {remaining/60:.1f}min")

    # Final summary
    print(f"\n{'='*60}")
    print("ENTITY EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"  Documents processed: {total}")
    print(f"  Success: {success_count}")
    print(f"  Errors:  {error_count}")
    print(f"\nActual Stats:")
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"  Avg time per doc: {total_time/total:.2f}s")
    print(f"  Est. input tokens: ~{total_input_tokens:,}")

    # Cost calculation
    estimated_output = total * ESTIMATED_OUTPUT_TOKENS
    input_cost = (total_input_tokens / 1_000_000) * INPUT_COST_PER_1M
    output_cost = (estimated_output / 1_000_000) * OUTPUT_COST_PER_1M
    print(f"\nEstimated Cost:")
    print(f"  Input:  ${input_cost:.3f}")
    print(f"  Output: ${output_cost:.3f}")
    print(f"  Total:  ${input_cost + output_cost:.3f}")

    if errors and not args.verbose:
        print(f"\nFirst 5 errors:")
        for err in errors[:5]:
            print(f"  - {err}")


def main():
    parser = argparse.ArgumentParser(description="Extract entities from documents to knowledge graph")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be done")
    parser.add_argument("--estimate", action="store_true", help="Show cost/time estimates only")
    parser.add_argument("--limit", type=int, help="Limit number of documents to process")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
