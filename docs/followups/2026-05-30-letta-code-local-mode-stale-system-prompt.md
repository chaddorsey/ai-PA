---
date: 2026-05-30
status: workaround-in-place
severity: silent-correctness-bug
agents_affected: any local-mode agent whose memfs is populated AFTER initial creation (i.e., every migrated agent)
related:
  - docs/runbooks/letta-local-mode-per-agent-migration.md
  - docs/migrations/local-mode/docs-and-transcripts-agent.md
  - docs/migrations/local-mode/calendar-agent.md
---

# Local-mode agents run with stale system prompts after memfs import

## TL;DR

When you `letta agents create` a local-mode agent, its conversation's
`system-prompt.json` is compiled IMMEDIATELY against the empty bootstrap
memfs. Subsequent memfs commits do NOT trigger recompile. The agent will
run with stale defaults forever unless you force recompile.

**Workaround**: delete `system-prompt.json` from the conversation dir and
re-run any prompt; it recompiles cleanly against current memfs HEAD.

## The silent-failure shape

Both Docs and Calendar passed all Phase E smoke tests (E1 identity, E2
memfs round-trip, E3 Bash tool calling) while running with stale prompts.
The smoke tests didn't catch this because:

- E1 "who are you" → agent self-identifies from the agent record's NAME,
  not the persona content
- E2 "edit memfs" → operates via Read/Edit tools; doesn't require persona
  content to be in-context
- E3 "run a CLI" → operates via Bash; doesn't require tool-use guidelines
  to be in-context

The failure surfaces when the agent needs *durable knowledge* from memfs:
"who is Leslie?", "what does canonical look up?", "what's the slot-finding
recipe?". All of those live in the imported memfs files, but the system
prompt the model receives doesn't contain them — so the agent honestly
says "I don't know" or asks for clarification.

## Reproducer

```bash
# 1. Create local-mode agent
letta --backend local agents create --name foo --model lmstudio/<m>

# 2. Add a system/ file with distinctive content
cp my-persona.md ~/.letta/lc-local-backend/memfs/<new-id>/memory/system/persona.md
git -C ~/.letta/lc-local-backend/memfs/<new-id>/memory commit -am "add persona"

# 3. Run a prompt and watch the compiled prompt — content is stale
LETTA_LOCAL_BACKEND_DIR=~/.letta/lc-local-backend letta --backend local \
  --agent <new-id> --conversation default -p "Who are you?"

CONV_DIR=~/.letta/lc-local-backend/conversations/$(echo -n "default:<new-id>" | base64 | tr -d '=')
jq -r '.memfsRevision' "$CONV_DIR/system-prompt.json"
# Returns the INITIAL bootstrap commit, not your subsequent commits.

# 4. Compare to current memfs HEAD
git -C ~/.letta/lc-local-backend/memfs/<new-id>/memory rev-parse HEAD
# Different.

# 5. Workaround
rm "$CONV_DIR/system-prompt.json"
letta --backend local --agent <new-id> --conversation default -p "Who are you?"
# Now memfsRevision matches HEAD; prompt size jumps from ~10KB → ~35-40KB
```

## Source-code clues

Letta-code bundle (around line 141247):
> Local backend MemFS is a local git repository. Local memory changes affect your future system prompt only after they are committed to the local MemFS git repo. There is no required Letta remote for local backend MemFS; optional user-configured mirrors are handled separately. **The system prompt is recompiled on new conversations, explicit recompiles, and when the committed memory revision changes.**

The last clause ("when the committed memory revision changes") doesn't
appear to actually fire. Both Docs and Calendar had commits AFTER the
initial prompt compile, but the prompt stayed stale until manually
deleted.

The `recompileConversation` API for local backend is explicitly
unsupported (line 202432: `throw new Error("Prompt recompile is not
supported by this backend yet")`), so `/recompile` slash command and
`letta agents recompile <id>` both fail.

`--new` flag DOES trigger recompile (starts a fresh conversation), but
that loses message history.

## Recommended fixes

### Short-term (in our recipe)

1. **Runbook D4 added** — "Force system-prompt recompile" as the last
   step of Phase D, before Phase E smoke tests. Mandatory.
2. **Both migrated agents fixed** — system-prompt.json deleted +
   recompiled for Docs and Calendar; backups saved as
   `system-prompt.json.stale-bak` for forensics.
3. **Phase E smoke tests should be sharpened** to include a
   knowledge-from-memfs check (e.g. "name three sections of your
   imported tool-use guidelines"). The existing E1/E2/E3 don't catch
   stale-prompt because they don't require memfs *content* in context.

### Upstream (letta-code)

- Local backend's "recompile on committed memory revision changes"
  behavior should fire. If it can't be implemented now, the explicit
  `recompile` API should at least work for local mode.
- `/recompile` slash command shouldn't silently throw "not supported";
  it should either work or document a workaround.

## Open question

Does the prompt stay synced after the agent makes its OWN memfs commits
during a session? Untested. If not, the agent's own learning loop is
broken — it can write to memfs but can't see what it wrote until next
session. Worth testing during the soak window.
