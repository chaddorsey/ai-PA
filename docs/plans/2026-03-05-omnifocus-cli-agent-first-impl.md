# OmniFocus CLI v1 Agent-First Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the OmniFocus CLI so agents interact via `--body` JSON, schema introspection, input hardening, dry-run, and field masks — while keeping the existing bridge and plugin unchanged.

**Architecture:** CLI receives `--body '{...}'` JSON → validates against static schema registry → calls osascript bridge → filters output with `--fields`. New modules: `schema.py`, `validate.py`, `fields.py`. Rewritten: `cli.py`, `formatters.py`. New: `CONTEXT.md`, 5 Letta tools.

**Tech Stack:** Python 3.11+, Click 8.x, pytest 8.x, Poetry

**Working directory:** `/Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli/`

**Design doc:** `docs/plans/2026-03-05-omnifocus-cli-agent-first-design.md`

---

## Task 1: Schema Registry (`schema.py`)

**Files:**
- Create: `src/omnifocus_cli/schema.py`
- Test: `tests/test_schema.py`

**Step 1: Write the failing tests**

```python
# tests/test_schema.py
import pytest
from omnifocus_cli.schema import SCHEMAS, get_schema, list_schemas


def test_get_schema_returns_task_create():
    s = get_schema("task.create")
    assert s["method"] == "createTask"
    assert "name" in s["params"]
    assert s["params"]["name"]["required"] is True


def test_get_schema_returns_none_for_unknown():
    assert get_schema("bogus.method") is None


def test_list_schemas_returns_all_keys():
    keys = list_schemas()
    assert "task.create" in keys
    assert "task.get" in keys
    assert "task.update" in keys
    assert "task.complete" in keys
    assert "task.list" in keys
    assert "search" in keys
    assert "project.list" in keys
    assert "project.get" in keys
    assert "project.create" in keys
    assert "project.update" in keys
    assert "project.folders" in keys
    assert "inbox.list" in keys
    assert "inbox.process" in keys
    assert "tags.list" in keys
    assert "tags.create" in keys
    assert "tags.rename" in keys
    assert "tags.delete" in keys


def test_all_schemas_have_method_and_params():
    for key in list_schemas():
        s = get_schema(key)
        assert "method" in s, f"{key} missing 'method'"
        assert "params" in s, f"{key} missing 'params'"
        assert isinstance(s["params"], dict), f"{key} params not a dict"


def test_param_entries_have_required_fields():
    """Every param must have type, required, description."""
    for key in list_schemas():
        s = get_schema(key)
        for pname, pdef in s["params"].items():
            assert "type" in pdef, f"{key}.{pname} missing 'type'"
            assert "required" in pdef, f"{key}.{pname} missing 'required'"
            assert "description" in pdef, f"{key}.{pname} missing 'description'"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Volumes/main-drive/ai-PA/.worktrees/omnifocus-cli/omnifocus-cli && poetry run pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'omnifocus_cli.schema'`

**Step 3: Write the implementation**

Create `src/omnifocus_cli/schema.py` with a `SCHEMAS` dict containing all 17 method schemas. Each schema maps `<group>.<action>` to:
```python
{
    "method": "<pluginMethodName>",
    "description": "...",
    "params": {
        "paramName": {"type": "string", "required": True, "description": "..."},
        ...
    }
}
```

