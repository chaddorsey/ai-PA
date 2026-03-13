# notebooklm-cli Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Click-based Python CLI that wraps `notebooklm-py` through a schema/bridge architecture, exposing NotebookLM to Letta agents and Letta Code agents.

**Architecture:** Schema registry maps `group.action` keys to `notebooklm-py` client methods. Bridge layer wraps async client calls with `asyncio.run()`, serializes dataclass results, and handles errors. CLI provides `--body`/`--fields`/`--dry-run`/`--storage` global flags. Single `run_notebooklm` Letta tool wrapper invokes CLI via subprocess.

**Tech Stack:** Python >=3.9, Click >=8.1, notebooklm-py ^0.1, Poetry

**Spec:** `docs/superpowers/specs/2026-03-13-notebooklm-cli-design.md`

**Reference implementations:**
- omnifocus-cli: `/Volumes/main-drive/ai-PA/omnifocus-cli/` (schema, bridge, cli, fields, validate, formatters)
- Letta tool wrapper: `/Volumes/main-drive/ai-PA/letta/omnifocus_tools.py`

---

## Chunk 1: Project Scaffolding & Core Infrastructure

### Task 1: Project scaffolding

**Files:**
- Create: `notebooklm-cli/pyproject.toml`
- Create: `notebooklm-cli/src/notebooklm_cli/__init__.py`

- [ ] **Step 1: Create project directory**

```bash
mkdir -p /Volumes/main-drive/ai-PA/notebooklm-cli/src/notebooklm_cli
mkdir -p /Volumes/main-drive/ai-PA/notebooklm-cli/tests
touch /Volumes/main-drive/ai-PA/notebooklm-cli/tests/__init__.py
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[tool.poetry]
name = "notebooklm-cli"
version = "0.1.0"
description = "CLI for Google NotebookLM via notebooklm-py"
authors = ["ai-PA"]
packages = [{include = "notebooklm_cli", from = "src"}]

[tool.poetry.dependencies]
python = "^3.9"
click = "^8.1"
notebooklm-py = "^0.1"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"

[tool.poetry.scripts]
notebooklm-cli = "notebooklm_cli.cli:cli"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
markers = [
    "integration: requires NotebookLM authentication",
]
```

- [ ] **Step 3: Write `__init__.py`**

```python
"""NotebookLM CLI — agent-friendly interface to Google NotebookLM."""
```

- [ ] **Step 4: Install dependencies**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && pip install -e ".[dev]" 2>&1 | tail -5
```

This ensures `notebooklm-py`, `click`, and `pytest` are available. All subsequent test commands can use plain `pytest` instead of `PYTHONPATH=src`.

- [ ] **Step 5: Commit**

```bash
git add notebooklm-cli/pyproject.toml notebooklm-cli/src/notebooklm_cli/__init__.py notebooklm-cli/tests/__init__.py
git commit -m "feat(notebooklm-cli): scaffold project structure"
```

---

### Task 2: Schema registry

**Files:**
- Create: `notebooklm-cli/src/notebooklm_cli/schema.py`
- Create: `notebooklm-cli/tests/test_schema.py`

- [ ] **Step 1: Write test**

```python
# tests/test_schema.py
from notebooklm_cli.schema import get_schema, list_schemas

def test_list_schemas_returns_all():
    schemas = list_schemas()
    assert len(schemas) >= 35
    assert "notebook.create" in schemas
    assert "source.add-url" in schemas
    assert "artifact.generate" in schemas
    assert "chat.ask" in schemas
    assert "research.start" in schemas
    assert "note.create" in schemas

def test_get_schema_returns_method():
    s = get_schema("notebook.create")
    assert s is not None
    assert s["method"] == "create"
    assert "title" in s["params"]
    assert s["params"]["title"]["required"] is True

def test_get_schema_unknown():
    assert get_schema("bogus.command") is None

def test_all_schemas_have_method():
    for key in list_schemas():
        s = get_schema(key)
        assert "method" in s, f"{key} missing method"
        assert "description" in s, f"{key} missing description"
        assert "params" in s, f"{key} missing params"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_schema.py -v
