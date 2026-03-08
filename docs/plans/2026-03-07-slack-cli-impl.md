# Slack CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI wrapping the Slack Web API for agent consumption, following the omnifocus-cli and gws patterns.

**Architecture:** Click-based CLI with `slack <resource> <method>` command pattern, `--body` JSON-first agent path, `+helper` convenience commands, structured JSON output, credential chain auth, input validation, and schema introspection.

**Tech Stack:** Python 3.11+, Click 8.x, slack_sdk, Poetry, pytest

**Reference:** Design doc at `docs/plans/2026-03-07-slack-cli-design.md`. Follow omnifocus-cli patterns exactly (see `.worktrees/omnifocus-cli/omnifocus-cli/`).

---

### Task 1: Project Scaffolding

**Files:**
- Create: `slack-cli/pyproject.toml`
- Create: `slack-cli/src/slack_cli/__init__.py`
- Create: `slack-cli/src/slack_cli/cli.py`
- Create: `slack-cli/tests/__init__.py`
- Create: `slack-cli/tests/test_cli.py`

**Step 1: Create project directory and pyproject.toml**

```bash
mkdir -p slack-cli/src/slack_cli slack-cli/tests slack-cli/letta_tools
```

```toml
# slack-cli/pyproject.toml
[tool.poetry]
name = "slack-cli"
version = "0.1.0"
description = "Agent-first CLI for the Slack Web API"
authors = ["ai-PA"]
packages = [{include = "slack_cli", from = "src"}, {include = "letta_tools"}]

[tool.poetry.dependencies]
python = "^3.11"
click = "^8.1"
slack-sdk = "^3.27"
pyyaml = "^6.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^5.0"

[tool.poetry.scripts]
slack = "slack_cli.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: requires Slack API access",
]

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**Step 2: Create minimal CLI entry point**

```python
# slack-cli/src/slack_cli/__init__.py
"""Slack CLI - Agent-first CLI for the Slack Web API."""
```

```python
# slack-cli/src/slack_cli/cli.py
"""Slack CLI entry point."""
import sys
import click


@click.group()
@click.option("--format", "format_flag", type=click.Choice(["json", "text", "csv", "yaml"]), default=None,
              help="Output format (default: json)")
@click.option("--body", "body_json", default=None, help="Raw JSON input (agent-first path)")
@click.option("--dry-run", is_flag=True, default=False, help="Validate + preview, no execution")
@click.option("--fields", default=None, help="Comma-separated output fields")
@click.option("--page-all", is_flag=True, default=False, help="Auto-paginate through all results")
@click.option("--page-limit", default=10, type=int, help="Max pages when paginating (default: 10)")
@click.option("--as-user", is_flag=True, default=False, help="Force user token (xoxp)")
@click.option("--as-bot", is_flag=True, default=False, help="Force bot token (xoxb)")
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx, format_flag, body_json, dry_run, fields, page_all, page_limit, as_user, as_bot):
    """Slack CLI - manage messages, channels, users, and more."""
    ctx.ensure_object(dict)
    ctx.obj["format"] = format_flag
    ctx.obj["body"] = body_json
    ctx.obj["dry_run"] = dry_run
    ctx.obj["fields"] = fields.split(",") if fields else None
    ctx.obj["page_all"] = page_all
    ctx.obj["page_limit"] = page_limit
    ctx.obj["as_user"] = as_user
    ctx.obj["as_bot"] = as_bot
```

**Step 3: Write test verifying CLI loads**

```python
# slack-cli/tests/__init__.py
```

```python
# slack-cli/tests/test_cli.py
from click.testing import CliRunner
from slack_cli.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Slack CLI" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
```

**Step 4: Install and run tests**

```bash
cd slack-cli && poetry install && poetry run pytest tests/test_cli.py -v
```
Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add slack-cli/
git commit -m "feat: scaffold slack-cli project with Click entry point"
```

---

### Task 2: Error Module

**Files:**
- Create: `slack-cli/src/slack_cli/error.py`
- Create: `slack-cli/tests/test_error.py`

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_error.py
import json
from slack_cli.error import format_error, SlackCliError

EXIT_VALIDATION = 2
EXIT_EXECUTION = 1


def test_format_error_returns_json():
    result = format_error("channel_not_found", "Channel 'C999' does not exist")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert parsed["error"] == "channel_not_found"
    assert parsed["detail"] == "Channel 'C999' does not exist"


def test_format_error_without_detail():
    result = format_error("invalid_auth")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_auth"
    assert "detail" not in parsed


def test_slack_cli_error_has_exit_code():
    err = SlackCliError("channel_not_found", "Not found", exit_code=EXIT_VALIDATION)
    assert err.exit_code == EXIT_VALIDATION
    assert err.error == "channel_not_found"


def test_slack_cli_error_json():
    err = SlackCliError("rate_limited", "Too many requests", exit_code=EXIT_EXECUTION, hint="Wait and retry")
    output = err.to_json()
    parsed = json.loads(output)
    assert parsed["ok"] is False
    assert parsed["error"] == "rate_limited"
    assert err.hint == "Wait and retry"
```

**Step 2: Run tests to verify they fail**

```bash
cd slack-cli && poetry run pytest tests/test_error.py -v
```
Expected: FAIL (module not found)

**Step 3: Implement error module**

```python
# slack-cli/src/slack_cli/error.py
"""Structured error output for Slack CLI."""
import json
import sys

EXIT_SUCCESS = 0
EXIT_EXECUTION = 1
EXIT_VALIDATION = 2


def format_error(error: str, detail: str | None = None) -> str:
    """Format an error as JSON string for stdout."""
    result = {"ok": False, "error": error}
    if detail is not None:
        result["detail"] = detail
    return json.dumps(result, indent=2)


