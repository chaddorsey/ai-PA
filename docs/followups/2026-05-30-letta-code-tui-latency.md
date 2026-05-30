---
date: 2026-05-30
status: root-caused
severity: blocking-user-facing-local-mode
agents_affected: all local-mode agents (Docs pilot surfaced it)
root_cause: OpenAI prompt-cache cold-start on every >5min-gap turn
related:
  - docs/runbooks/letta-local-mode-per-agent-migration.md
  - docs/plans/2026-05-25-letta-code-local-mode-investigation.md
---

# Letta Code TUI latency — root cause

## TL;DR

**The TUI is not slow.** Cold calls to OpenAI's `gpt-4.1-mini` with the
agent's ~12K-token prompt take ~25s due to prompt-cache misses; warm calls
take 5-7s. OpenAI's prompt cache has ~5min TTL. TUI inter-prompt gaps usually
exceed that, so every TUI step pays the cold-cache penalty.

Three viable fixes (see Resolution path).

## Symptom

Running `letta --backend local --agent <id> --conversation default` against
the `lmstudio/gpt-4.1-mini/docs` model handle produces **25-50 second per-step
latency** for every tool call and assistant response. Headless `-p` mode is
fast (single response in ~4s). The TUI is unworkable as a primary chat
surface in this state.

User feedback: *"laughably, unbelievably, laggy and high latency"*.

## Measurements (from docs-and-transcripts-agent-local TUI session, 2026-05-30 17:06-17:14)

Extracted from `~/.letta/lc-local-backend/conversations/default:.../messages.jsonl`:

| Step | Wallclock |
|---|---|
| `granola list --help && granola list` tool call → result | ~36 s |
| `Edit` on system/human.md → result | ~45 s |
| Result back → next assistant tool call | ~25 s |
| `git commit` failure → assistant apology text | ~32 s |

Pattern: every model turn (whether decision-making or response composition)
takes 25-50 s in TUI. Comparable headless invocations of the same agent +
model in Phase E completed in 4-7 s for single-turn responses.

## Hypotheses to investigate (in order)

### H1: LiteLLM proxy serialization (Prisma DB lock)
LiteLLM's Prisma watchdog has been known to brick all chat completions
for hours when its DB connection wedges (per memory entry on LiteLLM health
monitoring). The TUI may be hitting this slow path while `-p` mode hits a
different code path.

**Test**: tail `docker logs litellm` during a TUI session; look for slow
request log lines, DB-lock warnings, or per-request latency spikes.

```bash
docker logs litellm -f --tail 0 2>&1 | grep -iE "slow|lock|timeout|prisma|warning"
```

### H2: gpt-4.1-mini at OpenAI is just slow today
The litellm alias `lmstudio/gpt-4.1-mini/docs` resolves to OpenAI's
`gpt-4.1-mini`. OpenAI rate limits or model cold-starts could account for
seconds, not 30-second per-step delays — but worth ruling out.

**Test**: swap the agent's model handle to a Claude or Constellation-hosted
fast model and re-measure. Or hit `openai/gpt-4.1-mini` directly via curl
from the host to baseline raw model latency.

```bash
# Bypass litellm, hit OpenAI directly
time curl -sS https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"reply with the single word OK"}],"max_tokens":5}'
```

### H3: TUI render pipeline overhead
letta-code's TUI (terminal rendering, streaming display, tool-approval UX)
may serialize work that the headless `-p` mode skips. Could be a render-
blocking loop or a sync delay between assistant chunks.

**Test**: run the same prompt three ways and compare:
1. `letta --backend local --agent <id> -p "<prompt>"` (headless)
2. `letta --backend local --agent <id> --output-format stream-json -p "<prompt>"` (stream-json headless)
3. `letta --backend local --agent <id> --conversation default` interactive (TUI)

If 1 + 2 are fast and 3 is slow, the TUI render is the culprit.

### H4: Approval round-trips even with --yolo (unlikely but possible)
Each tool call going through stop_reason=requires_approval → executeApprovalBatch
→ resume cycle adds 2-4 server roundtrips. Per existing memory entry
(`feedback_letta_code_approval_flow.md`), `--yolo` bypasses user prompts
but NOT server-side approval state machine. In local mode there's no server,
but the same state machine may still run locally and serialize.

**Test**: try `letta --backend local --agent <id> --yolo --conversation default`
and measure the same prompts. If approvals are the issue, --yolo should be
near-identical to headless.

