# GWS CLI Upgrade + Auto-Update + Tool Cleanup

**Date:** 2026-04-01
**Triggered by:** MC agent unable to create Gmail draft with attachment — `gws` v0.7.0 lacks `+reply`, `+forward`, `--draft`, `-a`/`--attach` flags that were added in v0.18.0+

## Problem

1. `gws` CLI is at v0.7.0 on both the server host and Letta container; latest is v0.22.5
2. `run_gws` docstring documents features that don't exist in v0.7.0 (but do exist in v0.18+), causing agent confusion
3. `compose_gmail` was built to compensate for missing CLI features (MIME construction, threading, attachments) — now redundant with v0.18+
4. No mechanism to keep `gws` current; it's a fast-moving project (15 releases in ~6 weeks)

## Solution

Upgrade `gws` to latest, add auto-update, fix the docstring to be self-maintaining, retire `compose_gmail`.

## Design

### 1. Upgrade `gws` binary (two locations)

**Server host (`~/bin/gws`):**
- Download v0.22.5 binary (note: naming changed from `gws-<target>.tar.gz` to `google-workspace-cli-<target>.tar.gz`)
- Keep old binary as `gws.bak` for rollback

**Letta container (`entrypoint-wrapper.sh`):**
- Replace the inline download block with a call to the shared `update-gws.sh` script (mounted via docker-compose volume)
- This runs on every container restart, ensuring the binary is current

### 2. Auto-update script

A single `scripts/update-gws.sh` script usable in both contexts:
- Queries GitHub API for latest release tag
- Compares to installed `gws --version`
- If newer: downloads, backs up current as `gws.bak`, installs new
- Logs version transitions
- Detects platform automatically (aarch64 vs x86_64, darwin vs linux)

**Scheduled execution:**
- **Server host:** cron job, weekly (e.g., Monday 3am)
- **Letta container:** cron job on host running `docker exec ai-pa-letta-1 /app/tools/scripts/update-gws.sh` on the same schedule
- **Entrypoint:** also runs on container restart as a bonus

### 3. Refactor `run_gws` docstring (hybrid approach C)

Keep stable structural info that doesn't change between versions:
- Service list
- `gws <service> <resource> <method>` pattern
- `schema` discovery pattern
- Key tips (e.g., labelIds string gotcha, `/dev/stdout` for exports)

Replace detailed helper flag documentation with self-discovery pointers:
- "Use `command='gmail +send --help'` to see current flags"
- "Use `command='gmail --help'` to list available helpers"
- Cross-reference: "For email composition with attachments, threading, HTML, or drafts, use the gmail helpers (+send, +reply, +reply-all, +forward) with --help to discover flags"

Keep a few stable examples per service for orientation, but not flag-level details.

### 4. Retire `compose_gmail`

- Remove `compose_gmail` function from `gmail_tools.py`
- Remove from `register_gmail_tools.py`
- Unregister from Letta (delete the tool via API)
- Check if any agents have it attached (MC does not; verify others)
- `fetch_gmail_messages` stays — still provides value for batch reads not covered by `+read`

### 5. Version tracking

Add `gws` to `config/versions/versions.lock.yml` under a new `cli_tools` section:

```yaml
cli_tools:
  gws:
    source: "github.com/googleworkspace/cli"
    version: "0.22.5"
    locked: false  # auto-updated
    locations:
      - "~/bin/gws (server host)"
      - "/usr/local/bin/gws (letta container)"
      - "@googleworkspace/cli (gws-bridge, npm)"
    upgrade_path: "auto"
    notes: "Auto-updated weekly via scripts/update-gws.sh"
```

### 6. gws-bridge sync

Currently at v0.22.3 via npm. A `docker-compose build gws-bridge` gets latest. Not urgent but should be rebuilt after upgrade to stay in sync. No auto-update mechanism needed — it rebuilds when the service is rebuilt.

## File Changes

| File | Change |
|------|--------|
| `scripts/update-gws.sh` | **New** — auto-update script |
| `letta/entrypoint-wrapper.sh` | Update gws install block to use update script or latest-pull logic |
| `letta/gmail_tools.py` | Remove `compose_gmail`, refactor `run_gws` docstring |
| `letta/register_gmail_tools.py` | Remove `compose_gmail` registration |
| `config/versions/versions.lock.yml` | Add `cli_tools.gws` entry |
| `~/bin/gws` | Upgraded binary (manual or via script) |

## Out of Scope

- Upgrading gws-bridge beyond a rebuild (it's close to current)
- Changing how `fetch_gmail_messages` works
- Modifying MC's tool list (it already has `run_gws`; `compose_gmail` was never attached)
- Auto-generating the full docstring from `--help` output (hybrid approach is sufficient)

## Rollback

- Host: `mv ~/bin/gws.bak ~/bin/gws`
- Container: set `GWS_VERSION=0.7.0` in entrypoint and restart
- Tool: re-register old `gmail_tools.py` from git history
