# MC persona append — Skill awareness for memfs migration

When MC migrates to memfs, its `assistant_role_playbook` (or whichever block
becomes its primary persona post-translation) needs explicit Skill-tool
awareness so `/doctor` and other skill-driven flows actually invoke
`Skill(skill: "...")` instead of falling back to web_search.

This is **mandatory** pre-migration prep — confirmed empirically:
- Calendar-agent's persona (no Skill awareness) → `/doctor` looped on
  web_search until max_steps
- MC's `assistant_role_playbook` currently has 0 mentions of "skill",
  "doctor", or "context_doctor" — same risk applies even though MC has
  the `origin:letta-code` tag

Per Ezra's Option A guidance (Apr 25), append the following to MC's persona
text. Apply this **before** running `/memfs enable` on MC so the persona
context already includes it on first activation.

## Snippet to append

```
## Tool awareness — Skill, Task, and the memory filesystem

You have access to letta-code paradigm tools including Skill, Task, Read,
Edit, Write, Bash, Glob, Grep, and TodoWrite. When the user invokes
/doctor (or otherwise asks for a memory check, audit, or refinement),
invoke Skill with `skill: "context_doctor"` and follow its loaded
instructions. Do not web-search; do not improvise; the skill is the
contract.

When you need to spawn a subagent for a discrete task, use the Task tool
and capture its returned task_id from the tool response. Pass that exact
task_id (which will be in the form `subagent-<unix_ms>-<n>`) to TaskOutput
when polling for results. Do not invent task IDs (e.g. `task_1`,
`task_2`) — those are training-data patterns, not real Task return
values.

When working with your memory filesystem, prefer Read/Edit/Write/Glob/Grep
over web_search. Your memory files live under `system/` and capture your
identity, persona, and operational context. Editing them directly via the
file tools is the supported way to refine your context.
```

## Application

Before MC migration:

1. Get current `assistant_role_playbook` content via REST
2. Append the snippet above (preserving existing content; do not replace)
3. PATCH the block via `/v1/blocks/<block_id>` with the merged content
4. Verify the merged content is what's now stored
5. Open MC in TUI with the env-var trio and run `/memfs enable`

Apply NO sooner than immediately before migration — appending text
recompiles the agent and changes context-window characteristics, so we
want minimal time between persona update and migration.

## Open question

Whether the Task→TaskOutput hallucination defect (Issue 2) is mitigated by
this persona language, or whether it persists regardless because it's a
model-grounding issue. Per Ezra: "If the model is generating TaskOutput
calls without first generating Task calls, that's pure model misbehavior —
no contract you can tighten on the harness side will fix it."

Implication: persona language is a useful *prompt* but may not be
*sufficient*. If `/doctor` still hits hallucinated TaskOutput IDs after this
append, the next mitigation is switching MC's model (currently `kimi-k2p6`
via litellm — same general topology that produced the gpt-5.2 hallucinations
on our test agent).

The model-comparison test (next planned step) will tell us whether MC's
model is safe or whether we need to migrate MC's model to a known-good
provider before the memfs migration.
