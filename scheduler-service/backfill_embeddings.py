#!/usr/bin/env python3
"""Backfill embeddings for existing jobs that don't have them."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from scheduler_service.models.job import Job
from scheduler_service.services.embeddings import embed_texts
from scheduler_service.settings import get_settings
from scheduler_service.logging_config import setup_logging

setup_logging()
settings = get_settings()


async def backfill_embeddings():
    """Backfill embeddings for jobs that don't have them."""
    engine = create_async_engine(str(settings.database_url), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Find all jobs without embeddings
        result = await session.execute(
            select(Job).where(Job.vector_embedding.is_(None))
        )
        jobs = result.scalars().all()
        
        if not jobs:
            print("No jobs need embedding backfill.")
            return
        
        print(f"Found {len(jobs)} jobs without embeddings. Backfilling...")
        
        updated = 0
        for job in jobs:
            embedding = embed_texts([job.title, job.description or ""])
            if embedding:
                job.vector_embedding = embedding
                updated += 1
                print(f"  ✓ Updated: {job.job_id} - {job.title[:50]}")
            else:
                print(f"  ✗ Failed: {job.job_id} - {job.title[:50]} (embedding model unavailable)")
        
        await session.commit()
        print(f"\nSuccessfully backfilled embeddings for {updated}/{len(jobs)} jobs.")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill_embeddings())

