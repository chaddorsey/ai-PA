import pytest
import pytest_asyncio
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
