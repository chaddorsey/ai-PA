---
date: 2026-04-24
status: REVISED — superseded by wire capture (see ./2026-04-24-letta-issue-3205-wire-capture.md)
issue: https://github.com/letta-ai/letta/issues/3205
letta-version: 0.16.7 (verified deployed)
letta-code-version: 0.23.8
deployed-image: letta/letta:0.16.7
---

> **THIS DOCUMENT IS SUPERSEDED.**
> Wire capture on 2026-04-24 confirmed the bug is **not in the Letta server**. The hypotheses below (D1–D4 patches at `letta_agent_v3.py:982-984` etc.) **do not apply**.
> The actual blocker is a `letta-code` client-side bug: `letta --new-agent -p` silently exits in headless mode without producing output or contacting the configured Letta server. Every Task subagent launch hits this path because `buildSubagentArgs` always uses `--new-agent` for fresh subagents.
> See: [`2026-04-24-letta-issue-3205-wire-capture.md`](./2026-04-24-letta-issue-3205-wire-capture.md)

# #3205 Source-Code Diagnosis (Letta 0.16.7)

## Summary of Findings

**The diagnosis the forum thread arrived at is partially correct but misframes the bug location.** The `utils.py:218-220` deprecation warnings are real, but they are pointing at a *symptom*, not the root cause. The actual mechanism is more subtle than "approval-consumption path reads deprecated fields and fails silently."

After reading the deployed source end-to-end, the bug is best characterized as:

> **The `approval_request_id` / `approve` / `denial_reason` fields on `ApprovalCreate` were marked deprecated in favor of a unified `approvals: List[LettaMessageReturnUnion]` field, with a `migrate_deprecated_fields` validator that synthesizes `approvals` from the deprecated fields on input. However, when a client (letta-code) submits a payload with empty or malformed `approvals` content for client-side tool returns, the migration validator does *not* fire (it only fires when both `approve` and `approval_request_id` are non-None), and the downstream consumer at `letta_agent_v3.py:982-1001` interprets an empty/malformed approvals list as "no approvals, no denials, no tool returns" — which then takes the malformed-response branch, persists an empty tool result, and the LLM retries.**

So:
- The deprecation comment is real
- The emerging-from-DB-as-empty symptom is real
- But the *patch surface* is not at `utils.py:218`. That line is just **the only place those deprecated fields are still read** when a legacy client sends them.
- The *real* patch surface is either:
  - **(a) fix the migration validator** in `ApprovalCreate.migrate_deprecated_fields` to handle the "client_tools result with empty approvals" case, or
  - **(b) fix the consumer** at `letta_agent_v3.py:986-1001` so it doesn't treat an empty `approvals` list as "nothing to do," or
  - **(c) fix letta-code** to send a properly-shaped `approvals` list with `ToolReturn` entries instead of an empty list when returning client_tools results.

The forum thread proposed (a) implicitly. After reading the source, **(c) is the most likely fix location**, with (b) as a server-side defense-in-depth.

This is important: **patching `utils.py:218` won't fix anything**. It's a vestigial code path retained for legacy compatibility. The real flow is the `MessageCreate` → `convert_message_creates_to_messages` path *or* the v3 agent's `approval_response` consumer path.

## Source-Code Walkthrough

### 1. The schema (`letta/schemas/message.py:178-197`)

```python
class ApprovalCreate(MessageCreateBase):
    """Input to approve or deny a tool call request"""

    type: Literal[MessageCreateType.approval] = ...
    approvals: Optional[List[LettaMessageReturnUnion]] = ...   # <-- the new field
    approve: Optional[bool] = Field(None, ..., deprecated=True)
    approval_request_id: Optional[str] = Field(None, ..., deprecated=True)
    reason: Optional[str] = Field(None, ..., deprecated=True)

    @model_validator(mode="after")
    def migrate_deprecated_fields(self):
        # Only fires if BOTH approve and approval_request_id are non-None
        # AND approvals is empty/None
        if not self.approvals and self.approve is not None and self.approval_request_id is not None:
            self.approvals = [
                ApprovalReturn(
                    tool_call_id=self.approval_request_id,
                    approve=self.approve,
                    reason=self.reason,
                )
            ]
        return self
```

