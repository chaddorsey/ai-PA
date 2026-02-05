#!/usr/bin/env python3
"""Populate snapshots for existing documents.

This script creates snapshots for documents that were indexed before the
snapshot feature was added, without re-chunking the content.

Usage:
    python scripts/populate_snapshots.py --dry-run  # Preview what would be done
    python scripts/populate_snapshots.py            # Create snapshots
    python scripts/populate_snapshots.py --limit 100  # Process only 100 documents
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

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
from drive_rag.db import get_db
from drive_rag.models import DocumentSnapshot
from drive_rag.snapshots import save_snapshot
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


def insert_snapshot_metadata(
    drive_file_id: str,
    revision_id: str,
    content_hash: str,
    normalized_text_length: int,
    blocks_count: int,
    compressed_size_bytes: int,
    snapshot_path: str,
    modifier_email: str = None,
    modifier_name: str = None,
    modified_time: datetime = None,
) -> None:
    """Insert snapshot metadata via direct SQL.

    Uses docker exec psql to bypass PostgREST auth issues.
    """
    import subprocess

    # Escape single quotes in strings
    def escape(s):
        if s is None:
            return "NULL"
        return "'" + str(s).replace("'", "''") + "'"

    # Format modified_time
    mod_time = "NULL"
    if modified_time:
        if isinstance(modified_time, datetime):
            mod_time = f"'{modified_time.isoformat()}'"
        else:
            mod_time = escape(str(modified_time))

    query = f"""
        INSERT INTO rag.document_snapshots (
            drive_file_id, revision_id, content_hash, normalized_text_length,
            blocks_count, compressed_size_bytes, snapshot_path,
            modifier_email, modifier_name, modified_time
        ) VALUES (
            {escape(drive_file_id)}, {escape(revision_id)}, {escape(content_hash)},
            {normalized_text_length}, {blocks_count}, {compressed_size_bytes},
            {escape(snapshot_path)}, {escape(modifier_email)}, {escape(modifier_name)},
            {mod_time}
        ) ON CONFLICT (drive_file_id, revision_id) DO UPDATE SET
            content_hash = EXCLUDED.content_hash,
            snapshot_path = EXCLUDED.snapshot_path,
            compressed_size_bytes = EXCLUDED.compressed_size_bytes;
    """

    result = subprocess.run(
        ["docker", "exec", "supabase-db", "psql", "-U", "postgres", "-d", "postgres",
         "-c", query],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Insert failed: {result.stderr}")


def run_db_query(query: str) -> str:
    """Run a query via docker exec psql.

    Args:
        query: SQL query to execute

    Returns:
        Query output as string
    """
    import subprocess

    result = subprocess.run(
        ["docker", "exec", "supabase-db", "psql", "-U", "postgres", "-d", "postgres",
         "-t", "-A", "-c", query],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Database query failed: {result.stderr}")

    return result.stdout.strip()


def get_documents_without_snapshots_count() -> int:
    """Get count of documents without snapshots."""
    query = """
        SELECT COUNT(*)
        FROM rag.document_state ds
        LEFT JOIN rag.document_snapshots snap
            ON ds.drive_file_id = snap.drive_file_id
            AND ds.last_seen_revision_id = snap.revision_id
        WHERE snap.id IS NULL;
    """
    result = run_db_query(query)
    return int(result) if result else 0


def get_documents_without_snapshots_batch(offset: int, batch_size: int) -> list[dict]:
    """Get a batch of documents without snapshots.

    Args:
        offset: Row offset
        batch_size: Number of rows to fetch

    Returns:
        List of document state records
    """
    import json

    query = f"""
        SELECT row_to_json(t) FROM (
            SELECT ds.drive_file_id, ds.title, ds.mime_type, ds.last_seen_revision_id,
                   ds.last_modifier_email, ds.last_modifier_name, ds.modified_time
            FROM rag.document_state ds
            LEFT JOIN rag.document_snapshots snap
                ON ds.drive_file_id = snap.drive_file_id
                AND ds.last_seen_revision_id = snap.revision_id
            WHERE snap.id IS NULL
            ORDER BY ds.drive_file_id
            OFFSET {offset} LIMIT {batch_size}
        ) t;
    """

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


def create_snapshot_for_document(
    google: GoogleClient,
    db,
    doc: dict,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Create a snapshot for a single document.

    Args:
        google: Google API client
        db: Database connection
        doc: Document state record
        dry_run: If True, don't actually save

    Returns:
        Tuple of (success, message)
    """
    file_id = doc["drive_file_id"]
    title = doc["title"]
    mime_type = doc["mime_type"]
    revision_id = doc["last_seen_revision_id"]

    if dry_run:
        return True, f"Would create snapshot for {title[:40]}"

    try:
        # Fetch and normalize content based on file type
        if mime_type == GOOGLE_DOCS_MIME_TYPE:
            try:
                doc_content = google.get_document(file_id)
                snapshot = normalize_docs_document(file_id, revision_id, doc_content)
            except Exception:
                plain_text = google.export_document_as_text(file_id)
                snapshot = normalize_plain_text_document(file_id, revision_id, plain_text)

        elif mime_type == GOOGLE_SHEETS_MIME_TYPE:
            csv_content = google.export_spreadsheet_as_csv(file_id)
            snapshot = normalize_spreadsheet_csv(file_id, revision_id, csv_content)

        elif mime_type == GOOGLE_SLIDES_MIME_TYPE:
            text_content = google.export_presentation_as_text(file_id)
            snapshot = normalize_presentation_text(file_id, revision_id, text_content)

        elif mime_type == PDF_MIME_TYPE:
            pdf_content = google.download_file_content(file_id)
            snapshot = normalize_pdf_document(file_id, revision_id, pdf_content)
        else:
            return False, f"Unsupported mime type: {mime_type}"

        # Parse modified time
        modified_time = None
        if doc.get("modified_time"):
            if isinstance(doc["modified_time"], datetime):
                modified_time = doc["modified_time"]
            elif isinstance(doc["modified_time"], str):
                modified_time = datetime.fromisoformat(doc["modified_time"].replace("Z", "+00:00"))

        # Save snapshot to filesystem
        snapshot_meta = save_snapshot(
            file_id=file_id,
            revision_id=revision_id,
            snapshot=snapshot,
            modifier_email=doc.get("last_modifier_email"),
            modifier_name=doc.get("last_modifier_name"),
            modified_time=modified_time,
        )

        # Store metadata in database via direct SQL (bypass PostgREST auth issues)
        insert_snapshot_metadata(
            drive_file_id=file_id,
            revision_id=revision_id,
            content_hash=snapshot_meta["content_hash"],
            normalized_text_length=snapshot_meta["normalized_text_length"],
            blocks_count=snapshot_meta["blocks_count"],
            compressed_size_bytes=snapshot_meta["compressed_size_bytes"],
            snapshot_path=snapshot_meta["snapshot_path"],
            modifier_email=snapshot_meta["modifier_email"],
            modifier_name=snapshot_meta["modifier_name"],
            modified_time=snapshot_meta["modified_time"],
        )

        return True, f"Created snapshot for {title[:40]}"

    except Exception as e:
        return False, f"Error for {title[:40]}: {str(e)[:60]}"


