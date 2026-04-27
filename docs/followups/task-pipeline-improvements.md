---
date: 2026-04-27
status: open
owner: chad
related:
  - docs/plans/2026-04-26-001-feat-pa-organizational-memory-cycle1-plan.md
  - letta/fetch_source_content_tool.py
  - letta/refine_task_description_tool.py
  - letta/write_packet_info_tool.py
  - scheduler-service/scripts/enrichment-scanner.py
  - slackbot/listeners/shortcuts/send_to_tasks.py
---

# Task pipeline improvements

Living list of refinements to the cycle-1 task extraction + enrichment chain.
Surfaced during initial pipeline restoration soak (post-2026-04-27 cutover).
Not blocking; queued for a focused pass.

## 1. Weight the user-signaled message highest in Slack enrichment (SHIPPED 2026-04-27)

**Symptom**: when a Slack message is sent to tasks via the "Send to Tasks"
shortcut and enrichment runs, the agent has been observed picking a *different*
message in the thread (or a nearby channel message) as the focal task. Example:
`a350fc9a` re-enrichment shifted the focal task from the user-clicked Kate
Miller reschedule message to a CODAP scheduling message elsewhere in the thread.

**Cause**: `fetch_source_content` was actually NOT fetching the anchor
message's text at all — it returned only `[THIS MESSAGE] ts=…` (no body) plus
the surrounding thread + ±3 channel context. The agent had to guess the focal
task from ambient messages because the anchor itself was missing from the
bundle. Compounded by no anchor weighting in the dispatch message and no
guard against topic drift in `refine_task_description`.

**Shipped fix** (three layers):
- `fetch_source_content` slack branch now explicitly fetches the anchor
  message via `conversations.history?latest=ts&inclusive=true&limit=1`
  and wraps it with `[*** ANCHOR — USER-SELECTED MESSAGE ***] ... [*** END
  ANCHOR ***]` markers. Thread replies are labeled `[ANCHOR]` vs `[reply]`
  to distinguish the anchor from siblings. Channel ±3 is reframed as
  "AMBIENT CHANNEL CONTEXT (low-weight; consult only for enrichment, never
  to redefine the task)." Anchor text/user/ts also surfaced in
  `metadata.{anchor_text,anchor_user,anchor_ts}`.
- `enrichment-scanner.py` dispatch message instructs the agent: anchor
  `suggested_title` and `direct_action` on the ANCHOR block; thread/ambient
  context is for enrichment fields ONLY (resources, knowns, unknowns,
  intent_genesis); only call `refine_task_description` when raw_description
  is genuinely malformed.
- `refine_task_description` defense-in-depth guard computes content-word
  overlap (stopwords stripped) between proposed new title and
  raw_description. Refuses with `status='blocked_drift'` if overlap < 30%.
  New `force=True` parameter for the rare malformed-raw case.

**Verified**: re-enrichment of `01f3e015` after fix preserved
raw_description verbatim (no `refine_task_description` call) and produced a
direct_action correctly anchored on the Kate reschedule message, with
ambient CODAP-thread content folded in as supporting context only.

## 2. Don't overwrite a user-supplied task title in enrichment (PARTIALLY SHIPPED 2026-04-27)

**Symptom**: `refine_task_description` rewrites `suggested_title` even when the
incoming `raw_description` (or a prior `suggested_title`) was supplied by the
user (typed into the Slack shortcut modal, or via a "task body" field). User
expects this to be heavily preserved.

**Shipped (anchor-drift guard)**: `refine_task_description` now refuses
overwrites with < 30% content-word overlap vs `raw_description`, with a
`force=True` escape hatch. Dispatch message tells agent NOT to call the tool
unless raw_description is malformed.

**Still open**:
- Treat `raw_description` originating from a user-shortcut payload as a
  *supplied title*, not a placeholder. Currently the guard fires on EVERY
  row regardless of origin; that's fine for the slack-shortcut case but may
  be over-aggressive for purely-discovered tasks (e.g., gmail-watch-derived
  tasks where raw_description is auto-generated and the agent's refinement
  IS the actual title). Consider gating the guard on
  `origin LIKE 'From%'` (user-indicated) vs auto-discovered origins, or on
  a future `origin_kind` column.