**Critical observation**: the migrator's gate is `not self.approvals AND self.approve is not None AND self.approval_request_id is not None`. If any of those three conditions doesn't hold, the migrator silently does nothing.

The new shape is `approvals: List[ApprovalReturn | ToolReturn]`. `ApprovalReturn` is for "user said yes/no on a requires-approval tool"; `ToolReturn` is for "client executed a client_tool and here's the result."

### 2. The `LettaMessageReturnUnion` (`letta/schemas/letta_message.py:31-43`)

```python
class ApprovalReturn(MessageReturn):
    type: Literal[MessageReturnType.approval] = ...
    tool_call_id: str = Field(..., description="The ID of the tool call ...")
    approve: bool = Field(..., description="Whether the tool has been approved")
    reason: Optional[str] = Field(None, ...)


class ToolReturn(MessageReturn):
    type: Literal[MessageReturnType.tool] = ...
    tool_return: Union[str, List[LettaToolReturnContentUnion]] = ...
    # tool_call_id, status, stdout, stderr inherited
```

### 3. The "input → Message" conversion (`utils.py:175-228`)

The function `create_approval_response_message_from_input` is called when the server receives an `ApprovalCreate`. It does this:

```python
async def create_approval_response_message_from_input(
    agent_state: AgentState, input_message: ApprovalCreate, run_id: Optional[str] = None
) -> List[Message]:
    # ... uses input_message.approvals (the NEW field)
    approvals_list = input_message.approvals or []
    # ... wraps each into a LettaToolReturn or passes through as-is
    converted_approvals = await asyncio.gather(*[maybe_convert_tool_return_message(approval) for approval in approvals_list])

    return [
        Message(
            role=MessageRole.approval,
            agent_id=agent_state.id,
            model=agent_state.llm_config.model,
            approval_request_id=input_message.approval_request_id,   # line 218 — deprecation warning
            approve=input_message.approve,                            # line 219 — deprecation warning
            denial_reason=input_message.reason,                        # line 220 — deprecation warning
            approvals=list(converted_approvals),                       # the actual data
            run_id=run_id,
            ...
        )
    ]
```

**This is where the forum diagnosis got the location wrong.** The deprecation warnings on lines 218-220 fire because `Message.approval_request_id`, `approve`, and `denial_reason` are deprecated **on the Message class itself** (not the input class). The handler is dutifully copying the deprecated input fields to the corresponding deprecated output fields for backward compat.

The actual data — the new-shape `approvals` list — is passed through correctly on line 221.

So: **`utils.py:218-220` does not lose data.** What it does is *also* populate the deprecated fields on the persisted `Message` for backward compat. The deprecation warnings are noisy but not the bug.

### 4. The consumer (`letta_agent_v3.py:973-1001`)

This is the actual reader that processes approval responses on the next agent step:

```python
approval_request, approval_response = _maybe_get_approval_messages(messages)
tool_call_denials, tool_returns = [], []
if approval_request and approval_response:
    # case of handling approval responses
    content = approval_request.content

    backfill_tool_call_id = approval_request.tool_calls[0].id  # legacy case

    if approval_response.approvals:
        approved_tool_call_ids = {
            backfill_tool_call_id if a.tool_call_id.startswith("message-") else a.tool_call_id
            for a in approval_response.approvals
            if isinstance(a, ApprovalReturn) and a.approve
        }
    else:
        approved_tool_call_ids = {}
    tool_calls = [tool_call for tool_call in approval_request.tool_calls if tool_call.id in approved_tool_call_ids]
    pending_tool_call_message = _maybe_get_pending_tool_call_message(messages)
    if pending_tool_call_message:
        tool_calls.extend(pending_tool_call_message.tool_calls)

    # Get tool calls that were denied
    if approval_response.approvals:
        denies = {d.tool_call_id: d for d in approval_response.approvals if isinstance(d, ApprovalReturn) and not d.approve}
    else:
        denies = {}
    tool_call_denials = [...]

    # Get tool calls that were executed client side
    if approval_response.approvals:
        tool_returns = [r for r in approval_response.approvals if isinstance(r, ToolReturn)]

    # Validate that the approval response contains meaningful data
    # If all three lists are empty, this is a malformed approval response
    if not tool_calls and not tool_call_denials and not tool_returns:
        self.logger.error(...)
```

