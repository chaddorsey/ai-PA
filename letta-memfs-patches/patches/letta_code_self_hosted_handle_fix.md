# letta-code self-hosted handle fix

**Status**: Drafted, NOT applied. Pending decision on applying via project-local letta-code build.

**Target**: `letta-code` 0.24.x bundled `letta.js`. Specifically the `createAgent` function near line 79870 (in 0.24.2; line numbers drift between minor versions — search by content, not line).

**Purpose**: Fix `Task` (and other `INTERACTIVE_APPROVAL_TOOLS`) on self-hosted Letta where the server's `provider_models` registry doesn't contain the parent agent's handle. Switches subagent agent-creation from `model: "<handle>"` (string, requires registry resolution) to `llm_config: <object>` (full pre-resolved config, bypasses resolution per `server.py:540` guard).

**Source verification**: Confirmed by Letta team agent (2026-04-24) that `if request.llm_config is None:` guard short-circuits handle resolution entirely. Inner handle string is NOT validated. Path C is the structurally correct fix.

## Patch shape (descriptive — applied as a unified diff once locked)

### Site 1: `createAgent` function in letta.js (around line 79870 in 0.24.2)

**Before:**

```js
const createAgentRequestBase = {
  agent_type: "letta_v1_agent",
  system: systemPromptContent,
  name,
  description: agentDescription,
  embedding: embeddingModelVal || undefined,
  model: modelHandle,
  ...(contextWindow && { context_window_limit: contextWindow }),
  memory_blocks: filteredMemoryBlocks.length > 0 ? filteredMemoryBlocks : undefined,
  block_ids: referencedBlockIds.length > 0 ? referencedBlockIds : undefined,
  tags,
  ...(isSubagent && { hidden: true }),
  include_base_tools: false,
  include_base_tool_rules: false,
  initial_message_sequence: [],
  parallel_tool_calls: parallelToolCallsVal,
  enable_sleeptime: enableSleeptimeVal,
  compaction_settings: {
    model: DEFAULT_SUMMARIZATION_MODEL  // = "letta/auto"
  }
};
```

**After:**

```js
// [PATCH-3205] On self-hosted Letta where the provider_models registry may not contain
// the parent agent's handle, sending model: <string> forces server-side handle resolution
// which fails with HandleNotFoundError. Sending llm_config: <object> verbatim from the
// parent bypasses resolution per server.py:540 guard.
const isCloudLetta = (process.env.LETTA_BASE_URL || "https://api.letta.com").includes("api.letta.com");
let parentLlmConfig = null;
let parentEmbeddingConfig = null;
if (!isCloudLetta && isSubagent) {
  try {
    const parentId = process.env.LETTA_PARENT_AGENT_ID;
    if (parentId) {
      const parentAgent = await client.agents.retrieve(parentId);
      parentLlmConfig = parentAgent.llm_config || null;
      parentEmbeddingConfig = parentAgent.embedding_config || null;
      // Sanity guard: LET-7991 / LET-8322 may stomp context_window. If the inherited
      // value looks suspiciously like a known reset (30000), restore from the model's known
      // window via contextWindow that letta-code already computed.
      if (parentLlmConfig && parentLlmConfig.context_window === 30000 && contextWindow && contextWindow > 30000) {
        parentLlmConfig = { ...parentLlmConfig, context_window: contextWindow };
      }
    }
  } catch (err) {
    // Fall through to original behavior on any failure — patch is best-effort.
    parentLlmConfig = null;
    parentEmbeddingConfig = null;
  }
}

const createAgentRequestBase = {
  agent_type: "letta_v1_agent",
  system: systemPromptContent,
  name,
  description: agentDescription,
  ...(parentEmbeddingConfig
    ? { embedding_config: parentEmbeddingConfig }
    : { embedding: embeddingModelVal || undefined }),
  ...(parentLlmConfig
    ? { llm_config: parentLlmConfig }
    : { model: modelHandle }),
  ...(contextWindow && !parentLlmConfig && { context_window_limit: contextWindow }),
  memory_blocks: filteredMemoryBlocks.length > 0 ? filteredMemoryBlocks : undefined,
  block_ids: referencedBlockIds.length > 0 ? referencedBlockIds : undefined,
  tags,
  ...(isSubagent && { hidden: true }),
  include_base_tools: false,
  include_base_tool_rules: false,
  initial_message_sequence: [],
  parallel_tool_calls: parallelToolCallsVal,
  enable_sleeptime: enableSleeptimeVal,
  compaction_settings: {
    // [PATCH-3205] Use parent's handle for compaction so summarizer doesn't try to
    // resolve "letta/auto" on self-hosted (graceful fallback exists at compact.py:108
    // but produces noise warnings — using parent's handle eliminates them).
    model: parentLlmConfig?.handle || DEFAULT_SUMMARIZATION_MODEL
  }
};
```

## Detection logic

`isCloudLetta` checks `LETTA_BASE_URL`. If unset or contains `api.letta.com`, behavior is unchanged from upstream (Cloud-safe). Self-hosted users get the bypass.

