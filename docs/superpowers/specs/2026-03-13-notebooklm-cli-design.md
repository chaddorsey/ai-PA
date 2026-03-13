# notebooklm-cli Design Spec

**Date:** 2026-03-13
**Status:** Approved
**Author:** Claude + Chad

## Overview

A Click-based Python CLI that wraps the `notebooklm-py` library through a schema/bridge architecture, providing agent-friendly access to Google NotebookLM. Enables Letta agents and Letta Code agents to create notebooks, manage sources, run Q&A, generate content (audio, video, reports, quizzes, etc.), and conduct web/drive research.

NotebookLM is positioned as a **complementary tool** to the existing RAG/Graphiti infrastructure — it handles curated, deep-dive synthesis and content generation on focused document collections, while drive-rag and Graphiti handle broad retrieval across the full corpus.

## Architecture

### Approach: Library Import with Bridge Isolation (Option C)

```
Agent -> run_notebooklm Letta tool -> subprocess -> notebooklm-cli
  -> schema.py (validate) -> bridge.py (call notebooklm-py client) -> Google APIs
```

The CLI imports `notebooklm-py`'s `NotebookLMClient` as a library but isolates it behind a bridge layer that:
- Wraps async client methods with `asyncio.run()` for sync CLI invocation
- Serializes dataclass results to dicts
- Converts exceptions to structured `{"status": "error", "error_message": "..."}` responses
- Handles auth refresh on token expiration

### Why Not the Alternatives

- **Thin wrapper (Option A):** Too tightly coupled — `notebooklm-py` API changes would break the CLI directly.
- **CLI-wrapping-CLI (Option B):** Fragile output parsing, double process overhead, can't access features not in their CLI.

## Authentication

`notebooklm-py` uses browser-based Google login via Playwright (one-time), then persists cookies to `~/.notebooklm/storage_state.json`. All subsequent API calls use the saved cookies (pure HTTP via httpx, no browser).

Three auth resolution paths (built into `notebooklm-py`):
1. `--storage` CLI flag (explicit path)
2. `NOTEBOOKLM_AUTH_JSON` env var (inline JSON — ideal for Docker)
3. `$NOTEBOOKLM_HOME/storage_state.json` or `~/.notebooklm/storage_state.json` (default)

Playwright is only a dependency of the `notebooklm login` command, not the CLI itself. Google session cookies persist for weeks to months; re-auth is infrequent.

## Command Groups & Schema

Six command groups mapping to `notebooklm-py`'s six sub-APIs, plus standard `schema` and `health` commands. ~35-40 schema entries total.

### notebook

| Action | Description | Key Params |
|--------|-------------|------------|
| `create` | Create a new notebook | `title` (required) |
| `list` | List all notebooks | — |
| `get` | Get notebook details | `notebookId` |
| `delete` | Delete a notebook | `notebookId` |
| `rename` | Rename a notebook | `notebookId`, `title` |
| `describe` | Get AI-generated description | `notebookId` |
| `topics` | Get suggested topics | `notebookId` |

### source

| Action | Description | Key Params |
|--------|-------------|------------|
| `add-url` | Add a URL source | `notebookId`, `url` |
| `add-text` | Add pasted text | `notebookId`, `text`, `title` |
| `add-file` | Add a file (PDF, DOCX, MD, etc.) | `notebookId`, `filePath` |
| `add-youtube` | Add a YouTube video | `notebookId`, `url` |
| `add-drive` | Add a Google Drive file | `notebookId`, `driveFileId` |
| `list` | List sources in a notebook | `notebookId` |
| `get` | Get source details | `notebookId`, `sourceId` |
| `delete` | Delete a source | `notebookId`, `sourceId` |
| `rename` | Rename a source | `notebookId`, `sourceId`, `title` |
| `refresh` | Refresh a source | `notebookId`, `sourceId` |
| `guide` | Get source guide/summary | `notebookId`, `sourceId` |
| `fulltext` | Get source full text | `notebookId`, `sourceId` |

### artifact

| Action | Description | Key Params |
|--------|-------------|------------|
| `generate` | Generate an artifact | `notebookId`, `type` (audio/video/report/quiz/slides/infographic/mindmap/table), `instructions` |
| `list` | List artifacts in a notebook | `notebookId` |
| `get` | Get artifact details | `notebookId`, `artifactId` |
| `delete` | Delete an artifact | `notebookId`, `artifactId` |
| `rename` | Rename an artifact | `notebookId`, `artifactId`, `title` |
| `download` | Download artifact to file | `notebookId`, `type`, `outputPath` |
| `status` | Check generation status | `notebookId`, `taskId` |
| `wait` | Wait for generation completion | `notebookId`, `taskId` |

