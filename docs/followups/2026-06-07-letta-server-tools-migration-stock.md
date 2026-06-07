---
date: 2026-06-07
status: stock-taking ONLY — migration ON HOLD
related: docs/plans/2026-06-07-analytics-briefing-local-completion-charter.md
letta_bug: LET-9147 (non-deterministic tool interpreter in local mode)
---

> **HOLD (2026-06-07, per Chad):** Do NOT plan or execute any
> significant-scope tool migration from this inventory yet. Recent
> Letta-code updates introduce a **new path** Chad needs to evaluate
> first; it may change the approach (incl. the server-harden vs.
> re-home-local decision below). This doc is inventory/reference only
> until Chad brings in the new-path details.

# Letta server tools — stock-taking for local-mode migration

## Why this exists

The pulse analytics tools flaked because letta-code (local backend) runs
**server-registered** Letta tools in a non-deterministic environment
(host pulse-cli venv 3.13 / CommandLineTools 3.9 / Docker server sandbox
`/root`). Letta support (ticket **LET-9147**) confirmed this isn't expected
and gave the supported hardening pattern:

1. Declare deps via **`pip_requirements`** on each tool.
2. Keep imports inside the function.
3. **Don't rely on ambient `~` / CWD / user-site.**
4. Pass credential paths via explicit **absolute env vars**, read with
   `os.getenv()`.
5. **Inline or package** helper modules — no sibling imports from `/tmp`.

This pattern must be applied to *every* custom server tool, not just pulse.
This doc inventories the surface.

## Headline numbers

- **228** tools on the Letta server; **202** custom (have `source_code`).
- **`pip_requirements`: `none` on ALL of them** — nothing declares deps.

## Migration-risk tiers

**Tier A — high risk (flaky like pulse): exotic dep AND/OR cred-file AND/OR
sibling import.** Fix first.

- Sibling imports (must inline/package): `collect_analytics_snapshot`
  (drive_analytics_tools, email_analytics_tools), `get_document_activity`
  (drive_analytics_tools).
- Credential-file dependent (`~/.gmail-mcp`, `expanduser`, creds.json):
  `collect_daily_personal_activity`, `collect_daily_workspace_activity`,
  `download_attachment`, `draft_email`, `fetch_source_content`,
  `get_document_events`, `get_email_analytics`, `modify_email`,
  `read_email`, `run_gws`, `search_drive_activity`, `search_emails`,
  `send_email` (~13).
- `psycopg` users (~10): `add_extracted_tasks_postgres`, `backtrace_task`,
  `collect_analytics_snapshot`, `consume_queue`, `fetch_source_content`,
  `refine_task_description`, `refresh_plate`, `retrieve_task_info`,
  `scan_meeting_notes`, `write_packet_info`.
- `pytz` users (~13): `add_extracted_tasks`, `check_current_time`,
  `find_my_availability`, `generate_daily_briefing`, `get_email_analytics`,
  `merge_extracted_tasks`, `prepare_meeting_followup`,
  `process_drive_task_queue`, `process_email_task_queue`,
  `scan_meeting_notes`, `sync_omnifocus_completions`,
  `transition_extracted_task`, `update_extracted_task`.
- `google`-lib users (~7): `download_attachment`, `draft_email`,
  `get_document_activity`, `modify_email`, `read_email`, `search_emails`,
  `send_email`.

**Tier B — medium: `requests`-only (~50).** `requests` is usually present so
these often "work," but should still declare `pip_requirements:[requests]`
for determinism. (sports/media, watch-history, Jira/Confluence-via-http,
curator, RAG ingest, etc.)

**Tier C — low: stdlib-only / pure API-call tools (~120).** Most Slack,
scheduler, Jira/Confluence, calendly, granola wrappers. Likely fine; add
`pip_requirements:[]` explicitly only if needed.

## Hardening template (per tool)

1. Add `pip_requirements` (e.g. `[{"name":"pytz"},{"name":"psycopg[binary]"}]`).
2. Replace `os.path.expanduser("~/...")` cred reads with
   `os.getenv("<TOOL>_CREDENTIALS_FILE")` → an **absolute** path, provided
   in BOTH the local runner env and the server sandbox env/mount.
3. Inline sibling-helper logic into the tool source (or publish the helpers
   as a pip package and add to `pip_requirements`).
4. After changing tools, ensure the server sandbox venv installs the new
   `pip_requirements` (`use_venv: true` already; recreate venv:
   `POST /v1/sandbox-config/local/recreate-venv`).

## Open architecture question (blocks a clean migration)

These are **server** tools, but the agents using them are migrating to
**local** mode (letta-code). The non-determinism is partly because the
*same* server tool runs sometimes locally, sometimes in the Docker server
sandbox. The strategic decision before mass migration: do tools become
fully local (letta-code-owned, no server dependency — aligns with the
local-mode + no-Docker direction), or stay server-registered with the
sandbox hardened? This determines whether "migration" = re-home tools to
local mode, or = harden the 202 server tools in place.

## Immediate next step

Harden the pulse cluster first (it's the canary and the active failure):
`collect_analytics_snapshot`, `get_email_analytics`, `compose_daily_briefing`,
`collect_daily_workspace_activity`. Validate the template end-to-end, then
roll Tier A → B.
