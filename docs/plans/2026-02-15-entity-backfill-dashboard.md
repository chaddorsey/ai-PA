# Entity Backfill Runner + Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone Docker service that runs the full-corpus entity extraction backfill with checkpoint-based resume and a PWA dashboard with Web Push notifications.

**Architecture:** Single FastAPI container with asyncio background task for the backfill loop, SQLite for checkpoint state, SSE for live dashboard updates, and Web Push for alerts. Serves a vanilla HTML/CSS/JS PWA.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, aiosqlite, httpx, pywebpush, sse-starlette, cryptography

**Design doc:** `docs/plans/2026-02-15-entity-backfill-dashboard-design.md`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `entity-backfill-service/requirements.txt`
- Create: `entity-backfill-service/Dockerfile`
- Create: `entity-backfill-service/app/__init__.py`
- Create: `entity-backfill-service/tests/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p entity-backfill-service/app/static
mkdir -p entity-backfill-service/tests
mkdir -p entity-backfill-service/data
touch entity-backfill-service/app/__init__.py
touch entity-backfill-service/tests/__init__.py
```

**Step 2: Write requirements.txt**

Create `entity-backfill-service/requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
aiosqlite==0.20.0
httpx==0.28.1
pywebpush==2.0.1
cryptography==44.0.0
sse-starlette==2.2.1
py-vapid==1.9.2
pytest==8.3.4
pytest-asyncio==0.25.0
pytest-httpx==0.35.0
```

**Step 3: Write Dockerfile**

Create `entity-backfill-service/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 4: Commit scaffolding**

```bash
git add entity-backfill-service/
git commit -m "feat: scaffold entity-backfill-service"
```

---

### Task 2: Checkpoint Module (TDD)

**Files:**
- Create: `entity-backfill-service/app/checkpoint.py`
- Test: `entity-backfill-service/tests/test_checkpoint.py`

**Step 1: Write the failing tests**

Create `entity-backfill-service/tests/test_checkpoint.py`:

```python
import pytest
import pytest_asyncio
from pathlib import Path
from app.checkpoint import CheckpointDB


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    checkpoint = CheckpointDB(str(db_path))
    await checkpoint.initialize()
    yield checkpoint
    await checkpoint.close()


@pytest.mark.asyncio
async def test_initialize_creates_tables(db):
    state = await db.get_runner_state()
    assert state["state"] == "idle"
    assert state["started_at"] is None


@pytest.mark.asyncio
async def test_load_documents(db):
    file_ids = ["file_a", "file_b", "file_c"]
    await db.load_documents(file_ids)
    counts = await db.get_counts()
    assert counts["total"] == 3
    assert counts["pending"] == 3
    assert counts["success"] == 0
    assert counts["error"] == 0
    assert counts["skipped"] == 0


@pytest.mark.asyncio
async def test_load_documents_idempotent(db):
    """Loading same IDs twice should not duplicate."""
    await db.load_documents(["file_a", "file_b"])
    await db.load_documents(["file_b", "file_c"])
    counts = await db.get_counts()
    assert counts["total"] == 3


@pytest.mark.asyncio
async def test_mark_document_success(db):
    await db.load_documents(["file_a"])
    await db.mark_document("file_a", "success")
    counts = await db.get_counts()
    assert counts["success"] == 1
    assert counts["pending"] == 0


@pytest.mark.asyncio
async def test_mark_document_error(db):
    await db.load_documents(["file_a"])
    await db.mark_document("file_a", "error", error_message="timeout")
    counts = await db.get_counts()
    assert counts["error"] == 1
    errors = await db.get_errors()
    assert len(errors) == 1
    assert errors[0]["file_id"] == "file_a"
    assert errors[0]["error_message"] == "timeout"


@pytest.mark.asyncio
async def test_get_next_pending(db):
    await db.load_documents(["file_a", "file_b", "file_c"])
    await db.mark_document("file_a", "success")
    next_doc = await db.get_next_pending()
    assert next_doc == "file_b"


@pytest.mark.asyncio
async def test_get_next_pending_none_left(db):
    await db.load_documents(["file_a"])
    await db.mark_document("file_a", "success")
    next_doc = await db.get_next_pending()
    assert next_doc is None


@pytest.mark.asyncio
async def test_set_runner_state(db):
    await db.set_runner_state("running")
    state = await db.get_runner_state()
    assert state["state"] == "running"
    assert state["started_at"] is not None


@pytest.mark.asyncio
async def test_retry_errors(db):
    await db.load_documents(["file_a", "file_b"])
    await db.mark_document("file_a", "error", error_message="timeout")
    await db.mark_document("file_b", "error", error_message="500")
    count = await db.retry_errors()
    assert count == 2
    counts = await db.get_counts()
    assert counts["pending"] == 2
    assert counts["error"] == 0


@pytest.mark.asyncio
async def test_get_errors_limit(db):
    await db.load_documents([f"file_{i}" for i in range(5)])
    for i in range(5):
        await db.mark_document(f"file_{i}", "error", error_message=f"err {i}")
    errors = await db.get_errors(limit=3)
    assert len(errors) == 3
```

**Step 2: Run tests to verify they fail**

Run: `cd entity-backfill-service && python -m pytest tests/test_checkpoint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.checkpoint'`

