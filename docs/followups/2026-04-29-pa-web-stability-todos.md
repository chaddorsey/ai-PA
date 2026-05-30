---
title: pa-web-ui MC stability — open todos and shipped fixes
date: 2026-04-29
status: living document
related:
  - docs/diagnoses/letta-code-empty-approvals.md
  - pa-web-ui/approval_responder.py
  - pa-web-ui/Dockerfile
  - letta-memfs-patches/patches/apply_letta_code_empty_approvals_fix.py
---

# pa-web-ui MC stability — open todos and shipped fixes

Comprehensive record of the 2026-04-29 deep-dive into pa-web-ui's letta-code
subprocess + MC tool surface + canonical/memfs alignment. Captures both
shipped fixes and the explicit follow-up queue going forward.

## Shipped today (in dependency order)

| # | What | Where it landed |
|---|---|---|
| 84 | Slackbot listener for analytics CSVs (later superseded by xoxp poller — listener kept as harmless leftover) | `slackbot/listeners/events/analytics_csv_capture.py`, `slackbot/manifest.json` |
| 88 | Pipeline-health emission for the 4 stale agents (calendar-agent, tasks-agent, mc, daily-schedule-agent) — daily 06:30 ET self-check crons + steward rollup at 06:45 | scheduler-service crons; `system/duties` block on steward |
| 90 | Auto-approval responder for letta-code's empty-approvals subprocess crash. **Later disabled (race-loss false positives)** but kept as belt-and-suspenders | `pa-web-ui/approval_responder.py`, `pa-web-ui/tests/test_approval_responder.py` (42 tests) |
| 93 | Race-loss vs subprocess-crashed disambiguation in the responder classifier | `classify_race_loss()` in approval_responder.py |
| 95 | Signals heartbeat producing `agents-canonical/digest/recent_signals.md` hourly | `scheduler-service/scripts/signals-heartbeat.py` + cron `0 6-23 * * *` ET |
| 97 | letta-code 0.23.8 → 0.24.10 bump + 4 bundle patches + memfs enabled in pa-web subprocess | `pa-web-ui/Dockerfile`, `docker-compose.yml`, `pa-web-ui/subprocess_pool.py` |

