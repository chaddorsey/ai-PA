# memfs-helpers — defensive subagent infrastructure

Tooling that pre-creates persistent helper subagent agents so that Task
invocations always have an `agent_id` to fall back on, even if our Path C
patch gets wiped by a letta-code auto-update.

## Background

`letta-code`'s `Task` tool spawns subagents via two distinct code paths
in `buildSubagentArgs`:

- **No `agent_id`** → `letta --new-agent --system <type> --tags ...` →
  hits a code path that's broken on self-hosted (handle-registry-empty
  bug), surfaces as silent exit + "Failed to parse subagent output"
- **With `agent_id`** → `letta --conv <conv_id>` or
  `letta --agent <id> --new` → unaffected by the bug

Path C (our `apply_letta_code_self_hosted_handle_fix.py` patch) fixes the
no-agent_id path by sending `llm_config` object instead of `model` handle
on `POST /v1/agents/`, bypassing the registry resolution. But Path C is
applied to a bundled `letta.js` file that letta-code's auto-update silently
overwrites.

The wrapper at `bin/letta-patched` self-heals Path C on every invocation,
but if the user invokes bare `letta` directly (or skill-spawned subagents
do — they don't go through our wrapper), they hit the unpatched bundle.

**Pre-created helper agents are the defense-in-depth**: instructing
personas and skills to use `Task(agent_id=helper-X, subagent_type='X')`
always uses the with-agent_id code path, which works regardless of Path C
state.

## Usage

```bash
# Provision the standard set (general-purpose, explore, plan, init,
# memory, history-analyzer)
LETTA_BASE_URL=http://localhost:8283 \
  python3 scripts/memfs-helpers/provision-helper-agents.py

# List existing helpers
LETTA_BASE_URL=http://localhost:8283 \
  python3 scripts/memfs-helpers/provision-helper-agents.py --list

# Recreate one helper (delete and recreate — useful if state has drifted)
LETTA_BASE_URL=http://localhost:8283 \
  python3 scripts/memfs-helpers/provision-helper-agents.py \
    --recreate general-purpose

# Provision a custom set
LETTA_BASE_URL=http://localhost:8283 \
  python3 scripts/memfs-helpers/provision-helper-agents.py \
    --types general-purpose,recall
```

Output is `{subagent_type: agent_id}` JSON, suitable for piping into other
scripts or sourcing into env vars.

## How agents/skills should use the helpers

Persona append for any agent that uses Task:

```
When invoking the Task tool to delegate work to a subagent, prefer to
pass an explicit `agent_id` of a persistent helper agent (rather than
letting Task spawn a fresh agent). Helper agent IDs by subagent_type:

- general-purpose: <helper-general-purpose ID>
- explore: <helper-explore ID>
- plan: <helper-plan ID>
- init: <helper-init ID>
- memory: <helper-memory ID>
- history-analyzer: <helper-history-analyzer ID>

Example: Task(subagent_type='general-purpose',
              agent_id='<helper-general-purpose ID>',
              prompt='...')

Why: this routes through a working code path on self-hosted Letta. Bare
Task without agent_id may silently fail.
```

The actual agent IDs from your provisioning run can be substituted in by
re-running `provision-helper-agents.py --list` and pasting the output into
the persona block.

## Skill override for context_doctor (optional)

If you want `/doctor` to work with the helper-agent pattern, override the
bundled `context_doctor` skill at:

```
~/.letta/skills/context_doctor/SKILL.md
```

Copy the bundled skill text from
`/opt/homebrew/lib/node_modules/@letta-ai/letta-code/skills/context_doctor/SKILL.md`
and modify any `Task(subagent_type='...')` invocations in the skill text
to use `Task(subagent_type='...', agent_id='<helper ID>')`.

Per Ezra's note on skill precedence: project-local `.letta/skills/` >
global `~/.letta/skills/` > bundled. Your override takes precedence over
the bundled skill text.

## Cleanup

Helper agents accumulate conversation history each Task invocation. If
that becomes large enough to slow Task spawns or dominate context windows,
either:

- Delete and recreate the helper:
  `python3 provision-helper-agents.py --recreate general-purpose`
- Or compact the helper's conversation via Letta API:
  `POST /v1/conversations/<conv_id>/compact`