```

Expected: `ModuleNotFoundError: No module named 'notebooklm_cli.schema'`

- [ ] **Step 3: Implement schema.py**

Create `notebooklm-cli/src/notebooklm_cli/schema.py` with the full static registry. Each entry maps a `group.action` key to a `method` name (matching the `notebooklm-py` client method), description, and params dict.

**Import path note:** The `notebooklm-py` package imports as `from notebooklm.client import NotebookLMClient`. Verify this before implementing the bridge. The sub-APIs are: `client.notebooks`, `client.sources`, `client.artifacts`, `client.chat`, `client.research`, `client.notes`.

Representative entries per group (implement ALL entries, these show the pattern):

```python
"""Static schema registry for NotebookLM CLI."""
from __future__ import annotations

SCHEMAS: dict[str, dict] = {
    # --- notebook group (7 entries) ---
    "notebook.create": {
        "method": "create",
        "description": "Create a new notebook",
        "params": {
            "title": {"type": "string", "required": True, "description": "Notebook title"},
        },
    },
    "notebook.list": {
        "method": "list",
        "description": "List all notebooks",
        "params": {},
    },
    "notebook.get": {
        "method": "get",
        "description": "Get notebook details",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "notebook.delete": {
        "method": "delete",
        "description": "Delete a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    "notebook.rename": {
        "method": "rename",
        "description": "Rename a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "title": {"type": "string", "required": True, "description": "New title"},
        },
    },
    # notebook.describe, notebook.topics follow same pattern with notebookId required

    # --- source group (12 entries) ---
    "source.add-url": {
        "method": "add_url",
        "description": "Add a URL source to a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "url": {"type": "string", "required": True, "description": "URL to add"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for processing to complete"},
        },
    },
    "source.add-file": {
        "method": "add_file",
        "description": "Add a file source (PDF, DOCX, MD, etc.)",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "filePath": {"type": "string", "required": True, "description": "Path to file"},
            "wait": {"type": "boolean", "required": False, "description": "Wait for processing"},
        },
    },
    "source.list": {
        "method": "list",
        "description": "List sources in a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
        },
    },
    # source.add-text (notebookId, text, title), source.add-youtube (notebookId, url),
    # source.add-drive (notebookId, driveFileId), source.get, source.delete,
    # source.rename, source.refresh, source.guide, source.fulltext
    # All take notebookId + sourceId where applicable

    # --- artifact group (8 entries) ---
    "artifact.generate": {
        "method": "generate",
        "description": "Generate an artifact (audio, video, report, quiz, etc.)",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "type": {"type": "string", "required": True, "description": "Artifact type: audio, video, report, quiz, slides, infographic, mindmap, table"},
            "instructions": {"type": "string", "required": False, "description": "Generation instructions"},
        },
    },
    "artifact.wait": {
        "method": "wait_for_completion",
        "description": "Wait for artifact generation to complete",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "taskId": {"type": "string", "required": True, "description": "Generation task ID"},
            "timeout": {"type": "integer", "required": False, "description": "Timeout in seconds (default 300)"},
        },
    },
    "artifact.download": {
        "method": "download",
        "description": "Download an artifact to a file",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "type": {"type": "string", "required": True, "description": "Artifact type to download"},
            "outputPath": {"type": "string", "required": True, "description": "Output file path"},
        },
    },
    # artifact.list, artifact.get, artifact.delete, artifact.rename, artifact.status

    # --- chat group (4 entries) ---
    "chat.ask": {
        "method": "ask",
        "description": "Ask the notebook a question",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "question": {"type": "string", "required": True, "description": "Question to ask"},
            "sourceIds": {"type": "array[string]", "required": False, "description": "Limit to specific sources"},
            "conversationId": {"type": "string", "required": False, "description": "Continue a conversation (from previous ask response)"},
        },
    },
    # chat.history (notebookId), chat.clear (notebookId), chat.save (notebookId)

    # --- research group (3 entries) ---
    "research.start": {
        "method": "start",
        "description": "Start a web or Drive research session",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "query": {"type": "string", "required": True, "description": "Research query"},
            "source": {"type": "string", "required": False, "description": "web or drive (default: web)"},
            "mode": {"type": "string", "required": False, "description": "fast or deep (default: fast)"},
        },
    },
    # research.poll (notebookId), research.import (notebookId, taskId, sourceIds)

    # --- note group (4 entries) ---
    "note.create": {
        "method": "create",
        "description": "Create a user note in a notebook",
        "params": {
            "notebookId": {"type": "string", "required": True, "description": "Notebook ID"},
            "title": {"type": "string", "required": True, "description": "Note title"},
            "content": {"type": "string", "required": True, "description": "Note content"},
        },
    },
    # note.list (notebookId), note.update (notebookId, noteId, content, title),
    # note.delete (notebookId, noteId)
}