def print_error(error: str, detail: str | None = None, hint: str | None = None,
                exit_code: int = EXIT_EXECUTION) -> None:
    """Print structured error to stdout (JSON) and optional hint to stderr, then exit."""
    click_echo = None
    try:
        import click
        click_echo = click.echo
    except ImportError:
        pass

    output = format_error(error, detail)
    print(output)

    if hint:
        msg = f"Hint: {hint}"
        if click_echo:
            click_echo(msg, err=True)
        else:
            print(msg, file=sys.stderr)

    sys.exit(exit_code)


class SlackCliError(Exception):
    """Structured error with exit code and optional hint."""

    def __init__(self, error: str, detail: str | None = None,
                 exit_code: int = EXIT_EXECUTION, hint: str | None = None):
        self.error = error
        self.detail = detail
        self.exit_code = exit_code
        self.hint = hint
        super().__init__(detail or error)

    def to_json(self) -> str:
        return format_error(self.error, self.detail)
```

**Step 4: Run tests to verify they pass**

```bash
cd slack-cli && poetry run pytest tests/test_error.py -v
```
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add slack-cli/src/slack_cli/error.py slack-cli/tests/test_error.py
git commit -m "feat: add structured error module"
```

---

### Task 3: Formatter Module

**Files:**
- Create: `slack-cli/src/slack_cli/formatter.py`
- Create: `slack-cli/tests/test_formatter.py`

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_formatter.py
import json
import sys
from unittest.mock import patch
from slack_cli.formatter import format_output, apply_field_mask, should_use_json


def test_should_use_json_default_tty():
    with patch.object(sys.stdout, "isatty", return_value=True):
        assert should_use_json(None) is False


def test_should_use_json_default_pipe():
    with patch.object(sys.stdout, "isatty", return_value=False):
        assert should_use_json(None) is True


def test_should_use_json_explicit():
    assert should_use_json("json") is True
    assert should_use_json("text") is False


def test_format_output_json():
    data = {"id": "C123", "name": "general"}
    result = format_output(data, "json")
    parsed = json.loads(result)
    assert parsed == data


def test_format_output_json_compact_when_not_tty():
    data = {"id": "C123"}
    with patch.object(sys.stdout, "isatty", return_value=False):
        result = format_output(data, "json")
    assert "\n" not in result


def test_apply_field_mask_dict():
    data = {"id": "C123", "name": "general", "topic": "stuff"}
    result = apply_field_mask(data, ["id", "name"])
    assert result == {"id": "C123", "name": "general"}


def test_apply_field_mask_list():
    data = [{"id": "C1", "name": "a", "extra": 1}, {"id": "C2", "name": "b", "extra": 2}]
    result = apply_field_mask(data, ["id", "name"])
    assert result == [{"id": "C1", "name": "a"}, {"id": "C2", "name": "b"}]


def test_apply_field_mask_none():
    data = {"id": "C123", "name": "general"}
    assert apply_field_mask(data, None) == data


def test_format_output_csv_list():
    data = [{"id": "C1", "name": "a"}, {"id": "C2", "name": "b"}]
    result = format_output(data, "csv")
    lines = result.strip().split("\n")
    assert lines[0] == "id,name"
    assert lines[1] == "C1,a"


def test_format_output_yaml():
    data = {"id": "C123", "name": "general"}
    result = format_output(data, "yaml")
    assert "id:" in result
    assert "C123" in result
```

**Step 2: Run tests to verify they fail**

```bash
cd slack-cli && poetry run pytest tests/test_formatter.py -v
```

**Step 3: Implement formatter**

```python
# slack-cli/src/slack_cli/formatter.py
"""Output formatting for Slack CLI."""
import csv
import io
import json
import sys

import yaml


def should_use_json(format_flag: str | None) -> bool:
    """Determine if output should be JSON. Default: JSON when piped, text when TTY."""
    if format_flag == "json":
        return True
    if format_flag in ("text", "csv", "yaml"):
        return False
    return not sys.stdout.isatty()


def apply_field_mask(data, fields: list[str] | None):
    """Filter dict or list of dicts to only include specified fields."""
    if fields is None:
        return data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [
            {k: v for k, v in item.items() if k in fields}
            for item in data
            if isinstance(item, dict)
        ]
    return data


def format_output(data, format_flag: str | None) -> str:
    """Format data according to the requested format."""
    fmt = format_flag or ("json" if not sys.stdout.isatty() else "json")

    if fmt == "json":
        if sys.stdout.isatty():
            return json.dumps(data, indent=2, ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)

    if fmt == "yaml":
        return yaml.dump(data, default_flow_style=False, allow_unicode=True).rstrip()

    if fmt == "csv":
        return _format_csv(data)

    if fmt == "text":
        return _format_text(data)

    return json.dumps(data, indent=2, ensure_ascii=False)


def _format_csv(data) -> str:
    """Format data as CSV."""
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return ""
    output = io.StringIO()
    keys = list(data[0].keys())
    writer = csv.DictWriter(output, fieldnames=keys)
    writer.writeheader()
    for row in data:
        writer.writerow({k: row.get(k, "") for k in keys})
    return output.getvalue().rstrip()


def _format_text(data) -> str:
    """Format data as human-readable text."""
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if isinstance(data, list):
        return "\n---\n".join(_format_text(item) for item in data)
    return str(data)


def output(data, format_flag: str | None = None, fields: list[str] | None = None) -> None:
    """Apply field mask, format, and print to stdout."""
    masked = apply_field_mask(data, fields)
    print(format_output(masked, format_flag))
