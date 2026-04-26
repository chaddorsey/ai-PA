# Issue 4 — root cause correction (it's not the IPC bug)

Following up on the isolation note: I went to source and found the actual
root cause. It's narrower than the #3205 client_tools/approval IPC bug
class — it's specifically `letta --new-agent` in headless mode.

## What I did

You suggested looking at server logs for `requires_approval`,
`approval_request_id`, etc. during a failing run. Did that — the only
suspicious signal was that `POST /v1/agents/` was logged once but no
new agent was actually created in the DB. So the subagent's agent-creation
step was failing silently.

Read `buildSubagentArgs` in letta-code (line 72768 in 0.24.6 letta.js) and
reproduced the subagent's spawn manually:

```
LETTA_BASE_URL=http://localhost:8283 \
LETTA_CODE_AGENT_ROLE=subagent \
LETTA_PARENT_AGENT_ID=<parent> \
USER_CWD="$HOME" \
letta --new-agent \
  --system general-purpose \
  --tags type:general-purpose \
  --no-memfs \
  -p "Reply with HELLO" \
  --output-format stream-json \
  --permission-mode bypassPermissions
```

**Result: exits with code 0, ZERO bytes stdout, ZERO bytes stderr.**
Completely silent. Reproduced four ways:

| Invocation | Result |
|---|---|
| `letta -p "..." --agent EXISTING --output-format stream-json` | works — full output |
| `letta --new-agent --system X --no-memfs -p "..." --output-format stream-json` | silent exit |
| `letta --new-agent -p "..."` | silent exit |
| `letta --new-agent --no-memfs --model Y -p "..." --permission-mode bypassPermissions` | silent exit |

So whenever Task spawns a fresh subagent (no `existingAgentId`), it goes
through the broken `--new-agent` path. Whenever Task is called with an
explicit `agent_id`, it goes through `letta --conv` or
`letta --agent --new` and works.

## Workaround verified

```
Task(agent_id='agent-8f885655-...', subagent_type='general-purpose',
     prompt='Reply with HELLO_REUSE_SUBAGENT')
```

Result: `subagent_status=success`, returned `"HELLO_REUSE_SUBAGENT"`.
Existing agent reused via the working code path. Subagent infrastructure
is fine; the problem is exclusively `--new-agent` headless.

## And `recall` works natively

```
Task(subagent_type='recall', prompt='Look back at our recent conversation
     and tell me what tests we have been running today...')
```

Returned a real summary that correctly identified my `doctor-test` memory
edit + the explore-subagent-failure-fallback I logged on 2026-04-20. Fork-
based subagents (`fork: true`) use `client.conversations.fork()` and
bypass `--new-agent` entirely. No workaround needed for recall, fork, etc.

## Massively reframed picture

| Subagent invocation | Status |
|---|---|
| `Task(subagent_type='X')` (no agent_id, fresh subagent) | broken — `--new-agent` silent exit |
| `Task(subagent_type='X', agent_id=<existing>)` | works |
| `Task(subagent_type='recall')` and other `fork: true` | works natively |

So the previous "subagents are universally broken on self-hosted" picture
was wrong. It's actually "fresh subagent creation is broken." The
operationally-important `recall` works fine. `general-purpose` works with
a pre-created helper-agent workaround. `/doctor` is broken because
`context_doctor` skill calls Task without an explicit agent_id (and it
spawns analyzer subagents).

## Questions

1. **Is the `letta --new-agent` headless silent-exit known?** It's
   completely silent — no stderr message, no exit code, nothing. If a
   patch is in flight, would love to know. If not, I might add diagnostic
   logging to my local bundle and bisect to find where the silent return
   happens — but if you already know, that saves a session of source dive.

2. **Workaround for `/doctor` specifically**: would overriding
   `context_doctor` at `~/.letta/skills/context_doctor/SKILL.md` to
   instruct Task with explicit `agent_id` work? Or is the doctor flow
   constructing those Task calls in code rather than via the skill text?

3. **Does naturlich's filing match this narrower diagnosis?** Their
   description had the same symptoms ("things look right at boot, but
   approval IPC doesn't actually flow"). If theirs is also `--new-agent`
   silent exit, that simplifies the upstream fix surface — single
   regression rather than separate issuance/consumption-side bugs.

For our migration plan we're going to:
- Pre-create helper agents per subagent_type for general-purpose Task
- Update MC's persona to invoke Task with explicit `agent_id=helper-...`
- Override `context_doctor` skill text if your answer to #2 is yes
- Otherwise accept `/doctor` is non-functional until upstream fix

Substrate work is solid; this just unblocks the operational layer at
much lower risk than I'd thought a few hours ago.

Thanks for the breadcrumbs that pointed me at the right place to dig.