Methods to include (from plugin research):
- `task.create` → `createTask` (name*, projectId, note, flagged, dueDate, deferDate, plannedDate, estimatedMinutes, tagIds)
- `task.get` → `getTask` (taskId*)
- `task.update` → `updateTask` (taskId*, name, projectId, note, flagged, dueDate, deferDate, plannedDate, estimatedMinutes, tagIds)
- `task.complete` → `completeTask` (taskId*)
- `task.list` → `queryTasks` (projectId, tagId, flagged, includeCompleted)
- `search` → `searchTasks` (query*, scope, scopeId, tagId, flagged, isAvailable, dueBefore, dueAfter, deferBefore, deferAfter, isOverdue, maxResults)
- `project.list` → `listProjects` (completion, folderId, listByFolder)
- `project.get` → `getProjectById` (projectId*)
- `project.create` → `createProject` (name*, folderId, properties)
- `project.update` → `setProjectProperties` (projectId*, properties)
- `project.folders` → `listFolders` (no params)
- `inbox.list` → `listInbox` (limit, includeCompleted)
- `inbox.process` → `processInboxItem` (taskId*, projectId, tagIds, flagged, dueDate, deferDate)
- `tags.list` → `listTags` (no params)
- `tags.create` → `createTag` (name*, parentTagId)
- `tags.rename` → `updateTag` (tagId*, name*)
- `tags.delete` → `deleteTag` (tagId*, force)

Also add:
```python
def get_schema(key: str) -> dict | None:
    return SCHEMAS.get(key)

def list_schemas() -> list[str]:
    return sorted(SCHEMAS.keys())
```

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_schema.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/omnifocus_cli/schema.py tests/test_schema.py
git commit -m "feat(omnifocus-cli): add static schema registry for all 17 methods"
```

---

## Task 2: Input Validation (`validate.py`)

**Files:**
- Create: `src/omnifocus_cli/validate.py`
- Test: `tests/test_validate.py`

**Step 1: Write the failing tests**

```python
# tests/test_validate.py
import pytest
from omnifocus_cli.validate import validate_body, validate_uuid, validate_date, validate_name


class TestValidateBody:
    def test_valid_body_passes(self):
        errors = validate_body("task.create", {"name": "Buy milk"})
        assert errors == []

    def test_missing_required_field(self):
        errors = validate_body("task.create", {})
        assert any(e["field"] == "name" and "required" in e["error"] for e in errors)

    def test_unknown_field_rejected(self):
        errors = validate_body("task.create", {"name": "X", "bogusField": 1})
        assert any(e["field"] == "bogusField" and "unknown" in e["error"] for e in errors)

    def test_type_mismatch_boolean(self):
        errors = validate_body("task.create", {"name": "X", "flagged": "yes"})
        assert any(e["field"] == "flagged" and "boolean" in e["error"] for e in errors)

    def test_type_mismatch_integer(self):
        errors = validate_body("task.create", {"name": "X", "estimatedMinutes": "thirty"})
        assert any(e["field"] == "estimatedMinutes" and "integer" in e["error"] for e in errors)

    def test_type_mismatch_array(self):
        errors = validate_body("task.create", {"name": "X", "tagIds": "not-an-array"})
        assert any(e["field"] == "tagIds" and "array" in e["error"] for e in errors)

    def test_multiple_errors_returned(self):
        errors = validate_body("task.create", {"flagged": "yes", "bogus": 1})
        assert len(errors) >= 3  # missing name, type mismatch flagged, unknown bogus

    def test_unknown_schema_key(self):
        errors = validate_body("bogus.method", {"name": "X"})
        assert any("unknown" in e["error"].lower() or "schema" in e["error"].lower() for e in errors)

    def test_optional_fields_not_required(self):
        errors = validate_body("task.create", {"name": "Buy milk"})
        assert errors == []


class TestValidateUuid:
    def test_valid_uuid(self):
        assert validate_uuid("abc-123-def") is None

    def test_rejects_question_mark(self):
        assert validate_uuid("abc?123") is not None

    def test_rejects_hash(self):
        assert validate_uuid("abc#123") is not None

    def test_rejects_percent(self):
        assert validate_uuid("abc%123") is not None

    def test_rejects_dot_dot(self):
        assert validate_uuid("abc..123") is not None

    def test_rejects_control_chars(self):
        assert validate_uuid("abc\x00123") is not None
        assert validate_uuid("abc\x1f123") is not None
        assert validate_uuid("abc\x7f123") is not None

    def test_rejects_whitespace(self):
        assert validate_uuid("abc 123") is not None
        assert validate_uuid("abc\t123") is not None
        assert validate_uuid("abc\n123") is not None

    def test_rejects_empty(self):
        assert validate_uuid("") is not None