```

**Step 4: Run tests**

```bash
cd slack-cli && poetry run pytest tests/test_formatter.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add slack-cli/src/slack_cli/formatter.py slack-cli/tests/test_formatter.py
git commit -m "feat: add output formatter with JSON/CSV/YAML/text support"
```

---

### Task 4: Input Validation Module

**Files:**
- Create: `slack-cli/src/slack_cli/validate.py`
- Create: `slack-cli/tests/test_validate.py`

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_validate.py
from slack_cli.validate import validate_slack_id, validate_timestamp, validate_body, sanitize_value

VALID_CHANNEL_IDS = ["C0123ABCDEF", "C012345678", "C0123456789AB"]
VALID_USER_IDS = ["U0123ABCDEF", "U012345678"]
VALID_DM_IDS = ["D0123ABCDEF"]
VALID_GROUP_IDS = ["G0123ABCDEF"]
VALID_TIMESTAMPS = ["1234567890.123456", "1709000000.000001"]


def test_valid_channel_ids():
    for cid in VALID_CHANNEL_IDS:
        assert validate_slack_id(cid) is None, f"Should accept {cid}"


def test_valid_user_ids():
    for uid in VALID_USER_IDS:
        assert validate_slack_id(uid) is None, f"Should accept {uid}"


def test_reject_query_params_in_id():
    assert validate_slack_id("C0123ABCD?foo=bar") is not None


def test_reject_fragment_in_id():
    assert validate_slack_id("U0123ABCD#section") is not None


def test_reject_encoded_chars_in_id():
    assert validate_slack_id("C%200123ABCD") is not None


def test_reject_control_chars_in_id():
    assert validate_slack_id("C0123\x00ABCD") is not None


def test_reject_empty_id():
    assert validate_slack_id("") is not None


def test_reject_bad_prefix():
    assert validate_slack_id("X0123ABCDEF") is not None


def test_valid_timestamps():
    for ts in VALID_TIMESTAMPS:
        assert validate_timestamp(ts) is None, f"Should accept {ts}"


def test_reject_bad_timestamp():
    assert validate_timestamp("not-a-timestamp") is not None
    assert validate_timestamp("1234567890") is not None
    assert validate_timestamp("") is not None


def test_sanitize_value_strips_control():
    assert sanitize_value("hello\x00world") is not None


def test_sanitize_value_allows_newlines():
    assert sanitize_value("hello\nworld", allow_newlines=True) is None


def test_validate_body_missing_required():
    schema_params = {
        "channel": {"type": "string", "required": True},
        "text": {"type": "string", "required": True},
    }
    errors = validate_body({"channel": "C123"}, schema_params)
    assert len(errors) == 1
    assert errors[0]["field"] == "text"


def test_validate_body_unknown_field():
    schema_params = {
        "channel": {"type": "string", "required": True},
    }
    errors = validate_body({"channel": "C123", "bogus": "val"}, schema_params)
    assert len(errors) == 1
    assert "unknown" in errors[0]["error"].lower()
```

**Step 2: Run tests to verify they fail**

```bash
cd slack-cli && poetry run pytest tests/test_validate.py -v
```

**Step 3: Implement validation**

```python
# slack-cli/src/slack_cli/validate.py
"""Input validation for Slack CLI."""
import re

# Slack ID prefixes: C=channel, U=user, D=DM, G=group, W=workspace, T=team, B=bot, F=file, E=enterprise
VALID_ID_PREFIXES = {"C", "U", "D", "G", "W", "T", "B", "F", "E"}
SLACK_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{8,12}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{10}\.\d{6}$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
FORBIDDEN_ID_CHARS = re.compile(r"[?#%]")


def validate_slack_id(value: str) -> str | None:
    """Validate a Slack ID. Returns error message or None if valid."""
    if not value:
        return "empty ID"
    if FORBIDDEN_ID_CHARS.search(value):
        return f"ID contains forbidden characters: {value}"
    if CONTROL_CHAR_PATTERN.search(value):
        return f"ID contains control characters: {value!r}"
    if value[0] not in VALID_ID_PREFIXES:
        return f"unknown ID prefix '{value[0]}' (expected one of {sorted(VALID_ID_PREFIXES)})"
    if not SLACK_ID_PATTERN.match(value):
        return f"malformed Slack ID: {value}"
    return None


def validate_timestamp(value: str) -> str | None:
    """Validate a Slack timestamp. Returns error message or None if valid."""
    if not value:
        return "empty timestamp"
    if not TIMESTAMP_PATTERN.match(value):
        return f"invalid timestamp format: {value} (expected NNNNNNNNNN.NNNNNN)"
    return None


def sanitize_value(value: str, allow_newlines: bool = False) -> str | None:
    """Check a string value for control characters. Returns error or None if clean."""
    pattern = CONTROL_CHAR_PATTERN if not allow_newlines else re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    if pattern.search(value):
        return f"value contains control characters"
    return None


def validate_body(body: dict, schema_params: dict) -> list[dict]:
    """Validate a --body JSON dict against schema parameters.

    Returns list of {"field": ..., "error": ...} dicts. Empty list means valid.
    """
    errors = []

    # Check required fields
    for name, spec in schema_params.items():
        if spec.get("required") and name not in body:
            errors.append({"field": name, "error": f"required field missing"})

    # Check unknown fields
    for name in body:
        if name not in schema_params:
            errors.append({"field": name, "error": f"unknown field"})

    return errors


def validate_semantic(body: dict, schema_params: dict) -> list[dict]:
    """Run semantic validation on field values based on naming conventions.

    Fields ending with _id or named 'channel'/'user' get Slack ID validation.
    Fields ending with _ts get timestamp validation.
    """
    errors = []
    for name, value in body.items():
        if not isinstance(value, str):
            continue
        spec = schema_params.get(name, {})
        field_type = spec.get("semantic_type", "")

        is_id_field = (
            field_type == "slack_id"
            or name in ("channel", "user")
            or name.endswith("_id")
        )
        is_ts_field = field_type == "timestamp" or name.endswith("_ts")

        if is_id_field:
            err = validate_slack_id(value)
            if err:
                errors.append({"field": name, "error": err})
        elif is_ts_field:
            err = validate_timestamp(value)
            if err:
                errors.append({"field": name, "error": err})

    return errors
```

