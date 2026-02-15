import aiosqlite
from datetime import datetime, timezone
from typing import Optional


class CheckpointDB:
    def __init__(self, db_path: str = "data/backfill.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                file_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                processed_at TEXT,
                queue_position INTEGER
            );

            CREATE TABLE IF NOT EXISTS runner_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state TEXT NOT NULL DEFAULT 'idle',
                started_at TEXT,
                paused_at TEXT
            );

            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vapid_keys (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                public_key TEXT NOT NULL,
                private_key TEXT NOT NULL
            );

            INSERT OR IGNORE INTO runner_state (id, state) VALUES (1, 'idle');
        """)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def load_documents(self, file_ids: list[str]):
        async with self._db.cursor() as cur:
            existing = set()
            await cur.execute("SELECT file_id FROM documents")
            rows = await cur.fetchall()
            for row in rows:
                existing.add(row["file_id"])

            max_pos_row = await cur.execute(
                "SELECT COALESCE(MAX(queue_position), -1) as mp FROM documents"
            )
            max_pos = (await max_pos_row.fetchone())["mp"]

            pos = max_pos + 1
            for fid in file_ids:
                if fid not in existing:
                    await cur.execute(
                        "INSERT INTO documents (file_id, status, queue_position) VALUES (?, 'pending', ?)",
                        (fid, pos),
                    )
                    pos += 1
        await self._db.commit()

    async def get_counts(self) -> dict:
        async with self._db.cursor() as cur:
            await cur.execute(
                """SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END), 0) as pending,
                    COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0) as success,
                    COALESCE(SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END), 0) as skipped,
                    COALESCE(SUM(CASE WHEN status='error' THEN 1 ELSE 0 END), 0) as error
                FROM documents"""
            )
            row = await cur.fetchone()
            return {
                "total": row["total"],
                "pending": row["pending"],
                "success": row["success"],
                "skipped": row["skipped"],
                "error": row["error"],
            }

    async def mark_document(
        self, file_id: str, status: str, error_message: str = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE documents SET status=?, error_message=?, processed_at=? WHERE file_id=?",
            (status, error_message, now, file_id),
        )
        await self._db.commit()

    async def get_next_pending(self) -> Optional[str]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT file_id FROM documents WHERE status='pending' ORDER BY queue_position LIMIT 1"
            )
            row = await cur.fetchone()
            return row["file_id"] if row else None

    async def get_errors(self, limit: int = 50) -> list[dict]:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT file_id, error_message, processed_at FROM documents WHERE status='error' ORDER BY processed_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def retry_errors(self) -> int:
        async with self._db.cursor() as cur:
            await cur.execute(
                "UPDATE documents SET status='pending', error_message=NULL, processed_at=NULL WHERE status='error'"
            )
            count = cur.rowcount
        await self._db.commit()
        return count

    async def get_runner_state(self) -> dict:
        async with self._db.cursor() as cur:
            await cur.execute(
                "SELECT state, started_at, paused_at FROM runner_state WHERE id=1"
            )
            row = await cur.fetchone()
            return dict(row)

    async def set_runner_state(self, state: str):
        now = datetime.now(timezone.utc).isoformat()
        if state == "running":
            await self._db.execute(
                "UPDATE runner_state SET state=?, started_at=COALESCE(started_at, ?), paused_at=NULL WHERE id=1",
                (state, now),
            )
        elif state == "paused":
            await self._db.execute(
                "UPDATE runner_state SET state=?, paused_at=? WHERE id=1",
                (state, now),
            )
        else:
            await self._db.execute(
                "UPDATE runner_state SET state=? WHERE id=1", (state,)
            )
        await self._db.commit()
