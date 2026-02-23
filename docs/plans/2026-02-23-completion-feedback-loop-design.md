# Completion Feedback Loop: Notifying Source Origins on Task Completion

## Context

When extracted tasks are completed in OmniFocus, the `sync_omnifocus_completions` tool detects this and transitions the archival passage to `status:completed`. However, many extracted tasks originate from external requests — Google Doc comments from colleagues, Slack messages, email threads — where the original requester has no visibility into the task's completion.

**The gap**: Completing a task closes the loop within Letta and OmniFocus, but does not close the loop with the person who triggered the task.

## Concrete Example: Savvas Follow-Up (ref_id: 8a3b5089)

- **Source**: Google Doc comment from Kiley Brown on "Notes - Concord Consortium + Matt K Check-in"
- **Reference ID**: `gdocs-comment-1i_3zrQ1mhOAgyQF80cIiqCCQE6uxK7Yv_tbGrVPz81U-AAAB0ig98xU`
- **Task**: "Reach out to Savvas to schedule a follow-up conversation including Matt K"
- **OmniFocus Task ID**: `kpNzsCBLQsd`
- **Current status**: `confirmed` (will be completed soon)
- **What should happen on completion**: A reply to Kiley's Google Doc comment summarizing the action taken, then optionally resolve the comment thread.

## Source Types and Feedback Channels

| Source Type | Reference ID Pattern | Feedback Action | Tools Available |
|-------------|---------------------|----------------|-----------------|
| `google-docs-comment` | `gdocs-comment-{fileId}-{commentId}` | Reply to comment + optionally resolve | `reply_to_document_comment`, `resolve_document_comment` (on `docs-and-transcripts-agent`) |
| `email` | `email-{threadId}` | Flag to user; generally skip auto-reply | `reply_to_email` (exists but emails are too formal for auto-reply) |
| `slack` | `{channelId}:{messageTs}` | Threaded reply to original message | Slack MCP tools (send_message with thread_ts) |

## Design Decisions

### 1. Not all completions need feedback

Signals for whether feedback is appropriate:
- **`from_person`**: If from someone other than the user, feedback likely appropriate
- **`source_type`**: Google Doc comments and Slack messages are conversational; email is more formal
- **Task nature**: Some tasks are informational ("review X") vs. action-oriented ("reach out to Y") — action tasks are better candidates

### 2. Human-in-loop for initial phase

The flow:
1. `sync_omnifocus_completions` detects completion, returns details with `source_type` and `from_person`
2. Agent calls `prepare_completion_feedback(ref_id)` for tasks with external origins
3. Tool parses passage, returns structured routing info + draft message
4. Agent presents to user via Slack DM: "Task X completed. Suggested follow-up to [person] via [channel]: [draft]. Send?"
5. User approves, modifies, or skips
6. Agent dispatches via appropriate tool

### 3. Source-specific strategies

- **Google Doc comments**: Reply summarizing action + optionally resolve. Most natural fit for auto-feedback.
- **Slack messages**: Threaded reply noting completion. Natural but needs care to avoid noise.
- **Email threads**: Generally skip auto-reply (too formal). Flag to user as "you may want to follow up."
- **Future sources**: Extensible via new elif branches in the routing logic.

## Architecture: Option 2+3 (Agent Reasoning + Preparation Tool)

### New Tool: `prepare_completion_feedback`

**Input**: `ref_id` (8-char hex)

**Output**:
```json
{
    "status": "ok",
    "ref_id": "8a3b5089",
    "source_type": "google-docs-comment",
    "from_person": "Kiley Brown",
    "task_description": "Reach out to Savvas to schedule follow-up...",
    "should_send_feedback": true,
    "reason": "External request from colleague via Google Doc comment",
    "suggested_action": "reply_and_resolve",
    "routing": {
        "tool": "reply_to_document_comment",
        "args": {
            "file_id": "1i_3zrQ1mhOAgyQF80cIiqCCQE6uxK7Yv_tbGrVPz81U",
            "comment_id": "AAAB0ig98xU"
        }
    },
    "draft_message": "Done — I've reached out to Savvas to schedule the follow-up conversation with Matt K included.",
    "resolve_after_reply": true
}
```

### Modification to `sync_omnifocus_completions`

Minimal change to the return `details` for each completed task — add:
- `source_type`: from passage metadata
- `from_person`: from passage metadata
- `has_external_origin`: true if `from_person` is not the user

This gives the agent enough signal to decide whether to call `prepare_completion_feedback` without parsing the passage itself.

### Agent Instructions (tasks-agent-sleeptime system prompt addition)

```
When sync_omnifocus_completions reports completed tasks with has_external_origin: true,
call prepare_completion_feedback(ref_id) to check if source notification is appropriate.
Present the suggested feedback to the user via send_message for approval before sending.
Never send source feedback without user approval.
```

### Cross-Agent Tool Access

The `reply_to_document_comment` tool is currently on `docs-and-transcripts-agent`. Options:
1. **Attach it to `tasks-agent-sleeptime` too** — simplest, but credential access needs verification in Letta sandbox
2. **Use `send_message_to_agent_and_wait_for_reply`** to delegate to docs agent — cleaner separation
3. The preparation tool runs anywhere; only the dispatch tool needs API credentials

**Recommendation**: Start with option 1 (attach tools directly). If credential issues arise in sandbox, fall back to option 2.

## Implementation Scope

### Phase 1: Google Doc Comments Only
- New tool: `prepare_completion_feedback`
- Modify: `sync_omnifocus_completions` to include source metadata in return
- Agent instructions update for `tasks-agent-sleeptime`
- Attach `reply_to_document_comment` and `resolve_document_comment` to tasks-agent-sleeptime
- Test with the Savvas example (ref_id: 8a3b5089)

### Phase 2: Slack Messages
- Extend routing logic for `slack` source type
- Parse `{channelId}:{messageTs}` from reference_id
- Use Slack MCP `send_message` with `thread_ts` parameter

### Phase 3: Email (Flagging Only)
- For email sources, return `should_send_feedback: false` with `reason: "Email follow-ups should be manual"`
- Agent mentions to user: "You may want to follow up on [email subject]"

### Future: Automation Graduation
- As patterns emerge, some feedback types can be sent automatically
- Criteria for graduating past human-in-loop: consistent approval rate > 95% for a source type + message pattern
- Agent tracks approval/rejection patterns in archival memory

## Key Files

| File | Change |
|------|--------|
| `letta/prepare_completion_feedback_tool.py` | New tool |
| `letta/register_prepare_feedback_tool.py` | Registration script |
| `letta/sync_omnifocus_completions_tool.py` | Add source metadata to return details |
| Agent system prompt for tasks-agent-sleeptime | Add feedback loop instructions |

## Dependencies

- Archive embedding migration (separate plan) should complete first if we want the preparation tool to use semantic search for passage lookup
- The `reply_to_document_comment` tool requires Google Drive API credentials accessible from Letta sandbox
- Slack feedback requires Slack MCP tools accessible from tasks-agent-sleeptime

## Verified 2026-02-23

- Reference ID pattern confirmed parseable: `gdocs-comment-{fileId}-{commentId}` splits on last `-` before comment ID
- `reply_to_document_comment` tool exists and uses Google Drive API v3 `replies().create()`
- `resolve_document_comment` tool exists and uses `comments().update(resolved=True)`
- Both tools on `docs-and-transcripts-agent`; need attachment to tasks-agent-sleeptime or cross-agent delegation
- Current source types in archive: `google-docs-comment` (3 tasks), `email` (6 tasks), `slack` (0 tasks yet — queue exists but extraction pipeline not yet wired)