def get_schema(key: str) -> dict | None:
    return SCHEMAS.get(key)


def list_schemas() -> list[str]:
    return sorted(SCHEMAS.keys())
```

Complete ALL entries marked with comments above. Inspect `notebooklm-py` source at `/Users/dorseyhomeserver/Library/Python/3.9/lib/python/site-packages/notebooklm/` for exact method signatures: `_notebooks.py`, `_sources.py`, `_artifacts.py`, `_chat.py`, `_research.py`, `_notes.py`.

- [ ] **Step 4: Run test — expect PASS**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_schema.py -v
```

- [ ] **Step 5: Commit**

```bash
git add notebooklm-cli/src/notebooklm_cli/schema.py notebooklm-cli/tests/test_schema.py
git commit -m "feat(notebooklm-cli): add schema registry with 38 operations"
```

---

### Task 3: Validation, fields, and formatters

**Files:**
- Create: `notebooklm-cli/src/notebooklm_cli/validate.py`
- Create: `notebooklm-cli/src/notebooklm_cli/fields.py`
- Create: `notebooklm-cli/src/notebooklm_cli/formatters.py`
- Create: `notebooklm-cli/tests/test_validate.py`
- Create: `notebooklm-cli/tests/test_fields.py`

- [ ] **Step 1: Write validation tests**

```python
# tests/test_validate.py
from notebooklm_cli.validate import validate_body, validate_path

def test_validate_body_required_field():
    errors = validate_body("notebook.create", {})
    assert any(e["field"] == "title" for e in errors)

def test_validate_body_valid():
    errors = validate_body("notebook.create", {"title": "Test"})
    assert errors == []

def test_validate_body_unknown_field():
    errors = validate_body("notebook.create", {"title": "Test", "bogus": "x"})
    assert any(e["field"] == "bogus" for e in errors)

def test_validate_body_type_check():
    errors = validate_body("notebook.create", {"title": 123})
    assert any(e["field"] == "title" for e in errors)

def test_validate_path_rejects_traversal():
    err = validate_path("../../etc/passwd")
    assert err is not None
    assert ".." in err

def test_validate_path_allows_normal():
    err = validate_path("/Users/test/file.pdf")
    assert err is None
```

- [ ] **Step 2: Write fields tests**

```python
# tests/test_fields.py
from notebooklm_cli.fields import apply_field_mask

def test_mask_dict():
    data = {"id": "1", "title": "Test", "extra": "x"}
    assert apply_field_mask(data, ["id", "title"]) == {"id": "1", "title": "Test"}

def test_mask_list():
    data = [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]
    result = apply_field_mask(data, ["id"])
    assert result == [{"id": "1"}, {"id": "2"}]

def test_mask_none_passthrough():
    data = {"id": "1", "title": "Test"}
    assert apply_field_mask(data, None) == data
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_validate.py tests/test_fields.py -v
```

- [ ] **Step 4: Implement validate.py, fields.py, formatters.py**

Copy the pattern from omnifocus-cli's equivalents:
- `validate.py`: `validate_body()` (schema-based), `validate_path()` (rejects `..` components)
- `fields.py`: `apply_field_mask()` — identical to omnifocus-cli
- `formatters.py`: `should_use_json()`, `output_result()`, `output_error()` — identical to omnifocus-cli