**Step 3: Implement checkpoint.py**

Create `entity-backfill-service/app/checkpoint.py`:

```python
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
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) as skipped,
                    SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error
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
            await cur.execute("SELECT state, started_at, paused_at FROM runner_state WHERE id=1")
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
```

**Step 4: Run tests to verify they pass**

Run: `cd entity-backfill-service && python -m pytest tests/test_checkpoint.py -v`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
git add entity-backfill-service/app/checkpoint.py entity-backfill-service/tests/test_checkpoint.py
git commit -m "feat: checkpoint module with SQLite state management"
```

---

### Task 3: Notifications Module (TDD)

**Files:**
- Create: `entity-backfill-service/app/notifications.py`
- Test: `entity-backfill-service/tests/test_notifications.py`

**Step 1: Write the failing tests**

Create `entity-backfill-service/tests/test_notifications.py`:

```python
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    checkpoint = CheckpointDB(str(db_path))
    await checkpoint.initialize()
    yield checkpoint
    await checkpoint.close()


@pytest_asyncio.fixture
async def manager(db):
    mgr = NotificationManager(db)
    await mgr.initialize()
    return mgr


@pytest.mark.asyncio
async def test_vapid_keys_generated_on_init(manager):
    keys = await manager.get_vapid_keys()
    assert "public_key" in keys
    assert "private_key" in keys
    assert len(keys["public_key"]) > 20


@pytest.mark.asyncio
async def test_vapid_keys_persist(db):
    mgr1 = NotificationManager(db)
    await mgr1.initialize()
    keys1 = await mgr1.get_vapid_keys()

    mgr2 = NotificationManager(db)
    await mgr2.initialize()
    keys2 = await mgr2.get_vapid_keys()

    assert keys1["public_key"] == keys2["public_key"]


@pytest.mark.asyncio
async def test_add_subscription(manager, db):
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "key", "auth": "auth"}}
    await manager.add_subscription(sub)
    subs = await manager.get_subscriptions()
    assert len(subs) == 1
    assert json.loads(subs[0]["subscription_json"])["endpoint"] == sub["endpoint"]


@pytest.mark.asyncio
async def test_send_notification_no_subscribers(manager):
    """Should not raise when no subscribers."""
    await manager.send_notification("Test", "Body")


@pytest.mark.asyncio
async def test_send_notification_calls_webpush(manager):
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "key", "auth": "auth"}}
    await manager.add_subscription(sub)

    with patch("app.notifications.webpush") as mock_wp:
        await manager.send_notification("Title", "Body text")
        assert mock_wp.called
        call_kwargs = mock_wp.call_args
        payload = json.loads(call_kwargs[1]["data"])
        assert payload["title"] == "Title"
        assert payload["body"] == "Body text"
```

**Step 2: Run tests to verify they fail**

Run: `cd entity-backfill-service && python -m pytest tests/test_notifications.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications'`

**Step 3: Implement notifications.py**

Create `entity-backfill-service/app/notifications.py`:

```python
import json
import logging
from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from datetime import datetime, timezone
from app.checkpoint import CheckpointDB

logger = logging.getLogger(__name__)

VAPID_CLAIMS_EMAIL = "mailto:admin@localhost"


class NotificationManager:
    def __init__(self, db: CheckpointDB):
        self.db = db
        self._vapid_keys: dict = {}

    async def initialize(self):
        existing = await self._load_vapid_keys()
        if existing:
            self._vapid_keys = existing
        else:
            self._vapid_keys = self._generate_vapid_keys()
            await self._save_vapid_keys(self._vapid_keys)

    def _generate_vapid_keys(self) -> dict:
        vapid = Vapid()
        vapid.generate_keys()
        return {
            "public_key": vapid.public_key_urlsafe_base64,
            "private_key": vapid.private_pem.decode("utf-8"),
        }

    async def _load_vapid_keys(self) -> dict | None:
        async with self.db._db.cursor() as cur:
            await cur.execute("SELECT public_key, private_key FROM vapid_keys WHERE id=1")
            row = await cur.fetchone()
            if row:
                return {"public_key": row["public_key"], "private_key": row["private_key"]}
            return None

    async def _save_vapid_keys(self, keys: dict):
        await self.db._db.execute(
            "INSERT OR REPLACE INTO vapid_keys (id, public_key, private_key) VALUES (1, ?, ?)",
            (keys["public_key"], keys["private_key"]),
        )
        await self.db._db.commit()

    async def get_vapid_keys(self) -> dict:
        return self._vapid_keys

    async def add_subscription(self, subscription: dict):
        now = datetime.now(timezone.utc).isoformat()
        await self.db._db.execute(
            "INSERT INTO push_subscriptions (subscription_json, created_at) VALUES (?, ?)",
            (json.dumps(subscription), now),
        )
        await self.db._db.commit()

    async def get_subscriptions(self) -> list[dict]:
        async with self.db._db.cursor() as cur:
            await cur.execute("SELECT id, subscription_json, created_at FROM push_subscriptions")
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def send_notification(self, title: str, body: str, url: str = "/"):
        subs = await self.get_subscriptions()
        if not subs:
            logger.debug("No push subscribers, skipping notification")
            return

        payload = json.dumps({"title": title, "body": body, "url": url})
        failed_ids = []

        for sub in subs:
            sub_info = json.loads(sub["subscription_json"])
            try:
                webpush(
                    subscription_info=sub_info,
                    data=payload,
                    vapid_private_key=self._vapid_keys["private_key"],
                    vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
                )
            except WebPushException as e:
                logger.warning(f"Push failed for subscription {sub['id']}: {e}")
                if "410" in str(e) or "404" in str(e):
                    failed_ids.append(sub["id"])
            except Exception as e:
                logger.error(f"Unexpected push error: {e}")

        for sid in failed_ids:
            await self.db._db.execute("DELETE FROM push_subscriptions WHERE id=?", (sid,))
        if failed_ids:
            await self.db._db.commit()
```

