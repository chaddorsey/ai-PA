# OmniFocus CLI — GlobalOptionsGroup Refactor Plan

**Date:** 2026-03-20
**Status:** Ready to build
**Context:** The slack-cli uses a `GlobalOptionsGroup` pattern that allows `--format`, `--body`, `--fields`, `--dry-run`, `--as-user`/`--as-bot` to appear anywhere in the command line. The omnifocus-cli currently requires group options before the subcommand (standard Click behavior), which breaks agent usage patterns where flags appear after the subcommand. This refactor brings omnifocus-cli into consistency with slack-cli and the gws CLI pattern.

## Problem

Agents naturally write:
```
omnifocus-cli task list --limit 50 --format json --fields id,name
```

But Click requires:
```
omnifocus-cli --format json --fields id,name task list --limit 50
```

The slack-cli solved this with `GlobalOptionsGroup` — a custom Click Group class that extracts global options from any position before standard parsing. The omnifocus-cli needs the same pattern.

## Current State

**slack-cli** (`slack-cli/src/slack_cli/cli.py`):
- `GlobalOptionsGroup` class extracts `--format`, `--body`, `--dry-run`, `--fields`, `--page-all`, `--page-limit`, `--as-user`, `--as-bot` from any position
- All subcommands work with options in any order

**omnifocus-cli** (`omnifocus-cli/src/omnifocus_cli/cli.py`):
- Standard `@click.group()` — options must precede subcommands
- `--body`, `--format`, `--fields`, `--dry-run` defined as group-level options
- Workaround: `--fields` duplicated as subcommand option on `task list`
- Agents must know the correct option ordering or calls fail

## Changes

### 1. Port GlobalOptionsGroup from slack-cli

Copy the `GlobalOptionsGroup` class and `GLOBAL_OPTIONS` dict from `slack-cli/src/slack_cli/cli.py` lines 14-60 into `omnifocus-cli/src/omnifocus_cli/cli.py`.

Adapt the options list:
```python
GLOBAL_OPTIONS = {
    "--format": {"nargs": 1, "key": "format"},
    "--body": {"nargs": 1, "key": "body"},
    "--dry-run": {"nargs": 0, "key": "dry_run"},
    "--fields": {"nargs": 1, "key": "fields"},
}
```

### 2. Apply to CLI group

Change:
```python
@click.group()
@click.option("--format", ...)
@click.option("--body", ...)
@click.option("--dry-run", ...)
@click.option("--fields", ...)
def cli(ctx, format_flag, body_json, dry_run, fields):
```

To:
```python
@click.group(cls=GlobalOptionsGroup)
def cli(ctx):
    ctx.ensure_object(dict)
    # Global options are populated by GlobalOptionsGroup.parse_args
```

### 3. Remove duplicate subcommand options

Remove `--fields` from `task list` subcommand (it's now handled globally). Same for any other duplicated options.

### 4. Update _run to read from ctx.obj

Verify `_run` reads `format`, `body`, `fields`, `dry_run` from `ctx.obj` (it already does — just confirm the key names match the `GLOBAL_OPTIONS` dict).

### 5. Test all command forms

Verify these all work:
```bash
omnifocus-cli task list --limit 50 --format json --fields id,name
omnifocus-cli --format json task list --limit 50 --fields id,name
omnifocus-cli task count --added-after 2026-01-01 --format json
omnifocus-cli task list --body '{"limit":50}' --format json
omnifocus-cli task create --name "Test" --dry-run
omnifocus-cli schema task.list
```

### 6. Rebuild and install

```bash
cd omnifocus-cli && poetry build
docker cp dist/omnifocus_cli-*.whl ai-pa-letta-1:/tmp/
docker exec ai-pa-letta-1 pip install --force-reinstall /tmp/omnifocus_cli-*.whl
```

## Files to Modify

- `omnifocus-cli/src/omnifocus_cli/cli.py` — Add GlobalOptionsGroup, update cli group, remove duplicate options
- No other files need changes (schema, bridge, formatters, fields all work with ctx.obj already)

## Scope

This is a focused refactor — ~50 lines of new code (the GlobalOptionsGroup class), ~20 lines removed (duplicate options), and verification. No new features, no schema changes, no bridge changes.

## Follow-Up

Consider whether gws-bridge/gws CLI also needs this pattern for consistency. The three CLIs (slack, omnifocus, gws) should ideally share the same `GlobalOptionsGroup` implementation, possibly as a shared utility.
