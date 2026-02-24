# Agent Outbound Notifications Design

**Last updated:** 2026-02-23

**Problem:** Letta agents have no way to proactively reach the user. All communication is user-initiated (Slack DM → slackbot → pa-routing-handler → agent → response). When agents need to surface time-sensitive information — like completion feedback requests, meeting follow-up approvals, or scheduling confirmations — they can only wait for the user to start a conversation.

**Immediate trigger:** The Completion Feedback Loop (WIP item 2) generates draft replies for completed tasks with external origins. The agent has the draft and routing info but no channel to present it to the user for approval.

---

## Current Architecture

```
User → Slack DM → slackbot (Socket Mode) → pa-routing-handler → selects agent → Letta API stream → response → Slack DM
```

- **Slackbot** owns the Slack bot token (`SLACK_BOT_TOKEN`) and Socket Mode connection
- **pa-routing-handler** selects which agent handles a conversation based on routing rules
- **pa-web-ui** provides an alternative chat frontend, using the same routing handler
- **No agent→user push path exists** — agents cannot initiate messages

### Existing Push-Like Patterns

1. **Gmail watch service** (`agent_notifier.py`): POSTs to `POST /v1/agents/{id}/messages` when new emails arrive. This is service→agent push, not agent→user.
2. **Scheduling proposals**: Slackbot already uses interactive Slack blocks for structured user input (approve/reject proposals).
3. **Scheduler cron jobs**: Can trigger agent messages (`agent_message` action type) or HTTP calls (`http` action type).

### Why `send_message()` Doesn't Help

Letta's built-in `send_message()` is a `letta_core` tool that writes to the agent's own message history. When the scheduler triggers `tasks-agent-sleeptime` via cron, the agent can call `send_message()` all it wants — the output sits in Letta's message log and nobody sees it. It's not connected to Slack, web, or any user-facing channel.

---

## Options Considered

### Option A: Standalone Slack DM Tool

Add a `send_slack_dm` Letta tool that calls `chat.postMessage` directly using the bot token. The agent calls it, user sees the DM, user replies naturally in Slack.

**Problem:** The reply goes through slackbot → pa-routing-handler → main agent (or pulse agent). It doesn't route back to `tasks-agent-sleeptime`. The approval conversation is disconnected — the user would need to say "approve the Savvas feedback" and hope the main agent understands and delegates.

**Good for:** One-way notifications. **Poor for:** Multi-step approval flows.

### Option B: Interactive Slack Blocks (Button-Based)

Build approval as Slack interactive message blocks with Approve / Modify / Skip buttons. When the user clicks, a callback hits the slackbot, which routes the action directly back to `tasks-agent-sleeptime`.

This is how scheduling proposals already work — the slackbot renders interactive buttons for time slots, user clicks one, `send_synthetic_message()` fires back to the agent.

**Good for:** Structured approval. **But rigid** — "modify" requires a modal, and each new approval type needs custom block templates.

### Option C: Agent Outbound Channel (Middle-Ground Approach) — Recommended

This is the interesting one. Today `pa-routing-handler` solves inbound routing: "user said something, which agent should handle it?" The missing piece is outbound routing: "agent wants to tell the user something, how does it reach them?"

**Benefits of laying groundwork:**
- Every agent gets outbound capability, not just tasks-agent
- Meeting follow-up approvals, daily briefing interactions, scheduled check-ins — all use the same channel
- Web UI (`pa-web-ui`) could also receive these notifications (same outbound handler, different delivery)
- Reply routing solves a real recurring problem: today if an agent needs user input during a background job, it has no way to ask

**The recommendation:** Start with a pragmatic middle ground — Option A's simplicity with Option C's reply routing awareness. Build a simple `send_slack_dm` tool that any agent can use, but also tag the outbound message with the originating agent ID. Then add a lightweight "pending reply" mechanism to the slackbot so replies to agent-initiated messages route back correctly. This gives:
- Working feedback loop immediately
- Reusable `send_slack_dm` tool for any agent
- Reply routing that future features build on
- No new service — extends slackbot incrementally

The full outbound handler (Option C Stage 4) can evolve from this naturally once 2-3 agents use the pattern and the real routing requirements are clear.

---

## Proposed Solution: Combined Stage 1+3 — Slack Notify with Interactive Blocks

**Decision (2026-02-23):** Build buttons from the start rather than free-text thread replies. The scheduling proposal pattern already proves interactive blocks work in the slackbot. Adding buttons costs ~1-1.5 hours more than plain text but avoids throwaway free-text parsing and gives better UX from day one.

### Components