Plus several smaller landings:
- **gws CLI installed in pa-web-ui** + credentials volume mounted; `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` allowlisted in subprocess env
- **execute_on_laptop + manage_widget_queue + 22 historical tools reattached** to MC (pre-session reduction had left it at 2). Recovery primitive documented in `~/.claude/.../memory/feedback_tools_attach_endpoint.md`.
- **Bundle patch trio applied** to pa-web's letta-code:
  - `apply_letta_code_self_hosted_handle_fix.py` (#3205 handle resolution; 8 markers)
  - `apply_letta_code_memfs_external_git.py` (memfs against Gitea; 3 markers)
  - `apply_letta_code_empty_approvals_fix.py` (subprocess-survival on empty approvals; 3 markers)
- **Protocol patches** to remove memfs-assumption Read calls and replace with Bash+curl per canonical_reference_protocol:
  - `system/scheduling_protocol` — apply via `gws calendar events patch` (was: curl googleapis directly)
  - `system/find_from_person_protocol` Step 1 — Bash+curl to canonical digest (was: Read the digest as a memfs path)
  - `system/signals_protocol` — Bash+curl to canonical (was: Read the digest, use `read_recent_signals` legacy tool)
  - `system/shared_context` — pointer table updated to reflect canonical paths
- **Daily-schedule script (in `letta-code/.scripts/schedule`) rewritten** to read from canonical signals/{date}/schedule.md (was: stale memfs ~/.letta/agents/<MC>/memory/schedule/today.md). Subrepo commit `f3113c4`.
- **Auto-approval responder disabled** at the call site after the bundle patches + bypassPermissions made it redundant + harmful (false-positive "stranded" errors). Module + tests retained for future regressions.
- **Daemon config**: `analytics_raw` Postgres schema + raw-archive directory created; analytics CSV daily poll wired (`scheduler-service/scripts/slack-analytics-csv-poll.py` + `parse-slack-analytics-csv.py` → silver tables `slack_channel_daily` + `slack_member_rollup`).

## Open queue (pending tasks, ordered by priority)

### High priority — directly affects user-visible behavior

**#86 — Fix `collect_analytics_snapshot` "0 active members" bug.**
The Letta tool reports `slack_members_active=0` in `analytics.daily_snapshots` even when the source CSV shows real numbers. Affects ~14 days of recent slack data. Fix the tool's CSV parsing logic, then re-run for affected dates. Slack-section backfill is GATED on this fix (see #89).

**#94 — Investigate spurious "another device is composing" 409s.**
On 2026-04-29, frontend received 409 turn_locked while server-side state showed `in_flight=False, forking=False` for all handles. Restart cleared it. Reproduce path: send a message that triggers a tool the subprocess will fail on; watch for crash; send follow-up; check whether 409 fires spuriously. If reproducible, fix is likely in the in_flight=False reset path on subprocess crash.

### Medium priority — capability completion

**#85 — Schedule lookahead Stage 2.**
Replace per-day LLM call with a pure-Python schedule builder; add cross-tabulation tool (`query_available_time(start, end, min_duration)`); dirty-day recompute via Calendar Activity API. Format decision baked in: YAML frontmatter as machine truth, markdown body rendered from it. Pick up after Stage 1 has run for a week (~2026-05-06).

**#89 — Resume drive+email backfill fan-out.**
68 gap-days in last 180 identified. Earlier fan-out attempts overloaded Letta. Resume safely with `--max 5 --throttle-ms 30000` (5 calls every 30s) so Letta has time to process each. Total ~7 min for full 68. Idempotent.

**#92 — Deprecate `run_gws` Letta tool — migrate to Bash + gws CLI.**
Per MEMORY note `feedback_capability_pattern_choice` ("default to Skill + CLI-via-Bash"). MC's scheduling_protocol already uses `gws` directly via Bash. Wider audit: calendar-agent_copy, pulse-monitor, daily-schedule-agent, tasks-agent likely still reference `run_gws`. After migration, retire the gws-bridge service container.

**#96 — Migrate `run_slack` and `read_recent_signals` to Bash+CLI.**
Same shape as #92. find_from_person_protocol still references both. Verify slack CLI is installed in subprocess; if not, install. Replace per-protocol references; detach tools after each agent migrated.

**#98 — Strategic tool-inventory audit + skill/CLI migration pass.**
The umbrella for #92 + #96. Classifies every Letta tool as KEEP-AS-TOOL / CONVERT-TO-SKILL / REPLACE-WITH-BASH+CLI / RETIRE-COMPLETELY. Reduces system-prompt token cost across all agents. Subsumes #92 + #96 once a per-agent audit lands.

### Low priority — hygiene

**#91 — Decide pa-web-ui gws install: build-time vs entrypoint.**
Current build-time install requires `docker compose up -d --build` to upgrade gws. Letta uses entrypoint hook (`docker compose restart` is enough). Recommend build-time for now; revisit if gws upgrades become time-sensitive.

### Architectural / domain (deferred from earlier in session)

**E (project files)** — the genuinely-deferred conversation thread.
Discussion not yet started. Framing questions on the table:
- What is a "project" in canonical? (Slack-channel-anchored, funded-work-anchored, both, calendar-anchored)
- Where does data come from? (Slack channel scan, manual curation, hybrid)
- What does the agent ecosystem do with project files? ("status of #X", "who's working on Y", "next milestone for Z")
- Privacy / scope boundary
- Entry point: build seed list from existing `top_shared_channels` data, or start with manual 5-10

## Cleanup follow-ups (low effort, opportunistic)

- **Remove TRACE-SKILL debug markers** from the bundle on next rebuild. Currently 5 markers in `pa-web-ui/letta.js`. Harmless but unnecessary now that the diagnosis is complete.
- **Re-enable auto-approval responder** if a future letta-code regression brings back the empty-approvals path. Module + 23 tests still on disk; uncomment the call site in `subprocess_pool.py::_emit`.

## Diagnostic hooks (still in place)

- `pa-web-ui/approval_responder.py` — module + classifier still importable; just not called from `_emit`.
- `[PATCH-EMPTY-APPROVALS]` console.error in the bundle (3 markers) — fires if the empty-approvals path is ever reached. Surfaces as `console.error` in pa-web container logs.
- `pa-web-ui/tests/test_approval_responder.py` — 23 unit tests covering policy, dedup, classifier outcomes, synthesis. Pass.
- `docs/diagnoses/letta-code-empty-approvals.md` — full diagnosis writeup for future-us + upstream Letta team.

## Structural state at end-of-day

| Layer | Status |
|---|---|
| pa-web-ui letta-code version | 0.24.10 (matched to host's letta-code-patched) |
| Bundle patches | 4 applied: #3205 (8 markers), MEMFS-GIT (3), EMPTY-APPROVALS (3), TRACE-SKILL debug (5; remove next rebuild). exitHeadless removed (0 occurrences). |
| memfs in pa-web subprocess | enabled (`memfs_enabled: true` in spawn init) |
| gws CLI in pa-web | 0.22.5 installed, credentials mounted, env allowlisted |
| MC tool surface | 27 attached (web_search, fetch_webpage, emit_canonical_signal, execute_on_laptop, manage_widget_queue, archival_memory_*, conversation_search, run_gws/slack/etc, get_meeting_*, search_*, etc.) |
| Auto-approval responder | disabled at call site (false-positive race-loss); kept as backup |
| Pipeline-health emission | live for all 5 worker agents; steward rollup at 06:45 ET |
| Signals digest heartbeat | hourly 6 AM – 11 PM ET writing canonical/digest/recent_signals.md |
| Daily schedule script | reads canonical signals/{date}/schedule.md (was: stale memfs) |
| Slack analytics → silver | poll + parse cron live; silver tables populated; member privacy boundary respected (aggregate-only rollups) |

## How to use this doc

When picking up a queued item, find its number above, read the related code/files, and update the status in this doc and in `~/.claude/.../memory/MEMORY.md` if the change affects how the system should be used going forward. When new follow-ups surface in MC sessions, append them to the "Open queue" section with the same number-or-letter scheme.