class TestValidateDate:
    def test_valid_date(self):
        assert validate_date("2026-03-10") is None

    def test_valid_datetime(self):
        assert validate_date("2026-03-10T17:00:00Z") is None

    def test_valid_datetime_with_offset(self):
        assert validate_date("2026-03-10T17:00:00+05:00") is None

    def test_invalid_date(self):
        assert validate_date("not-a-date") is not None

    def test_invalid_format(self):
        assert validate_date("03/10/2026") is not None

    def test_empty_string(self):
        assert validate_date("") is not None


class TestValidateName:
    def test_valid_name(self):
        assert validate_name("Buy milk") is None

    def test_allows_slashes(self):
        assert validate_name("Work / Personal") is None

    def test_allows_hyphens_dashes(self):
        assert validate_name("High-priority -- urgent") is None

    def test_allows_unicode(self):
        assert validate_name("Reunión con José") is None

    def test_rejects_control_chars(self):
        assert validate_name("Bad\x00name") is not None
        assert validate_name("Bad\x1fname") is not None
        assert validate_name("Bad\x7fname") is not None

    def test_rejects_empty(self):
        assert validate_name("") is not None
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'omnifocus_cli.validate'`

**Step 3: Write the implementation**

Create `src/omnifocus_cli/validate.py`:

- `validate_body(schema_key: str, body: dict) -> list[dict]`: Look up schema via `get_schema()`, check required fields, unknown fields, type mismatches. Return list of `{"field": ..., "error": ...}` dicts.
- `validate_uuid(value: str) -> str | None`: Return error string if invalid, None if OK. Reject `?`, `#`, `%`, `..`, control chars (< 0x20, 0x7F), whitespace, empty.
- `validate_date(value: str) -> str | None`: Validate ISO 8601 using regex pattern `^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)?)?$` plus `datetime.fromisoformat()` parse check. Return error string or None.
- `validate_name(value: str) -> str | None`: Reject empty, reject control chars (< 0x20, 0x7F). Everything else allowed.

Type checking logic for `validate_body`:
- `"string"` → `isinstance(v, str)`
- `"boolean"` → `isinstance(v, bool)` (not int — Python `bool` is subclass of `int`)
- `"integer"` → `isinstance(v, int) and not isinstance(v, bool)`
- `"array[string]"` → `isinstance(v, list) and all(isinstance(x, str) for x in v)`
- `"object"` → `isinstance(v, dict)`

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_validate.py -v`
Expected: PASS (all ~25 tests)

**Step 5: Commit**

```bash
git add src/omnifocus_cli/validate.py tests/test_validate.py
git commit -m "feat(omnifocus-cli): add input validation (UUIDs, dates, names, body schema)"
```

---

## Task 3: Field Mask Filtering (`fields.py`)

**Files:**
- Create: `src/omnifocus_cli/fields.py`
- Test: `tests/test_fields.py`

**Step 1: Write the failing tests**

```python
# tests/test_fields.py
from omnifocus_cli.fields import apply_field_mask


def test_filters_dict():
    data = {"id": "t-1", "name": "Buy milk", "flagged": True, "note": "long text"}
    result = apply_field_mask(data, ["id", "name", "flagged"])
    assert result == {"id": "t-1", "name": "Buy milk", "flagged": True}


def test_filters_list_of_dicts():
    data = [
        {"id": "t-1", "name": "A", "note": "x"},
        {"id": "t-2", "name": "B", "note": "y"},
    ]
    result = apply_field_mask(data, ["id", "name"])
    assert result == [{"id": "t-1", "name": "A"}, {"id": "t-2", "name": "B"}]


def test_unknown_fields_ignored_gracefully():
    data = {"id": "t-1", "name": "A"}
    result = apply_field_mask(data, ["id", "name", "nonexistent"])
    assert result == {"id": "t-1", "name": "A"}


