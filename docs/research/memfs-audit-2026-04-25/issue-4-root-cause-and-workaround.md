---
date: 2026-04-25
status: ROOT CAUSE FOUND + WORKAROUND VERIFIED
supersedes: issue-4-isolation.md (which assumed system-wide IPC bug)
---

# Issue 4 root cause: `letta --new-agent` headless mode silently broken

## Diagnosis

Manually reproduced the subagent invocation and discovered:

**`letta --new-agent` in headless mode (with `-p` and `--output-format
stream-json`) exits with code 0 producing ZERO bytes of stdout AND ZERO
bytes of stderr.** Completely silent exit. This is a clear letta-code bug
in the `--new-agent` headless code path.

Test grid:

| Invocation | Result |
|---|---|
| `letta -p "..." --agent EXISTING --output-format stream-json` | ✓ works — full stream-json output |
| `letta --new-agent --system X --no-memfs -p "..." --output-format stream-json` | ✗ silent exit (0 bytes output) |
| `letta --new-agent -p "..."` | ✗ silent exit |
| `letta --new-agent --no-memfs --model Y -p "..." --permission-mode bypassPermissions` | ✗ silent exit |

This is what produces the "Failed to parse subagent output" error in Task:
parent expects `{type:"result"}` JSON line on subagent's stdout; subagent
produces nothing.

## Root cause is letta-code, NOT Letta server

Earlier diagnosis assumed this was the #3205 client_tools/approval IPC
bug (per Ezra). It's not — that bug is in the Letta server. This bug is
in letta-code's `--new-agent` headless path.

Server-side investigation showed during a failing Task test:
- `POST /v1/agents/` was called once → BUT no agent was actually created
  in the database
- `POST /v1/conversations/conv-.../messages` succeeded multiple times with
  200 OK from litellm — but those were the PARENT's calls, not the
  subagent's

The subagent process exits silently before making any successful API call
of its own.

## Workaround: pre-create persistent subagent agents and reuse via Task with `agent_id`

Verified empirically:

```
Use the Task tool with agent_id='agent-8f885655-...' subagent_type='general-purpose'.
Pass it the prompt: 'Reply with HELLO_REUSE_SUBAGENT.'
```

Result: `subagent_status=success`, returned `"HELLO_REUSE_SUBAGENT"`,
existing agent reused successfully.

`buildSubagentArgs` (letta-code letta.js:72768) chooses code path based on
whether `existingAgentId` is set:

- If `existingAgentId` set → uses `letta --conv` or `letta --agent X --new`
  (headless path that WORKS)
- If not set → uses `letta --new-agent --system X --tags ...`
  (the broken headless path)

So whenever Task is called with explicit `agent_id`, subagents WORK.
Whenever Task is called without `agent_id`, subagents fail.

## `recall` works natively (different code path entirely)

`recall` and other `fork: true` subagents go through
`client.conversations.fork()` server-side. They do NOT use the
`--new-agent` code path. Verified:

```
subagent_type=recall subagent_id=subagent-1777169607817-1 subagent_status=success
agent_id=agent-7f293624-0c25-47d0-9360-8050d32a7bd5
[Task completed]
```

Recall successfully forked the parent conversation, searched it, and
produced a real summary of today's tests. **MC's cross-channel history
search via recall WILL work post-migration without any workaround.**

## What this means for MC migration

Updated readiness picture:

| Capability | Status post-migration |
|---|---|
| Memfs enable, block translation | ✓ works |
| Round-trip edits + sync-from-git relay | ✓ works |
| Parent agent operations | ✓ unaffected |
| pa-web-ui letta-code subprocesses | ✓ unaffected |
| **`recall` for cross-channel history search** | **✓ works natively** |
| **`general-purpose` Task with explicit agent_id** | **✓ works (pre-create agents, reuse)** |
| Other `fork: true` subagents | likely works (same path as recall) |
| `/doctor` (context_doctor) | ✗ broken — context_doctor calls Task without explicit agent_id |
| `Task(subagent_type='X')` without agent_id | ✗ broken — uses --new-agent path |

## Workaround design for production

For agents that need Task subagents (MC, calendar-agent, etc.):

1. **Pre-create a pool of persistent helper agents** per subagent_type:
   - `helper-general-purpose` — for general-purpose Task spawns
   - `helper-explore` — for explore subagent (if/when needed)
   - `helper-init` — for init subagent
   - etc.

2. **Tag them appropriately** (`role:helper`, `type:general-purpose`,
   etc.) so they're identifiable

3. **Modify Task callers to use explicit `agent_id`**:
   - In agent personas: instruct to use `Task(agent_id='helper-...',
     subagent_type='X', prompt='...')` instead of bare
     `Task(subagent_type='X', prompt='...')`
   - In skills (like `context_doctor`): modify the skill content to use
     the helper-agent pattern

4. **Reset helper agents periodically** if state accumulation becomes a
   concern (each Task call leaves the helper with its conversation
   history; could be summarized/compressed periodically)

## Updated note for Ezra

This is a much more actionable diagnosis than "approval IPC bug." Worth
sending him an update:

- Not the #3205 bug class
- Specifically `letta --new-agent` headless silently fails (0 stdout/stderr)
- Workaround verified with existing agent_id
- recall (fork: true) works natively
- Asking whether the --new-agent headless behavior is known, and if a
  patch is in flight

Then we can move to (a) implementing the helper-agent pre-creation
infrastructure, (b) updating MC migration plan to incorporate the
workaround, and (c) actually proceeding with MC migration.