**This is the real read path.** It reads exclusively from the new-shape `approvals` list, never from the deprecated fields. Three categories are extracted:
- `approved_tool_call_ids` — `ApprovalReturn` with `approve=True`
- `denies` — `ApprovalReturn` with `approve=False`
- `tool_returns` — `ToolReturn` instances (the client_tool results)

If `approval_response.approvals` is empty or `None`, all three categories are empty, and the "malformed approval response" branch fires.

### 5. The error site (`agents/helpers.py:288-291`)

```python
logger.warn(
    f"Cannot process approval response: No tool call is currently awaiting approval. Last message: {current_in_context_messages[-1]}"
)
raise ValueError(
    "Cannot process approval response: No tool call is currently awaiting approval. "
    "Please send a regular message to interact with the agent."
)
```

This fires **before** the v3 agent consumer ever runs — it's in the request prep path. It triggers when the server receives an approval-shaped input but the most-recent in-context message is not an approval-request. This is what the issue filer (lingyalong) hit directly.

But it's **not what we hit in our pilot test.** Our symptoms were:
- 5 runs entered `final_stop_reason=requires_approval`
- Stream Finalizer forced `[DONE]` for each
- LLM self-retried Task 5 times
- Tool messages in the conversation were *empty*
- No "Cannot process approval response" error in our logs

That tells us **our failure mode is *downstream* of helpers.py:288** — the approval response gets accepted, but the v3 agent consumer's `tool_returns` extraction is not finding what it needs. We're hitting the `not tool_calls and not tool_call_denials and not tool_returns` branch at `letta_agent_v3.py:1000`, not the "no tool call is currently awaiting approval" branch.

## Reframed Mechanism

The actual chain when letta-code makes a `Bash` or `Task` client_tool call:

1. Agent emits a tool call. Server marks as approval-required (because `t.function.name in client_tool_names` at `letta_agent_v3.py:1690`).
2. Server stops with `StopReasonType.requires_approval`. Persists an approval-request message with `tool_calls = [the bash call]`.
3. Letta-code locally executes bash, captures output, sends approval message back. **The wire format is what matters here.**
4. Server validates → calls `create_approval_response_message_from_input` → persists a Message with `approvals = converted_approvals`.
5. Next agent step: `letta_agent_v3.py:973` reads `(approval_request, approval_response)`, extracts `approved_tool_call_ids`, `denies`, `tool_returns` from `approval_response.approvals`.
6. **If letta-code sent the wrong shape**, all three lists are empty → malformed-response branch at line 1000 → no tool result wired up → empty `tool` message persisted → LLM retries.

The bug is therefore EITHER:

- **(C) letta-code sends the wrong shape** — most likely candidate. Specifically: it sends approvals that are dict-shaped rather than `ToolReturn`-shaped, or it sends `ApprovalReturn`-only approvals without an accompanying `ToolReturn` for the client_tool result.
- **(B) the server consumer is too strict** about what counts as a valid approval response — possible defensive-in-depth fix, but not the root cause.
- **(A) the migration validator is too narrow** — possible, if letta-code is sending the legacy `approve=True` / `approval_request_id=...` shape *along with* a tool result that the validator should pick up. Less likely but verifiable.

## What We Need To Do Next

To produce a real patch, we need **the actual wire format**. There are three ways to get it:

### Option 1: HTTP capture (most authoritative, ~30 min)

Run a Task call against a pilot agent with `mitmproxy` or tcpdump+jq watching localhost:8283. Capture the actual POST body letta-code sends when it returns the bash result. We then know exactly which schema fields are populated.