def test_none_fields_returns_data_unchanged():
    data = {"id": "t-1", "name": "A"}
    result = apply_field_mask(data, None)
    assert result == data


def test_empty_fields_returns_empty_dicts():
    data = {"id": "t-1", "name": "A"}
    result = apply_field_mask(data, [])
    assert result == {}


def test_non_dict_data_returned_as_is():
    assert apply_field_mask("raw string", ["id"]) == "raw string"
    assert apply_field_mask(42, ["id"]) == 42
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_fields.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `src/omnifocus_cli/fields.py`:

```python
def apply_field_mask(data, fields: list[str] | None):
    """Filter output data to only include specified fields.

    If fields is None, return data unchanged.
    Works on dicts and lists of dicts. Non-dict data returned as-is.
    """
    if fields is None:
        return data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in fields} for item in data if isinstance(item, dict)]
    return data
```

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_fields.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/omnifocus_cli/fields.py tests/test_fields.py
git commit -m "feat(omnifocus-cli): add field mask filtering for output"
```

---

## Task 4: Rewrite `formatters.py` with TTY Auto-Detection

**Files:**
- Modify: `src/omnifocus_cli/formatters.py`
- Modify: `tests/test_formatters.py`

**Step 1: Write the failing tests**

Add new tests to `tests/test_formatters.py`:

```python
# Add to existing tests/test_formatters.py
from unittest.mock import patch
from omnifocus_cli.formatters import output_result, output_error, should_use_json


def test_should_use_json_explicit_true():
    assert should_use_json(format_flag="json") is True


def test_should_use_json_explicit_false():
    assert should_use_json(format_flag="text") is False


@patch("sys.stdout.isatty", return_value=False)
def test_should_use_json_auto_non_tty(mock_tty):
    assert should_use_json(format_flag=None) is True


@patch("sys.stdout.isatty", return_value=True)
def test_should_use_json_auto_tty(mock_tty):
    assert should_use_json(format_flag=None) is False
```

**Step 2: Run tests to verify new tests fail**

Run: `poetry run pytest tests/test_formatters.py -v`
Expected: `should_use_json` tests FAIL — function doesn't exist yet

**Step 3: Rewrite `formatters.py`**

Update `src/omnifocus_cli/formatters.py` to add `should_use_json(format_flag: str | None) -> bool`:
- If `format_flag == "json"`: return True
- If `format_flag == "text"`: return False
- If `format_flag is None`: return `not sys.stdout.isatty()`

Keep existing `output_result` and `output_error` unchanged — they already accept `json_output` parameter.

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_formatters.py -v`
Expected: PASS (all old + new tests)

**Step 5: Commit**

```bash
git add src/omnifocus_cli/formatters.py tests/test_formatters.py
git commit -m "feat(omnifocus-cli): add TTY auto-detection to formatters"
```

---

## Task 5: Rewrite `cli.py` — Global Flags + `--body` Primary Path

This is the largest task. It rewrites `cli.py` to add `--body`, `--dry-run`, `--fields`, `--format` global flags and makes `--body` the primary input path. Convenience flags remain as sugar.

**Files:**
- Rewrite: `src/omnifocus_cli/cli.py`
- Rewrite: `tests/test_cli_task.py`
- Create: `tests/test_cli_global.py` (global flag tests)
- Modify: `tests/test_cli_search.py`, `tests/test_cli_project.py`, `tests/test_cli_inbox.py`, `tests/test_cli_tags.py`

### Step 1: Write global flag tests

