# Enrichment-loop context lifetime — fix via App Server + per-task conversation

**Date:** 2026-08-12
**Author:** Chad Dorsey + PA assistant
**Status:** Approved direction (B), pre-implementation (one spike task outstanding)
**Component:** `letta-push-receiver` (`warm_pool.py` → App Server client), `scheduler-service` enrichment loop, `pa_web.tasks`
**Supersedes:** the initial "external kill/respawn recycle" draft in this file's history — see *Why not the recycle guardrail* below.

---

## Problem

The task **enrichment loop** silently stopped producing enriched work packets from
**~2026-07-24 through 2026-08-09** (~2.5 weeks). Root cause is fully diagnosed and
confirmed against Letta support guidance (2026-08-12).

### Pipeline recap

Detectors → `pa_web.task_queue` → rows created in `pa_web.tasks` with
`enrichment_state='pending'` → the **enrichment-scanner**
(`scheduler-service/scripts/enrichment-scanner.py`, every 30s) claims one pending row,
marks it `in_progress`, and dispatches a source-aware enrichment prompt to the
**tasks-agent** via the **push-receiver** (`http://host.docker.internal:8099/push`). The
agent is expected to run the enrichment chain and call `write_packet_info`, which flips
the row to `enrichment_state='done'`. If it never does, `recover_stuck_rows()` times the
row out after 20 min, bumps `enrichment.retry_count`, and reverts to `pending`; after 3
retries the row is set to `enrichment_state='failed'`.

### Root cause

The push-receiver runs **one long-lived `letta` stream-json subprocess per agent** and
feeds every task into it over stdin. Per Letta support: `--new` runs **only at startup**,
so **every stdin task enters the same conversation** — the wrong isolation boundary for
unrelated jobs. Context therefore accumulates without bound across hundreds of pushes.

The tasks subprocess that started **2026-07-12** grew until it crossed the model window:

- Model `gpt-5.2`, window **272,000** tokens; compaction pressure begins above
  **255,616** (16,384 reserved), preflight and post-turn; overflow gets at most **3**
  compact/retry passes.
- By ~07-24 the conversation exceeded the window. Every later push threw
  `litellm.ContextWindowExceededError` (HTTP 400), reporting 375,771 → 378,418 input
  tokens across successive attempts.
- **Compaction failed to recover it** — a pathological no-op compaction bug (no public
  issue found; confirmed plausible by support). **Runtime caveat:** the wedged resident
  started **2026-07-12** and a resident process never hot-updates, so it ran a
  **pre-0.30.19** letta-code (0.30.19 was installed here **2026-08-12 03:00**). The
  behavior below is therefore an *older* runtime; 0.30.19 carries a Jul-26
  preflight/usage-estimate fix that keeps a *fresh* conversation off the edge, but the
  sliding planner's missing "must make meaningful progress" guard is **unchanged** in
  0.30.19 (still bug-worthy).
  - Compaction worked **early** (e.g. 249,497 → 192,081 tokens, 279 → 169 messages — a
    real multi-message cutoff) and **degraded once the transcript grew huge**: from
    2026-08-07 onward every `context_window_overflow` compaction became a **cutoff-index-1
    no-op** (253→253 … 259→259 messages, ~110 tokens each) while context climbed
    364,522 → 373,118 — each failed task persisted one more user message, so the wedge
    *grew*. Emitted summaries stayed small (~3,830–4,977 chars ≈ ~1k tokens), which
    **rules out a "huge summary" cause**.
  - Support's mechanism: compaction stats count *stored messages only* (system/MemFS/
    tool-schema overhead excluded — provider input minus compaction-before was only
    ~9.8k); sliding compaction inserts one summary so evicting one message reports N→N;
    and the planner **accepts** cutoff-1 without a meaningful-progress check → repeated
    near-no-op compactions that exhaust the 3 retries.
  - **Fields the runtime did *not* emit** (support asked): `compaction_stats` had no
    `context_window`; no `compaction_settings` (mode / sliding_window_percentage /
    clip_chars); `init` had no version string. Overflow also triggered as low as
    context_tokens_before = 249,497 (below the 255,616 pressure point for a true 272k
    window) — another old-runtime/effective-window discrepancy.
- Every run therefore returned `subtype: error`, `num_turns: 1`, empty result, **zero
  tool calls** → `write_packet_info` never ran → scanner timed out → 3 retries → `failed`.

**87 tasks** failed enrichment in the window, all stamped `{"retry_count": 3}`.

### Telemetry facts (from support + our logs)