**Step 4: Run tests to verify they pass**

Run: `cd entity-backfill-service && python -m pytest tests/test_notifications.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add entity-backfill-service/app/notifications.py entity-backfill-service/tests/test_notifications.py
git commit -m "feat: web push notification manager with VAPID keys"
```

---

### Task 4: Backfill Runner (TDD)

**Files:**
- Create: `entity-backfill-service/app/runner.py`
- Test: `entity-backfill-service/tests/test_runner.py`

**Step 1: Write the failing tests**

Create `entity-backfill-service/tests/test_runner.py`:

```python
import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager
from app.runner import BackfillRunner


@pytest_asyncio.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    checkpoint = CheckpointDB(str(db_path))
    await checkpoint.initialize()
    yield checkpoint
    await checkpoint.close()


@pytest_asyncio.fixture
async def notifications(db):
    mgr = NotificationManager(db)
    await mgr.initialize()
    mgr.send_notification = AsyncMock()
    return mgr


@pytest_asyncio.fixture
async def runner(db, notifications):
    r = BackfillRunner(
        db=db,
        notifications=notifications,
        extract_url="http://test:8000/v1/entities/extract",
        supabase_dsn="postgresql://test@localhost/test",
    )
    return r


@pytest.mark.asyncio
async def test_runner_initial_state(runner):
    assert runner.state == "idle"


@pytest.mark.asyncio
async def test_process_single_document_success(runner, db):
    await db.load_documents(["file_a"])
    await db.set_runner_state("running")

    mock_response = httpx.Response(
        200, json={"status": "ok", "reference_id": "uuid-123"}
    )

    with patch.object(runner._client, "post", return_value=mock_response):
        result = await runner._process_one("file_a")

    assert result == "success"
    counts = await db.get_counts()
    assert counts["success"] == 1


@pytest.mark.asyncio
async def test_process_single_document_skipped(runner, db):
    await db.load_documents(["file_a"])

    mock_response = httpx.Response(200, json={"status": "skipped"})

    with patch.object(runner._client, "post", return_value=mock_response):
        result = await runner._process_one("file_a")

    assert result == "skipped"
    counts = await db.get_counts()
    assert counts["skipped"] == 1


@pytest.mark.asyncio
async def test_process_single_document_error(runner, db):
    await db.load_documents(["file_a"])

    with patch.object(
        runner._client, "post", side_effect=httpx.TimeoutException("timeout")
    ):
        result = await runner._process_one("file_a")

    assert result == "error"
    counts = await db.get_counts()
    assert counts["error"] == 1


@pytest.mark.asyncio
async def test_pause_stops_loop(runner, db):
    await db.load_documents(["file_a", "file_b", "file_c"])

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            runner._pause_requested = True
        return httpx.Response(200, json={"status": "ok"})

    with patch.object(runner._client, "post", side_effect=mock_post):
        await runner._run_loop()

    assert call_count == 2
    state = await db.get_runner_state()
    assert state["state"] == "paused"


@pytest.mark.asyncio
async def test_rate_tracking(runner):
    runner._record_timing(1.0)
    runner._record_timing(2.0)
    runner._record_timing(3.0)
    rate = runner.get_rate()
    assert rate == pytest.approx(0.5, abs=0.01)  # 1 / avg(1,2,3)
```

**Step 2: Run tests to verify they fail**

Run: `cd entity-backfill-service && python -m pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.runner'`

**Step 3: Implement runner.py**

Create `entity-backfill-service/app/runner.py`:

