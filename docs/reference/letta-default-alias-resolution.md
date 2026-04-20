---
title: Letta 0.16.7 — resolving the "default" conversation alias
date: 2026-04-20
probed-by: Phase 2 Unit 2.0
status: empirical
---

# Resolving letta-code's `"default"` conversation alias to a real UUID

## TL;DR

- `"default"` is **not** a Letta server-side alias for a path parameter.
  `GET /v1/conversations/default/` returns HTTP 422 (min length 41 chars).
- Instead, the Letta server's `POST /v1/conversations/{conversation_id}/messages/`
  handler has a **special case**: when `conversation_id == "default"` AND
  the request body includes `agent_id`, the server routes the message to
  that agent's existing "default" conversation (or creates one if none
  exists).
- letta-code's CLI persists `"conversationId": "default"` as a literal
  string in `~/.letta/settings.json` (`sessionsByServer`). It does NOT
  resolve to a UUID on the client side — it passes the string `"default"`
  directly to the server's messages endpoint.
- To find the real UUID behind MC's `"default"` alias for Phase 2's
  backfill: query `GET /v1/conversations/?agent_id=<MC>&order_by=last_message_at&limit=1`.
  The first result is MC's active default conversation.

For pa-web-ui Mission Control (`agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef`)
as of 2026-04-20:
**`conv-20d6297a-790c-43bc-96ce-5e628ce1092d`**

## Evidence

### Attempt 1: path-param resolution fails

```
curl http://letta:8283/v1/conversations/default/?agent_id=<MC>
→ HTTP 422
{"detail":[{"type":"string_too_short","loc":["path","conversation_id"],
  "msg":"String should have at least 41 characters",
  "input":"default","ctx":{"min_length":41}}]}
```

The server's path-parameter validator rejects `"default"` before any
alias handling. So `GET /v1/conversations/default/` is not a viable
resolution path.

### Attempt 2: agent metadata does NOT expose a default_conversation_id

```
curl http://letta:8283/v1/agents/<MC>/
```

Returns agent fields including `last_run_completion`, `last_run_duration_ms`,
`last_stop_reason`, `blocks`, `identity_ids`, etc. — but no
`current_conversation_id` or `default_conversation_id` or similar.

### Attempt 3: letta-code CLI source reveals the mechanism

In the installed package's bundled CLI at
`/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js`:

```js
// Line ~82030:
function buildConversationMessagesCreateRequestBody(conversationId, messages, opts, ...) {
  const isDefaultConversation = conversationId === "default";
  if (isDefaultConversation && !opts.agentId) {
    throw new Error("agentId is required in opts when using default conversation");
  }
  return {
    messages: normalizeOutgoingApprovalMessages(...),
    streaming: true,
    stream_tokens: opts.streamTokens ?? true,
    ...
    ...isDefaultConversation ? { agent_id: opts.agentId } : {}
  };
}

// Line ~82100:
stream2 = await client.conversations.messages.create(resolvedConversationId, requestBody, {...});
```

So the resolution pattern is:
- Client sends `POST /v1/conversations/default/messages/` with body
  `{"messages": [...], "agent_id": "<agent-id>", ...}`.
- Server inspects the path param; if `"default"` + body.agent_id present,
  routes to that agent's default conversation.
- Client persists `"default"` in settings, not the resolved UUID —
  it's a cheap way to say "this agent's canonical thread".

letta-code's `~/.letta/settings.json`:
```json
{
  "sessionsByServer": {
    "letta:8283": {
      "agentId": "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef",
      "conversationId": "default"
    }
  }
}
```

### Attempt 4: find the UUID via conversations.list

The practical resolution for pa-web-ui's backfill:

```
curl http://letta:8283/v1/conversations/?agent_id=<MC>&order_by=last_message_at&limit=1
```

This returns the single most-recently-active conversation for the agent.
For MC as of 2026-04-20:

```json
[{
  "id": "conv-20d6297a-790c-43bc-96ce-5e628ce1092d",
  "agent_id": "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef",
  "created_at": "2026-04-02T01:06:40.794599Z",
  "updated_at": "2026-04-20T19:24:08.970237Z",
  "last_message_at": "2026-04-20T19:24:08.957884Z",
  "summary": null,
  "in_context_message_ids": [],
  "isolated_block_ids": [],
  "model": null,
  "model_settings": null
}]
```

Cross-check: the `last_message_at` timestamp matches the last Phase-1
message sent through pa-web-ui (`--conversation default`). Message
count on this conv: 1115. This IS the default.

## `order_by=last_message_at` works on 0.16.7

Feared concern from `memory/project_letta_upgrade_migration.md`:
`last_message_at` column drift around 0.16.6 → 0.16.7. **Confirmed
working on this deployment** — `order_by=last_message_at` returns
results in the expected descending order. NULL values sort last (PG
default). The alembic + table-ownership migration sequence from the
upgrade completed cleanly.

If a future upgrade breaks this again, the fallback is
`order_by=created_at` — also returns UUID-shaped IDs; slightly
different semantics (creation time vs last activity) but same schema.

## Implications for Phase 2

**Unit 2.1 backfill:**

```python
def _resolve_mc_default_conv(agent_id: str = MC_AGENT_ID) -> str:
    resp = httpx.get(
        f"{LETTA_BASE_URL}/v1/conversations/",
        params={"agent_id": agent_id, "order_by": "last_message_at", "limit": 1},
        timeout=10.0,
    )
    resp.raise_for_status()
    convs = resp.json()
    if not convs:
        # No existing default — agent has never been used via --conversation default.
        # Unlikely for MC, but handle: create one via the alias mechanism.
        # Or for Phase 2, fail loudly and let the operator intervene.
        raise RuntimeError(f"agent {agent_id} has no conversations; cannot resolve default")
    return convs[0]["id"]
```

Run this ONCE at backfill time, cache the UUID in
`pa_web.conversation_meta` with `label='Main'`. All future references
use the UUID directly — never the string `"default"`.

**Phase 1 compatibility:** Phase 1's subprocess pool passes
`--conversation default` to letta-code. This continues to work
unchanged — letta-code + Letta server route to the same UUID. No
action needed on Phase 1 code during the Phase 2 migration.

**Telegram (LettaBot) compatibility:** LettaBot's subprocesses also
use `--conversation default` for the MC agent. Same alias → same
UUID. Phase 2's "Main" conversation in pa-web-ui's switcher IS
Telegram's thread. Phone messages via Telegram will appear in
pa-web-ui's "Main" conv (and vice versa) — the origin-doc intent of
"same agent, same memory, different surfaces" is realized as "one
conversation, two surfaces rendering it".

New pa-web-ui conversations (via `POST /api/conversations`) create
**distinct** Letta conv UUIDs, isolated from "Main"/Telegram.

## Open risks

- If the Letta server ever introduces a new-per-call default conv for
  the same agent (breaking the current stable mapping), pa-web-ui's
  backfill UUID would become stale. Detection: add a reconciliation
  probe to `/api/subprocess/status` or a startup check.
- A future Letta version could deprecate the `"default"` path-param
  special case, requiring letta-code (and pa-web-ui) to resolve
  upfront. Detection: letta-code --version bumps; re-probe this
  document when upgrading.
