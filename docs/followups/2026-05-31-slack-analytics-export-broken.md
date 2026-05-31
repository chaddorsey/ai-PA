---
date: 2026-05-31
status: resolved
component: slack-analytics-mcp-server
fix_committed_in: scripts/slack_analytics_with_dates.py
---

# Slack admin analytics export broken (2026-05-17 → 2026-05-31)

## Summary

Daily Slack admin CSV export silently failed for ~13 days. Discovered
2026-05-31 during pulse-cli smoke testing. Root cause: Slack moved
the admin analytics UI from a hash-router (`/admin/stats#channels`) to a
path-router (`app.slack.com/manage/<team_id>/analytics/channels`). The
old URL silently redirects to the analytics overview, where the
date-range-dropdown and tab-switch selectors don't exist.

## Timeline

| Date | Event |
|---|---|
| 2026-05-16 06:01 ET | Last successful export run |
| ~2026-05-17 | Slack changed the admin analytics URL pattern |
| 2026-05-19 06:00 ET | First failure (37 total failures through 2026-05-31) |
| 2026-05-31 ~14:30 ET | URL fix applied + verified |

## Impact

- 13 days of stale `slack-analytics_*` CSVs in the canonical
  analytics dataset
- `pulse compose-briefing` "top channels by traffic" component read
  stale data through the affected window
- Live `slack` CLI queries unaffected throughout
- Drive analytics + email analytics unaffected (independent pipelines)

## Root cause detail

Old URL: `https://concord-consortium.slack.com/admin/stats#channels`

New URL: `https://app.slack.com/manage/T02V91KU0/analytics/channels`

Slack's redirect did keep the user "logged in" (auth_state.json
remained valid), so the script reported `✓ Already authenticated` and
proceeded — but landed on the analytics overview page. From there:

- `a[data-analytics-tab="channels"]` (in-page tab) — not present on
  overview → timeout warning, then fallback
- `div[data-qa="analytics_channels-table-header-filter-button"]`
  (date dropdown) — only exists on the channels page → not found
- Script returned exit 1, service returned HTTP 500

Once the script navigates to the path-router URL, the channels/members
pages render with their original DOM and **the old date-dropdown +
export-button selectors still work** as-is.

## Fix

Three changes in `scripts/slack_analytics_with_dates.py`:

1. Added `import os` and `SLACK_TEAM_ID` constant (env-overridable,
   defaults to `T02V91KU0`)
2. Changed target URL from `{workspace}/admin/stats#{tab}` to
   `app.slack.com/manage/{team_id}/analytics/{tab}`
3. Removed the now-vestigial in-page tab click (the path-router lands
   on the right page directly)

Verification (2026-05-31 ~14:31 ET):
- channels export: `success: True`, CSV generation triggered
- members export: `success: True`, CSV generation triggered

Container picks up the change via bind-mount; no rebuild needed.

## Why it went unnoticed

- The slack-analytics-mcp-server logs `ERROR` lines on failure but
  nothing pages
- The Docker-side pulse-monitor agent still produced its morning
  briefing; the briefing just composed from stale block data without
  flagging "underlying CSV is N days old"
- Migration work was the focus through this window; the silent
  degradation wasn't on anyone's screen

## Hardening (also landed 2026-05-31)

New watchdog: `scripts/check-slack-analytics-export.sh` runs daily at
07:15 ET via `~/Library/LaunchAgents/com.ai-pa.slack-analytics-watchdog.plist`.

It greps the last 26h of container logs for "export succeeded" — if
none, it:

1. Emits a canonical signal `slack-analytics-export-failed` at
   attention=elevated (surfaces in the next morning briefing)
2. Attempts a Slack DM to @chad.dorsey (best-effort; depends on
   workspace token scope)
3. Logs to `logs/health/check-slack-analytics-export.log` and the
   per-run stdout/stderr files

To trigger ad-hoc: `bash scripts/check-slack-analytics-export.sh`.

## Debug artifacts captured

Snapshots from the failing 2026-05-31 run (preserved for the record):

- `/tmp/slack-analytics-debug/channels_today.html` — DOM of the page
  Slack redirected to (the new analytics overview)
- `/tmp/slack-analytics-debug/channels_today.png` — screenshot of same
- `/tmp/slack-analytics-debug/members_yesterday.{html,png}` — analogous

Inside the container, debug artifacts continue to land in
`/app/slack_analytics_screenshots/` with timestamped filenames.

## Backfill (2026-05-31)

Triggered via `scripts/backfill-slack-analytics.sh 2026-05-17 2026-05-30`
— 14 days × 2 types (channels + members) = 28 CSV exports, matching the
daily cron's 1-day window pattern. CSVs are sent to the workspace admin
DM as Slack file attachments.

Log: `logs/health/backfill-<timestamp>.log`

Downstream ingestion: as the pulse-monitor agent (or the user) walks
the resulting DMs, each CSV can be fed through `pulse slack-analyze
--url <slack-file-url>` to fold it back into the analytics block /
`analytics.daily_snapshots`. For the 8–30 day analytics window already
covered by the pulse recipe, the live `slack` CLI remains the
preferred path for ad-hoc rollups; the backfilled CSVs primarily exist
so the rolling averages and "top channels" tracker have continuous
data through the affected window.

## Open items

- [ ] Walk the backfill DMs and ingest the 28 CSVs via
      `pulse slack-analyze` (or wait for the morning briefing pipeline
      to pull them on its next pass)
- [ ] Consider similar URL-pattern watchdog for any other
      Playwright-driven services (none currently — auto-madden and
      sports-service use HTTP APIs, no scraping)
