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
