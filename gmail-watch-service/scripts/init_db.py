#!/usr/bin/env python3
"""Initialize the gmail_watch database schema.

This script creates the gmail_watch schema and all tables in PostgreSQL.
It is idempotent - safe to run multiple times.

Usage:
    # Using environment variable
    DATABASE_URL=postgresql://user:pass@host:5432/db python init_db.py

    # Or with .env file in project root
    python init_db.py

    # Or specify URL directly
    python init_db.py postgresql://user:pass@host:5432/db
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg


async def init_schema(database_url: str) -> None:
    """Create the gmail_watch schema and tables.

    Args:
        database_url: PostgreSQL connection URL (asyncpg format).
    """
    # Convert SQLAlchemy URL format to asyncpg format if needed
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    schema_file = Path(__file__).parent / "init_schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    schema_sql = schema_file.read_text()

    print("Connecting to database...")
    conn = await asyncpg.connect(url)
    try:
        print("Executing schema creation...")
        await conn.execute(schema_sql)
        print("Schema gmail_watch created successfully")

        # Verify tables were created
        tables = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'gmail_watch'
            ORDER BY table_name
            """
        )
        print(f"Tables created: {[t['table_name'] for t in tables]}")

    finally:
        await conn.close()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    import os

    from dotenv import load_dotenv

    # Load .env from project root (two levels up from scripts/)
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    # Get database URL from command line arg, env var, or default
    if len(sys.argv) > 1:
        db_url = sys.argv[1]
    else:
        db_url = os.getenv(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
        )

    print(f"Using database URL: {db_url.split('@')[-1]}")  # Hide credentials

    try:
        asyncio.run(init_schema(db_url))
        return 0
    except Exception as e:
        print(f"Error initializing schema: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