```python
import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

import httpx

from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager

logger = logging.getLogger(__name__)

COST_PER_DOC = 116.0 / 44353  # ~$0.00262 per doc from pilot estimate
ERROR_RATE_WINDOW = 50
ERROR_RATE_THRESHOLD = 0.10
SERVICE_RETRY_INTERVAL = 30
PAUSE_REMINDER_INTERVAL = 300  # 5 minutes
NEO4J_CACHE_TTL = 60


class BackfillRunner:
    def __init__(
        self,
        db: CheckpointDB,
        notifications: NotificationManager,
        extract_url: str = "http://drive-rag-service:8000/v1/entities/extract",
        supabase_dsn: str = "",
    ):
        self.db = db
        self.notifications = notifications
        self.extract_url = extract_url
        self.supabase_dsn = supabase_dsn

        self.state = "idle"
        self._pause_requested = False
        self._task: Optional[asyncio.Task] = None
        self._client = httpx.AsyncClient(timeout=120.0)

        # Rate tracking
        self._timings: deque[float] = deque(maxlen=100)
        self._started_at: Optional[float] = None

        # Error rate tracking
        self._recent_results: deque[str] = deque(maxlen=ERROR_RATE_WINDOW)

        # SSE event callback
        self.on_event: Optional[Callable[[dict], Awaitable[None]]] = None

        # Neo4j stats cache
        self._neo4j_stats: dict = {}
        self._neo4j_stats_at: float = 0

    async def load_queue_from_supabase(self) -> int:
        """Fetch document IDs from Supabase and load into checkpoint DB."""
        import subprocess
        result = subprocess.run(
            [
                "docker", "exec", "supabase-db", "psql",
                "-U", "postgres", "-d", "postgres", "-t", "-A", "-c",
                "SELECT drive_file_id FROM rag.document_state ORDER BY modified_time DESC;",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to query Supabase: {result.stderr}")

        file_ids = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        await self.db.load_documents(file_ids)
        return len(file_ids)

    async def start(self) -> dict:
        if self.state == "running":
            return {"status": "already_running"}

        counts = await self.db.get_counts()
        if counts["total"] == 0:
            count = await self.load_queue_from_supabase()
            logger.info(f"Loaded {count} documents from Supabase")

        self.state = "running"
        self._pause_requested = False
        self._started_at = self._started_at or time.time()
        await self.db.set_runner_state("running")

        self._task = asyncio.create_task(self._run_loop())
        return {"status": "started"}

    async def pause(self) -> dict:
        if self.state != "running":
            return {"status": "not_running"}
        self._pause_requested = True
        return {"status": "pause_requested"}

    async def resume(self) -> dict:
        return await self.start()

    async def _run_loop(self):
        try:
            while not self._pause_requested:
                file_id = await self.db.get_next_pending()
                if file_id is None:
                    self.state = "completed"
                    await self.db.set_runner_state("completed")
                    counts = await self.db.get_counts()
                    await self.notifications.send_notification(
                        "Backfill Complete",
                        f"{counts['total']} docs processed. {counts['success']} ok, {counts['skipped']} skip, {counts['error']} err.",
                    )
                    await self._emit_event("completed", counts)
                    return

                start = time.time()
                result = await self._process_one(file_id)
                elapsed = time.time() - start

                self._record_timing(elapsed)
                self._recent_results.append(result)
                self._check_error_rate()

                counts = await self.db.get_counts()
                await self._emit_event("progress", {
                    **counts,
                    "last_file_id": file_id,
                    "last_result": result,
                    "rate": self.get_rate(),
                    "elapsed": time.time() - self._started_at if self._started_at else 0,
                })

            # Pause requested
            self.state = "paused"
            await self.db.set_runner_state("paused")
            await self._emit_event("paused", await self.db.get_counts())

        except Exception as e:
            logger.error(f"Runner loop error: {e}", exc_info=True)
            self.state = "paused"
            await self.db.set_runner_state("paused")
            await self.notifications.send_notification(
                "Backfill Error", f"Runner crashed: {str(e)[:100]}"
            )

    async def _process_one(self, file_id: str) -> str:
        try:
            response = await self._client.post(f"{self.extract_url}/{file_id}")
            data = response.json()
            status = data.get("status", "error")
            if status == "ok":
                await self.db.mark_document(file_id, "success")
                return "success"
            elif status == "skipped":
                await self.db.mark_document(file_id, "skipped")
                return "skipped"
            else:
                error_msg = data.get("error", data.get("detail", str(data)))
                await self.db.mark_document(file_id, "error", error_message=error_msg)
                return "error"
        except httpx.ConnectError:
            await self.db.mark_document(file_id, "error", error_message="service unreachable")
            await self._handle_service_down()
            return "error"
        except httpx.TimeoutException:
            await self.db.mark_document(file_id, "error", error_message="timeout (120s)")
            return "error"
        except Exception as e:
            await self.db.mark_document(file_id, "error", error_message=str(e)[:200])
            return "error"

    async def _handle_service_down(self):
        self._pause_requested = True
        await self.notifications.send_notification(
            "Backfill Paused",
            "drive-rag-service unreachable. Pausing until service returns.",
        )
        logger.warning("drive-rag-service unreachable, pausing runner")

    def _check_error_rate(self):
        if len(self._recent_results) < ERROR_RATE_WINDOW:
            return
        error_count = sum(1 for r in self._recent_results if r == "error")
        rate = error_count / len(self._recent_results)
        if rate > ERROR_RATE_THRESHOLD:
            asyncio.create_task(
                self.notifications.send_notification(
                    "High Error Rate",
                    f"{rate:.0%} errors in last {ERROR_RATE_WINDOW} docs.",
                )
            )

    def _record_timing(self, elapsed: float):
        self._timings.append(elapsed)

    def get_rate(self) -> float:
        if not self._timings:
            return 0.0
        avg = sum(self._timings) / len(self._timings)
        return 1.0 / avg if avg > 0 else 0.0

    def get_eta_seconds(self, pending: int) -> float:
        rate = self.get_rate()
        if rate <= 0:
            return 0.0
        return pending / rate

    def get_cost_estimate(self, processed: int) -> float:
        return processed * COST_PER_DOC

    async def get_neo4j_stats(self) -> dict:
        now = time.time()
        if now - self._neo4j_stats_at < NEO4J_CACHE_TTL and self._neo4j_stats:
            return self._neo4j_stats

        try:
            import subprocess
            result = subprocess.run(
                [
                    "docker", "exec", "graphiti-neo4j", "cypher-shell",
                    "-u", "neo4j", "-p", "demodemo",
                    "MATCH (n) RETURN labels(n)[0] as type, count(n) as cnt ORDER BY cnt DESC;",
                ],
                capture_output=True, text=True, timeout=10,
            )
            stats = {}
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n")[1:]:  # skip header
                    parts = line.split(",")
                    if len(parts) == 2:
                        label = parts[0].strip().strip('"')
                        count = int(parts[1].strip())
                        stats[label] = count

            rel_result = subprocess.run(
                [
                    "docker", "exec", "graphiti-neo4j", "cypher-shell",
                    "-u", "neo4j", "-p", "demodemo",
                    "MATCH ()-[r]->() RETURN count(r) as cnt;",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if rel_result.returncode == 0:
                for line in rel_result.stdout.strip().split("\n")[1:]:
                    stats["relationships"] = int(line.strip())

            self._neo4j_stats = stats
            self._neo4j_stats_at = now
        except Exception as e:
            logger.warning(f"Failed to fetch Neo4j stats: {e}")

        return self._neo4j_stats

    async def _emit_event(self, event_type: str, data: dict):
        if self.on_event:
            await self.on_event({"type": event_type, **data})

    async def get_status(self) -> dict:
        counts = await self.db.get_counts()
        processed = counts["success"] + counts["skipped"] + counts["error"]
        neo4j_stats = await self.get_neo4j_stats()
        return {
            "state": self.state,
            **counts,
            "processed": processed,
            "rate": self.get_rate(),
            "eta_seconds": self.get_eta_seconds(counts["pending"]),
            "elapsed": time.time() - self._started_at if self._started_at else 0,
            "cost_estimate": self.get_cost_estimate(processed),
            "neo4j": neo4j_stats,
        }

    async def shutdown(self):
        await self._client.aclose()
```

