#!/usr/bin/env python3
"""Script to cancel all past-due one-off jobs."""

import asyncio
import sys
from datetime import datetime, timezone
from typing import List

import httpx

SCHEDULER_BASE_URL = "http://localhost:8087"
BATCH_SIZE = 100  # Cancel in batches to avoid overwhelming the API


async def get_past_due_one_off_jobs() -> List[str]:
    """Fetch all past-due one-off jobs."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(f"{SCHEDULER_BASE_URL}/v1/jobs?status_filter=active")
        response.raise_for_status()
        jobs = response.json()
        
        now = datetime.now(timezone.utc)
        past_due_one_off = []
        
        for job in jobs:
            if job.get("schedule_type") != "one_off":
                continue
            
            next_run_at = job.get("next_run_at")
            if not next_run_at:
                continue
            
            try:
                run_time = datetime.fromisoformat(next_run_at.replace("Z", "+00:00"))
                if run_time < now:
                    past_due_one_off.append(job["job_id"])
            except (ValueError, TypeError):
                # Skip jobs with invalid dates
                continue
        
        return past_due_one_off


async def cancel_jobs_batch(job_ids: List[str]) -> dict:
    """Cancel a batch of jobs."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{SCHEDULER_BASE_URL}/v1/jobs/batch/cancel",
            json=job_ids
        )
        response.raise_for_status()
        return response.json()


async def main():
    """Main entry point."""
    print("Fetching past-due one-off jobs...")
    job_ids = await get_past_due_one_off_jobs()
    
    if not job_ids:
        print("No past-due one-off jobs found.")
        return
    
    print(f"Found {len(job_ids)} past-due one-off jobs to cancel.")
    print(f"Cancelling in batches of {BATCH_SIZE}...")
    
    total_cancelled = 0
    total_failed = 0
    
    for i in range(0, len(job_ids), BATCH_SIZE):
        batch = job_ids[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(job_ids) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} jobs)...")
        
        try:
            result = await cancel_jobs_batch(batch)
            batch_cancelled = result.get("cancelled_count", 0)
            batch_failed = result.get("failed_count", 0)
            
            total_cancelled += batch_cancelled
            total_failed += batch_failed
            
            print(f"  ✓ Cancelled: {batch_cancelled}, Failed: {batch_failed}")
            
            if batch_failed > 0:
                failed_jobs = result.get("failed", [])
                for failed_job in failed_jobs[:5]:  # Show first 5 failures
                    print(f"    - {failed_job['job_id']}: {failed_job['error']}")
                if len(failed_jobs) > 5:
                    print(f"    ... and {len(failed_jobs) - 5} more failures")
        
        except Exception as exc:
            print(f"  ✗ Error processing batch: {exc}")
            total_failed += len(batch)
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total jobs processed: {len(job_ids)}")
    print(f"  Successfully cancelled: {total_cancelled}")
    print(f"  Failed: {total_failed}")
    print(f"{'='*60}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n\nError: {exc}")
        sys.exit(1)

