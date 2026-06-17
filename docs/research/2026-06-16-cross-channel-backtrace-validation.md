# Cross-Channel Backtrace — E2E Validation (Vernier SOW)

**Date:** 2026-06-16
**Task:** `fcdf4afb-a` ("Review Vernier module/philosophy docs and draft a scoped SOW")
**Plan:** `docs/plans/2026-06-16-cross-channel-backtrace-plan.md`
**Design:** `docs/plans/2026-06-16-cross-channel-backtrace-design.md`

## What was validated

Confirming a task triggers an async cross-channel backtrace (push → local tasks-agent
`agent-local-30c45759` running the `cross_channel_backtrace.md` memfs recipe) that grounds
in memory, fans out via `task xsearch` across Drive/Slack/Gmail/tasks/meetings/canonical/
history/reference, judges + tiers the hits, and writes a tiered Primary/Supporting/Related
resource set — the exact gap from the design's motivating example.

## Before

The packet had **2 resources, 1 host** (only the originating Granola meeting note):

```
[primary]   Granola meeting permalink — notes.granola.ai/d/a6edb157…
[secondary] Meeting notes (offline copy) — notes.granola.ai/… | offline: openfile://…
```

## After (backtrace run)

**11 resources across 3 distinct hosts** (notes.granola.ai, concord-consortium.slack.com,
mail.google.com), tiered:

- **Primary** — Granola source meeting; Slack: high-level SOW draft shared to Kiley+Dan.
- **Supporting** — Slack status thread moving the Vernier SOW forward; Slack pointer to the
  follow-up Granola notes; Granola "Vernier & Concord Follow-up" notes; Slack coordination
  note about emailing the draft SOW to Matt K; **three Gmail Google-Docs comment
  notifications for "Vernier Curriculum Development SOW – July 2026"** (the prior SOW doc).
- **Related** — Slack prior-SOW-revision thread (pattern/reference); neighbor task
  `6ddc5c1f` ("Send proposal w/ numbers + timelines to Vernier early next week").

Channels hit: Granola (meetings), Slack, Gmail. `failed_channels` empty after the fix below.
The agent honestly flagged in `unknowns` that it could not obtain the raw Drive Doc ID for
the SOW (only Slack + Gmail point to it) — no fabrication.

## Eval loop untouched

`original_est_minutes=180, revised_est_minutes=45, actual_minutes=NULL` — unchanged before
and after. The backtrace writes only the `enrichment` jsonb column.

## Backstop

`scripts/check-packet-enrichment.py --dry-run` flagged thin packets 4 → 3 after enrichment;
the Vernier task dropped out of the thin set (now multi-channel).

## Bug found + fixed during validation

The first run produced a single-channel packet (`backtrace_hits=0`). Root cause: `xsearch`'s
`gws` adapters failed with "No credentials provided" because the launchd warm-pool runner
does not carry `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` from `pa-tools.env`, so Drive + Gmail
returned nothing and the agent never saw the prior SOW. Fix (commit `84f2ae6a`):
`_gws_json` now self-defaults the repo-relative `gws-bridge/credentials.json` when the env
var is absent (same lesson as other host CLIs shelled out under the runner); `_search_qmd`
retries once on transient concurrent-sqlite failures. Re-run produced the full tiered packet
above.

## On-device render

The Primary/Supporting/Related grouping is covered by `pa-web-ui/tests/test_work_packet_segments.py`
(16 tests, incl. tier grouping + dual-link preservation). The OF note refreshes via the
standard confirm/reassemble path; the manual reassemble API correctly rejects non-browser
origins (CSRF), so render fidelity is asserted via the unit suite.