- `result.usage` is **hardcoded `null`** in bidirectional 0.30.19 — do not use it.
- The usable live signal is the `type:"message", message_type:"usage_statistics"` event,
  field **`context_tokens`**. In the failure log it grew steadily and **maxed at 122,506
  (2026-07-24T15:30, last successful run)**, then stopped emitting once preflight overflow
  began — while `compaction_stats.context_tokens_before` two weeks later read **365,953**.
  The ~3× divergence corroborates the "stored-messages-only vs full-request" accounting.

### Why it "recovered" on 2026-08-11

The wedged subprocess finally died and the pool lazy-respawned a fresh one → clean
conversation → 5/5 enrichments succeeded. Luck, not a fix: the current subprocess is the
same agent/conversation and would re-wedge in weeks.

### Non-issues (ruled out)

- **`note_render` HTTP 400 on every `packet-write`** is **benign** — the reassemble
  endpoint (`pa-web-ui/app.py`) returns 400 by design when a task has no `omnifocus_id`
  or `status != 'confirmed'`. Enrichment runs at `status='extracted'`, so the task is not
  in OmniFocus yet. `packet-write` still succeeds (`enrichment_state='done'`). Cosmetic
  nit: packet-write labels that expected 400 as `"error"`.
- **0 tasks in OmniFocus in 40 days** is **disuse** — tasks reach OF on user confirmation,
  and none have been confirmed recently.

---

## Decision

Adopt the **intended Letta pattern (option B)**: run a **warm App Server** and give each
enrichment task a **fresh conversation/session**, with MemFS remaining agent-wide.

### Why not the recycle guardrail (rejected option A)

The initial draft added an external context/push/age recycle to `warm_pool.py`. Support
made clear that "one conversation per subprocess, many unrelated tasks" is the wrong
boundary; recycling only guards a mis-designed pattern and re-pays a cold start
(prompt-cache + MemFS reload) on every rollover. Stream-json also exposes **no**
reset/new/compact/max-turns/idle control, so within it "rollover" *is* a respawn. The App
Server rolls over **without recycling the runtime process**. Given you explicitly want to
build with — not against — the platform, B is the correct target. The loop is currently
healthy (fresh subprocess since 08-11; weeks before re-wedge), so there is no pressure to
ship the guardrail as an interim.

---

## Design

### Runtime

The push-receiver supervises a warm **`letta server --listen`** App Server (loopback →
no auth needed) as the resident runtime, replacing the per-agent long-lived stdin
subprocess. Launch env carries the same curated credentials/paths the current
`_build_agent_env` provides (POSTGRES_PASSWORD, `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`,
`LETTA_LOCAL_BACKEND_DIR`, `PA_AI_REPO_ROOT`, `PA_WEB_POSTGRES_PORT`, MemFS/Gitea token,
Slack/GitHub/Granola tokens). MemFS stays agent-wide, so per-agent memory/recipes are
unchanged.

### Dispatch (per push)

For each `/push`, the receiver:
1. Opens a **fresh conversation/session** for the target agent against the App Server.
2. Sends the enrichment prompt.
3. Streams to completion; the agent runs its normal tool chain
   (`fetch_source_content` → optional `backtrace_task` → `task stage` →
   `write_packet_info`), which flips `enrichment_state='done'`.
4. Discards the conversation. Next task starts clean — **no cross-task accumulation, so no
   wedge is possible by construction.**

Serialization (one task at a time per agent) and the fire-and-forget contract the scanner
depends on are preserved.

### Observability

Monitor `usage_statistics.context_tokens` per run for telemetry/health only (a single
task's conversation should never approach the window; a run above, say, ~200k signals a
pathological single task — log loudly). This is a sanity check, **not** a recycle trigger,
since per-task conversations don't accumulate.

### Open questions — resolved by Spike (implementation Task 0)

The App Server is a WebSocket server (`--listen`) with an optional OpenAI-compatible HTTP
API (`--openai-api`: `/v1/chat/completions`, `/v1/responses`, each agent as a "model").
letta-code ships compiled (no App Server API docs in-tree), so a live probe must confirm,
**before** the port work:

1. **Dispatch surface.** Does `--openai-api /v1/chat/completions` (or `/v1/responses`)
   run the agent's **full tool loop** (tools actually execute) and behave
   **stateless-per-call** (fresh context each request)? If yes, that is the simplest
   Python-native dispatch from the (Python) push-receiver and inherently gives fresh
   context per task.
2. **Else** use the WebSocket App Server with an explicit **new conversation/session per
   task** (the Agent SDK `createSession(agentId)` shape). Determine the minimal
   Python-side protocol or whether a small TS sidecar is warranted.