### chat

| Action | Description | Key Params |
|--------|-------------|------------|
| `ask` | Ask a question | `notebookId`, `question`, `sourceIds` (optional), `conversationId` (optional) |
| `history` | Get conversation history | `notebookId` |
| `clear` | Clear conversation | `notebookId` |
| `save` | Save conversation to notes | `notebookId` |

### research

| Action | Description | Key Params |
|--------|-------------|------------|
| `start` | Start web/drive research | `notebookId`, `query`, `source` (web/drive), `mode` (fast/deep) |
| `poll` | Check research status | `notebookId` |
| `import` | Import discovered sources | `notebookId`, `taskId`, `sourceIds` |

### note

| Action | Description | Key Params |
|--------|-------------|------------|
| `create` | Create a note | `notebookId`, `title`, `content` |
| `list` | List notes | `notebookId` |
| `update` | Update a note | `notebookId`, `noteId`, `content`, `title` |
| `delete` | Delete a note | `notebookId`, `noteId` |

## Project Structure

```
notebooklm-cli/
  pyproject.toml              # Poetry, python >=3.9, deps: click, notebooklm-py
  CONTEXT.md                  # Agent-facing quick reference
  src/notebooklm_cli/
    __init__.py
    cli.py                    # Click CLI: 6 command groups + schema + health
    schema.py                 # Static registry (~35-40 entries)
    bridge.py                 # Async wrapper around NotebookLMClient
    fields.py                 # Output field masking
    validate.py               # Input validation
    formatters.py             # JSON/text output
  skills/                     # OpenClaw SKILL.md files
    notebooklm-shared/SKILL.md
    notebooklm-notebooks/SKILL.md
    notebooklm-sources/SKILL.md
    notebooklm-chat/SKILL.md
    notebooklm-artifacts/SKILL.md
    recipe-notebooklm-research-project/SKILL.md
    recipe-notebooklm-meeting-prep/SKILL.md
  tests/
```

### Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.9"
click = "^8.1"
notebooklm-py = "*"
```

Playwright is NOT a dependency — it's only needed for the one-time `notebooklm login` command (installed separately: `pip install "notebooklm-py[browser]"`).

## CLI Conventions

Follows the established pattern from omnifocus-cli, gws-cli, and slack-cli:

### Global Flags (before subcommand)

| Flag | Description |
|------|-------------|
| `--body '{"key": "val"}'` | JSON input (agent-first path) |
| `--format json\|text` | Output format (default: auto-detect) |
| `--fields id,title,...` | Comma-separated output field mask |
| `--dry-run` | Validate and preview, no execution |

### Input Paths

1. **Agent path (preferred):** `--body '{"title": "My Research"}'`
2. **Human path:** `--title "My Research"` (convenience flags per command)

### Exit Codes

| Code | Meaning | Output |
|------|---------|--------|
| 0 | Success | stdout = JSON |
| 1 | Execution error | stderr has details |
| 2 | Validation error | stdout = JSON with field-level errors |

### Workflow Pattern

```
1. notebooklm-cli schema notebook.create       # discover params
2. notebooklm-cli --body '...' --dry-run notebook create  # validate
3. notebooklm-cli --body '...' notebook create             # execute
4. Parse stdout JSON for result
```

## Bridge Design

```python
# bridge.py — key patterns

def call(method: str, params: dict) -> dict:
    """Sync entry point. Routes method to NotebookLMClient sub-API."""
    import asyncio
    try:
        return asyncio.run(_async_call(method, params))
    except Exception as e:
        return {"status": "error", "error_message": str(e)}

async def _async_call(method: str, params: dict) -> dict:
    """Resolve method to client call, serialize result."""
    async with await NotebookLMClient.from_storage() as client:
        group, action = method.split(".", 1)
        api = {
            "notebook": client.notebooks,
            "source": client.sources,
            "artifact": client.artifacts,
            "chat": client.chat,
            "research": client.research,
            "note": client.notes,
        }[group]

        # Dispatch to method, serialize dataclass results to dicts
        result = await _dispatch(api, action, params)
        return {"status": "ok", "result": _serialize(result)}