### Option 2: Source-read letta-code's letta.js (also viable, ~1 hour)

Grep `letta.js` for `approvals:` / `approval_request_id:` / `tool_call_id` adjacent to the approval-response construction. Understand the exact JS object shape it serializes.

### Option 3: Server log instrumentation (most dangerous, ~15 min)

Add a `logger.info("approval_response payload: %s", input_message.model_dump_json())` at the top of `create_approval_response_message_from_input`, restart Letta, run a Task call, read the log. Instantly tells us the shape on the server side.

**Recommended: Option 1 + Option 3 in parallel.** Option 3 confirms what reaches the validator; Option 1 confirms what's on the wire (catches any FastAPI middleware/validator transforms).

## Candidate Patches (Pre-Wire-Format)

Once we know the wire format, the patch is one of these depending on what we find:

### Patch A — letta-code sends `approve=True` + `approval_request_id=...` plus a separate tool result somewhere

Then the migration validator at `message.py:188-197` should also synthesize a `ToolReturn` if a tool result is present. That's a ~10-line change in the validator.

### Patch B — letta-code sends `approvals: [{type: 'approval', approve: True, ...}]` with no tool result

Then we need a new wire shape from letta-code: it should send `approvals: [{type: 'approval', ...}, {type: 'tool', tool_return: ...}]`. This is a letta-code patch, not a server patch.

### Patch C — letta-code sends `approvals: [<malformed dict>]`

Then the server should be more permissive in `create_approval_response_message_from_input` and reconstruct the `ToolReturn` from the dict. ~20-line change.

### Patch D (defense in depth) — relax the consumer

At `letta_agent_v3.py:1000`, if `tool_returns` is empty but `tool_calls` is non-empty (i.e., user approved but no result was supplied), synthesize a placeholder `ToolReturn` so the agent at least knows the call was approved and can retry through the normal path. This avoids the silent-empty-tool-message symptom regardless of the wire format issue.

## Forum-Thread Implications

The forum thread's framing:
- ✅ Correct: this is a real bug, present since at least 0.16.5, not fixed in 0.16.7
- ✅ Correct: the bug shape is silent corruption + LLM self-retry, not a hang
- ✅ Correct: Task is the worst-case amplifier because it produces more client_tool round-trips
- ❌ Incorrect: the patch surface is *not* `utils.py:218-220`. Those lines are vestigial backward-compat. They produce noise (deprecation warnings) but don't lose data.
- ❌ Incorrect: the failure isn't "approval state lost across requests." The state is fine — the `approvals` list field is being persisted. The failure is that *what's persisted in `approvals` is empty or wrong-shaped*, which only the consumer at v3 agent step time discovers.

The forum thread's diagnosis was based on the deprecation warnings being a tempting proximate cause. Reading the source shows they're a red herring. **The real bug is a wire-format / consumer-strictness mismatch**, and we need a wire capture to know which side to patch.

## Plan Forward (revised given letta-code wire-format reading)

1. **Wire capture (next session, requires user OK)**: add `logger.info("approval_response payload: %s", input_message.model_dump_json())` at the top of `create_approval_response_message_from_input`. Restart Letta. Re-run the pilot Task test. Read the log output to confirm the actual entry shapes and tool_call_id formats reaching the server.
2. **Patch decision**: based on capture, finalize between D1 alone, D1+D2, D3 (letta-code fix), or D4. D2 applied unconditionally as defense-in-depth.
3. **Build patched server image**: vendored as `letta-memfs-patches/patches/server_approval_consumer_fix.patch`. Same fork-and-build pattern as the external-memfs patches. Tagged `letta-local:0.16.7-task-fix-v1` separately from the memfs image so variables are isolated during testing.
4. **Validate on a fresh pilot agent**: run the same `Task(subagent_type="explore", ...)` workload that originally failed. Success criteria: no `requires_approval` runs persist in the messages table, no empty `tool` messages, no Stream Finalizer forced `[DONE]` warnings, the Task subagent's actual output appears in the conversation.
5. **Update GitHub #3205**: post a follow-up correcting the earlier `utils.py:218` framing and identifying the real defect at `letta_agent_v3.py:982-984` (or wherever the wire capture confirms). Include the patch as a candidate fix. **This makes upstream contribution feasible because we now have a precise, well-justified minimum-edit change.**
6. **Promote the patch to the memfs upgrade plan's vendored set**: combine with the three external-memfs patches into a single applied set. Phase -1 of the migration plan now has a concrete deliverable.