**Step 4: Run tests**

```bash
cd slack-cli && poetry run pytest tests/test_validate.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add slack-cli/src/slack_cli/validate.py slack-cli/tests/test_validate.py
git commit -m "feat: add input validation with Slack ID and timestamp checks"
```

---

### Task 5: Schema Registry

**Files:**
- Create: `slack-cli/src/slack_cli/schema.py`
- Create: `slack-cli/tests/test_schema.py`

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_schema.py
from slack_cli.schema import get_schema, list_schemas, list_groups


def test_get_schema_exists():
    schema = get_schema("chat.postMessage")
    assert schema is not None
    assert schema["method"] == "chat.postMessage"
    assert "channel" in schema["params"]


def test_get_schema_not_found():
    assert get_schema("bogus.method") is None


def test_list_schemas():
    schemas = list_schemas()
    assert len(schemas) > 10
    assert "chat.postMessage" in schemas
    assert "conversations.list" in schemas


def test_list_groups():
    groups = list_groups()
    assert "chat" in groups
    assert "conversations" in groups
    assert "users" in groups


def test_schema_has_token_type():
    schema = get_schema("chat.postMessage")
    assert schema["token_type"] in ("bot", "user", "either")


def test_search_requires_user_token():
    schema = get_schema("search.messages")
    assert schema["token_type"] == "user"
```

**Step 2: Run tests to verify they fail**

```bash
cd slack-cli && poetry run pytest tests/test_schema.py -v
```

**Step 3: Implement schema registry**

Create `slack-cli/src/slack_cli/schema.py` with a `SCHEMAS` dict containing all core API methods. Each entry has:
- `method`: Slack API method name (e.g., `"chat.postMessage"`)
- `description`: One-line description
- `token_type`: `"bot"`, `"user"`, or `"either"`
- `params`: dict of `{name: {type, required, description, semantic_type?}}`
- `scopes`: list of required OAuth scopes

Cover these groups from the design doc:
- `conversations`: list, info, history, create, archive, unarchive, invite, kick, join, leave, open, close, members, rename, setPurpose, setTopic
- `chat`: postMessage, update, delete, postEphemeral, scheduleMessage, unfurl
- `users`: list, info, lookupByEmail, getPresence, setPresence
- `reactions`: add, remove, get, list
- `files`: list, upload, info, delete, completeUploadExternal
- `search`: messages, files
- `pins`: add, remove, list
- `bookmarks`: add, edit, remove, list
- `reminders`: add, complete, delete, info, list
- `team`: info, accessLogs, billableInfo

**Note:** This file will be ~500-800 lines. The schema is the source of truth for validation, introspection, and auto-generated help. Scaffold from the [Slack Web API reference](https://api.slack.com/methods). Include at minimum 3-5 params per method (the most commonly used ones).

Helper functions:

```python
def get_schema(method: str) -> dict | None:
    return SCHEMAS.get(method)

def list_schemas() -> list[str]:
    return sorted(SCHEMAS.keys())

def list_groups() -> list[str]:
    return sorted({key.split(".")[0] for key in SCHEMAS})

def get_group_methods(group: str) -> list[str]:
    return sorted(k for k in SCHEMAS if k.startswith(f"{group}."))
```

**Step 4: Run tests**

```bash
cd slack-cli && poetry run pytest tests/test_schema.py -v
```

**Step 5: Commit**

```bash
git add slack-cli/src/slack_cli/schema.py slack-cli/tests/test_schema.py
git commit -m "feat: add schema registry with core Slack API methods"
```

---

### Task 6: Auth Module (Credential Chain)

**Files:**
- Create: `slack-cli/src/slack_cli/auth.py`
- Create: `slack-cli/tests/test_auth.py`

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_auth.py
import os
import json
import tempfile
from unittest.mock import patch
from slack_cli.auth import resolve_token, TOKEN_TYPE_BOT, TOKEN_TYPE_USER


def test_resolve_bot_token_from_env():
    with patch.dict(os.environ, {"SLACK_CLI_TOKEN": "xoxb-test-token"}, clear=False):
        token = resolve_token(TOKEN_TYPE_BOT)
        assert token == "xoxb-test-token"


def test_resolve_user_token_from_env():
    with patch.dict(os.environ, {"SLACK_CLI_USER_TOKEN": "xoxp-test-token"}, clear=False):
        token = resolve_token(TOKEN_TYPE_USER)
        assert token == "xoxp-test-token"


def test_resolve_fallback_bot_token():
    env = {"SLACK_BOT_TOKEN": "xoxb-fallback"}
    with patch.dict(os.environ, env, clear=True):
        token = resolve_token(TOKEN_TYPE_BOT)
        assert token == "xoxb-fallback"


def test_resolve_fallback_user_token():
    env = {"SLACK_MCP_XOXP_TOKEN": "xoxp-fallback"}
    with patch.dict(os.environ, env, clear=True):
        token = resolve_token(TOKEN_TYPE_USER)
        assert token == "xoxp-fallback"


def test_resolve_from_config_file():
    config = {"bot_token": "xoxb-from-file", "user_token": "xoxp-from-file"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        with patch.dict(os.environ, {}, clear=True):
            with patch("slack_cli.auth.CONFIG_PATH", f.name):
                token = resolve_token(TOKEN_TYPE_BOT)
                assert token == "xoxb-from-file"
    os.unlink(f.name)


def test_resolve_either_prefers_bot():
    with patch.dict(os.environ, {
        "SLACK_CLI_TOKEN": "xoxb-bot",
        "SLACK_CLI_USER_TOKEN": "xoxp-user",
    }, clear=False):
        token = resolve_token("either")
        assert token == "xoxb-bot"


def test_resolve_returns_none_when_missing():
    with patch.dict(os.environ, {}, clear=True):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent/path"):
            token = resolve_token(TOKEN_TYPE_BOT)
            assert token is None
```