```python
# tests/test_cli_global.py
import json
from unittest.mock import patch
from click.testing import CliRunner
from omnifocus_cli.cli import cli


@patch("omnifocus_cli.cli.call_omnifocus")
def test_body_flag_creates_task(mock_call):
    mock_call.return_value = {"id": "new-1", "name": "Buy milk"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "Buy milk", "flagged": true}',
    ])
    assert result.exit_code == 0
    mock_call.assert_called_once_with("createTask", {"name": "Buy milk", "flagged": True})


def test_body_flag_validation_rejects_bad_type():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "X", "flagged": "yes"}',
    ])
    assert result.exit_code == 2
    err = json.loads(result.output)
    assert err["error"] == "validation_failed"
    assert any(e["field"] == "flagged" for e in err["errors"])


def test_body_flag_validation_rejects_unknown_field():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "X", "bogus": 1}',
    ])
    assert result.exit_code == 2


def test_body_flag_validation_rejects_missing_required():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"flagged": true}',
    ])
    assert result.exit_code == 2


def test_dry_run_no_execution():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "Test"}',
        "--dry-run",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["dry_run"] is True
    assert parsed["method"] == "createTask"
    assert parsed["validation"] == "passed"


def test_dry_run_with_validation_error():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"flagged": "yes"}',
        "--dry-run",
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert parsed["dry_run"] is True
    assert "validation_errors" in parsed


@patch("omnifocus_cli.cli.call_omnifocus")
def test_fields_flag_filters_output(mock_call):
    mock_call.return_value = [
        {"id": "t-1", "name": "A", "note": "long", "flagged": True},
        {"id": "t-2", "name": "B", "note": "long", "flagged": False},
    ]
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "list",
        "--fields", "id,name",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == [{"id": "t-1", "name": "A"}, {"id": "t-2", "name": "B"}]


@patch("omnifocus_cli.cli.call_omnifocus")
def test_format_json_flag(mock_call):
    mock_call.return_value = {"id": "t-1"}
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", "task", "get", "t-1"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"id": "t-1"}


@patch("omnifocus_cli.cli.call_omnifocus")
def test_body_wins_over_convenience_flags(mock_call):
    """When --body and convenience flags both provided, --body wins."""
    mock_call.return_value = {"id": "new-1", "name": "From body"}
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "From body"}',
        "--name", "From flag",
    ])
    assert result.exit_code == 0
    # --body should win
    mock_call.assert_called_once_with("createTask", {"name": "From body"})


def test_schema_command_shows_method():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "task.create"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "createTask"
    assert "name" in parsed["params"]


def test_schema_list():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    assert "task.create" in result.output
    assert "search" in result.output


def test_invalid_json_body():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{not valid json}',
    ])
    assert result.exit_code == 2
```

### Step 2: Run tests to verify they fail

Run: `poetry run pytest tests/test_cli_global.py -v`
Expected: Various failures — new flags/behavior don't exist yet

### Step 3: Rewrite `cli.py`

Rewrite `src/omnifocus_cli/cli.py` with this structure:

1. **Global options on `cli` group**: `--format`, `--body`, `--dry-run`, `--fields`
2. **`_run` helper** rewritten to:
   - Accept `ctx` (has global flags), `schema_key` (e.g., `"task.create"`), `method`, `params`
   - If `--body` is set: parse JSON, validate against schema, use body params (ignore convenience flags, warn to stderr)
   - If `--body` not set: use convenience-flag params, validate UUID/date/name fields
   - If validation fails: print structured error JSON to stdout, exit 2
   - If `--dry-run`: print preview JSON, exit 0
   - Otherwise: call `call_omnifocus(method, params)`, apply field mask, output result
3. **`schema` command** at top level: `omnifocus-cli schema task.create` or `omnifocus-cli schema --list`
4. **All command groups** kept (task, search, project, inbox, tags) — each command adds both `--body` passthrough and convenience flags

Key design decisions in the rewrite:
- `--body` is on each subcommand (not global) because Click processes options before subcommand
- Actually: `--body`, `--dry-run`, `--fields`, `--format` go on the **cli group** as global options accessed via `ctx.obj`
- Each subcommand still has convenience flags but checks `ctx.obj["body"]` first
- Validation errors are JSON to stdout (not stderr) with exit code 2, so agents parse them
- `--format` accepts `json` or `text`; default is auto-detect via `should_use_json()`

### Step 4: Update existing test files