## Verification That Will Confirm Each Hypothesis

| Hypothesis | Confirming evidence | How to gather |
|---|---|---|
| Patch C (server should be permissive) | Wire capture shows `approvals: [<dict missing fields>]` | Wire capture |
| Patch B (letta-code wire format wrong) | Wire capture shows no `ToolReturn` in approvals at all | Wire capture |
| Patch A (validator too narrow) | Wire capture shows legacy `approve=True` with separate tool result alongside | Wire capture |
| Patch D (defense in depth, regardless) | Always applicable as backstop | None — apply alongside whichever of A/B/C wins |

## Open Questions Worth Surfacing

1. **Why does the `migrate_deprecated_fields` validator only fire when *both* `approve` and `approval_request_id` are non-None?** What about a denial with no `approve=True`? What about a tool result with no approval? These edge cases look uncovered.
2. **What does "client_tools" actually mean in letta-code 0.23.8 vs the server's understanding?** The server treats `t.function.name in client_tool_names` as approval-required. But that requires the server to know which tools the client claims to handle. How is this list communicated, and is it kept consistent?
3. **Is there a difference between Task and other client_tools in how letta-code packages the result?** Task spawns a subagent which runs more client_tool round-trips, each of which would individually hit this same path. If the bug is per-round-trip, Task amplifies it linearly, which matches the 5× we observed. But it might also be that Task results have a different shape than Bash results — worth checking in the wire capture.
4. **Are there v1/v2/v3 agent variants with different consumer logic?** Yes — letta_agent.py, letta_agent_v2.py, letta_agent_v3.py all exist. We need to know which one our agents are using. (Likely v3, based on file timestamps and the depth of approval logic in v3.)
5. **The "stream finalizer forced [DONE]" warnings** suggest the run never gracefully closed after the approval round-trip. Is there a separate stream-completion bug downstream of the approval handling, or is it a direct consequence of the "malformed approval response" branch persisting nothing?

## Letta-Code Side: What's Actually On The Wire

I read `/opt/homebrew/lib/node_modules/@letta-ai/letta-code/letta.js` (0.23.8). All 30+ approval-message construction sites use the new shape consistently:

```js
{
  type: "approval",
  approvals: [<entries>],
  otid: <uuid>
}
```

Each entry in the `approvals` array is one of two shapes — both already correctly typed for the server:

**Shape A — successful client_tool execution (e.g. Bash returned output):**
```js
{
  type: "tool",
  tool_call_id: <toolCallId>,
  tool_return: <result>,
  status: "success" | "error"
}
```

**Shape B — denial / interrupt:**
```js
{
  type: "approval",
  tool_call_id: <toolCallId>,
  approve: false,
  reason: "..."
}
```

These map directly to the server's `ToolReturn` and `ApprovalReturn` schemas. The wire format is **not** the bug. Letta-code never sends the deprecated `approve` / `approval_request_id` / `denial_reason` top-level fields; those code paths are dead on this client version.

