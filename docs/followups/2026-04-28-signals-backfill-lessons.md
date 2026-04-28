---
date: 2026-04-28
status: lessons-from-implementation
companion_to: 2026-04-28-analytics-db-and-robustness.md, 2026-04-28-signals-roadmap.md
---

# Backfill Lessons — 2026-04-28 Session

What we learned implementing the first round of analytics + vibe-check backfills.
This is a record of the surprises, not a roadmap. The roadmap is in the companion docs.

## Key surprises

### 1. The Slack vibe-check capability had **never actually worked**

Every historical `system/daily_vibe_check_<DATE>.md` file in pulse-monitor's
memfs was a placeholder string ("unable to fetch per-channel Slack message
context"). The cron has been firing for months but the agent has been
silently emitting placeholders the entire time.

**Why this matters**: an apparent-healthy signal pipeline ("succeeded" cron
status, file written, frontmatter intact) had been producing zero actual
content. The Pattern 1 (health-signal emission) work is the right antidote,
but this case shows the failure mode goes deeper — the agent itself can be
"emitting" without producing useful content.

**Diagnostic that would have caught it earlier**: a length-check on emitted
signal bodies. A daily vibe check should be >300 chars; anything under that
is a placeholder. Trivially detectable by a steward.

### 2. Anthropic API account was at $0 balance

Discovered when trying to use the Claude API directly for vibe-check
summarization. The system has been routing all Claude calls through
LiteLLM proxy (which uses OpenAI for some providers). For backfill scripts
running outside the agent context, route through LiteLLM (`localhost:4000`)
or use OpenAI models. Don't assume direct Anthropic API access works.

**Action**: top up Anthropic credits OR keep routing exclusively through
LiteLLM and document this. The session's vibe-check backfill ran on
`gpt-4.1-mini` via LiteLLM (cheap, good summaries).

### 3. Sandbox vs. script timeout asymmetry

The Letta tool sandbox had a hardcoded 180s timeout, configurable via
`TOOL_SANDBOX_TIMEOUT` env var. **The backfill script also had its own
300s urlopen timeout**, separate from the sandbox.

Bumping just one of them isn't enough — both must agree. We bumped sandbox
to 600s and script to 700s. **Lesson**: any script invoking
`/v1/tools/run` should use `urlopen(timeout = sandbox_timeout + buffer)`.

### 4. "Apparent timeout" doesn't mean "no work happened"

When the script's HTTP read times out at 300s while the tool keeps running
in the sandbox, the tool can complete and persist to DB *after* the script
gives up. We saw 4/06 and 4/02 both write to DB successfully despite the
script logging "timeout."

**Lesson**: never trust the script's exit code as the source of truth on
DB state. Always verify by querying the target table after the run.

### 5. Channel selection matters more than script logic

First-pass priority channels (`#general-work-related`, `#directors`, `#info-tech`)
had near-zero activity over a 14-day window. Re-running with channels chosen
by **actual recent activity** (`#proposal-dev`, `#clue-dev`, `#pearls`,
proposal channels) produced substantive vibe checks immediately.

**Lesson**: when bootstrapping a "watch top channels" feature, derive the
list from `users.conversations` + `conversations.history` activity scan,
not from a static priority guess. The vibe-check script's
`DEFAULT_PRIORITY_CHANNELS` should be re-derived periodically (monthly?).

### 6. Slack quant data is bound to the rolling CSV window

`collect_analytics_snapshot(date='2026-04-08')` populates Drive + Email
correctly via Admin Reports (which lookback ~6 months), but **Slack
`slack_total_messages` shows the same value across all backfilled dates
because the Slack CSV is whatever's currently in Slack DMs from the
last `trigger_slack_analytics_export` run** — not date-specific.

**Lesson**: historical Slack quant via this path is unreliable. For
real backfill of Slack quant, we'd need to either:
- Use `conversations.history` per channel for each historical date and
  count messages directly (expensive but accurate)
- Persist CSV bytes durably at trigger-time so future backfills can
  reference the same date-bound CSV (the "Layer-1 raw retention" idea
  in `2026-04-28-analytics-db-and-robustness.md`)

For now the backfilled Slack-message counts in `analytics.daily_snapshots`
should be considered indicative-only, not authoritative.

### 7. Direct push beats agent for time-sensitive intra-day data

The agent-driven backfill (sending each date to pulse-monitor as an
agent_message) returned in 4-20 seconds with placeholder refusals
("I couldn't perform the requested backfill"). The direct API path
(slack-cli + LiteLLM + emit_canonical_signal) produced real content
in seconds.

**Lesson**: when the work is deterministic — fetch X, summarize Y,
write Z — bypass the agent. Use the agent for genuine judgment calls,
not for procedural workflows the agent itself struggles to execute
reliably.

This reinforces the heuristic in `feedback_capability_pattern_choice.md`:
**Skill + CLI-via-Bash beats a Letta tool for procedural work**, AND
**direct script beats agent for deterministic backfill**.

## What worked well

- **`emit_canonical_signal` as the universal write API** — used by both
  the new push handler (slackbot) and the direct backfill script. Same
  contract; same idempotent overwrite semantics. Proved its worth.
- **`agents-canonical/signals/<DATE>/<source>-<slug>.md` as the path
  contract** — naming convention plus git-backed storage means every
  emit is auditable. Re-runs are safe (sha-based PUT).
- **LiteLLM proxy for non-agent LLM work** — `gpt-4.1-mini` produced
  good 2-4 sentence per-channel summaries at ~$0.001 each. ~14 channels
  × 11 dates × 1 LLM call = 154 calls, total cost <$0.20.

## Outstanding follow-ups

1. **Re-run analytics backfill for any dates still missing after the
   current run completes.** Use the patched script with 700s urlopen.
2. **Decide on Slack-quant durability strategy**: persist CSVs at trigger
   time vs. accept rolling-window-only quant.
3. **Document Anthropic API key state**: top up or remove from .env.
4. **Add a daily steward check**: any vibe-check signal body <300 chars
   = placeholder; any pipeline-health signal with `status: failed` for
   >24h = surface to user.
5. **Retire the agent-driven vibe-check cron** in favor of a cron that
   invokes the direct-script approach. Cron-as-shell, not agent_message.
6. **Refresh `DEFAULT_PRIORITY_CHANNELS`** monthly: re-derive from a
   14-day activity scan via `users.conversations`. Bake into a
   `scripts/refresh-vibe-channels.py` helper.

## What we are NOT doing yet

- No CSV durable archive (Layer-1 raw retention) — deferred.
- No `analytics_raw` schema — deferred.
- No `collection_status` table — deferred (Pattern 1 handles for now).
- No automatic "vibe-check is broken" detection — deferred to steward.