3. **Env/MemFS propagation** to the server process; confirm gws/postgres creds reach tool
   execution (the 2026-06-10 `_build_agent_env` lesson).
4. **Auth** — confirm loopback needs none; document token flow if we ever bind non-loopback.

The spike picks (1) or (2) and pins the exact request/response shape the receiver will use.

### Migration / fallback

Keep the existing `warm_pool.py` stdin path in place until the App Server dispatch is
validated end-to-end on real enrichments; cut `/push` over behind a receiver config flag;
remove the stdin path once steady-state is confirmed. launchd `com.ai-pa.letta-push-receiver`
supervises the App Server lifecycle (start-if-absent, restart on death) the same way it
currently owns the warm pool.

### One-time remediation — requeue orphans

Idempotent SQL (committed under `scripts/`) requeues the outage survivors so the healthy
loop enriches them:

```sql
UPDATE pa_web.tasks
   SET enrichment_state = 'pending',
       enrichment = (COALESCE(enrichment, '{}'::jsonb) - 'retry_count'),
       updated_at = NOW()
 WHERE enrichment_state = 'failed'
   AND status = 'extracted'
   AND closed_at IS NULL;
```

Expected ~27 rows (the `status='extracted'` guard excludes the 60 `failed`+`rejected`).
Run once, after the new dispatch is deployed and verified; the scanner drains them at one
per 30s cycle.

---

## Error handling

- **App Server death:** launchd/receiver supervises and restarts it; an in-flight push
  fails and the scanner's existing timeout/retry re-dispatches — no new loss.
- **Session/conversation-create failure:** surface the error; scanner reverts the row to
  `pending` (existing behavior) and retries next cycle.
- **Single-task context blow-up (pathological):** logged via the `usage_statistics`
  sanity check; the task fails and retries, but cannot poison other tasks (isolated
  conversation).

## Testing

- **Spike acceptance:** a scripted App Server call runs a real enrichment end-to-end for
  one `ref_id` — tools execute, `write_packet_info` fires, row → `done` — and a second
  call for a different `ref_id` shows **no context carryover** (its `usage_statistics`
  starts near-baseline, not cumulative).
- **Dispatch unit tests:** receiver builds the correct per-task request; handles
  create-failure → error; parses completion → status.
- **e2e:** dispatch several tasks back-to-back; assert each reaches `enrichment_state='done'`
  and per-task `context_tokens` stays flat across tasks (the core proof the wedge is gone).
- **Remediation:** dry-run the requeue `SELECT` (~27 rows), run the UPDATE, watch them
  drain to `done`.

## Rollout

1. Spike (Task 0) → pick dispatch surface, pin request shape.
2. Implement App Server supervision + per-task dispatch behind a receiver flag; keep stdin
   path as fallback.
3. Validate e2e on live enrichments; confirm flat per-task context.
4. Cut `/push` to the App Server path; run the one-time orphan requeue.
5. Remove the stdin warm-pool path after a clean steady-state window.

## Runtime-version requirement

The wedge behavior came from a **pre-0.30.19** resident. Our App Server (and any warm
runtime) MUST run **verified 0.30.19** (installed 2026-08-12 03:00). Both current warm
residents (07-12, 08-11) predate that install and are stale; restarting the push-receiver
so residents/the App Server come up on 0.30.19 is a precondition for the canary and for
steady state. Per-task fresh conversations sidestep the still-unfixed meaningful-progress
gap regardless.

## Upstream follow-up (file with Letta)

Report the **pathological cutoff-1 no-op compaction** — present as the missing
"meaningful-progress" guard, still unfixed in 0.30.19 (no public issue exists). The
resident that produced it ran a pre-0.30.19 build, so frame it as: *does the 0.30.19
sliding planner still accept cutoff-1 on a very large transcript?* Data payload for
support (they will draft the GitHub issue): the full compaction timeline showing
healthy → cutoff-1-no-op degradation (249,497→192,081/279→169 msgs early; 253→253 …
259→259 / ~110 tokens late while tokens climb 364,522→373,118, +1 message per failed
task); emitted summary lengths (~3,830–4,977 chars, i.e. *not* huge); the **absence** of
`compaction_stats.context_window` and `compaction_settings` (mode/sliding_window_percentage/
clip_chars) and of a version field in `init`; overflow triggering at 249,497 (< the
255,616 pressure point for a true 272k window); and resident start 2026-07-12 vs 0.30.19
install 2026-08-12 03:00. Recommended: restart into verified 0.30.19, run a fresh-conversation
canary, preserve the old logs as evidence. This is the true upstream defect; our design
routes around it rather than depending on it.
```
