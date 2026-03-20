# Granola CLI — Plan Document

**Date:** 2026-03-19
**Status:** Ready to build
**Context:** MC currently has 5 individual Granola MCP tools. These should be unified into a single `run_granola` CLI tool following the established patterns from `slack-cli`, `omnifocus-cli`, and `gws-bridge`.

---

## Goal

Create a `granola-cli` package that wraps Granola meeting access into a single Click-based CLI binary (`granola`), exposed to Letta agents via one `run_granola` tool with progressive disclosure via `schema` commands.

## Pattern Reference

| Aspect | slack-cli | omnifocus-cli | granola-cli (target) |
|--------|-----------|---------------|---------------------|
| Binary | `slack` | `omnifocus-cli` | `granola` |
| Letta tool | `run_slack(command, body, fields, timeout)` | `run_omnifocus(command, fields, timeout)` | `run_granola(command, body, fields, timeout)` |
| Schema | `slack schema --group conversations` | `omnifocus-cli schema --list` | `granola schema --group meetings` |
| Package | `slack-cli/` | `omnifocus-cli/` | `granola-cli/` |
| Data source | Slack Web API (via slack_sdk) | OmniFocus (via AppleScript bridge) | Granola API (via MCP proxy or direct HTTP) |

## Command Groups

Based on current MCP tool capabilities and the Granola API:

```
granola
├── meetings
│   ├── list          — list meetings by time range (this_week, last_week, last_30_days, custom)
│   ├── search        — search with filters (participants, date_range, project, meeting_type)
│   ├── get           — get full details for a meeting by ID
│   ├── transcript    — get verbatim transcript for a meeting by ID
│   └── +query        — natural language question about meetings (convenience helper)
├── schema
│   ├── (no args)     — list all groups and methods
│   └── --group       — list methods in a group
└── auth
    └── status        — check Granola OAuth token status
```

## Data Access Layer

Two possible backends for the CLI:

**Option A: Via Granola MCP proxy (supergateway on port 8089)**
- Already running, handles OAuth token refresh
- CLI calls `http://localhost:8089/mcp` with MCP JSON-RPC
- Pros: reuses existing auth infrastructure
- Cons: extra hop, MCP protocol overhead

**Option B: Direct Granola API**
- CLI calls `https://api.granola.ai/v1/...` directly
- Reads OAuth tokens from `.granola-tokens.json`
- Pros: simpler, faster
- Cons: needs its own token refresh logic

**Recommendation: Option A** for initial build (reuse supergateway), with option to add direct API later.

## Letta Tool Design

```python
def run_granola(command: str, body: Optional[str] = None,
                fields: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Run any Granola CLI command. Access meeting notes, transcripts, and search.

    Commands follow the pattern: <resource> <method>
    Use "schema" to discover all available commands.

    Meetings examples:
      command="meetings list --range this_week"
      command="meetings search", body='{"query":"budget discussion","participants":"leslie"}'
      command="meetings get --id f258f91e-..."
      command="meetings transcript --id f258f91e-..."
      command="meetings +query --question 'What did we decide about the MADESE proposal?'"

    Schema discovery:
      command="schema"
      command="schema --group meetings"

    Args:
        command: Granola CLI command string.
        body: JSON string of additional parameters.
        fields: Comma-separated output fields to limit response size.
        timeout: Command timeout in seconds (default 30).

    Returns:
        Dictionary with status and parsed JSON response.
    """
```

## Implementation Steps

### 1. Scaffold `granola-cli/` package
- `pyproject.toml` (Poetry, Python 3.11+, entry point `granola=granola_cli.cli:cli`)
- `src/granola_cli/cli.py` — Click entry point with GlobalOptionsGroup
- `src/granola_cli/client.py` — Granola API client (via MCP proxy)
- `src/granola_cli/schema.py` — Schema definitions for discovery
- `src/granola_cli/formatter.py` — Output formatting (json/text/yaml)

### 2. Implement command groups
- `meetings list` — wraps `list_meetings` MCP tool
- `meetings search` — wraps `search_meetings_smart` MCP tool
- `meetings get` — wraps `get_meeting_details` MCP tool
- `meetings transcript` — wraps `get_meeting_transcript` MCP tool
- `meetings +query` — wraps `query_granola_meetings` MCP tool (convenience)
- `schema` — returns command/method descriptions

### 3. Create Letta tool
- `granola-cli/letta_tools/granola_tool.py` — `run_granola()` function
- `granola-cli/register_letta_tools.py` — registration script
- Follow exact patterns from `slack-cli/letta_tools/slack_tool.py`

### 4. Install and attach
- Install in Letta container sandbox (pip)
- Register tool with Letta API
- Attach to MC (replace 5 individual tools with 1 unified tool)
- Remove individual Granola tools from MC

### 5. Schema passages
- Add `ARCHIVE SCHEMA` passage for Granola live data
- Update `archival_knowledge_sources` block on MC

## Files to Create

```
granola-cli/
├── pyproject.toml
├── src/granola_cli/
│   ├── __init__.py
│   ├── cli.py              — Click CLI with meetings group + schema
│   ├── client.py           — MCP proxy client
│   ├── schema.py           — Method schemas for discovery
│   └── formatter.py        — Output formatting
├── letta_tools/
│   ├── granola_tool.py     — run_granola() Letta tool
│   └── __init__.py
├── register_letta_tools.py — Registration + deprecated tool cleanup
└── skills/
    └── granola-meetings/
        └── SKILL.md        — Agent skill documentation
```

## Current State (Pre-Build)

- 5 individual Granola tools attached to MC (interim solution)
- Granola MCP proxy running on port 8089 (supergateway + mcp-remote)
- OAuth tokens managed by `scripts/granola-oauth.py`
- 726 markdown exports in `~/Dropbox/Granola-exports/`
- Archival ingest broken for recent meetings (Nov 2025 – present gap)

## Cleanup After Build

- Remove 5 individual tools from MC: `search_meetings_smart`, `query_granola_meetings`, `list_meetings`, `get_meeting_details`, `get_meeting_transcript`
- Remove from docs-and-transcripts agent if no longer needed there
- Update `archival_knowledge_sources` block to reference `run_granola` instead of individual tools
- Fix archival ingest pipeline as separate task