`isSubagent` is already a local var (gated on `LETTA_CODE_AGENT_ROLE === "subagent"`), so this only affects the subagent-creation path. Top-level `letta --new-agent` from a TUI session still uses the original code path (it's not subagent context).

## Application process

1. Project-local letta-code installed at `~/code/letta-code-memfs/` (per migration plan Phase 2)
2. Patch applied at install time via the same vendored-toolchain that handles the memfs patches
3. The Homebrew-installed letta-code at `/opt/homebrew/lib/node_modules/@letta-ai/letta-code/` is **not** modified — it stays as the unpatched stable copy
4. pa-web-ui and LettaBot select binary via `LETTA_CODE_BIN` env var (which the migration plan already documents at Phase 2.2)

## Verification plan

After applying the patch and rebuilding:

1. **Smoke test — subagent spawns**: Run a parent letta-code session against MC. Have the agent call `Task(subagent_type="general-purpose", prompt="echo OK")`. Verify the subagent completes with output, no `HandleNotFoundError` on the server side.
2. **Test all four `INTERACTIVE_APPROVAL_TOOLS`**: Task, TodoWrite, EnterPlanMode, AskUserQuestion. Verify each works, since they all flow through the same approval IPC.
3. **Test fork-based subagent (`recall`)**: `Task(subagent_type="recall", prompt="summarize last 5 messages")`. Validates the consolidator pattern's foundation.
4. **Test nested Task (consolidator depth)**: A `general-purpose` subagent that itself invokes `recall`. Validates Phase 6+ feasibility.
5. **Regression — ensure normal pa-web-ui flow unaffected**: Run a normal pa-web-ui chat session that doesn't use Task. Bash, Read, Edit should all behave identically to pre-patch.
6. **Regression — ensure Cloud users unaffected**: If we ever spin up a Cloud-targeting test session with `LETTA_BASE_URL=https://api.letta.com`, verify behavior is identical to upstream.

## Rollback

Revert by replacing patched `letta.js` with its pre-patch backup. Vendored toolchain keeps `letta.js.original` alongside.

## Upstream contribution

Per the Letta team agent's offer (2026-04-24), they will draft a GitHub issue body covering the empty-`provider_models`-for-base-providers issue + the `model: <string>` vs `llm_config: <object>` POST asymmetry. They'll hand it to Cameron for review/filing. Once filed, this patch becomes a reference workaround in that issue. If they merge a server-side fix (`sync_base_providers` extension), this client-side patch becomes unnecessary. If they merge a client-side fix in letta-code itself, this patch becomes obsolete on the next letta-code release.

We track the issue and remove our local patch when upstream lands a permanent fix.

## Resolved questions (2026-04-25, source-verified by Letta team agent)

1. **Multiple parent paths** — RESOLVED. `LETTA_PARENT_AGENT_ID` is the canonical source. Set per-spawn at `letta.js:62483-62495` from `getCurrentAgentId()` of the spawning process, then injected into the child's env. Walks up exactly one level per spawn (B→A, C→B, D→C — not D→A). `getCurrentAgentId()` is **NOT** a useful fallback inside `createAgent`'s patch context — at that point we're literally in the middle of creating the agent, so `context2.agentId` is undefined and the call would throw. Recommended fallback: if `LETTA_PARENT_AGENT_ID` is unset, **fail loudly** with an actionable error rather than silently fall back to the broken `model: <string>` path. Converts the existing 6-second silent exit into a fast, debuggable failure.

2. **Compaction handle inheritance** — RESOLVED. Inherit verbatim, no special-casing. `compact.py:67` short-circuits with `if agent_llm_config.handle.startswith("letta/auto"): return haiku` BEFORE consulting `compaction_settings.model` at all. So whether we set `compaction_settings.model = "letta/auto"` or `parent.handle`, runtime behavior is identical. And our `!isCloudLetta` gate means parent.handle = "letta/auto" only occurs when self-hosted has auto mode actively enabled (Redis configured) — in which case the auto path resolves correctly anyway. Cleaner patch.

3. **Embedding config absence on parent** — covered by the existing `parentEmbeddingConfig ? ... : ...` ternary in the patch draft.

4. **Two createAgent paths in letta.js** — RESOLVED via inspection. Both `createAgent` (line 38316) and `createAgent2` (exports_create2 module, line ~158490+) have identical `createAgentRequestBase` shapes with `model: modelHandle` and `compaction_settings: {model: DEFAULT_SUMMARIZATION_MODEL}`. The patch must apply to both sites. They're bundled duplicates of the same logic across two TS source files (`src/agent/create.ts` and `src/cli/create.ts` likely). Single patch file with two hunks.

5. **Conversation creation paths** — RESOLVED via grep. `client.conversations.create()` and `client.conversations.fork()` invocations do NOT pass model handle strings. Fork-based subagents (`recall`, `fork`) inherit via server-side conversation fork, which already has the parent's resolved `llm_config`. So the patch scope is exclusively the agent-creation path, not the conversation-creation path.

## Final patch design (locked)

Patch applies to BOTH `createAgent` sites:
- Line ~38422 area (`createAgent`)
- Line ~158498 area (`createAgent2`)

Behavior:
- If `isCloudLetta` (LETTA_BASE_URL contains `api.letta.com` or unset) → original behavior unchanged
- Else if `isSubagent && process.env.LETTA_PARENT_AGENT_ID` → fetch parent, inject `llm_config` + `embedding_config` verbatim, set `compaction_settings.model = parent.handle` (or omit if equivalent — verified safe)
- Else if `isSubagent && !process.env.LETTA_PARENT_AGENT_ID` → throw error: `"LETTA_PARENT_AGENT_ID not set. On self-hosted, subagent creation requires inheriting llm_config from a parent agent. Either run from within a Letta Code session (which sets this env var automatically), or invoke createAgent with an explicit llm_config object."`
- Else (top-level `letta --new-agent` self-hosted) → original behavior. **Caveat**: this path still 404s on self-hosted with empty registry, but it's not the subagent path so doesn't block our use case. Future improvement: extend the patch to the top-level path too if someone needs it.

Sanity guard for LET-7991/LET-8322 context_window stomp retained.