**Step 2: Implement auth module**

```python
# slack-cli/src/slack_cli/auth.py
"""Credential chain for Slack CLI."""
import json
import os
from pathlib import Path

TOKEN_TYPE_BOT = "bot"
TOKEN_TYPE_USER = "user"
TOKEN_TYPE_EITHER = "either"

CONFIG_PATH = os.path.expanduser("~/.config/slack-cli/credentials.json")


def _load_config() -> dict:
    """Load credentials from config file if it exists."""
    path = Path(CONFIG_PATH)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def resolve_token(token_type: str, force_user: bool = False, force_bot: bool = False) -> str | None:
    """Resolve a Slack token using the credential chain.

    Priority:
    1. SLACK_CLI_TOKEN / SLACK_CLI_USER_TOKEN env vars
    2. ~/.config/slack-cli/credentials.json
    3. SLACK_BOT_TOKEN / SLACK_MCP_XOXP_TOKEN env vars (fallback)
    """
    if force_user:
        token_type = TOKEN_TYPE_USER
    elif force_bot:
        token_type = TOKEN_TYPE_BOT

    if token_type == TOKEN_TYPE_EITHER:
        return resolve_token(TOKEN_TYPE_BOT) or resolve_token(TOKEN_TYPE_USER)

    if token_type == TOKEN_TYPE_BOT:
        sources = [
            ("env", "SLACK_CLI_TOKEN"),
            ("config", "bot_token"),
            ("env", "SLACK_BOT_TOKEN"),
        ]
    else:  # user
        sources = [
            ("env", "SLACK_CLI_USER_TOKEN"),
            ("config", "user_token"),
            ("env", "SLACK_MCP_XOXP_TOKEN"),
        ]

    config = _load_config()

    for source_type, key in sources:
        if source_type == "env":
            val = os.environ.get(key)
        else:
            val = config.get(key)
        if val:
            return val

    return None


def save_credentials(bot_token: str | None = None, user_token: str | None = None) -> None:
    """Save tokens to config file."""
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_config()
    if bot_token:
        existing["bot_token"] = bot_token
    if user_token:
        existing["user_token"] = user_token

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    path.chmod(0o600)
```

**Step 3: Run tests**

```bash
cd slack-cli && poetry run pytest tests/test_auth.py -v
```

**Step 4: Commit**

```bash
git add slack-cli/src/slack_cli/auth.py slack-cli/tests/test_auth.py
git commit -m "feat: add credential chain auth module"
```

---

### Task 7: Client Module (Slack SDK Bridge)

**Files:**
- Create: `slack-cli/src/slack_cli/client.py`
- Create: `slack-cli/tests/test_client.py`

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_client.py
from unittest.mock import patch, MagicMock
from slack_cli.client import SlackClient
from slack_cli.error import SlackCliError


def test_client_resolves_method():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = MagicMock()
    client._user_client = None
    # chat.postMessage -> client._bot_client.api_call("chat.postMessage", ...)
    mock_response = MagicMock()
    mock_response.data = {"ok": True, "ts": "123.456"}
    mock_response.__getitem__ = lambda self, key: self.data[key]
    client._bot_client.api_call.return_value = mock_response
    result = client.call("chat.postMessage", {"channel": "C123", "text": "hi"})
    client._bot_client.api_call.assert_called_once_with("chat.postMessage", params={"channel": "C123", "text": "hi"})
    assert result["ok"] is True


def test_client_auto_selects_user_token():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = MagicMock()
    client._user_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = {"ok": True, "messages": []}
    mock_response.__getitem__ = lambda self, key: self.data[key]
    client._user_client.api_call.return_value = mock_response
    # search.messages requires user token
    result = client.call("search.messages", {"query": "test"}, token_type="user")
    client._user_client.api_call.assert_called_once()


def test_client_raises_on_no_token():
    client = SlackClient.__new__(SlackClient)
    client._bot_client = None
    client._user_client = None
    try:
        client.call("chat.postMessage", {"channel": "C123"}, token_type="bot")
        assert False, "Should have raised"
    except SlackCliError as e:
        assert e.error == "no_token"
```

**Step 2: Implement client**

```python
# slack-cli/src/slack_cli/client.py
"""Slack SDK client wrapper with credential chain and auto token selection."""
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from slack_cli.auth import resolve_token, TOKEN_TYPE_BOT, TOKEN_TYPE_USER, TOKEN_TYPE_EITHER
from slack_cli.error import SlackCliError, EXIT_EXECUTION
from slack_cli.schema import get_schema


