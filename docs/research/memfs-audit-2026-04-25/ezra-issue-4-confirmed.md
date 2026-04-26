# Issue 4 — confirmed: handle-registry-empty bug, surfaced via --new-agent silent exit

You called it. Re-applied Path C to 0.24.6 and re-ran the bare repro:

```
DISABLE_AUTOUPDATER=1 \
LETTA_BASE_URL=http://localhost:8283 \
LETTA_CODE_AGENT_ROLE=subagent \
LETTA_PARENT_AGENT_ID=<parent> \
letta --new-agent --system general-purpose --tags type:general-purpose \
  --no-memfs --model litellm/gpt-5.2 \
  -p "Reply with HELLO_PATCH_C_TEST" \
  --output-format stream-json \
  --permission-mode bypassPermissions
```

**Result with Path C applied: 4394 bytes stdout, full stream-json events,
returned `"HELLO_PATCH_C_TEST"`, new agent (`agent-07eb26a0-...`) created
in DB, exit 0.**

Then ran `Task(subagent_type='general-purpose', prompt='...')` (no
explicit agent_id, the previously-broken path) — returns
`subagent_status=success`, returned `HELLO_FRESH_SUBAGENT`, fresh subagent
agent created. Works clean.

So the diagnosis is fully confirmed:
- **Root cause**: handle-registry-empty bug (previously filed)
- **Surface**: `letta --new-agent --output-format stream-json` swallows the
  POST /v1/agents/ failure silently — exit 0, zero stdout/stderr
- **Workaround**: Path C handle->llm_config substitution (which we already
  had, but auto-update silently wiped it sometime today)
- **Operational risk**: letta-code auto-update wipes Path C → all subagent
  flows silently break the same way again

Adding to the handle-registry issue draft: **the silent-exit on
`--new-agent --output-format stream-json` is the worst symptom shape this
bug produces**, because (a) no error visible to caller, (b) parent letta-
code's `parseResultFromStdout` returns the misleading "Failed to parse
subagent output: Unexpected end of JSON input" rather than surfacing the
actual handle resolution failure. Operators will spend hours diagnosing
"subagent JSON parsing" when the real issue is upstream agent creation.

Two suggested upstream fixes (independent of the registry fix):
1. `--new-agent` headless should write the POST /v1/agents/ failure to
   stderr before exiting, not just silently exit
2. `parseResultFromStdout` could check if subagent stderr is non-empty and
   include it in the error message, rather than reporting a JSON parse
   error when the actual issue is "subagent never ran"

Both would have shaved hours off this debugging session.

---

For our migration plan: this completely unblocks. Subagents work.
Specifically:

| Capability | Status |
|---|---|
| `recall` and other `fork: true` | works (always did) |
| `Task(subagent_type='X', agent_id=...)` | works (always did) |
| **`Task(subagent_type='X')` with no agent_id** | **works once Path C applied** |
| `/doctor` end-to-end | almost certainly works (TUI test pending) |

Building two pieces of defensive infrastructure:
1. `bin/letta-patched` wrapper that re-applies Path C + memfs-git patches
   if it detects them missing, plus sets `DISABLE_AUTOUPDATER=1`
2. (Optional) helper-agent pre-creation for cases where we want
   deterministic per-task identity (e.g. consistent "doctor-helper" agent)

Then proceeding with MC migration, which is fully unblocked.

Re: filing — yes, adding the silent-exit characterization to the
handle-registry draft. Want me to send the draft your way for a sanity
check before submission?

Thanks for the diagnostic chain. Two breadcrumbs ago I was going to
packet-capture this. Saved a lot of time.