```

The bridge:
- Creates a fresh `NotebookLMClient` per invocation (stateless CLI)
- Serializes `Notebook`, `Source`, `Artifact`, `AskResult`, etc. dataclasses to plain dicts
- Wraps all exceptions into structured error responses
- Attempts auth refresh once on auth errors before failing

## Letta Integration

### Tool Wrapper

Single function in `letta/notebooklm_tools.py`:

```python
def run_notebooklm(command: str, params: Optional[str] = None,
                   fields: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
```

Default timeout of 60s (artifact generation and research can take 10-30s).

Follows all Letta tool constraints:
- All imports inside function body
- No nested `def` statements
- `Args:` docstring section required
- `Dict[str, Any]` return with `status` key
- Full try-except wrapper

### Deployment

| | Host (Letta Code) | Docker (Letta agent) |
|---|---|---|
| Install | `pip install ./notebooklm-cli` | Volume mount + pip in entrypoint-wrapper.sh |
| Auth | `~/.notebooklm/storage_state.json` | Volume mount or `NOTEBOOKLM_AUTH_JSON` env var |
| Network | Direct HTTPS to Google | Direct HTTPS to Google |
| Auth setup | `notebooklm login` on Mac Mini | `notebooklm login` on Mac Mini, mount credentials |

Docker compose addition:
```yaml
volumes:
  - ${NOTEBOOKLM_HOME:-~/.notebooklm}:/notebooklm-auth:ro
  - ./notebooklm-cli:/app/tools/notebooklm-cli:ro
environment:
  NOTEBOOKLM_HOME: /notebooklm-auth
```

No scheduler integration needed — NotebookLM operations are agent-initiated, not polled.

## Key Workflows

### Research Project (persistent notebook)

```bash
notebooklm-cli --body '{"title": "NSF CAMEL Proposal Research"}' notebook create
notebooklm-cli --body '{"notebookId": "nb123", "url": "https://docs.google.com/..."}' source add-url
notebooklm-cli --body '{"notebookId": "nb123", "filePath": "/path/to/paper.pdf"}' source add-file
notebooklm-cli --body '{"notebookId": "nb123", "question": "What are the key methodological gaps?"}' chat ask
notebooklm-cli --body '{"notebookId": "nb123", "type": "report", "instructions": "Executive summary"}' artifact generate
```

### Meeting Prep (on-demand notebook)

```bash
notebooklm-cli --body '{"title": "Helen Meeting Prep 2026-03-14"}' notebook create
notebooklm-cli --body '{"notebookId": "nb456", "filePath": "/data/exports/granolaNote--...--Helen.md"}' source add-file
notebooklm-cli --body '{"notebookId": "nb456", "question": "What open action items exist?"}' chat ask
```

### Content Generation

```bash
notebooklm-cli --body '{"notebookId": "nb123", "type": "audio", "instructions": "Focus on methodology"}' artifact generate
notebooklm-cli --body '{"notebookId": "nb123", "taskId": "task789"}' artifact wait
notebooklm-cli --body '{"notebookId": "nb123", "type": "audio", "outputPath": "./podcast.mp3"}' artifact download
```

### Web Research with Auto-Import

```bash
notebooklm-cli --body '{"notebookId": "nb123", "query": "AI-assisted science education", "source": "web"}' research start
notebooklm-cli --body '{"notebookId": "nb123"}' research poll
notebooklm-cli --body '{"notebookId": "nb123", "taskId": "rtask321", "sourceIds": ["s1","s2"]}' research import
```

## OpenClaw Skills

Ships with 7 skill files:

| Skill | Purpose |
|-------|---------|
| `notebooklm-shared` | Installation, auth, global flags, security rules |
| `notebooklm-notebooks` | Notebook CRUD, organization |
| `notebooklm-sources` | Multi-format source ingestion |
| `notebooklm-chat` | Q&A with conversation threading |
| `notebooklm-artifacts` | Content generation and download |
| `recipe-notebooklm-research-project` | Multi-step research workflow |
| `recipe-notebooklm-meeting-prep` | Meeting preparation workflow |

## Caveats

- **Unofficial APIs**: `notebooklm-py` uses undocumented Google APIs that can change without notice. Suitable for personal/research use. The bridge layer provides some insulation from breaking changes.
- **Cookie expiration**: Google session cookies expire after weeks to months. Re-running `notebooklm login` is required periodically.
- **Rate limits**: Heavy usage may be throttled by Google. No specific limits documented.
- **Async overhead**: Each CLI invocation creates a new `NotebookLMClient` and httpx session. This is fine for agent use (seconds between calls) but not suitable for high-throughput batch processing.