### H5: Conversation history compaction or large system prompt
docs-and-transcripts-agent's system prompt (incl. 7 imported memfs files
projected into context) is large. If TUI re-sends the entire conversation +
all memory blocks on every turn while headless doesn't, that's a per-turn
overhead amplifier.

**Test**: spawn a fresh conversation against the same agent in the TUI
(empty history) and measure first-turn latency. Compare to a long-history
conversation.

## Investigation results (2026-05-30)

H1 (LiteLLM serialization) — **ruled out**. LiteLLM logs are clean (200 OK,
no retries). Direct LiteLLM call: 0.95s.

H2 (gpt-4.1-mini slow at OpenAI) — **ruled out**. Direct OpenAI call: 1.19s.
LiteLLM call: 0.95s. Streaming + tool definitions + larger context: 0.45s.

H3 (TUI render overhead) — **ruled out**. Headless mode with one tool call
is just as slow as TUI on a cold start.

H5 (long conversation history) — **ruled out**. Headless against the
38-message `default` conv: 2.6s. History size doesn't drive the latency.

### What actually showed it

Three consecutive headless tool-using prompts:

| Run | duration_ms | duration_api_ms | Notes |
|---|---|---|---|
| 1 (cold) | **32,874** | 26,603 | First call after idle |
| 2 (warm, +30s) | 6,059 | 4,800 | Within OpenAI cache TTL |
| 3 (warm, +60s) | 7,764 | 7,288 | Still warm |

`cached_input_tokens: 28,672` on warm calls — OpenAI's prompt cache IS
working. The issue is its 5-10 minute TTL: when a TUI user takes >5min
between prompts (typing, reading, thinking), every step pays the cold cost.

### Why direct curl-to-LiteLLM didn't reproduce it

My benchmark calls used a tiny prompt. The agent's real-world request
includes:

- 9,301-char Letta Code system prompt
- ~12,000-token memfs context (7 imported files + scaffolded human.md
  projected into context every turn)
- 11 tool schemas (Bash, Edit, Read, Skill, Agent, memory, etc.)

That total (~12K input tokens) hits the cold-start penalty hard on
`gpt-4.1-mini`. Smaller prompts cache and respond fast.

## Resolution path

Three fixes, listed by effort:

### Fix A — Trim baseline context (~2-4 hrs)

Reduce the 12K-token per-turn prompt overhead to <5K. Audit what's in the
agent's system/ directory + scaffolded human.md and remove what's not
load-bearing. Smaller prompt → smaller cold-cache penalty.

### Fix B — Switch to a faster model handle (~30 min)

Try `claude-haiku-4-5` or another model with different cache behavior. Some
providers have different prompt-cache TTL and warm-up costs. Anthropic's
prompt cache has 5-min and 1-hour tiers — 1-hour cache TTL would solve the
TUI inter-prompt gap problem.

### Fix C — Subprocess-pool pattern for local-mode (~3-5 hrs)

This is what pa-web-ui already does for Docker mode: keep ONE letta-code
subprocess alive per conversation, feed it stream-json over stdin. Cache
stays warm because requests are seconds apart (same connection, same
process). Extending this to local-mode also resolves the deferred Option A
(pa-web-ui local-mode routing).

This is the "right" fix architecturally — it solves both the TUI latency
AND the user-facing surface problem at once.

## Recommended order

1. **Try Fix B first** — cheapest, may resolve the felt-experience issue
   immediately. Swap docs-agent-local's model handle to a different fast
   model and re-measure.
2. **If B isn't enough, do Fix A** — trim the agent's baseline context.
   This benefits everyone (faster cold + warm + cheaper inference) and is
   directly aligned with alignment item I-quater (migrate operational
   knowledge out of archival into right-sized memfs).
3. **Plan Fix C** as the proper long-term answer. Will be needed before
   Calendar / Tasks / Email migrations anyway, and definitely before MC.

## Out of scope until resolved

- pa-web-ui local-mode routing wire-up (deferred per Option C earlier; Fix C
  resolves this in the same workstream)
- Phase H switchover for Docs agent
- Subsequent agent migrations (Calendar, Tasks, etc.)

Local mode without a workable interactive surface degrades to "cron + one-shot
headless only", which is fine for some agents (Pulse, daily-schedule) but
breaks the case for migrating Docs / Calendar / Tasks / Email / MC. Resolving
this is on the critical path for the rest of the migration arc.

## Cross-references

- See [feedback_letta_code_approval_flow.md] memory entry for the related
  approval round-trip pattern (orthogonal to this latency issue but adds
  similar inter-step overhead).
- See pa-web-ui subprocess_pool.py architecture as the template for Fix C.
