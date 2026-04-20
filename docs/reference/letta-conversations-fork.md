---
title: Letta 0.16.7 — conversations.fork API empirical reference
date: 2026-04-20
probed-by: Phase 2 Unit 2.0
status: empirical
branch-classification: B (shared memory blocks)
---

# Letta `POST /v1/conversations/{id}/fork/` — empirical reference

## TL;DR

- Fork returns **HTTP 200** with a new conversation object (not 201).
- Response shape: standard `Conversation` — `id`, `agent_id`,
  `created_at`, `updated_at`, `summary`, `in_context_message_ids`,
  `isolated_block_ids`, `model`, `model_settings`, `last_message_at`.
  **No `parent_conversation_id` field** — pa-web-ui must track the
  parent link itself (in `conversation_meta.parent_conversation_id`).
- Fork copies a subset of parent's messages: 266 out of 1115 in the
  probe. The subset appears to be the in-context window plus some
  boundary history, enough for continued conversation.
- **Memory blocks are NOT copied** — they are agent-scoped, not
  conversation-scoped. Both parent and fork read from the same
  `core_memory/blocks` on the agent. **Mutations in the fork
  propagate to the parent via shared block IDs.**
- Branch classification: **B (shared block IDs)**. Phase 2's
  pre-planned response is to ship fork as "conversation branch with
  shared memory" — a banner in the fork warns the user that memory
  is shared with parent.

## Request / Response

### Request

```
POST http://letta:8283/v1/conversations/<parent_uuid>/fork/?agent_id=<agent-id>
(no body required)
```

### Response (200)

```json
{
  "created_by_id": "user-00000000-0000-4000-8000-000000000000",
  "last_updated_by_id": "user-00000000-0000-4000-8000-000000000000",
  "created_at": "2026-04-20T22:13:55.570448Z",
  "updated_at": "2026-04-20T22:13:55.570448Z",
  "id": "conv-12902c33-80a6-4b2b-91f3-305545275ec3",
  "agent_id": "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef",
  "summary": null,
  "in_context_message_ids": [],
  "isolated_block_ids": [],
  "model": null,
  "model_settings": null,
  "last_message_at": null
}
```

Note: `in_context_message_ids` is empty in the response but the fork
DOES have messages when queried:

```
GET http://letta:8283/v1/conversations/<fork_uuid>/messages?limit=2000
→ 266 messages (parent had 1115)
→ earliest: system_message, latest: assistant_message
```

The empty `in_context_message_ids` at fork creation appears to be a
"will be populated on next agent step" placeholder — the messages
exist server-side but the in-context pointer isn't set until the
first invocation.

## Memory block behavior (load-bearing for Phase 2 UX)

### What's in the agent's memory

```
GET http://letta:8283/v1/agents/<MC>/core-memory/blocks
```

Returns 5 core blocks for MC as of probe:
- `assistant_role_playbook`
- `important_people`
- `rover_status_log_202603a`
- `shared_context`
- `laptop_execution_preference`

(Plus archival memory not enumerated here.)

These blocks are attached to the **agent**, not to any conversation.
The relationship is N:1 — many conversations share one agent's
blocks.

### What happens in a fork

The fork's `isolated_block_ids` field is empty (`[]`). This field, if
populated, would specify blocks that should have conversation-scoped
values (I did not probe isolation during Unit 2.0; worth a Phase 3
follow-up). As-is, the fork reads the SAME block values as the
parent — same N:1 relationship.

### Implication for UX

If the user forks MC at a turn boundary and then, in the fork, asks
MC to edit `extracted_tasks` (e.g., "add 'buy milk' to my task
list"), MC will write to the shared `extracted_tasks` block. That
write is IMMEDIATELY visible to:
- The parent conversation (same agent, same block).
- The MC conversation on Telegram (same agent, same block).
- Any other agent or tool that reads the shared block (e.g., the
  tools agent that populates `extracted_tasks` from Slack messages
  has the same block attached at `block-90300b77`).

Fork is NOT a sandboxed exploration of alternative histories. It's
a conversation branch — different message path, same agent state.

## Branch classification

Per the Phase 2 plan's pre-framed branches:

- **Branch A (deep-copy blocks):** Not what we observed. The fork
  does not own its own block values; it reads the agent's.
- **Branch B (shared block IDs):** **This is our case.** Writes
  propagate to the parent.
- **Branch C (no block context at all):** Not our case. The fork
  reads the same blocks the parent reads.

## Phase 2 recommendation

**Ship fork as a "conversation branch" primitive in Unit 2.3.**

Specifically:

1. The fork UI creates a new Letta conv via this API and persists
   `parent_conversation_id` in `pa_web.conversation_meta`.
2. The fork banner should be explicit about shared memory:
   > "Forked from <parent label>. Memory and tools are shared with
   > the parent — changes to your task list, calendar, or other
   > persistent state will be visible in the parent conversation too."
3. Auto-switch to the fork (plan unchanged).
4. The fork's 266-message window lets MC continue the conversation
   with context, which is the primary user value.

If deeper isolation becomes a real need (Phase 3 or later):
- Probe `isolated_block_ids` support: create a fork, attach a
  conversation-scoped block via a POST, see whether mutations stay
  fork-local.
- OR: extend fork to clone specific blocks on creation (this is a
  Letta server feature request, not a pa-web-ui change).

## Cleanup (for future probes)

Forks delete cleanly:

```
DELETE http://letta:8283/v1/conversations/<fork_uuid>/
→ HTTP 200
```

The probe's throwaway fork `conv-12902c33-80a6-4b2b-91f3-305545275ec3`
was deleted after capture. Parent conv was unaffected.

## Open items for Phase 2 implementation

- **Unit 2.1 fork route** should store `parent_conversation_id`
  LOCALLY in `conversation_meta` since Letta's response doesn't
  carry it.
- **Unit 2.3 fork UI** MUST include the shared-memory banner per
  Branch B classification. Do not ship without it — users will
  otherwise assume memory isolation and be confused by
  block-propagation surprises.
- **No pa-web-ui-side validation** can prevent block writes in a
  fork (tools fire through letta-code → Letta server → block
  mutations are atomic at the agent level). The banner is the only
  mitigation.
- Fork is agent-scoped (response echoes the parent's `agent_id`).
  Cross-agent forks are not supported by this API. Out of scope for
  Phase 2 per the plan's "Out of scope" list.