This eliminates Patches A and B from the candidate list. **The bug is server-side**, in either the `executeApprovalBatch` result construction (which I haven't fully read yet) or in the consumer at `letta_agent_v3.py:982-1001`.

## A Critical Lead: `tool_call_id.startswith("message-")` Backfill

At `letta_agent_v3.py:982-984`:
```python
approved_tool_call_ids = {
    backfill_tool_call_id if a.tool_call_id.startswith("message-") else a.tool_call_id
    for a in approval_response.approvals
    if isinstance(a, ApprovalReturn) and a.approve
}
```

Where `backfill_tool_call_id = approval_request.tool_calls[0].id` (always the *first* tool call).

**This is a known schema-mismatch backstop.** It exists because some clients send `tool_call_id` as a message-ID (legacy) instead of the actual tool-call-ID. The backfill substitutes the *first* tool call's ID when this pattern is detected.

**This is broken when there are multiple parallel tool calls in a single approval request.** Example: Task spawns multiple subagents. Each subagent generates client_tool calls that need approval. If letta-code returns multiple approvals in one batch and any of them have `tool_call_id` starting with `"message-"`, they ALL get rewritten to the first tool call's ID — collapsing N approvals into 1, with the other N-1 silently dropped.

This matches our 5× amplification *exactly*: one Task call → multiple subagent client_tool round-trips → some collapse → result-extraction comes up with empty `tool_returns` → "malformed approval response" branch → empty tool message → LLM retries → retry sends fresh approvals → same collapse → loops 5×.

I have NOT confirmed letta-code is sending `"message-*"`-prefixed IDs (the backfill could be a relic from older clients). But the pattern fits. **Wire capture would resolve this immediately.**

## Revised Patch Hypotheses

| ID | Location | Approach | Confidence (pre-capture) |
|---|---|---|---|
| **D1** | `letta_agent_v3.py:982-984` | Drop the `startswith("message-")` collapse; if any approval has a `message-*` ID, log a warning and skip it (rather than rewriting to the wrong ID) | High — fits the symptom |
| **D2** | `letta_agent_v3.py:998-1001` | When the malformed-response branch fires, attach a synthetic `ToolReturn` with `status="error"` and an explanatory message instead of leaving an empty tool message. Prevents LLM retry loops regardless of root cause. | High — defense-in-depth, no risk |
| **D3** | letta-code | If the issue is letta-code generating `message-*` tool_call_ids in any path, fix at the source | Medium — needs wire capture to confirm |
| **D4** | server consumer permissiveness | If letta-code occasionally sends entries that pydantic refuses to coerce into `ApprovalReturn`/`ToolReturn`, server should be more forgiving | Low — speculative |

**Recommended near-term patch path:** D1 + D2 applied together. D1 fixes the likely root cause; D2 ensures that even if there's a *different* bug we haven't found, the LLM-retry cascade stops.

## Recommended Next Action

**Wire capture before finalizing the patch.** The forum thread already proposed adding a `logger.info` at `create_approval_response_message_from_input` — that's Option 3 from the earlier diagnosis. Combined with reading the actual `tool_call_id` values in the captured payload, we'll know definitively:
- Whether letta-code emits `message-*` prefixed IDs
- Whether `approval_response.approvals` ever contains entries the server can't coerce
- Whether the multi-parallel-tool-call scenario actually triggers in our usage

Once we have the capture (~30 minutes of work, requires server restart with one added log line and re-running the pilot Task test), the patch becomes definitive.

**This is the next concrete action; I have not run it autonomously because it requires modifying the deployed Letta image. Awaiting user approval to proceed.**

## Files Inspected (with line ranges)

| File | Lines | Purpose |
|---|---|---|
| `letta/server/rest_api/utils.py` | 160-225 | `create_approval_response_message_from_input` (the input handler) |
| `letta/schemas/message.py` | 170-200 | `ApprovalCreate` schema + migration validator |
| `letta/schemas/message.py` | 280-310 | `Message` ORM schema with deprecated fields |
| `letta/schemas/letta_message.py` | 30-45 | `ApprovalReturn` and `ToolReturn` definitions |
| `letta/agents/helpers.py` | 100-145 | `validate_persisted_tool_call_ids` / `validate_approval_tool_call_ids` |
| `letta/agents/helpers.py` | 260-295 | The "Cannot process approval response" error site |
| `letta/agents/letta_agent_v3.py` | 950-1010 | Approval consumer (extracts approved/denied/tool_returns from `approvals`) |
| `letta/agents/letta_agent_v3.py` | 1685-1715 | Approval gate (where client_tool calls are marked approval-required) |
| `letta/helpers/message_helper.py` | 92-180 | `convert_message_creates_to_messages` (the unified path) |