Update `test_cli_task.py`, `test_cli_search.py`, `test_cli_project.py`, `test_cli_inbox.py`, `test_cli_tags.py` to work with the new CLI structure. The v0 tests patched `omnifocus_cli.cli.call_omnifocus` — this stays the same. Main changes:
- Replace `--json` flag with `--format json` in invocations
- Verify convenience flags still work as before (backward compat)
- All existing behavior preserved — just the flag name changes

### Step 5: Run all tests

Run: `poetry run pytest -v`
Expected: All old tests (updated) + new global tests PASS

### Step 6: Commit

```bash
git add src/omnifocus_cli/cli.py tests/
git commit -m "feat(omnifocus-cli): rewrite CLI with --body, --dry-run, --fields, --format, schema command"
```

---

## Task 6: UUID and Date Validation in `_run` Path

**Files:**
- Modify: `src/omnifocus_cli/cli.py` (enhance `_run`)
- Create: `tests/test_cli_validation.py`

**Step 1: Write the failing tests**

```python
# tests/test_cli_validation.py
import json
from click.testing import CliRunner
from omnifocus_cli.cli import cli


def test_body_uuid_validation_rejects_bad_task_id():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "get",
        "--body", '{"taskId": "abc?123"}',
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert any(e["field"] == "taskId" for e in parsed["errors"])


def test_body_date_validation_rejects_bad_date():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "Test", "dueDate": "next Friday"}',
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert any(e["field"] == "dueDate" for e in parsed["errors"])


def test_body_name_validation_rejects_control_chars():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", json.dumps({"name": "Bad\x00name"}),
    ])
    assert result.exit_code == 2


def test_convenience_flag_uuid_validation():
    runner = CliRunner()
    result = runner.invoke(cli, ["task", "get", "abc?123"])
    assert result.exit_code == 2


def test_convenience_flag_date_validation():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create", "--name", "Test", "--due", "not-a-date",
    ])
    assert result.exit_code == 2
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_cli_validation.py -v`
Expected: FAIL — validation not yet wired into `_run`

**Step 3: Enhance `_run` in `cli.py`**

After body parsing/schema validation passes, add semantic validation:
- For each param whose schema type is `"string"` and name ends in `Id`: call `validate_uuid()`
- For each param whose schema type is `"string"` and name ends in `Date` or `Before` or `After`: call `validate_date()`
- For `name` params: call `validate_name()`
- Collect errors, return them the same way as schema validation errors

Also wire validation into the convenience-flag path (not just `--body`).

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_cli_validation.py tests/test_cli_global.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/omnifocus_cli/cli.py tests/test_cli_validation.py
git commit -m "feat(omnifocus-cli): wire UUID/date/name validation into CLI execution path"
```

---

## Task 7: CONTEXT.md (Agent Guidance Document)

**Files:**
- Create: `omnifocus-cli/CONTEXT.md`

**Step 1: Write `CONTEXT.md`**

```markdown
# OmniFocus CLI — Agent Context

## Quick Start

```bash
# Discover available methods and their parameters
omnifocus-cli schema --list
omnifocus-cli schema task.create

# Create a task (agent path)
omnifocus-cli task create --body '{"name": "Buy milk", "flagged": true}'

# Dry-run before mutating
omnifocus-cli task create --body '{"name": "Buy milk"}' --dry-run

# Limit output tokens
omnifocus-cli task list --fields id,name,flagged
```

## Invariants

- Use `omnifocus-cli schema <method>` to discover parameters before constructing payloads
- Always pass `--fields` on list/search operations to limit token usage
- Use `--dry-run` before any create/update/complete operation
- UUIDs are opaque strings — never construct, modify, or guess them
- Dates must be ISO 8601 format (e.g., `2026-03-10`, `2026-03-10T17:00:00Z`)
- `--body` accepts the full parameter set for any command as JSON
- Prefer `--body` over convenience flags for predictable behavior

## Error Handling