def main():
    parser = argparse.ArgumentParser(description="Populate snapshots for existing documents")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be done")
    parser.add_argument("--limit", type=int, help="Limit number of documents to process")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for fetching")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--retry-errors", action="store_true", help="Retry previously failed documents")
    args = parser.parse_args()

    # Initialize clients
    print("Initializing clients...")
    db = get_db()
    google = GoogleClient()

    # Get count of documents without snapshots
    print("Counting documents without snapshots...")
    total = get_documents_without_snapshots_count()

    if args.limit:
        total = min(total, args.limit)

    print(f"Found {total:,} documents without snapshots")

    if total == 0:
        print("All documents have snapshots!")
        return

    if args.dry_run:
        print("\n--- DRY RUN MODE ---")
        print("Would create snapshots for:")
        sample_docs = get_documents_without_snapshots_batch(0, min(20, total))
        for doc in sample_docs:
            print(f"  - {doc['title'][:60]}")
        if total > 20:
            print(f"  ... and {total - 20:,} more")
        return

    # Process documents in batches
    success_count = 0
    error_count = 0
    errors = []
    processed = 0
    batch_size = args.batch_size

    while processed < total:
        # Fetch next batch (always from offset 0 since processed docs get snapshots)
        docs = get_documents_without_snapshots_batch(0, batch_size)

        if not docs:
            print("No more documents to process")
            break

        for doc in docs:
            if args.limit and processed >= args.limit:
                break

            success, message = create_snapshot_for_document(
                google, db, doc, dry_run=args.dry_run
            )

            if success:
                success_count += 1
            else:
                error_count += 1
                errors.append(message)
                if args.verbose:
                    print(f"  ERROR: {message}")

            processed += 1

            # Progress report every 100 documents
            if processed % 100 == 0 or processed == total:
                print(f"  Progress: {processed:,}/{total:,} ({processed*100//total}%) - Success: {success_count:,}, Errors: {error_count:,}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Snapshot Population Complete")
    print(f"{'='*60}")
    print(f"  Success: {success_count:,}")
    print(f"  Errors:  {error_count:,}")

    if errors and not args.verbose:
        print(f"\nFirst 10 errors:")
        for err in errors[:10]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