1. **Slackbot `/api/notify` endpoint** — New HTTP endpoint on the slackbot service
2. **Supabase `pending_agent_replies` table** — Maps thread_ts → originating agent for reply routing (Supabase, not in-memory cache — notifications may sit for hours)
3. **Letta `send_slack_dm` tool** — Calls the notify endpoint from the Letta sandbox
4. **Notification action handlers** — `@app.action()` handlers for Approve/Modify/Skip buttons
5. **Thread-aware routing in DM handler** — Routes thread replies to the originating agent (used for "Modify" flow)

### Architecture

```
Agent calls send_slack_dm(text, suggested_reply, reply_context, actions)
    → HTTP POST to slackbot:8081/api/notify
        → Slackbot composes Block Kit (text sections + action buttons)
        → Slackbot posts DM to user via Slack API (chat.postMessage)
        → Slackbot stores pending_agent_reply record in Supabase
            {thread_ts, channel_id, agent_id, reply_context, notification_data, status}

User clicks [Send Reply] button
    → Socket Mode interaction payload → @app.action("notification_approve") handler
    → Look up pending_agent_reply by ID from button value
    → send_synthetic_message() to originating agent with structured approval data
    → Agent executes routing tools (reply_to_document_comment, etc.)
    → Response streamed back to DM

User clicks [Modify]
    → Slackbot opens modal with pre-filled suggested reply text
    → User edits and submits
    → Modal submission handler → send_synthetic_message() with custom text

User clicks [Skip]
    → @app.action("notification_skip") handler
    → Marks pending_agent_reply as resolved
    → Posts confirmation in thread: "Skipped — no feedback sent."

User replies in thread (fallback for Modify, or general follow-up)
    → Slack Socket Mode delivers message event to DM handler
    → DM handler checks pending_agent_replies for thread_ts
        → If found: routes to originating agent (not default routing)
        → If not found: normal routing via pa-routing-handler
```

### What It Reuses vs. What's New

**Reuses existing patterns:**
- Slackbot's existing bot token and `chat.postMessage` patterns (already used for scheduling proposals)
- Slackbot's existing DM handler (`message_im_hybrid.py`) — just add a thread_ts lookup at the top
- Supabase for the `pending_agent_replies` table (same DB everything else uses)
- Letta tool patterns (urllib POST from sandbox, same as every other custom tool)

**What's new:**
- One Flask endpoint on slackbot (~30 lines)
- One Supabase table (`pending_agent_replies`)
- One Letta tool (`send_slack_dm`)
- A few lines in the DM handler to check `pending_agent_replies` before default routing

### What the User Would See in Slack

```
Chadbot  2:30 PM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task completed: "Reach out to Savvas about the
state-level data integration"

Kiley Brown requested this via Google Doc comment
on "Notes - Concord Consortium + Matt K Check-in"

Suggested reply to Kiley:
> "Done — reached out to Savvas about the state-level
>  data integration. Thanks, Kiley!"

After replying, the comment thread would be resolved.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ Send Reply ]  [ Modify ]  [ Skip ]
```

If multiple tasks complete in one sync cycle, each gets its own thread. Each is independent — approve one, skip another, modify a third.

**[Send Reply]** → button click → interaction payload → slackbot → `send_synthetic_message()` to tasks-agent-sleeptime → agent calls `reply_to_document_comment` + `resolve_document_comment`

**[Modify]** → button click → opens modal with pre-filled suggested reply → user edits text, submits → `send_synthetic_message()` to agent with custom text

**[Skip]** → button click → marks pending reply as resolved → posts "Skipped — no feedback sent." in thread

### Key Design Decisions

1. **Bot token stays in slackbot** — The Letta tool never touches the Slack API directly. It calls slackbot's `/api/notify` endpoint, which owns the token and posting logic. This maintains the existing security boundary.

2. **Supabase for pending reply state** — Thread→agent mapping persists across slackbot restarts. Simple table, no new service needed.

3. **Thread-based replies** — Using Slack threads for the conversation keeps the DM channel clean. Each notification is a separate thread. User can reply at their own pace.

4. **Agent-aware routing** — The DM handler checks `pending_agent_replies` before falling through to normal pa-routing-handler routing. This means replies in notification threads go to the right agent automatically.

### Slackbot `/api/notify` Endpoint

```python
# POST /api/notify
{
    "text": "Task completed: ...\n---\nSuggested reply: ...\n---\nReply here: ...",
    "originating_agent_id": "agent-62edcfac-...",
    "reply_context": {
        "action": "completion_feedback",
        "ref_id": "8a3b5089",
        "routing_tool": "reply_to_document_comment",
        "routing_args": {"file_id": "...", "comment_id": "..."}
    },
    "user_slack_id": "U_CHAD"  # optional, defaults to configured owner
}
```