**Step 4: Run tests to verify they pass**

Run: `cd entity-backfill-service && python -m pytest tests/test_runner.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add entity-backfill-service/app/runner.py entity-backfill-service/tests/test_runner.py
git commit -m "feat: backfill runner with pause/resume and error handling"
```

---

### Task 5: FastAPI Main App

**Files:**
- Create: `entity-backfill-service/app/main.py`
- Test: `entity-backfill-service/tests/test_api.py`

**Step 1: Write the failing tests**

Create `entity-backfill-service/tests/test_api.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

# Patch subprocess before importing app to prevent real docker calls
with patch("app.runner.subprocess"):
    from app.main import create_app


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(db_path=str(tmp_path / "test.db"))
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_status_initial(client):
    r = await client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "idle"
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_errors_empty(client):
    r = await client.get("/api/errors")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_push_vapid_key(client):
    r = await client.get("/api/push/vapid-key")
    assert r.status_code == 200
    assert "public_key" in r.json()


@pytest.mark.asyncio
async def test_push_subscribe(client):
    sub = {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "k", "auth": "a"}}
    r = await client.post("/api/push/subscribe", json=sub)
    assert r.status_code == 200
    assert r.json()["status"] == "subscribed"


@pytest.mark.asyncio
async def test_pause_when_not_running(client):
    r = await client.post("/api/pause")
    assert r.status_code == 200
    assert r.json()["status"] == "not_running"
```

**Step 2: Run tests to verify they fail**

Run: `cd entity-backfill-service && python -m pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

**Step 3: Implement main.py**

Create `entity-backfill-service/app/main.py`:

```python
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app.checkpoint import CheckpointDB
from app.notifications import NotificationManager
from app.runner import BackfillRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Global references set during lifespan
_db: Optional[CheckpointDB] = None
_runner: Optional[BackfillRunner] = None
_notifications: Optional[NotificationManager] = None
_sse_queues: list[asyncio.Queue] = []


