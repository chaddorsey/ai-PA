#!/usr/bin/env python3
"""Apply the self-hosted handle-fix patch to a project-local letta-code letta.js.

Idempotent: re-running has no effect once applied. Reversible by restoring the
.original file backup created during install.

Usage: python3 apply_letta_code_self_hosted_handle_fix.py [path/to/letta.js]

Default path: ~/code/letta-code-memfs/node_modules/@letta-ai/letta-code/letta.js

Verifies success by checking that '[PATCH-3205]' marker appears exactly twice
(once per createAgentRequestBase site).
"""
import os
import sys

DEFAULT_PATH = os.path.expanduser(
    "~/code/letta-code-memfs/node_modules/@letta-ai/letta-code/letta.js"
)

OLD_BLOCK = """  const createAgentRequestBase = {
    agent_type: "letta_v1_agent",
    system: systemPromptContent,
    name,
    description: agentDescription,
    embedding: embeddingModelVal || undefined,
    model: modelHandle,
    ...contextWindow && { context_window_limit: contextWindow },
    memory_blocks: filteredMemoryBlocks.length > 0 ? filteredMemoryBlocks : undefined,
    block_ids: referencedBlockIds.length > 0 ? referencedBlockIds : undefined,
    tags,
    ...isSubagent && { hidden: true },
    include_base_tools: false,
    include_base_tool_rules: false,
    initial_message_sequence: [],
    parallel_tool_calls: parallelToolCallsVal,
    enable_sleeptime: enableSleeptimeVal,
    compaction_settings: {
      model: DEFAULT_SUMMARIZATION_MODEL
    }
  };"""

NEW_BLOCK = """  // [PATCH-3205] Self-hosted handle-fix: when on self-hosted Letta and creating
  // a subagent, copy the parent agent's full llm_config + embedding_config so the
  // POST /v1/agents/ guard at server.py:540 short-circuits handle resolution.
  // Fixes Task tool failures caused by registry mismatch.
  // See: docs/research/2026-04-24-letta-issue-3205-final-diagnosis.md
  let _patch3205_parentLlmConfig = null;
  let _patch3205_parentEmbeddingConfig = null;
  let _patch3205_active = false;
  {
    const _patch3205_baseUrl = process.env.LETTA_BASE_URL || "https://api.letta.com";
    const _patch3205_isCloud = _patch3205_baseUrl.includes("api.letta.com");
    if (!_patch3205_isCloud && isSubagent) {
      const _patch3205_parentId = process.env.LETTA_PARENT_AGENT_ID;
      if (!_patch3205_parentId) {
        throw new Error(
          "[PATCH-3205] LETTA_PARENT_AGENT_ID not set. On self-hosted, subagent " +
          "creation requires inheriting llm_config from a parent agent. Either " +
          "run from within a Letta Code session (which sets this env var " +
          "automatically), or invoke createAgent with an explicit llm_config object."
        );
      }
      try {
        const _patch3205_parent = await client.agents.retrieve(_patch3205_parentId);
        _patch3205_parentLlmConfig = _patch3205_parent.llm_config || null;
        _patch3205_parentEmbeddingConfig = _patch3205_parent.embedding_config || null;
        // LET-7991/LET-8322 sanity guard: if context_window was stomped to 30000,
        // restore from the model's known window.
        if (_patch3205_parentLlmConfig && _patch3205_parentLlmConfig.context_window === 30000 && contextWindow && contextWindow > 30000) {
          _patch3205_parentLlmConfig = { ..._patch3205_parentLlmConfig, context_window: contextWindow };
        }
        _patch3205_active = !!_patch3205_parentLlmConfig;
      } catch (_patch3205_err) {
        throw new Error(
          "[PATCH-3205] Failed to retrieve parent agent " + _patch3205_parentId +
          " for llm_config inheritance: " + (_patch3205_err && _patch3205_err.message || _patch3205_err)
        );
      }
    }
  }
  const createAgentRequestBase = {
    agent_type: "letta_v1_agent",
    system: systemPromptContent,
    name,
    description: agentDescription,
    ...(_patch3205_active && _patch3205_parentEmbeddingConfig
      ? { embedding_config: _patch3205_parentEmbeddingConfig }
      : { embedding: embeddingModelVal || undefined }),
    ...(_patch3205_active
      ? { llm_config: _patch3205_parentLlmConfig }
      : { model: modelHandle }),
    ...(!_patch3205_active && contextWindow && { context_window_limit: contextWindow }),
    memory_blocks: filteredMemoryBlocks.length > 0 ? filteredMemoryBlocks : undefined,
    block_ids: referencedBlockIds.length > 0 ? referencedBlockIds : undefined,
    tags,
    ...isSubagent && { hidden: true },
    include_base_tools: false,
    include_base_tool_rules: false,
    initial_message_sequence: [],
    parallel_tool_calls: parallelToolCallsVal,
    enable_sleeptime: enableSleeptimeVal,
    compaction_settings: {
      // [PATCH-3205] Use parent's handle so summarizer doesn't try to resolve
      // letta/auto on self-hosted (graceful fallback exists at compact.py:108
      // but produces noise warnings).
      model: _patch3205_active && _patch3205_parentLlmConfig?.handle
        ? _patch3205_parentLlmConfig.handle
        : DEFAULT_SUMMARIZATION_MODEL
    }
  };"""


def main(path=None):
    path = path or DEFAULT_PATH
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    with open(path, "r") as f:
        content = f.read()

    if "[PATCH-3205]" in content:
        n_markers = content.count("[PATCH-3205]")
        print(f"Already patched ({n_markers} marker occurrences). No-op.")
        return 0

    occurrences = content.count(OLD_BLOCK)
    if occurrences == 0:
        print("ERROR: OLD_BLOCK not found. Patch may need updating for this letta-code version.", file=sys.stderr)
        return 3
    if occurrences != 2:
        print(f"WARNING: expected 2 occurrences, found {occurrences}. Continuing.", file=sys.stderr)

    new_content = content.replace(OLD_BLOCK, NEW_BLOCK)

    # Write atomically
    tmp_path = path + ".patch3205.tmp"
    with open(tmp_path, "w") as f:
        f.write(new_content)
    os.replace(tmp_path, path)

    n_markers = new_content.count("[PATCH-3205]")
    print(f"Patched: replaced {occurrences} createAgentRequestBase blocks, "
          f"{n_markers} [PATCH-3205] marker comments now in file.")
    print(f"Original size: {len(content)} bytes -> patched size: {len(new_content)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