- Re-enrichment idempotency: when `enrichment_state` flips from `done` back
  to `pending`, the second pass should respect the existing
  `suggested_title` (if non-null) unless force=True. Currently the guard
  only checks raw_description, not prior suggested_title. Worth adding.
- Verify in `confirm` lifecycle that `confirmed_title` is honored — should
  already be the case since it's a separate column, but spot-check.

## 3. Slackbot dedup UX: announce instead of silently dropping

**Symptom**: re-clicking "Send to Tasks" on a Slack message that already has a
queued/extracted task results in `INSERT ... ON CONFLICT (source, source_ref)
DO NOTHING` with no user feedback. The shortcut appears to "do nothing,"
making it hard to tell whether the click registered.

**Proposed fix**:
- After the `INSERT ... ON CONFLICT DO NOTHING`, detect whether a row was
  actually inserted (use `RETURNING ref_id` and check empty result).
- On dedup hit, post an ephemeral Slack message: "Already queued as task
  `<ref_id>` — see sidebar." Link to pa-web-ui sidebar deep-link if available.
- On fresh insert, post the existing "queued" notification (already happening).

## 4. Investigate task-statement formation logic generally

**Symptom**: agent sometimes synthesizes task statements that drift from the
source's literal ask (over-paraphrasing, adding scope the source didn't
contain, occasionally selecting a sub-task instead of the headline ask).
Noted on `afbb3259` (biology/Vernier curriculum) — the user-supplied raw task
text was overwritten by an enriched paraphrase that the user felt diverged
more than warranted.

**Proposed investigation**:
- Audit `refine_task_description` invocations across recent enrichment runs.
  Compare `raw_description` (user-supplied) vs final `suggested_title` for
  semantic drift.
- Identify whether drift correlates with thread-context volume, source type,
  or specific kinds of phrasing in the source content.
- Decide whether the right primitive is a verb-led normalizer (gentle
  rewriting) vs a full paraphraser (current behavior). Likely the former for
  user-supplied content, the latter for purely-discovered tasks (e.g.,
  email-watch finds a new ask in a thread the user never tagged).

## 5. Multi-source verification (email, meeting, drive)

**Symptom**: cycle-1 enrichment chain has only been live-tested for the
`slack` source. The other sources (`email`, `meeting`, `meeting_marker`,
`drive`, `google-docs-comment`) have code paths in the new
`fetch_source_content` and `backtrace_task` fallbacks but haven't been
exercised against real pending tasks.

**Proposed verification**:
- Trigger a new email-source task (gmail-watch ingestion path) and walk it
  through the chain end-to-end. Confirm `gmail:<msgid>` fetch_hint resolves,
  thread-context is fetched, packet_info is rendered.
- Trigger a meeting-source task (Granola ingestion or `scan_meeting_notes`).
  Confirm `granola:<meeting_id>` fetch_hint resolves and transcript is loaded.
- Spot-check drive (Drive RAG ingestion) and google-docs-comment.
- Catalog any source-specific quirks (e.g., per Plan: email needs thread-walk,
  meeting needs Granola transcript) that the agent isn't handling well, and
  surface as new entries in this doc.

## 6. Re-enrichment safety / replay protection

**Symptom**: setting `enrichment_state='pending'` on a `done` row causes the
scanner to re-dispatch full enrichment, including `refine_task_description`,
which can stomp prior good output (see #2).

**Proposed fix**:
- Differentiate "re-enrich from scratch" (rare; admin action) from
  "augment-only re-pass" (common; e.g., MC re-dispatch to fill gaps).
- Add an `enrichment.replay_mode` field or distinct
  `enrichment_state='re_pending'` value for the augment-only case.
- In augment mode, `refine_task_description` is skipped entirely; only
  `write_packet_info` may merge new keys.

## 7. Permalink polish (closed but worth tracking)

**Status**: shipped 2026-04-27. `fetch_source_content` now calls Slack's
`chat.getPermalink`, returns the URL in `metadata.permalink` and prepends
it as `[Permalink: ...]` to the content body. Renderers (sidebar.js,
pa-web-ui app.py rich-text) substitute the visible link text "Permalink"
when the URL matches `slack.com/archives/`.

Open question for monitoring: the DM permalink form
(`https://<workspace>.slack.com/archives/D.../p…`) is workspace-scoped.
Confirm that opening it from a non-Slack-app context (browser without
active Slack session) gracefully redirects to the Slack login flow rather
than 404'ing.