- Exit 0: Success — parse stdout as JSON
- Exit 1: Execution error — osascript/OmniFocus failure, stderr has details
- Exit 2: Validation error — stdout has structured JSON with field-level errors

## Command Groups

| Group | Actions |
|-------|---------|
| task | create, get, update, complete, list |
| search | (single command with filters) |
| project | list, get, create, update, folders |
| inbox | list, process |
| tags | list, create, rename, delete |
| schema | (introspection: `schema <method>` or `schema --list`) |
```

**Step 2: Commit**

```bash
git add CONTEXT.md
git commit -m "docs(omnifocus-cli): add CONTEXT.md agent guidance document"
```

---

## Task 8: Simplify Letta Tools

**Files:**
- Create: `letta_tools/omnifocus_task.py`
- Create: `letta_tools/omnifocus_search.py`
- Create: `letta_tools/omnifocus_project.py`
- Create: `letta_tools/omnifocus_inbox.py`
- Create: `letta_tools/omnifocus_tags.py`
- Test: `tests/test_letta_tools.py`

**Step 1: Write the failing tests**

```python
# tests/test_letta_tools.py
"""Test that Letta tool functions follow Letta conventions and produce correct CLI args."""
import json
import pytest
from unittest.mock import patch, MagicMock

# Import each tool's function directly
import importlib


def _load_tool(module_name: str, func_name: str):
    """Load a tool function from letta_tools/<module>.py."""
    mod = importlib.import_module(f"letta_tools.{module_name}")
    return getattr(mod, func_name)


@patch("subprocess.run")
def test_omnifocus_task_create(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='{"id":"t-1","name":"Buy milk"}', stderr="")
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    result = fn(action="create", params='{"name": "Buy milk"}')
    assert result["status"] == "ok"
    args = mock_run.call_args[0][0]
    assert args[:3] == ["omnifocus-cli", "task", "create"]
    assert "--body" in args