def create_app(db_path: str = "data/backfill.db") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _db, _runner, _notifications
        _db = CheckpointDB(db_path)
        await _db.initialize()

        _notifications = NotificationManager(_db)
        await _notifications.initialize()

        _runner = BackfillRunner(db=_db, notifications=_notifications)
        _runner.on_event = _broadcast_sse

        # Auto-resume if was running before crash
        state = await _db.get_runner_state()
        if state["state"] == "running":
            logger.info("Auto-resuming backfill from checkpoint")
            await _runner.start()

        yield

        await _runner.shutdown()
        await _db.close()

    app = FastAPI(title="Entity Backfill Service", lifespan=lifespan)

    # --- Health ---
    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "entity-backfill-service"}

    # --- Status ---
    @app.get("/api/status")
    async def status():
        return await _runner.get_status()

    # --- Controls ---
    @app.post("/api/start")
    async def start():
        return await _runner.start()

    @app.post("/api/pause")
    async def pause():
        return await _runner.pause()

    @app.post("/api/resume")
    async def resume():
        return await _runner.resume()

    @app.post("/api/retry-errors")
    async def retry_errors():
        count = await _db.retry_errors()
        return {"status": "ok", "retried": count}

    # --- Errors ---
    @app.get("/api/errors")
    async def errors(limit: int = 50):
        return await _db.get_errors(limit=limit)

    # --- SSE ---
    @app.get("/api/events")
    async def events(request: Request):
        queue: asyncio.Queue = asyncio.Queue()
        _sse_queues.append(queue)

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield {"event": "progress", "data": json.dumps(data)}
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": "{}"}
            finally:
                _sse_queues.remove(queue)

        return EventSourceResponse(event_generator())

    # --- Push ---
    @app.get("/api/push/vapid-key")
    async def vapid_key():
        keys = await _notifications.get_vapid_keys()
        return {"public_key": keys["public_key"]}

    @app.post("/api/push/subscribe")
    async def push_subscribe(request: Request):
        sub = await request.json()
        await _notifications.add_subscription(sub)
        return {"status": "subscribed"}

    @app.get("/api/push/test")
    async def push_test():
        await _notifications.send_notification(
            "Test Notification", "Push notifications are working!"
        )
        return {"status": "sent"}

    # --- Static PWA ---
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        @app.get("/", response_class=HTMLResponse)
        async def index():
            return (static_dir / "index.html").read_text()

        # Service worker must be served from root
        @app.get("/sw.js")
        async def service_worker():
            from fastapi.responses import Response
            return Response(
                content=(static_dir / "sw.js").read_text(),
                media_type="application/javascript",
            )

        @app.get("/manifest.json")
        async def manifest():
            from fastapi.responses import Response
            return Response(
                content=(static_dir / "manifest.json").read_text(),
                media_type="application/json",
            )

        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


async def _broadcast_sse(data: dict):
    for queue in _sse_queues:
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            pass


app = create_app()
```

**Step 4: Run tests to verify they pass**

Run: `cd entity-backfill-service && python -m pytest tests/test_api.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add entity-backfill-service/app/main.py entity-backfill-service/tests/test_api.py
git commit -m "feat: FastAPI app with backfill control API and SSE"
```

---

### Task 6: PWA Static Files

**Files:**
- Create: `entity-backfill-service/app/static/index.html`
- Create: `entity-backfill-service/app/static/style.css`
- Create: `entity-backfill-service/app/static/app.js`
- Create: `entity-backfill-service/app/static/manifest.json`
- Create: `entity-backfill-service/app/static/sw.js`

**Step 1: Create manifest.json**

Create `entity-backfill-service/app/static/manifest.json`:

```json
{
  "name": "Entity Backfill Monitor",
  "short_name": "Backfill",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#0f172a",
  "icons": []
}
```

**Step 2: Create sw.js**

Create `entity-backfill-service/app/static/sw.js`:

```javascript
self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'Backfill Update', {
      body: data.body || '',
      icon: '/static/icon.png',
      badge: '/static/icon.png',
      data: { url: data.url || '/' }
    })
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const url = event.notification.data.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(function(clientList) {
      for (var i = 0; i < clientList.length; i++) {
        if (clientList[i].url.includes(url) && 'focus' in clientList[i]) {
          return clientList[i].focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});
```

**Step 3: Create style.css**

Create `entity-backfill-service/app/static/style.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #0f172a; --surface: #1e293b; --border: #334155;
  --text: #f1f5f9; --text-dim: #94a3b8;
  --green: #22c55e; --yellow: #eab308; --red: #ef4444; --blue: #3b82f6;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
}
body { background: var(--bg); color: var(--text); min-height: 100dvh; padding: 1rem; max-width: 480px; margin: 0 auto; }
h1 { font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1rem; margin-bottom: 0.75rem; }
.card h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-dim); margin-bottom: 0.5rem; }

