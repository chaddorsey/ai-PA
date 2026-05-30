---
description: Pointer to the existing slack-cli's per-resource skill bundle (March 2026 project). The CLI binary `slack` is already installed via pipx and on PATH; this file just surfaces the bundle in docs/skills/ for parity with other fleet-skill conventions.
applies-to: any local-mode agent that interacts with Slack (read, search, post, react, bookmark, file, pin, reminder, DM, user-lookup). Primary user: Pulse Agent.
cli: ~/.local/bin/slack  (installed from slack-cli/ package via pipx; not in scripts/)
---

# Slack CLI Skill

The Slack CLI is the comprehensive Click-based package at
[/Volumes/main-drive/ai-PA/slack-cli/](../../slack-cli/). Binary
installed via pipx at `~/.local/bin/slack` (already on PATH).

This `docs/skills/slack.md` is a **pointer**, not a full protocol —
the authoritative skill files live in the package itself at
`slack-cli/skills/`, where each resource group and recipe has its
own SKILL.md.

## When to use the slack-cli

- **Most things Slack**: messages, channels, users, search, DMs,
  reactions, bookmarks, pins, reminders, files. The CLI covers the
  full Slack Web API surface (via `slack_sdk`).
- **NOT for analytics CSV downloads**: those go through
  `slack-extract` (Playwright browser automation, separate concern).
- **NOT for posting via slackbot's higher-level handlers** (block
  kit, proposal cards, status updates): use the slackbot's surfaces.

## The skill bundle at `slack-cli/skills/`

```
slack-cli/skills/
├── slack-shared/             # auth, global flags, security rules — START HERE
├── slack-channels/           # list, info, history, +find
├── slack-messages/           # post, update, delete, thread
├── slack-users/              # lookup by id, +find by name, profile
├── slack-search/             # message + file search (requires user token)
├── slack-dm/                 # direct messages
├── slack-reactions/          # add, remove, list
├── slack-bookmarks/          # channel bookmarks
├── slack-files/              # upload, get, list
├── slack-pins/               # pinned items
├── slack-reminders/          # reminders
├── recipe-slack-channel-digest/    # summarize a channel
├── recipe-slack-daily-summary/     # daily activity rollup
├── recipe-slack-find-and-reply/    # search + draft reply
├── recipe-slack-pulse-report/      # cross-channel activity summary (Pulse Agent)
├── recipe-slack-thread-export/     # export a thread for context
└── recipe-slack-user-activity/     # activity report for a user
```

Each subdirectory has a `SKILL.md` with frontmatter (description,
requires, prerequisites) and a body explaining usage. Agents loading
skills via Letta's skill mechanism reach them at
`slack-cli/skills/<name>/SKILL.md`.

## Auth state

Configured 2026-05-30 via:

```bash
slack auth store \
  --bot-token "$SLACK_BOT_TOKEN" \
  --user-token "$SLACK_MCP_XOXP_TOKEN"
```

Tokens persisted at `~/.config/slack-cli/credentials.json`. Verify:

```bash
slack auth test
# → {"bot": {"ok": true, "user": "bolt_template_app", "team": "Concord Consortium"},
#    "user": {"ok": true, "user": "cdorsey", "team": "Concord Consortium"}}
```

## Quick reference

```bash
# Discovery first (the schema command)
slack schema --group conversations
slack schema chat.postMessage

# Common reads
slack conversations list --body '{"types":"public_channel","limit":50}' --fields "id,name"
slack conversations history --body '{"channel":"C123","limit":50}' --fields "ts,user,text"
slack users info --body '{"user":"U09B5JUK2TY"}' --fields "id,name,real_name,profile.email"

# Search (requires user token)
slack search messages --body '{"query":"on:2026-05-29 FY26 budget"}' --as-user

# Post (use with --dry-run first, then ask user before executing)
slack chat postMessage --body '{"channel":"C123","text":"hello"}' --dry-run

# Recipes
slack +pulse-report --time-range last_24h
slack +channel-digest --channel C123 --time-range last_week
```

For full details see the per-resource SKILL.md files under `slack-cli/skills/`.

## Naming convention note

Per the 2026-05-30 CLI-naming audit:
- Package directory: `slack-cli/` (suffix disambiguates from `slack-mcp-server/`, `slackbot/`)
- Binary name: `slack` (bare, matches gws CLI precedent)
- Letta tool wrapping it (if still attached): `run_slack`

Other CLIs in `scripts/` (signal, scheduler, gmail-watch, drive-rag-curl,
granola, atlassian) follow the bare-name convention — no `-cli` or
`run_` prefix on the binary.
