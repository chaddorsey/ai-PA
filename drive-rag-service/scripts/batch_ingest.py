#!/usr/bin/env python3
"""Batch document ingestion script.

Ingests all Google Docs in a folder with progress tracking,
failure handling, and optional entity extraction.

Usage:
    # Basic batch ingest
    python scripts/batch_ingest.py FOLDER_ID

    # With entity extraction
    python scripts/batch_ingest.py FOLDER_ID --extract-entities

    # Force re-index all documents
    python scripts/batch_ingest.py FOLDER_ID --force

    # Resume from a previous run
    python scripts/batch_ingest.py FOLDER_ID --resume progress.json

    # Dry run to see what would be ingested
    python scripts/batch_ingest.py FOLDER_ID --dry-run
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx


# API endpoint - defaults to local service
DEFAULT_API_BASE = "http://localhost:8095"

# Supported MIME types
SUPPORTED_MIME_TYPES = [
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/pdf",
]

# Status file format version
PROGRESS_FILE_VERSION = 1


def format_mime_type(mime_type: str) -> str:
    """Format MIME type for display."""
    type_map = {
        "application/vnd.google-apps.document": "Doc",
        "application/vnd.google-apps.spreadsheet": "Sheet",
        "application/vnd.google-apps.presentation": "Slides",
        "application/pdf": "PDF",
    }
    return type_map.get(mime_type, mime_type.split("/")[-1])


async def list_folder_files(
    client: httpx.AsyncClient,
    folder_id: str,
    api_base: str,
) -> list[dict]:
    """List all supported files in a folder.

    Uses a simple approach: calls the Drive API through a dedicated endpoint
    or falls back to direct Google API access.
    """
    # First, try to use the service's folder listing
    # If there's no dedicated list endpoint, we'll use direct Google API
    try:
        # Try a lightweight probe to check folder access
        response = await client.get(
            f"{api_base}/v1/status/{folder_id}",
            timeout=30.0,
        )
        # If this works, the folder might be a document (wrong ID)
        if response.status_code == 200:
            data = response.json()
            if data.get("indexed"):
                # This is a document, not a folder
                return [{"id": folder_id, "name": data.get("title", "Unknown"), "mimeType": "document"}]
    except Exception:
        pass

    # Use direct Google API through the service
    # Since the service doesn't expose folder listing directly with full results,
    # we'll need to use the ingest/folder endpoint with dry-run or similar
    # For now, use direct Google API

    # Import here to avoid dependency at module load
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from drive_rag.auth import get_google_client

    google = get_google_client()

    all_files = []
    for mime_type in SUPPORTED_MIME_TYPES:
        files = google.list_files_in_folder(folder_id, mime_type=mime_type)
        for f in files:
            f["mime_type_display"] = format_mime_type(f.get("mimeType", ""))
        all_files.extend(files)

    # Sort by name for consistent ordering
    all_files.sort(key=lambda f: f.get("name", "").lower())

    return all_files


async def ingest_single(
    client: httpx.AsyncClient,
    file_id: str,
    api_base: str,
    force: bool = False,
    extract_entities: bool = False,
    timeout: float = 300.0,
) -> dict:
    """Ingest a single document via the API."""
    params = {}
    if force:
        params["force"] = "true"
    if extract_entities:
        params["extract_entities"] = "true"

    try:
        response = await client.post(
            f"{api_base}/v1/ingest/{file_id}",
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        return {"status": "error", "drive_file_id": file_id, "reason": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "drive_file_id": file_id, "reason": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"status": "error", "drive_file_id": file_id, "reason": str(e)}


def load_progress(progress_file: Path) -> dict:
    """Load progress from a previous run."""
    if not progress_file.exists():
        return {}

    with open(progress_file) as f:
        data = json.load(f)

    # Validate version
    if data.get("version") != PROGRESS_FILE_VERSION:
        print(f"Warning: Progress file version mismatch, starting fresh")
        return {}

    return data


def save_progress(progress_file: Path, progress: dict):
    """Save progress to file."""
    progress["version"] = PROGRESS_FILE_VERSION
    progress["updated_at"] = datetime.utcnow().isoformat()

    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2, default=str)


def print_summary(results: list[dict], elapsed: float):
    """Print ingestion summary."""
    indexed = [r for r in results if r.get("status") == "indexed"]
    skipped = [r for r in results if r.get("status") == "skipped"]
    errors = [r for r in results if r.get("status") == "error"]

    print("\n" + "=" * 60)
    print("BATCH INGESTION COMPLETE")
    print("=" * 60)
    print(f"Total documents:  {len(results)}")
    print(f"  Indexed:        {len(indexed)}")
    print(f"  Skipped:        {len(skipped)}")
    print(f"  Errors:         {len(errors)}")
    print(f"Elapsed time:     {elapsed:.1f}s")

    if indexed:
        total_chunks = sum(
            r.get("chunks_added", 0) + r.get("chunks_updated", 0)
            for r in indexed
        )
        print(f"Total chunks:     {total_chunks}")

    if errors:
        print("\nFailed documents:")
        for r in errors:
            print(f"  - {r.get('drive_file_id', 'unknown')}: {r.get('reason', 'unknown error')[:60]}")


async def batch_ingest(
    folder_id: str,
    api_base: str = DEFAULT_API_BASE,
    force: bool = False,
    extract_entities: bool = False,
    dry_run: bool = False,
    resume_file: Optional[Path] = None,
    output_file: Optional[Path] = None,
    concurrency: int = 3,
):
    """Run batch ingestion for all documents in a folder.

    Args:
        folder_id: Google Drive folder ID
        api_base: Base URL for the drive-rag-service API
        force: Force re-indexing even if unchanged
        extract_entities: Extract entities to knowledge graph
        dry_run: List files without ingesting
        resume_file: Path to progress file for resumption
        output_file: Path to save results
        concurrency: Number of concurrent ingestion requests
    """
    start_time = datetime.utcnow()

    # Load progress from previous run
    progress = {}
    completed_ids = set()
    if resume_file and resume_file.exists():
        progress = load_progress(resume_file)
        completed_ids = set(progress.get("completed", []))
        print(f"Resuming from previous run: {len(completed_ids)} documents already processed")

    # Initialize progress tracking
    if not progress:
        progress = {
            "folder_id": folder_id,
            "started_at": start_time.isoformat(),
            "completed": [],
            "failed": [],
            "results": [],
        }

    # Default output file
    if output_file is None:
        output_file = Path(f"batch_ingest_{folder_id[:8]}_{start_time.strftime('%Y%m%d_%H%M%S')}.json")

    async with httpx.AsyncClient() as client:
        # Check API health
        try:
            health_response = await client.get(f"{api_base}/health", timeout=10.0)
            if health_response.status_code != 200:
                print(f"Error: API not healthy at {api_base}")
                sys.exit(1)
            print(f"Connected to drive-rag-service at {api_base}")
        except Exception as e:
            print(f"Error: Cannot connect to API at {api_base}: {e}")
            sys.exit(1)

        # List files in folder
        print(f"\nListing files in folder: {folder_id}")
        try:
            files = await list_folder_files(client, folder_id, api_base)
        except Exception as e:
            print(f"Error listing folder: {e}")
            sys.exit(1)

        print(f"Found {len(files)} documents")

        # Filter out already completed
        pending_files = [f for f in files if f["id"] not in completed_ids]
        print(f"Pending: {len(pending_files)} (already processed: {len(completed_ids)})")

        if dry_run:
            print("\n[DRY RUN] Would ingest:")
            for f in pending_files:
                mime_display = format_mime_type(f.get("mimeType", ""))
                print(f"  [{mime_display}] {f.get('name', 'Untitled')} ({f['id'][:12]}...)")
            return

        if not pending_files:
            print("No documents to process")
            return

        # Process documents
        print(f"\nIngesting {len(pending_files)} documents (concurrency: {concurrency})")
        if extract_entities:
            print("Entity extraction: ENABLED")
        if force:
            print("Force re-index: ENABLED")
        print()

        results = progress.get("results", [])
        semaphore = asyncio.Semaphore(concurrency)

        async def process_file(file: dict, index: int, total: int):
            async with semaphore:
                file_id = file["id"]
                file_name = file.get("name", "Untitled")
                mime_display = format_mime_type(file.get("mimeType", ""))

                print(f"[{index + 1}/{total}] [{mime_display}] {file_name[:50]}...", end=" ", flush=True)

                result = await ingest_single(
                    client=client,
                    file_id=file_id,
                    api_base=api_base,
                    force=force,
                    extract_entities=extract_entities,
                )

                # Add metadata to result
                result["file_name"] = file_name
                result["mime_type"] = file.get("mimeType", "")

                status = result.get("status", "unknown")
                if status == "indexed":
                    chunks = result.get("chunks_added", 0) + result.get("chunks_updated", 0)
                    print(f"✓ indexed ({chunks} chunks)")
                    progress["completed"].append(file_id)
                elif status == "skipped":
                    reason = result.get("reason", "")[:30]
                    print(f"○ skipped ({reason})")
                    progress["completed"].append(file_id)
                else:
                    reason = result.get("reason", "unknown")[:40]
                    print(f"✗ error: {reason}")
                    progress["failed"].append({"id": file_id, "reason": result.get("reason", "")})

                return result

        # Process all files with concurrency limit
        tasks = [
            process_file(file, i, len(pending_files))
            for i, file in enumerate(pending_files)
        ]

        # Process in chunks to allow progress saving
        chunk_size = 10
        for i in range(0, len(tasks), chunk_size):
            chunk_tasks = tasks[i:i + chunk_size]
            chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

            for result in chunk_results:
                if isinstance(result, Exception):
                    results.append({"status": "error", "reason": str(result)})
                else:
                    results.append(result)

            progress["results"] = results
            save_progress(output_file, progress)

        # Final summary
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        print_summary(results, elapsed)

        # Save final results
        progress["completed_at"] = datetime.utcnow().isoformat()
        progress["elapsed_seconds"] = elapsed
        save_progress(output_file, progress)
        print(f"\nResults saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch ingest Google Docs from a Drive folder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "folder_id",
        help="Google Drive folder ID to ingest",
    )

    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"Base URL for drive-rag-service API (default: {DEFAULT_API_BASE})",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing even if documents haven't changed",
    )

    parser.add_argument(
        "--extract-entities",
        action="store_true",
        help="Extract entities to knowledge graph via Graphiti",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files without actually ingesting",
    )

    parser.add_argument(
        "--resume",
        type=Path,
        metavar="FILE",
        help="Resume from a previous progress file",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        metavar="FILE",
        help="Output file for results (default: batch_ingest_<id>_<timestamp>.json)",
    )

    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=3,
        help="Number of concurrent ingestion requests (default: 3)",
    )

    args = parser.parse_args()

    # Run batch ingestion
    asyncio.run(batch_ingest(
        folder_id=args.folder_id,
        api_base=args.api_base,
        force=args.force,
        extract_entities=args.extract_entities,
        dry_run=args.dry_run,
        resume_file=args.resume,
        output_file=args.output,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()