.status-badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }
.status-idle { background: var(--border); }
.status-running { background: #166534; color: var(--green); }
.status-paused { background: #713f12; color: var(--yellow); }
.status-completed { background: #1e3a5f; color: var(--blue); }

.progress-bar { width: 100%; height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; margin: 0.75rem 0; }
.progress-fill { height: 100%; background: var(--green); border-radius: 4px; transition: width 0.3s ease; }

.stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
.stat { }
.stat-value { font-size: 1.25rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.stat-label { font-size: 0.75rem; color: var(--text-dim); }

.counts { display: flex; gap: 0.75rem; font-size: 0.875rem; font-variant-numeric: tabular-nums; }
.counts .ok { color: var(--green); }
.counts .skip { color: var(--text-dim); }
.counts .err { color: var(--red); }

.controls { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.btn { padding: 0.5rem 1rem; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text); font-size: 0.875rem; cursor: pointer; transition: background 0.15s; }
.btn:hover { background: var(--border); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--blue); border-color: var(--blue); }
.btn-primary:hover { background: #2563eb; }

.error-list { max-height: 200px; overflow-y: auto; font-size: 0.8125rem; }
.error-item { padding: 0.5rem 0; border-bottom: 1px solid var(--border); }
.error-item:last-child { border-bottom: none; }
.error-id { font-family: monospace; color: var(--text-dim); }
.error-msg { color: var(--red); margin-top: 0.125rem; }

.neo4j-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.25rem; font-size: 0.875rem; }
.neo4j-stats dt { color: var(--text-dim); }
.neo4j-stats dd { font-weight: 600; font-variant-numeric: tabular-nums; margin-bottom: 0.25rem; }

.notify-btn { font-size: 0.75rem; color: var(--blue); background: none; border: none; cursor: pointer; text-decoration: underline; float: right; }
```

**Step 4: Create index.html**

Create `entity-backfill-service/app/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#0f172a">
  <title>Entity Backfill Monitor</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="manifest" href="/manifest.json">
</head>
<body>
  <h1>Entity Backfill Monitor
    <button class="notify-btn" id="notifyBtn" onclick="subscribePush()">Enable notifications</button>
  </h1>

  <div class="card">
    <h2>Status</h2>
    <span class="status-badge status-idle" id="statusBadge">idle</span>
    <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
    <div style="text-align:center;font-size:0.875rem;margin-bottom:0.5rem" id="progressText">0 / 0 docs</div>
    <div class="counts">
      <span class="ok" id="cntOk">0 ok</span>
      <span class="skip" id="cntSkip">0 skip</span>
      <span class="err" id="cntErr">0 err</span>
    </div>
  </div>

  <div class="card">
    <h2>Performance</h2>
    <div class="stat-grid">
      <div class="stat"><div class="stat-value" id="rate">-</div><div class="stat-label">docs/sec</div></div>
      <div class="stat"><div class="stat-value" id="eta">-</div><div class="stat-label">ETA</div></div>
      <div class="stat"><div class="stat-value" id="elapsed">-</div><div class="stat-label">Elapsed</div></div>
      <div class="stat"><div class="stat-value" id="cost">$0</div><div class="stat-label">Est. cost</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Controls</h2>
    <div class="controls">
      <button class="btn btn-primary" id="btnStart" onclick="apiPost('start')">Start</button>
      <button class="btn" id="btnPause" onclick="apiPost('pause')" disabled>Pause</button>
      <button class="btn" id="btnResume" onclick="apiPost('resume')" disabled>Resume</button>
      <button class="btn" id="btnRetry" onclick="apiPost('retry-errors')">Retry Errors</button>
    </div>
  </div>

  <div class="card">
    <h2>Recent Errors <span id="errCount"></span></h2>
    <div class="error-list" id="errorList"><em style="color:var(--text-dim)">None</em></div>
  </div>

  <div class="card">
    <h2>Knowledge Graph</h2>
    <dl class="neo4j-stats" id="neo4jStats"><dd style="color:var(--text-dim)">Loading...</dd></dl>
  </div>

  <script src="/static/app.js"></script>
</body>
</html>
```

**Step 5: Create app.js**

Create `entity-backfill-service/app/static/app.js`:

```javascript
let evtSource = null;

function fmt(n) { return n != null ? n.toLocaleString() : '-'; }
function fmtTime(s) {
  if (!s || s <= 0) return '-';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return h + 'h ' + m + 'm';
  return m + 'm';
}

function update(d) {
  const total = d.total || 0;
  const processed = (d.success || 0) + (d.skipped || 0) + (d.error || 0);
  const pct = total > 0 ? (processed / total * 100) : 0;

  // Status badge
  const badge = document.getElementById('statusBadge');
  badge.textContent = d.state || 'idle';
  badge.className = 'status-badge status-' + (d.state || 'idle');

  // Progress
  document.getElementById('progressFill').style.width = pct.toFixed(1) + '%';
  document.getElementById('progressText').textContent = fmt(processed) + ' / ' + fmt(total) + ' docs (' + pct.toFixed(1) + '%)';

  // Counts
  document.getElementById('cntOk').textContent = fmt(d.success) + ' ok';
  document.getElementById('cntSkip').textContent = fmt(d.skipped) + ' skip';
  document.getElementById('cntErr').textContent = fmt(d.error) + ' err';

  // Performance
  document.getElementById('rate').textContent = d.rate ? d.rate.toFixed(2) : '-';
  document.getElementById('eta').textContent = fmtTime(d.eta_seconds);
  document.getElementById('elapsed').textContent = fmtTime(d.elapsed);
  document.getElementById('cost').textContent = '$' + (d.cost_estimate || 0).toFixed(2);

  // Controls
  const state = d.state || 'idle';
  document.getElementById('btnStart').disabled = state === 'running';
  document.getElementById('btnPause').disabled = state !== 'running';
  document.getElementById('btnResume').disabled = state !== 'paused';

  // Neo4j stats
  if (d.neo4j) {
    const dl = document.getElementById('neo4jStats');
    dl.innerHTML = '';
    for (const [k, v] of Object.entries(d.neo4j)) {
      dl.innerHTML += '<dt>' + k + '</dt><dd>' + fmt(v) + '</dd>';
    }
  }

  // Store for offline
  try { localStorage.setItem('lastStatus', JSON.stringify(d)); } catch(e) {}
}

async function apiPost(action) {
  try {
    const r = await fetch('/api/' + action, { method: 'POST' });
    const d = await r.json();
    console.log(action, d);
    refresh();
  } catch(e) { console.error(action, e); }
}

async function refresh() {
  try {
    const r = await fetch('/api/status');
    update(await r.json());
  } catch(e) { console.error('status fetch failed', e); }

  try {
    const r = await fetch('/api/errors?limit=20');
    const errors = await r.json();
    const el = document.getElementById('errorList');
    document.getElementById('errCount').textContent = errors.length > 0 ? '(' + errors.length + ')' : '';
    if (errors.length === 0) {
      el.innerHTML = '<em style="color:var(--text-dim)">None</em>';
    } else {
      el.innerHTML = errors.map(function(e) {
        return '<div class="error-item"><div class="error-id">' + e.file_id.substring(0, 20) + '...</div><div class="error-msg">' + (e.error_message || 'unknown') + '</div></div>';
      }).join('');
    }
  } catch(e) {}
}

function connectSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource('/api/events');
  evtSource.addEventListener('progress', function(e) {
    try { update(JSON.parse(e.data)); } catch(err) {}
  });
  evtSource.onerror = function() {
    evtSource.close();
    evtSource = null;
    setTimeout(connectSSE, 5000);
  };
}

async function subscribePush() {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      alert('Push notifications not supported in this browser');
      return;
    }
    const reg = await navigator.serviceWorker.register('/sw.js');
    const keyResp = await fetch('/api/push/vapid-key');
    const keyData = await keyResp.json();

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(keyData.public_key)
    });

    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub.toJSON())
    });

    document.getElementById('notifyBtn').textContent = 'Notifications on';
    document.getElementById('notifyBtn').disabled = true;
  } catch(e) {
    console.error('Push subscribe failed', e);
    alert('Failed to enable notifications: ' + e.message);
  }
}