All files must include `from __future__ import annotations` for Python 3.9 compatibility.

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_validate.py tests/test_fields.py -v
```

- [ ] **Step 6: Commit**

```bash
git add notebooklm-cli/src/notebooklm_cli/validate.py notebooklm-cli/src/notebooklm_cli/fields.py notebooklm-cli/src/notebooklm_cli/formatters.py notebooklm-cli/tests/test_validate.py notebooklm-cli/tests/test_fields.py
git commit -m "feat(notebooklm-cli): add validation, field masking, and formatters"
```

---

## Chunk 2: Bridge & CLI

### Task 4: Bridge layer

**Files:**
- Create: `notebooklm-cli/src/notebooklm_cli/bridge.py`
- Create: `notebooklm-cli/tests/test_bridge.py`

- [ ] **Step 1: Write bridge tests**

```python
# tests/test_bridge.py
"""Bridge tests — unit tests mock the NotebookLMClient, integration tests need auth."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from notebooklm_cli.bridge import call, serialize

def test_serialize_dataclass():
    """Dataclasses with __dict__ should serialize to plain dicts."""
    from dataclasses import dataclass
    @dataclass
    class Fake:
        id: str
        title: str
    result = serialize(Fake(id="abc", title="Test"))
    assert result == {"id": "abc", "title": "Test"}

def test_serialize_list_of_dataclasses():
    from dataclasses import dataclass
    @dataclass
    class Fake:
        id: str
    result = serialize([Fake(id="a"), Fake(id="b")])
    assert result == [{"id": "a"}, {"id": "b"}]

def test_serialize_none():
    assert serialize(None) is None

def test_serialize_dict_passthrough():
    d = {"key": "value"}
    assert serialize(d) == d

def test_call_unknown_group():
    """Unknown group should return error without hitting notebooklm-py."""
    result = call("bogus.action", {})
    assert result["status"] == "error"
    assert "Unknown group" in result["error_message"]

def test_call_auth_refresh_on_expired():
    """If first call raises expired auth, bridge should retry once after refresh."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    mock_client = AsyncMock()
    mock_client.notebooks.list = AsyncMock(
        side_effect=[ValueError("Authentication expired"), []]
    )
    mock_client.refresh_auth = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("notebooklm_cli.bridge._create_client", return_value=mock_client):
        result = call("notebook.list", {})
        assert result["status"] == "ok"
        mock_client.refresh_auth.assert_called_once()
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_bridge.py -v
```

- [ ] **Step 3: Implement bridge.py**

Key structure:

```python
"""Bridge layer — wraps notebooklm-py's async client for sync CLI use."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Method routing table: group -> sub-API attribute on NotebookLMClient
_API_MAP = {
    "notebook": "notebooks",
    "source": "sources",
    "artifact": "artifacts",
    "chat": "chat",
    "research": "research",
    "note": "notes",
}


def serialize(obj: Any) -> Any:
    """Convert dataclasses, lists, enums to JSON-safe dicts."""
    if obj is None:
        return None
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: serialize(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if hasattr(obj, 'value'):  # Enum
        return obj.value
    return obj


def call(method: str, params: dict) -> dict:
    """Sync entry point. Route method to notebooklm-py client."""
    try:
        return asyncio.run(_async_call(method, params))
    except Exception as e:
        logger.error(f"Bridge error: {e}")
        return {"status": "error", "error_message": str(e)}


async def _create_client():
    """Create NotebookLMClient from storage. Separated for testability."""
    from notebooklm.client import NotebookLMClient
    storage_path = os.environ.get("NOTEBOOKLM_STORAGE")
    return await NotebookLMClient.from_storage(path=storage_path)


async def _async_call(method: str, params: dict) -> dict:
    """Resolve group.action to client sub-API method, call it, serialize."""
    parts = method.split(".", 1)
    if len(parts) != 2:
        return {"status": "error", "error_message": f"Invalid method format: {method}"}

    group, action = parts
    api_attr = _API_MAP.get(group)
    if not api_attr:
        return {"status": "error", "error_message": f"Unknown group: {group}"}

    client = await _create_client()
    async with client:
        api = getattr(client, api_attr)
        method_name = action.replace("-", "_")
        fn = getattr(api, method_name, None)
        if fn is None:
            return {"status": "error", "error_message": f"Unknown method: {group}.{action}"}

        # Validate file paths before calling
        from notebooklm_cli.validate import validate_path
        for path_field in ("filePath", "outputPath"):
            if path_field in params:
                err = validate_path(params[path_field])
                if err:
                    return {"status": "error", "error_message": f"{path_field}: {err}"}

        # Attempt call with one auth refresh retry
        try:
            result = await fn(**params)
        except ValueError as e:
            if "expired" in str(e).lower() or "invalid" in str(e).lower():
                logger.info("Auth expired, attempting refresh...")
                await client.refresh_auth()
                result = await fn(**params)
            else:
                raise

        return {"status": "ok", "result": serialize(result)}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_bridge.py -v
```

- [ ] **Step 5: Commit**

```bash
git add notebooklm-cli/src/notebooklm_cli/bridge.py notebooklm-cli/tests/test_bridge.py
git commit -m "feat(notebooklm-cli): add bridge layer with serialization and error handling"
```

---

### Task 5: Click CLI with command groups

**Files:**
- Create: `notebooklm-cli/src/notebooklm_cli/cli.py`
- Create: `notebooklm-cli/tests/test_cli.py`

- [ ] **Step 1: Write CLI tests**

```python
# tests/test_cli.py
from click.testing import CliRunner
from notebooklm_cli.cli import cli

runner = CliRunner()

def test_schema_list():
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    assert "notebook.create" in result.output

def test_schema_detail():
    result = runner.invoke(cli, ["schema", "notebook.create"])
    assert result.exit_code == 0
    assert "title" in result.output

def test_schema_unknown():
    result = runner.invoke(cli, ["schema", "bogus.thing"])
    assert result.exit_code == 1

def test_dry_run_valid():
    result = runner.invoke(cli, ["--body", '{"title": "Test"}', "--dry-run", "notebook", "create"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower() or "dry" in result.output.lower()

def test_dry_run_invalid():
    result = runner.invoke(cli, ["--body", '{}', "--dry-run", "notebook", "create"])
    assert result.exit_code == 2
    assert "title" in result.output

def test_health_no_auth(tmp_path):
    """Health should report error when no storage_state.json exists."""
    result = runner.invoke(cli, ["--storage", str(tmp_path / "nonexistent.json"), "health"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert data["status"] == "error"
    assert "not found" in data.get("error", "").lower() or "not found" in data.get("error_message", "").lower()
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_cli.py -v
```

- [ ] **Step 3: Implement cli.py**

Follow the omnifocus-cli pattern exactly:

```python
"""Click CLI for NotebookLM."""
from __future__ import annotations

import json
import sys

import click

from notebooklm_cli.bridge import call
from notebooklm_cli.fields import apply_field_mask
from notebooklm_cli.formatters import output_error, output_result, should_use_json
from notebooklm_cli.schema import get_schema, list_schemas
from notebooklm_cli.validate import validate_body, validate_path


@click.group()
@click.option("--format", "format_flag", type=click.Choice(["json", "text"]), default=None)
@click.option("--body", "body_json", default=None, help="Raw JSON input (agent-first path)")
@click.option("--dry-run", is_flag=True, default=False, help="Validate + preview, no execution")
@click.option("--fields", default=None, help="Comma-separated output fields")
@click.option("--storage", default=None, help="Path to storage_state.json")
@click.pass_context
def cli(ctx, format_flag, body_json, dry_run, fields, storage):
    """NotebookLM CLI — manage notebooks, sources, and AI-generated content."""
    ctx.ensure_object(dict)
    ctx.obj["format"] = format_flag
    ctx.obj["body"] = body_json
    ctx.obj["dry_run"] = dry_run
    ctx.obj["fields"] = fields.split(",") if fields else None
    if storage:
        import os
        os.environ["NOTEBOOKLM_STORAGE"] = storage
```

Then implement:

**`_run()` helper** — Note: unlike omnifocus-cli, this does NOT take a separate `method` arg. The bridge resolves the method from the schema key directly via `action.replace("-", "_")`.

```python
def _run(ctx, schema_key: str, params: dict, had_convenience_flags: bool = False):
    """Core execution: parse --body, validate, dry-run, call bridge, output."""
    body_json = ctx.obj.get("body")
    dry_run = ctx.obj.get("dry_run", False)
    fields = ctx.obj.get("fields")
    fmt = ctx.obj.get("format")

    # --body takes precedence over convenience flags
    if body_json:
        if had_convenience_flags:
            click.echo("Warning: --body overrides convenience flags", err=True)
        try:
            params = json.loads(body_json)
        except json.JSONDecodeError as e:
            output_error(f"Invalid JSON in --body: {e}", fmt)
            sys.exit(1)

    # Validate
    errors = validate_body(schema_key, params)
    if errors:
        output_result({"valid": False, "errors": errors}, fmt)
        sys.exit(2)

    if dry_run:
        output_result({"valid": True, "dry_run": True, "schema": schema_key, "params": params}, fmt)
        return

    # Execute via bridge
    result = call(schema_key, params)
    if result.get("status") == "error":
        output_error(result.get("error_message", "Unknown error"), fmt)
        sys.exit(1)

    data = result.get("result", {})
    if fields:
        data = apply_field_mask(data, fields)
    output_result(data, fmt)
```

**`health` command:**

```python
@cli.command()
@click.pass_context
def health(ctx):
    """Check NotebookLM authentication status."""
    import os
    from pathlib import Path
    fmt = ctx.obj.get("format")

    # Check storage_state.json
    storage = os.environ.get("NOTEBOOKLM_STORAGE") or os.environ.get("NOTEBOOKLM_HOME")
    if storage:
        state_path = Path(storage) if storage.endswith(".json") else Path(storage) / "storage_state.json"
    else:
        state_path = Path.home() / ".notebooklm" / "storage_state.json"

    if not state_path.exists():
        output_result({"status": "error", "error_message": f"Storage not found: {state_path}. Run 'notebooklm login'"}, fmt)
        return

    # Check cookies
    try:
        data = json.loads(state_path.read_text())
        cookies = {c["name"] for c in data.get("cookies", []) if c.get("domain", "").endswith("google.com")}
        has_sid = "SID" in cookies
    except Exception as e:
        output_result({"status": "error", "error_message": f"Cannot read storage: {e}"}, fmt)
        return

    if not has_sid:
        output_result({"status": "error", "error_message": "SID cookie missing. Run 'notebooklm login'"}, fmt)
        return

    output_result({"status": "ok", "auth": "valid", "storagePath": str(state_path), "cookieCount": len(cookies)}, fmt)
```

**Command groups** — each follows this pattern. One example per group:

```python
# --- notebook ---
@cli.group()
def notebook():
    """Manage notebooks."""

@notebook.command("create")
@click.option("--title", default=None)
@click.pass_context
def notebook_create(ctx, title):
    params = {}
    had_flags = False
    if title is not None:
        params["title"] = title
        had_flags = True
    _run(ctx, "notebook.create", params, had_convenience_flags=had_flags)

# --- source (file path example) ---
@cli.group()
def source():
    """Manage notebook sources."""

@source.command("add-file")
@click.option("--notebook-id", default=None)
@click.option("--file-path", default=None)
@click.option("--wait/--no-wait", default=False)
@click.pass_context
def source_add_file(ctx, notebook_id, file_path, wait):
    params = {}
    had_flags = False
    if notebook_id is not None:
        params["notebookId"] = notebook_id
        had_flags = True
    if file_path is not None:
        params["filePath"] = file_path
        had_flags = True
    if wait:
        params["wait"] = True
        had_flags = True
    _run(ctx, "source.add-file", params, had_convenience_flags=had_flags)

# --- artifact (enum-like type param) ---
@cli.group()
def artifact():
    """Manage AI-generated artifacts."""

@artifact.command("generate")
@click.option("--notebook-id", default=None)
@click.option("--type", "artifact_type", default=None,
              type=click.Choice(["audio", "video", "report", "quiz", "slides", "infographic", "mindmap", "table"]))
@click.option("--instructions", default=None)
@click.pass_context
def artifact_generate(ctx, notebook_id, artifact_type, instructions):
    params = {}
    had_flags = False
    if notebook_id is not None:
        params["notebookId"] = notebook_id
        had_flags = True
    if artifact_type is not None:
        params["type"] = artifact_type
        had_flags = True
    if instructions is not None:
        params["instructions"] = instructions
        had_flags = True
    _run(ctx, "artifact.generate", params, had_convenience_flags=had_flags)

# --- chat ---
@cli.group()
def chat():
    """Chat with notebooks."""

@chat.command("ask")
@click.option("--notebook-id", default=None)
@click.option("--question", default=None)
@click.option("--conversation-id", default=None)
@click.pass_context
def chat_ask(ctx, notebook_id, question, conversation_id):
    params = {}
    had_flags = False
    if notebook_id is not None:
        params["notebookId"] = notebook_id
        had_flags = True
    if question is not None:
        params["question"] = question
        had_flags = True
    if conversation_id is not None:
        params["conversationId"] = conversation_id
        had_flags = True
    _run(ctx, "chat.ask", params, had_convenience_flags=had_flags)
```

Implement ALL subcommands for all 6 groups. The remaining commands (research, note) follow the same pattern. Every subcommand maps convenience flags to schema param names and delegates to `_run()`.

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Volumes/main-drive/ai-PA/notebooklm-cli && PYTHONPATH=src python -m pytest tests/test_cli.py -v
```

- [ ] **Step 5: Commit**

```bash
git add notebooklm-cli/src/notebooklm_cli/cli.py notebooklm-cli/tests/test_cli.py
git commit -m "feat(notebooklm-cli): add Click CLI with 6 command groups and schema discovery"
```

---

## Chunk 3: Agent Integration & Documentation

### Task 6: CONTEXT.md

**Files:**
- Create: `notebooklm-cli/CONTEXT.md`

- [ ] **Step 1: Write CONTEXT.md**

Follow the omnifocus-cli CONTEXT.md pattern. Include:
- Quick start (schema discovery, create notebook, add source, ask question)
- Invariants (always use --fields on lists, --dry-run before mutations, etc.)
- Error handling (exit codes)
- Command groups table
- Workflow pattern
- Conversation lifecycle (conversationId returned from chat ask, pass back for follow-ups)
- Artifact generation pattern (generate -> wait -> download)

- [ ] **Step 2: Commit**

```bash
git add notebooklm-cli/CONTEXT.md
git commit -m "docs(notebooklm-cli): add agent-facing CONTEXT.md"
```

---

### Task 7: Letta tool wrapper

**Files:**
- Create: `letta/notebooklm_tools.py`
- Create: `letta/register_notebooklm_tools.py`

- [ ] **Step 1: Write run_notebooklm tool**

Create `letta/notebooklm_tools.py` following the exact pattern from `letta/omnifocus_tools.py`:

```python
from typing import Dict, Any, Optional


def run_notebooklm(command: str, params: Optional[str] = None,
                   fields: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Run any NotebookLM CLI command. Manage notebooks, sources, chat, artifacts,
    research, and notes in Google NotebookLM.

    Commands follow the pattern: <group> <action>
    Use --body for JSON input (agent path), or convenience flags (human path).
    Use "schema --list" to see all available commands.

    Notebook examples:
      command="notebook list"
      command="notebook create", params='{"title": "My Research"}'
      command="notebook get", params='{"notebookId": "abc123"}'

    Source examples:
      command="source add-url", params='{"notebookId": "abc123", "url": "https://..."}'
      command="source add-file", params='{"notebookId": "abc123", "filePath": "/path/to.pdf"}'
      command="source list", params='{"notebookId": "abc123"}'

    Chat examples:
      command="chat ask", params='{"notebookId": "abc123", "question": "Summarize this"}'

    Artifact examples:
      command="artifact generate", params='{"notebookId": "abc123", "type": "audio", "instructions": "Make it engaging"}'
      command="artifact wait", params='{"notebookId": "abc123", "taskId": "task789"}'
      command="artifact download", params='{"notebookId": "abc123", "type": "audio", "outputPath": "./out.mp3"}'

    Research examples:
      command="research start", params='{"notebookId": "abc123", "query": "topic", "source": "web"}'

    Schema discovery:
      command="schema --list"
      command="schema notebook.create"

    Args:
        command: The notebooklm-cli subcommand (e.g. "notebook list", "chat ask")
        params: JSON string of parameters (optional). Passed as --body.
        fields: Comma-separated output fields (optional). Limits token usage.
        timeout: Command timeout in seconds (default 60). Use 300 for artifact wait.

    Returns:
        Dictionary with status and parsed JSON response.
    """
    import json
    import shlex
    import subprocess
    import traceback

    try:
        if not command or not command.strip():
            return {"status": "error", "error_message": "command is required"}

        cli_args = ["notebooklm-cli"]

        if params:
            cli_args.extend(["--body", params])
        if fields:
            cli_args.extend(["--fields", fields])

        first_word = command.strip().split()[0] if command.strip() else ""
        if first_word != "schema":
            cli_args.extend(["--format", "json"])

        cli_args.extend(shlex.split(command.strip()))

        r = subprocess.run(cli_args, capture_output=True, text=True, timeout=timeout)

        if r.returncode != 0:
            return {"status": "error", "error_message": r.stderr[:1000] if r.stderr else f"Exit code {r.returncode}"}

        output = r.stdout.strip()
        if not output:
            return {"status": "ok", "result": {}}

        try:
            parsed = json.loads(output)
            return {"status": "ok", "result": parsed}
        except json.JSONDecodeError:
            return {"status": "ok", "result_text": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "error_message": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

- [ ] **Step 2: Write registration script**

Create `letta/register_notebooklm_tools.py` following the pattern from `letta/register_omnifocus_tools.py`:

```python
"""Register run_notebooklm tool with Letta."""
import os
from letta_client import Letta
from notebooklm_tools import run_notebooklm

LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")

client = Letta(base_url=LETTA_BASE_URL)
tool = client.tools.upsert_from_function(func=run_notebooklm)
print(f"Registered tool: {tool.name} (id: {tool.id})")
```

- [ ] **Step 3: Commit**

```bash
git add letta/notebooklm_tools.py letta/register_notebooklm_tools.py
git commit -m "feat(letta): add run_notebooklm tool wrapper and registration script"
```

---

### Task 8: Docker and entrypoint integration

**Files:**
- Modify: `docker-compose.yml` (add volume mounts to letta service)
- Modify: `letta/entrypoint-wrapper.sh` (add notebooklm-cli pip install)

- [ ] **Step 1: Update entrypoint-wrapper.sh**

Add a block to install notebooklm-cli, following the existing omnifocus-cli pattern. Find the omnifocus-cli install block and add after it:

```bash
if [ -d "/app/tools/notebooklm-cli" ]; then
    echo "[entrypoint-wrapper] Installing notebooklm-cli..."
    python3 -m pip install --quiet --no-warn-script-location \
        /app/tools/notebooklm-cli/ 2>&1 | tail -3
fi
```

- [ ] **Step 2: Update docker-compose.yml**

Add to the letta service's `volumes` section:

```yaml
- ./notebooklm-cli:/app/tools/notebooklm-cli:ro
- ${NOTEBOOKLM_HOME:-~/.notebooklm}:/notebooklm-auth:ro
```

Add to the letta service's `environment` section:

```yaml
NOTEBOOKLM_HOME: /notebooklm-auth
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml letta/entrypoint-wrapper.sh
git commit -m "feat: add notebooklm-cli to Docker deployment pipeline"
```

---

### Task 9: OpenClaw skills

**Files:**
- Create: `notebooklm-cli/skills/notebooklm-shared/SKILL.md`
- Create: `notebooklm-cli/skills/notebooklm-notebooks/SKILL.md`
- Create: `notebooklm-cli/skills/notebooklm-sources/SKILL.md`
- Create: `notebooklm-cli/skills/notebooklm-chat/SKILL.md`
- Create: `notebooklm-cli/skills/notebooklm-artifacts/SKILL.md`
- Create: `notebooklm-cli/skills/recipe-notebooklm-research-project/SKILL.md`
- Create: `notebooklm-cli/skills/recipe-notebooklm-meeting-prep/SKILL.md`

- [ ] **Step 1: Create skill directories**

```bash
mkdir -p notebooklm-cli/skills/{notebooklm-shared,notebooklm-notebooks,notebooklm-sources,notebooklm-chat,notebooklm-artifacts,recipe-notebooklm-research-project,recipe-notebooklm-meeting-prep}
```

- [ ] **Step 2: Write all 7 SKILL.md files**

Follow the OpenClaw format established in `omnifocus-cli/skills/`. Each skill has:
- YAML frontmatter with `name`, `version`, `description`, `metadata.openclaw`
- `requires.bins: ["notebooklm-cli"]`
- Prerequisite link to shared skill
- Action table with descriptions
- Common patterns with CLI examples
- CLI help reference via `cliHelp`

Shared skill covers: installation (host + Docker), auth setup (`notebooklm login`), global flags, schema discovery, security rules, workflow pattern, conversation lifecycle.

Recipe skills: step-by-step workflows with CLI commands for research project setup and meeting prep.

- [ ] **Step 3: Commit**

```bash
git add notebooklm-cli/skills/
git commit -m "docs(notebooklm-cli): add 7 OpenClaw skill files"
```

---

### Task 10: Host installation and smoke test

- [ ] **Step 1: Install on host**

```bash
pip install /Volumes/main-drive/ai-PA/notebooklm-cli
```

- [ ] **Step 2: Verify CLI is available**

```bash
notebooklm-cli schema --list
notebooklm-cli schema notebook.create
notebooklm-cli health
```

- [ ] **Step 3: Run notebooklm login (one-time auth)**

```bash
pip install "notebooklm-py[browser]"
playwright install chromium
notebooklm login
```

Verify `~/.notebooklm/storage_state.json` exists after login.

- [ ] **Step 4: Integration smoke test**

```bash
# List notebooks
notebooklm-cli --fields id,title notebook list

# Create a test notebook
notebooklm-cli --body '{"title": "CLI Smoke Test"}' notebook create

# Verify it appears
notebooklm-cli --fields id,title notebook list

# Delete the test notebook
notebooklm-cli --body '{"notebookId": "<ID_FROM_ABOVE>"}' notebook delete
```

- [ ] **Step 5: Register Letta tool**

```bash
cd /Volumes/main-drive/ai-PA && LETTA_BASE_URL=http://localhost:8283 python letta/register_notebooklm_tools.py
```

- [ ] **Step 6: Final commit**

```bash
git add -A notebooklm-cli/
git commit -m "feat(notebooklm-cli): complete initial implementation"
```
