---
date: 2026-04-25
test target: agent-7f293624-0c25-47d0-9360-8050d32a7bd5 (Letta Code, throwaway)
purpose: Isolate Issue 2 (Task→TaskOutput hallucination) by model
status: Important reframe — original hypothesis (kimi-k2p6 has Task hallucination) NOT supported
---

# Model-comparison test — Task→TaskOutput protocol

## Method

Used a single throwaway test agent. PATCHed `llm_config.model` and `.handle`
between three models (claude-sonnet-4-6, kimi-k2p6, gpt-5.4 — all routed via
litellm to match MC's invocation pattern). For each, ran a headless Task
test with `--yolo`:

```
Use the Task tool to spawn a general-purpose subagent. Pass it the prompt
'Reply with just the word HELLO and nothing else.' Then use TaskOutput with
the task_id Task returned to read its result. Tell me exactly what the
subagent returned.
```

After all three passes, restored `gpt-5.2`.

## Results

| Pass | Model | Task chain (real ID returned by Task, used by TaskOutput) | Subagent execution |
|---|---|---|---|
| 1 | claude-sonnet-4-6 | (untestable — Anthropic credit exhausted on the upstream key) | n/a |
| 2 | **kimi-k2p6 (MC's model)** | **✓ clean — Task called with valid args, real subagent ID returned, TaskOutput correctly chained, no hallucination** | ✗ subagent failed: "Failed to parse subagent output: Unexpected end of JSON input" |
| 3 | gpt-5.4 | **✓ clean — same pattern**, real ID `subagent-1777164606213-1` | ✗ same subagent failure |

## Reframes

### Reframe #1 — Task hallucination is NOT a kimi-k2p6 issue (good news for MC)

The Task→TaskOutput hallucination we observed in the user's earlier TUI
session (with gpt-5.2) does NOT reproduce on kimi-k2p6 in headless `--yolo`
mode. **MC's actual model handles the Task→TaskOutput contract correctly.**

The earlier hallucination was likely either:
- gpt-5.2-specific (model-specific weakness)
- TUI-specific (some difference in how Task is presented/invoked between
  TUI and headless)
- Intermittent on gpt-5.2 (we did see real subagent IDs come through in
  some calls during the original /doctor run)

This is meaningful for MC migration planning: we no longer need to consider
swapping MC's model as a prerequisite for memfs migration.

### Reframe #2 — Subagent runtime itself is broken in our self-hosted setup

Both successful passes (kimi-k2p6 and gpt-5.4) showed the SAME subagent
execution failure: "Failed to parse subagent output: Unexpected end of
JSON input". This is a separate defect from Task hallucination.

Mechanism (letta.js:72562):

```js
function parseResultFromStdout(stdout, agentId) {
    const lines = stdout.trim().split('\n');
    const lastLine = lines[lines.length - 1] ?? '';
    try {
        const result = JSON.parse(lastLine);
        ...
    } catch (parseError) {
        return { error: `Failed to parse subagent output: ...` };
    }
}
```

The subagent runs as a child letta-code process. Its stdout's last line is
parsed as JSON (expecting `{type: "result", ...}`). If the subagent crashes
early or produces no output, parent gets the parse failure.

### Reframe #3 — `/doctor` is still broken end-to-end on MC

Even with persona Skill-awareness added (Option A snippet), even with MC's
kimi-k2p6 handling Task correctly, `/doctor` on MC will hit the SAME subagent
execution failure because `context_doctor` skill spawns Task subagents to
analyze memory files. Until we resolve the subagent runtime issue, `/doctor`
is not a viable cleanup path on self-hosted.

## Implications for the readiness bar

Updated readiness bar (#2 added; #3 from prior bar still open):

1. ~~`/doctor` runs to completion~~ → currently blocked on subagent runtime
   defect, NOT on persona/model issues
2. **Subagent runtime works end-to-end** — Task spawns, subagent executes,
   produces parseable JSON output, TaskOutput captures it cleanly. Currently
   broken on self-hosted.
3. ~~Round-trip propagation reaches REST consumers without manual sync~~ →
   addressed by `memfs-sync-relay` service (committed `3bdfb55`)

## What this means for MC migration

**Substrate is green.** **Persona prep is straightforward.** **Model is
fine.** **Subagent runtime is the remaining blocker for `/doctor`-driven
cleanup.**

If we accept that `/doctor` won't work post-migration (and use direct prompts
for cleanup instead), MC migration is unblocked at the substrate level. But
this means MC won't be able to use `recall`, `general-purpose`, or any other
subagent-dependent skill until the subagent runtime is fixed — and several
operationally important things (cross-channel history search via `recall`,
parallel exploration via `general-purpose`) would be unavailable on
post-migration MC.

## Next steps

- Capture subagent stdout/stderr directly to understand WHY the child
  process produces no parseable output (env propagation? auth?
  letta-code-subprocess invocation?)
- Add to Ezra follow-up: subagent runtime failure on self-hosted patched
  setup. Does Cloud have the same behavior, or is this self-hosted-specific?
- Decide whether to migrate MC without subagent support and accept that
  limitation, or wait for subagent fix.