class SlackClient:
    """Wrapper around slack_sdk.WebClient with credential chain."""

    def __init__(self, force_user: bool = False, force_bot: bool = False):
        bot_token = resolve_token(TOKEN_TYPE_BOT)
        user_token = resolve_token(TOKEN_TYPE_USER)
        self._bot_client = WebClient(token=bot_token) if bot_token else None
        self._user_client = WebClient(token=user_token) if user_token else None
        self._force_user = force_user
        self._force_bot = force_bot

    def _get_client(self, token_type: str) -> WebClient:
        """Get the appropriate WebClient for the token type."""
        if self._force_user:
            token_type = "user"
        elif self._force_bot:
            token_type = "bot"

        if token_type == TOKEN_TYPE_EITHER:
            client = self._bot_client or self._user_client
        elif token_type == TOKEN_TYPE_USER:
            client = self._user_client
        else:
            client = self._bot_client

        if client is None:
            hint = "Set SLACK_CLI_TOKEN (bot) or SLACK_CLI_USER_TOKEN (user) env var"
            if token_type == TOKEN_TYPE_USER:
                hint = "Set SLACK_CLI_USER_TOKEN env var (this method requires a user token)"
            raise SlackCliError("no_token", f"No {token_type} token available", hint=hint)

        return client

    def call(self, method: str, params: dict | None = None,
             token_type: str | None = None) -> dict:
        """Call a Slack API method.

        Args:
            method: Slack API method name (e.g., "chat.postMessage")
            params: API parameters
            token_type: Override token type. If None, auto-detect from schema.
        """
        if token_type is None:
            schema = get_schema(method)
            token_type = schema["token_type"] if schema else TOKEN_TYPE_EITHER

        client = self._get_client(token_type)

        try:
            response = client.api_call(method, params=params or {})
            return dict(response.data) if hasattr(response, 'data') else response
        except SlackApiError as e:
            raise SlackCliError(
                e.response.get("error", "api_error"),
                str(e),
                exit_code=EXIT_EXECUTION,
                hint=f"Slack API returned error for {method}",
            )

    def paginate(self, method: str, params: dict | None = None,
                 token_type: str | None = None, max_pages: int = 10) -> list[dict]:
        """Call a Slack API method with cursor-based pagination."""
        params = dict(params or {})
        all_pages = []

        for _ in range(max_pages):
            result = self.call(method, params, token_type)
            all_pages.append(result)

            cursor = result.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            params["cursor"] = cursor

        return all_pages
```

**Step 3: Run tests**

```bash
cd slack-cli && poetry run pytest tests/test_client.py -v
```

**Step 4: Commit**

```bash
git add slack-cli/src/slack_cli/client.py slack-cli/tests/test_client.py
git commit -m "feat: add Slack SDK client wrapper with auto token selection"
```

---

### Task 8: Core _run() Helper and First Command Group (conversations)

**Files:**
- Modify: `slack-cli/src/slack_cli/cli.py`
- Create: `slack-cli/src/slack_cli/commands/__init__.py`
- Create: `slack-cli/src/slack_cli/commands/conversations.py`
- Create: `slack-cli/tests/test_conversations.py`

This is the most critical task — it establishes the `_run()` pattern that all subsequent command groups follow.

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_conversations.py
import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from slack_cli.cli import cli


def _mock_client():
    """Create a mock SlackClient."""
    mock = MagicMock()
    mock.call.return_value = {
        "ok": True,
        "channels": [{"id": "C123", "name": "general"}],
    }
    return mock


@patch("slack_cli.cli.SlackClient")
def test_conversations_list_with_body(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["--body", '{"limit": 5}', "conversations", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["ok"] is True


@patch("slack_cli.cli.SlackClient")
def test_conversations_list_with_flags(mock_cls):
    mock_cls.return_value = _mock_client()
    runner = CliRunner()
    result = runner.invoke(cli, ["conversations", "list", "--limit", "5"])
    assert result.exit_code == 0


@patch("slack_cli.cli.SlackClient")
def test_conversations_list_dry_run(mock_cls):
    runner = CliRunner()
    result = runner.invoke(cli, ["--dry-run", "--body", '{"limit": 5}', "conversations", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "conversations.list"
    assert parsed["validation"] == "passed"
    mock_cls.return_value.call.assert_not_called()


def test_conversations_list_dry_run_validation_error():
    runner = CliRunner()
    result = runner.invoke(cli, ["--dry-run", "--body", '{"bogus_field": 1}', "conversations", "list"])
    assert result.exit_code == 2


@patch("slack_cli.cli.SlackClient")
def test_conversations_list_fields(mock_cls):
    client = _mock_client()
    client.call.return_value = {
        "ok": True,
        "channels": [{"id": "C123", "name": "general", "topic": "stuff"}],
    }
    mock_cls.return_value = client
    runner = CliRunner()
    result = runner.invoke(cli, ["--fields", "id,name", "conversations", "list"])
    assert result.exit_code == 0
```

**Step 2: Implement _run() in cli.py and conversations command group**

Add to `cli.py` the `_run()` helper (following omnifocus-cli pattern exactly), then register the conversations group. See the omnifocus-cli `_run()` for the exact pattern:
1. Parse `--body` JSON if provided
2. Merge with convenience flag params (body wins, warn if both)
3. Validate against schema
4. Semantic validation (IDs, timestamps)
5. If `--dry-run`, output validation result and exit
6. Otherwise, call client and output result

Create `commands/conversations.py` with the conversations group and register common methods: `list`, `info`, `history`, `create`, `archive`, `unarchive`, `invite`, `kick`, `join`, `leave`, `open`, `close`, `members`, `rename`, `setPurpose`, `setTopic`.

Each command follows the same template:
```python
@conversations.command("list")
@click.option("--limit", type=int, default=None)
@click.option("--types", default=None)
@click.option("--exclude-archived", is_flag=True, default=None)
@click.option("--cursor", default=None)
@click.pass_context
def conversations_list(ctx, limit, types, exclude_archived, cursor):
    """List channels in the workspace."""
    from slack_cli.cli import _run
    params = {k: v for k, v in {
        "limit": limit, "types": types,
        "exclude_archived": exclude_archived, "cursor": cursor,
    }.items() if v is not None}
    _run(ctx, "conversations.list", params)
```

**Step 3: Run tests**

```bash
cd slack-cli && poetry run pytest tests/test_conversations.py -v
```

**Step 4: Commit**

```bash
git add slack-cli/src/slack_cli/cli.py slack-cli/src/slack_cli/commands/
git add slack-cli/tests/test_conversations.py
git commit -m "feat: add _run() helper and conversations command group"
```

---

### Task 9: Remaining Command Groups (chat, users, reactions, files, search, pins, bookmarks, reminders, team)