Response: `{"ok": true, "thread_ts": "1234567890.123456"}`

### Supabase `pending_agent_replies` Table

```sql
CREATE TABLE pending_agent_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_ts TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    reply_context JSONB,
    status TEXT DEFAULT 'pending',  -- pending, resolved, expired
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
```

### Letta `send_slack_dm` Tool

```python
def send_slack_dm(
    text: str,
    reply_context: str,  # JSON string (Letta sandbox constraint)
) -> Dict[str, Any]:
    """Send a DM to the user via Slack and await their reply."""
    import json, os, urllib.request

    SLACKBOT_URL = os.getenv("SLACKBOT_NOTIFY_URL", "http://slackbot:8081/api/notify")
    AGENT_ID = os.getenv("LETTA_AGENT_ID", "")

    payload = json.dumps({
        "text": text,
        "originating_agent_id": AGENT_ID,
        "reply_context": json.loads(reply_context) if reply_context else {},
    }).encode("utf-8")

    req = urllib.request.Request(SLACKBOT_URL, data=payload, headers={"Content-Type": "application/json"})
    # ... post and return result
```

### Thread-Aware DM Handler Change

In `message_im_hybrid.py`, before the existing routing logic:

```python
# Check if this is a reply to an agent notification
if message.get("thread_ts"):
    pending = check_pending_agent_reply(message["thread_ts"])
    if pending:
        # Route to originating agent instead of default routing
        route_to_agent(pending["agent_id"], message["text"], pending["reply_context"])
        return
```

---

## Evolution Path

### Stage 2: Multi-Channel Delivery

Add `channel` field to `/api/notify`: `"slack"` (default), `"web"`. Web notifications delivered via pa-web-ui's existing SSE stream. Same `pending_agent_replies` table, different delivery mechanism.

### Stage 3: Structured Actions (Interactive Blocks)

Replace free-text "send/skip/customize" with Slack interactive blocks (buttons, dropdowns). Builds on the existing scheduling proposal pattern in slackbot. The `/api/notify` endpoint accepts an optional `actions` array describing the buttons to render.

### Stage 4: Full Outbound Routing Service

Extract notification logic into a dedicated `agent-outbound-service` that:
- Receives notifications from any agent
- Routes to the appropriate delivery channel based on user preferences
- Manages notification priority, batching, and quiet hours
- Provides a unified notification history

This is the natural endpoint but should only be built when multiple agents regularly generate outbound notifications.

### How Straight Is the Path?

Very. Each stage adds fields to the same endpoint and rows to the same table. The `pending_agent_replies` routing logic in the slackbot DM handler doesn't change — it's always "check thread_ts against `pending_agent_replies`, route to stored agent if matched." The Letta tool doesn't change either — it just calls `/api/notify` with whatever fields are relevant. The only real refactor is Stage 2's extraction from slackbot into its own service, and that's a clean cut because the endpoint is already self-contained.

---

## Implementation Scope (Combined Stage 1+3)

| Component | Files | Effort |
|-----------|-------|--------|
| Supabase table | SQL migration | ~15 min |
| Slackbot `/api/notify` endpoint + Block Kit rendering | `slackbot/listeners/api/notify.py` (new), `slackbot/adapters/notification_blocks.py` (new), `slackbot/app.py` (register) | ~1.5 hours |
| Notification action handlers (approve/modify/skip) | `slackbot/listeners/actions/notification_actions.py` (new) | ~1 hour |
| Modify modal + submission handler | `slackbot/listeners/views/notification_modify.py` (new) | ~30 min |
| Thread-aware DM routing | `slackbot/listeners/messages/message_im_hybrid.py` | ~30 min |
| Letta `send_slack_dm` tool | `letta/send_slack_dm_tool.py` (new), registration script | ~1 hour |
| Agent persona update | Letta API call | ~15 min |
| Testing | End-to-end with real Slack DM + button clicks | ~45 min |

**Total estimated effort:** ~5.5 hours

### Dependencies

- Completion Feedback Loop (WIP item 2) — already deployed, provides the feedback drafts
- Slackbot — needs rebuild after endpoint addition
- Supabase — needs table creation

### Risks

- **Low:** Slackbot already handles Slack API posting (scheduling proposals), so the notify endpoint is a small addition
- **Low:** Supabase table is simple with no complex queries
- **Medium:** Thread-aware routing changes the DM handler's control flow — needs careful testing to avoid breaking normal DM routing