@patch("subprocess.run")
def test_omnifocus_task_with_fields(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[{"id":"t-1","name":"A"}]', stderr="")
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    result = fn(action="list", fields="id,name")
    args = mock_run.call_args[0][0]
    assert "--fields" in args
    assert "id,name" in args


@patch("subprocess.run")
def test_omnifocus_search(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
    fn = _load_tool("omnifocus_search", "omnifocus_search")
    result = fn(params='{"query": "milk"}', fields="id,name")
    assert result["status"] == "ok"
    args = mock_run.call_args[0][0]
    assert args[:2] == ["omnifocus-cli", "search"]


@patch("subprocess.run")
def test_omnifocus_project(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
    fn = _load_tool("omnifocus_project", "omnifocus_project")
    result = fn(action="list", fields="id,name")
    assert result["status"] == "ok"


@patch("subprocess.run")
def test_tool_returns_error_on_nonzero_exit(mock_run):
    mock_run.return_value = MagicMock(returncode=2, stdout="", stderr='{"error":"validation_failed"}')
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    result = fn(action="create", params='{"flagged": "yes"}')
    assert result["status"] == "error"


def test_tool_has_correct_docstring():
    fn = _load_tool("omnifocus_task", "omnifocus_task")
    assert "Args:" in fn.__doc__
    assert "action" in fn.__doc__
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_letta_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'letta_tools'`

**Step 3: Create the 5 Letta tool files**

Each follows the Letta tool pattern (all imports inside function, try-except wrapper, Args docstring):

`letta_tools/omnifocus_task.py`:
```python
from typing import Dict, Any, Optional

def omnifocus_task(action: str, params: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
    """
    Manage OmniFocus tasks. Run omnifocus-cli schema task.<action> to discover params.

    Args:
        action: One of: create, get, update, complete, list (REQUIRED)
        params: JSON string with parameters. Use schema to discover fields.
        fields: Comma-separated output fields to return (limits token usage)

    Returns:
        Dictionary with status and result from OmniFocus.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["omnifocus-cli", "task", action]
        if params:
            cli_args.extend(["--body", params])
        if fields:
            cli_args.extend(["--fields", fields])
        result = subprocess.run(cli_args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"status": "error", "error_message": result.stderr.strip() or result.stdout.strip()}
        return {"status": "ok", "result": json.loads(result.stdout)}
    except Exception as e:
        return {"status": "error", "error_message": f"{str(e)}\n{traceback.format_exc()}"}
```

Same pattern for `omnifocus_search.py` (no `action` param — search is a single command), `omnifocus_project.py`, `omnifocus_inbox.py`, `omnifocus_tags.py`.

Also create `letta_tools/__init__.py` (empty).

**Step 4: Update `pyproject.toml`**

Add `letta_tools` as a package so tests can import it:
```toml
packages = [{include = "omnifocus_cli", from = "src"}, {include = "letta_tools"}]
```

**Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/test_letta_tools.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add letta_tools/ tests/test_letta_tools.py pyproject.toml
git commit -m "feat(omnifocus-cli): add 5 simplified Letta tool wrappers (~15 lines each)"
```

---

## Task 9: Integration Smoke Tests

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Update integration tests**

Update the existing integration tests to exercise the agent-first path:

```python
# Add to tests/test_integration.py
import json
import pytest
from click.testing import CliRunner
from omnifocus_cli.cli import cli

pytestmark = pytest.mark.integration


def test_schema_list_returns_all_methods():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    assert "task.create" in result.output


def test_schema_task_create_returns_params():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "task.create"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "createTask"


def test_dry_run_task_create():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"name": "Integration test"}',
        "--dry-run",
    ])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["dry_run"] is True
    assert parsed["validation"] == "passed"


def test_validation_error_returns_structured_json():
    runner = CliRunner()
    result = runner.invoke(cli, [
        "task", "create",
        "--body", '{"flagged": "not_bool"}',
    ])
    assert result.exit_code == 2
    parsed = json.loads(result.output)
    assert parsed["error"] == "validation_failed"


# Keep existing integration tests that hit real OmniFocus (tagged @integration)
# but update their CLI invocations to use --format json instead of --json
```

**Step 2: Run non-integration tests**

Run: `poetry run pytest -v -m "not integration"`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test(omnifocus-cli): update integration tests for agent-first CLI"
```

---

## Task 10: Full Test Suite Pass + Final Cleanup

**Files:**
- Various minor fixes

**Step 1: Run full test suite**

Run: `poetry run pytest -v -m "not integration"`
Expected: ALL PASS

**Step 2: Run linting (if ruff configured)**

Run: `poetry run ruff check src/ tests/ letta_tools/ 2>/dev/null || echo "ruff not configured, skip"`

**Step 3: Verify CLI help text**

Run: `poetry run omnifocus-cli --help`
Run: `poetry run omnifocus-cli task create --help`
Run: `poetry run omnifocus-cli schema --help`

**Step 4: Fix any issues found in steps 1-3**

**Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "chore(omnifocus-cli): cleanup and fix lint issues"
```

---

## Summary

| Task | Module | Tests | Description |
|------|--------|-------|-------------|
| 1 | `schema.py` | ~5 | Static schema registry for 17 plugin methods |
| 2 | `validate.py` | ~25 | Input hardening (UUID, date, name, body) |
| 3 | `fields.py` | ~6 | Field mask filtering |
| 4 | `formatters.py` | ~4 new | TTY auto-detection |
| 5 | `cli.py` rewrite | ~13 | Global flags, --body, --dry-run, schema command |
| 6 | `cli.py` enhance | ~5 | Wire validation into execution path |
| 7 | `CONTEXT.md` | — | Agent guidance document |
| 8 | `letta_tools/` | ~6 | 5 simplified Letta tool wrappers |
| 9 | `test_integration.py` | ~4 | Integration smoke tests for agent path |
| 10 | cleanup | — | Full suite pass, lint, help text |

**Total new tests:** ~63 (on top of 48 existing, some of which get updated)
**Total new/modified source files:** 8
**Estimated commits:** 10