**Files:**
- Create: `slack-cli/src/slack_cli/commands/chat.py`
- Create: `slack-cli/src/slack_cli/commands/users.py`
- Create: `slack-cli/src/slack_cli/commands/reactions.py`
- Create: `slack-cli/src/slack_cli/commands/files.py`
- Create: `slack-cli/src/slack_cli/commands/search.py`
- Create: `slack-cli/src/slack_cli/commands/pins.py`
- Create: `slack-cli/src/slack_cli/commands/bookmarks.py`
- Create: `slack-cli/src/slack_cli/commands/reminders.py`
- Create: `slack-cli/src/slack_cli/commands/team.py`
- Create: `slack-cli/tests/test_commands.py`

Each follows the exact same template established in Task 8. This is mechanical — each command group is a Click group registered on `cli`, each method is a subcommand with convenience flags that calls `_run()`.

**Write tests** for at least one command per group (e.g., `chat postMessage`, `users info`, `search messages`).

**Commit per group or batch:** Can commit all at once since the pattern is established.

```bash
git add slack-cli/src/slack_cli/commands/ slack-cli/tests/test_commands.py
git commit -m "feat: add chat, users, reactions, files, search, pins, bookmarks, reminders, team commands"
```

---

### Task 10: Auth Subcommands (status, test, store)

**Files:**
- Modify: `slack-cli/src/slack_cli/cli.py` (add auth group)
- Create: `slack-cli/tests/test_auth_commands.py`

**Commands:**
- `slack auth status` — Show which tokens are configured, workspace name
- `slack auth test` — Call `auth.test` API for each configured token
- `slack auth store --bot-token xoxb-... --user-token xoxp-...` — Save to config file

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_auth_commands.py
import json
import os
from unittest.mock import patch
from click.testing import CliRunner
from slack_cli.cli import cli


def test_auth_status_no_tokens():
    with patch.dict(os.environ, {}, clear=True):
        with patch("slack_cli.auth.CONFIG_PATH", "/nonexistent"):
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "status"])
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["bot_token"] == "not configured"


def test_auth_status_with_token():
    with patch.dict(os.environ, {"SLACK_CLI_TOKEN": "xoxb-test"}, clear=False):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "status"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["bot_token"] == "configured (env: SLACK_CLI_TOKEN)"
```

**Step 2: Implement and test**

**Step 3: Commit**

```bash
git add slack-cli/src/slack_cli/cli.py slack-cli/tests/test_auth_commands.py
git commit -m "feat: add auth status/test/store subcommands"
```

---

### Task 11: Schema Introspection Command

**Files:**
- Modify: `slack-cli/src/slack_cli/cli.py` (add schema command)
- Create: `slack-cli/tests/test_schema_command.py`

**Commands:**
- `slack schema chat.postMessage` — Show method schema as JSON
- `slack schema --list` — List all available methods
- `slack schema --group conversations` — List methods in a group

**Step 1: Write failing tests**

```python
# slack-cli/tests/test_schema_command.py
import json
from click.testing import CliRunner
from slack_cli.cli import cli


def test_schema_specific_method():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "chat.postMessage"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["method"] == "chat.postMessage"
    assert "params" in parsed


def test_schema_list():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--list"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert "chat.postMessage" in parsed


def test_schema_group():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "--group", "conversations"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert all(m.startswith("conversations.") for m in parsed)


def test_schema_not_found():
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "bogus.method"])
    assert result.exit_code == 1
```

**Step 2: Implement and test**

**Step 3: Commit**

```bash
git add slack-cli/src/slack_cli/cli.py slack-cli/tests/test_schema_command.py
git commit -m "feat: add schema introspection command"
```

---

### Task 12: +Helper Commands

**Files:**
- Create: `slack-cli/src/slack_cli/helpers/__init__.py`
- Create: `slack-cli/src/slack_cli/helpers/chat.py`
- Create: `slack-cli/src/slack_cli/helpers/conversations.py`
- Create: `slack-cli/src/slack_cli/helpers/users.py`
- Create: `slack-cli/tests/test_helpers.py`

**Helpers to implement:**

1. **`slack chat +send --channel general --text "Hello"`**
   - Resolve channel name → ID (call `conversations.list` with name filter)
   - Post message via `chat.postMessage`
   - Return message with permalink

2. **`slack conversations +find --name "project"`**
   - Search channels by name substring
   - Return matching channels with metadata

3. **`slack users +whois --name "John"` or `--email john@example.com`**
   - Search users by display name or email
   - Return matching user profiles

Each helper is registered as a Click command with `+` prefix on the appropriate group. They use the `SlackClient` internally for multi-step operations.

**Step 1: Write failing tests** for each helper

**Step 2: Implement helpers**

**Step 3: Commit**

```bash
git add slack-cli/src/slack_cli/helpers/ slack-cli/tests/test_helpers.py
git commit -m "feat: add +send, +find, +whois helper commands"
```

---

### Task 13: Hand-Written Skill Files (OpenClaw Format)

**Files:**
- Create: `slack-cli/skills/slack-shared/SKILL.md`
- Create: `slack-cli/skills/slack-channels/SKILL.md`
- Create: `slack-cli/skills/slack-messages/SKILL.md`
- Create: `slack-cli/skills/slack-search/SKILL.md`
- Create: `slack-cli/skills/slack-users/SKILL.md`
- Create: `slack-cli/skills/slack-files/SKILL.md`
- Create: `slack-cli/skills/slack-dm/SKILL.md`
- Create: `slack-cli/skills/recipe-slack-daily-summary/SKILL.md`
- Create: `slack-cli/skills/recipe-slack-thread-export/SKILL.md`

Skills are hand-written (not auto-generated) following the OpenClaw format from `gws`. Each teaches patterns and common examples, pointing to `slack schema <method>` for full parameter discovery.

**Step 1: Write slack-shared SKILL.md**

The shared skill covers:
- Installation: `pip install ./slack-cli` (host) or `pip install /app/tools/slack-cli/` (Docker)
- Auth: `SLACK_BOT_TOKEN` env var
- CLI syntax: `slack <resource> <method> [flags]`
- Global flags table: `--body`, `--format`, `--fields`, `--dry-run`, `--page-all`, `--page-limit`, `--as-user`/`--as-bot`
- Security rules: no secrets output, confirm before write/delete, prefer `--dry-run`

Format (matching gws-shared):
```yaml
---
name: slack-shared
version: 1.0.0
description: "Slack CLI: Shared patterns for authentication, global flags, and output formatting."
metadata:
  openclaw:
    category: "productivity"
    requires:
      bins: ["slack"]