function urlBase64ToUint8Array(base64String) {
  var padding = '='.repeat((4 - base64String.length % 4) % 4);
  var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  var rawData = window.atob(base64);
  var outputArray = new Uint8Array(rawData.length);
  for (var i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Init
(function() {
  // Try offline data first
  try {
    var cached = localStorage.getItem('lastStatus');
    if (cached) update(JSON.parse(cached));
  } catch(e) {}

  refresh();
  connectSSE();
  setInterval(refresh, 30000); // Fallback polling every 30s for errors + neo4j
})();
```

**Step 6: Commit**

```bash
git add entity-backfill-service/app/static/
git commit -m "feat: PWA dashboard with SSE, push notifications, mobile-first UI"
```

---

### Task 7: Docker Compose Integration

**Files:**
- Modify: `docker-compose.yml` (add service + volume)

**Step 1: Add volume declaration**

Add to the `volumes:` section of `docker-compose.yml`:

```yaml
  entity-backfill-data:
```

**Step 2: Add service definition**

Add to `docker-compose.yml` services section:

```yaml
  entity-backfill-service:
    build: ./entity-backfill-service
    container_name: entity-backfill-service
    ports:
      - "5140:8000"
    volumes:
      - entity-backfill-data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - pa-internal
    depends_on:
      drive-rag-service:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    labels:
      - "com.ai-pa.service=entity-backfill-service"
      - "com.ai-pa.purpose=entity-extraction-backfill"
```

Note: Docker socket mount is needed because the runner calls `docker exec` to query Supabase and Neo4j. This should be read-only.

**Step 3: Build and verify health**

```bash
docker compose build entity-backfill-service
docker compose up -d entity-backfill-service
# Wait for healthy
sleep 10
curl -s http://localhost:5140/health
# Expected: {"status":"healthy","service":"entity-backfill-service"}
```

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add entity-backfill-service to docker-compose"
```

---

### Task 8: Smoke Test End-to-End

**Step 1: Verify dashboard loads**

Open `http://localhost:5140/` in browser. Confirm:
- Dashboard renders with "idle" status
- All cards visible (status, performance, controls, errors, knowledge graph)

**Step 2: Verify API endpoints**

```bash
# Status
curl -s http://localhost:5140/api/status | python3 -m json.tool
# Should show state=idle, total=0

# VAPID key
curl -s http://localhost:5140/api/push/vapid-key | python3 -m json.tool
# Should show public_key

# Errors (empty)
curl -s http://localhost:5140/api/errors | python3 -m json.tool
# Should show []
```

**Step 3: Test start (loads documents from Supabase)**

```bash
curl -s -X POST http://localhost:5140/api/start | python3 -m json.tool
# Should show status=started

# Check status again
curl -s http://localhost:5140/api/status | python3 -m json.tool
# Should show state=running, total=~44353
```

**Step 4: Test pause/resume**

```bash
curl -s -X POST http://localhost:5140/api/pause | python3 -m json.tool
# Should show status=pause_requested

# Wait a moment for current doc to finish
sleep 5
curl -s http://localhost:5140/api/status | python3 -m json.tool
# Should show state=paused

curl -s -X POST http://localhost:5140/api/resume | python3 -m json.tool
# Should show status=started
```

**Step 5: Verify SSE stream**

```bash
curl -N http://localhost:5140/api/events
# Should show SSE events with progress data every few seconds
# Ctrl-C to stop
```

**Step 6: Commit final state**

```bash
git add -A
git commit -m "feat: entity-backfill-service complete with dashboard and push notifications"
```

---

Plan complete and saved to `docs/plans/2026-02-15-entity-backfill-dashboard.md`. Two execution options:

**1. Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

Which approach?