---
```

**Step 2: Write per-resource skills**

Each resource skill follows the gws-gmail pattern:
```yaml
---
name: slack-channels
version: 1.0.0
description: "Slack: List channels, get channel info, read channel history."
metadata:
  openclaw:
    category: "productivity"
    requires:
      bins: ["slack"]
    cliHelp: "slack conversations --help"
---
```

Body includes:
- PREREQUISITE reference to `../slack-shared/SKILL.md`
- Helper commands table (if any `+` helpers exist for this resource)
- Common command examples (2-4 per skill)
- "Discovering Commands" section pointing to `slack schema` and `--help`
- Known quirks specific to that resource

**Key quirks to document:**
- `slack-search`: `on:YYYY-MM-DD` works; `after:` + `before:` combined returns 0 results
- `slack-channels`: Channel names don't include `#`; prefer IDs over names
- `slack-messages`: `thread_ts` is the parent message timestamp, not the reply

**Step 3: Write recipe skills**

Recipe skills follow the `recipe-find-free-time` pattern:
```yaml
---
name: recipe-slack-daily-summary
version: 1.0.0
description: "Search today's messages across key channels and summarize activity."
metadata:
  openclaw:
    category: "recipe"
    domain: "communication"
    requires:
      bins: ["slack"]
      skills: ["slack-channels", "slack-search"]
---
```

Body includes numbered steps with exact CLI commands.

**Step 4: Commit**

```bash
git add slack-cli/skills/
git commit -m "feat: add OpenClaw skill files for Letta Code agent consumption"
```

---

### Task 14: Letta Tool Wrappers

**Files:**
- Create: `slack-cli/letta_tools/__init__.py`
- Create: `slack-cli/letta_tools/slack_conversations.py`
- Create: `slack-cli/letta_tools/slack_chat.py`
- Create: `slack-cli/letta_tools/slack_users.py`
- Create: `slack-cli/letta_tools/slack_search.py`
- Create: `slack-cli/letta_tools/slack_files.py`
- Create: `slack-cli/letta_tools/slack_reactions.py`
- Create: `slack-cli/letta_tools/slack_misc.py` (pins, bookmarks, reminders, team)
- Create: `slack-cli/register_letta_tools.py`

Each Letta tool follows the exact subprocess pattern from omnifocus-cli:

```python
from typing import Dict, Any, Optional

def run_slack_chat(action: str, params: Optional[str] = None, fields: Optional[str] = None) -> Dict[str, Any]:
    """
    Manage Slack messages. Run `slack schema chat.<action>` to discover params.

    Args:
        action: One of: postMessage, update, delete, postEphemeral, scheduleMessage (REQUIRED)
        params: JSON string with parameters. Use `slack schema chat.<action>` to discover fields.
        fields: Comma-separated output fields to return (limits token usage)

    Returns:
        Dictionary with status and result from Slack API.
    """
    import json
    import subprocess
    import traceback

    try:
        cli_args = ["slack", "chat", action]
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

**Registration script** registers all tools with Letta API and attaches to specified agents.

**Step 1: Write Letta tool files**

**Step 2: Write registration script**

**Step 3: Commit**

```bash
git add slack-cli/letta_tools/ slack-cli/register_letta_tools.py
git commit -m "feat: add Letta tool wrappers with subprocess pattern"
```

---

### Task 15: Integration Tests

**Files:**
- Create: `slack-cli/tests/test_integration.py`

**Step 1: Write integration tests (marked with `@pytest.mark.integration`)**

```python
# slack-cli/tests/test_integration.py
import json
import subprocess
import pytest


@pytest.mark.integration
def test_auth_test():
    result = subprocess.run(["slack", "auth", "test"], capture_output=True, text=True)
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is True


@pytest.mark.integration
def test_conversations_list():
    result = subprocess.run(
        ["slack", "conversations", "list", "--body", '{"limit": 2}'],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is True


@pytest.mark.integration
def test_users_list():
    result = subprocess.run(
        ["slack", "users", "list", "--body", '{"limit": 2}'],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


@pytest.mark.integration
def test_dry_run_no_side_effects():
    result = subprocess.run(
        ["slack", "--dry-run", "--body", '{"channel":"C123","text":"test"}', "chat", "postMessage"],
        capture_output=True, text=True,
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "method" in parsed
```

**Step 2: Run integration tests**

```bash
cd slack-cli && poetry run pytest tests/test_integration.py -v -m integration
```

**Step 3: Commit**

```bash
git add slack-cli/tests/test_integration.py
git commit -m "feat: add integration tests for Slack CLI"
```

---

### Task 16: README and CONTEXT.md

**Files:**
- Create: `slack-cli/README.md`
- Create: `slack-cli/CONTEXT.md`

Write README with:
- Installation instructions (`poetry install`)
- Quick start (auth setup, first commands)
- Command reference table
- Flag reference
- +Helper examples

Write CONTEXT.md with agent invariants:
- Always use `--fields` to limit response size
- Use `--dry-run` before mutating operations
- Channel IDs preferred over names
- Timestamps are Slack `ts` format
- `search.messages` requires user token
- Use `slack schema <method>` for parameter discovery

**Commit:**

```bash
git add slack-cli/README.md slack-cli/CONTEXT.md
git commit -m "docs: add README and CONTEXT.md for agent consumption"
```
