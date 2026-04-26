# Per-agent memfs migration runbook

End-to-end procedure for migrating one Letta agent from v1 attached-blocks
to memfs file-system memory. Tested empirically on calendar-agent
(memgpt_v2) and Letta Code agent (letta_v1). Designed to be repeatable for
each agent in the migration set including MC.

## Prerequisites (one-time per host)

- Letta server running on patched image (`letta-local:0.16.7-memfs-v3` or
  later) — see `.env` `LETTA_IMAGE`
- letta-code installed and patched on host — `bin/letta-patched` wraps it
  and self-heals patches
- Gitea running on `pa-internal` network with org `agents` provisioned
- `memfs-sync-relay` deployed and Gitea webhook configured (`docker compose
  up -d memfs-sync-relay`)
- `.env` contains `GITEA_ADMIN_USER`, `GITEA_ADMIN_PASS`,
  `GITEA_MEMFS_TOKEN`, `GITEA_MEMFS_WEBHOOK_SECRET`
- Shell has `export DISABLE_AUTOUPDATER=1` (prevents letta-code surprise
  updates that wipe patches)

## Variables

For each agent, set:

```bash
export AGENT_ID="agent-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
export LETTA_BASE_URL=http://localhost:8283
export LETTA_MEMFS_LOCAL=1
export LETTA_MEMFS_GIT_URL='http://pa-admin:'$(grep ^GITEA_MEMFS_TOKEN= /Volumes/main-drive/ai-PA/.env | cut -d= -f2)'@127.0.0.1:3030/agents/{agentId}.git'
```

## Phase A — Pre-flight (read-only)

### 1. Inspect agent state

```bash
curl -s "$LETTA_BASE_URL/v1/agents/$AGENT_ID" | jq '{
  name, agent_type, tags,
  llm: .llm_config.model,
  block_count: (.memory.blocks | length),
  block_labels: [.memory.blocks[].label],
  last_updated: .updated_at
}'
```

Confirm:
- `agent_type` is `letta_v1_agent` (preferred) or `memgpt_v2_agent`
  (works for substrate; `/doctor` flaky; OK for migration but expect
  `/doctor` to need persona-language workaround)
- `tags` does NOT contain `git-memory-enabled` (otherwise already migrated)
- LLM is one our litellm proxy supports

### 2. Verify model auth

```bash
letta-patched -p "respond with OK" --agent "$AGENT_ID" \
  --output-format json --new --yolo --disallowedTools 'Task,web_search,fetch_webpage' \
  | jq '{subtype, is_error, duration_ms, result}'
```

Should return `subtype: "success"` with `result: "OK"`. If it errors with
"credit balance too low" or auth issues, fix the upstream provider before
proceeding.

### 3. Classify attached blocks (shared vs. isolated)

```bash
python3 - <<EOF
import json, urllib.request
A = "$AGENT_ID"
agent = json.loads(urllib.request.urlopen(f"$LETTA_BASE_URL/v1/agents/{A}").read())
for b in agent.get("memory", {}).get("blocks", []):
    bid = b["id"]
    attachments = json.loads(urllib.request.urlopen(f"$LETTA_BASE_URL/v1/blocks/{bid}/agents").read())
    n = len(attachments)
    verdict = "ISOLATED" if n == 1 else f"SHARED ({n})"
    print(f"  {b['label']:<45} {verdict:<15} {bid}")
EOF
```

For each SHARED block, decide: detach pre-migration (clean separation) vs
leave attached (relies on patch 04 scoped delete). Detaching is safer.

### 4. (Optional) Append Skill-awareness to persona

If the agent will use `/doctor`, `Task`, or any skill-driven flow, append
the language at `docs/research/memfs-audit-2026-04-25/mc-persona-skill-append.md`
to its primary persona block (`assistant_role_playbook` for MC,
`persona` for most others) via PATCH:

```bash
BLOCK_ID="block-..."  # the persona block's ID
# Read current value, append snippet, PATCH back
```

Skip if the agent won't use skill-driven flows.

## Phase B — Pre-migration block detach (state change, reversible)

### 5. Detach shared blocks

For each shared block identified above:

```bash
curl -s -X PATCH \
  "$LETTA_BASE_URL/v1/agents/$AGENT_ID/core-memory/blocks/detach/<block_id>" \
  -H "Content-Type: application/json"
```

Verify each detach with the inspect command from step 3 — confirm the
block remains attached to other agents (patch 04 ensures we don't
accidentally delete it).

## Phase C — First memfs enable (state change, TUI required)

### 6. Open agent in TUI

```bash
/Volumes/main-drive/ai-PA/bin/letta-patched --agent "$AGENT_ID"
```

### 7. Enable memfs

In the TUI prompt:

```
/memfs enable
```

**Expected first attempt outcome**: fails at the local clone step with
`fatal: repository '...' not found` because the Gitea repo doesn't exist
yet. **This is normal.** Server-side state IS modified:
- Tag `git-memory-enabled` is set on the agent
- Server creates bare repo at
  `/root/.letta/memfs/repository/<org_id>/<agent_id>/repo.git/` and
  backfills it with the agent's existing block content as `system/*.md`
  files (one initial commit)

### 8. Quit the TUI

`Ctrl+C` or exit the TUI.

## Phase D — Gitea bridge (automated)

### 9. Run the bridge script

```bash
/Volumes/main-drive/ai-PA/scripts/memfs-helpers/bridge-agent-to-gitea.sh "$AGENT_ID"
```

This script (idempotent, safe to re-run):
- Creates Gitea repo `agents/<agent_id>` (or no-ops if exists)
- Pushes the bare repo's content from the Letta container to Gitea
- Configures Gitea as the bare repo's `origin` remote so patch 05's
  auto-fetch fires on subsequent sync-from-git calls

Expected output ends with `[bridge] DONE for <agent_id>`.

## Phase E — Re-enable + complete local materialization (TUI)

### 10. Re-open agent in TUI and re-run /memfs enable

```bash
/Volumes/main-drive/ai-PA/bin/letta-patched --agent "$AGENT_ID"
```

```
/memfs enable
```

**Expected**: `Memory filesystem enabled (git-backed). Path: /Users/.../.letta/agents/<agent_id>/memory`

This pass succeeds because Gitea repo now exists. letta-code:
- Clones from Gitea into `~/.letta/agents/<id>/memory/`
- Detaches v1 memory tools, attaches Skill/Read/Edit/Write/etc.
- Updates the agent's system prompt to memfs-aware version
- Initializes secrets

### 11. Quit the TUI

## Phase F — Verify

### 12. Run the verify script

```bash
/Volumes/main-drive/ai-PA/scripts/memfs-helpers/verify-agent-memfs.sh "$AGENT_ID"
```

Expected output: 5+ PASS, 0 FAIL, possibly some WARN about local working
tree details. Exits 0 on all pass, non-zero if any FAIL.

### 13. Optional round-trip test

Make a benign edit via Gitea API (or via the TUI's Edit tool), wait ~5s,
re-run verify script. Bare repo HEAD and Postgres content should both
reflect the edit automatically (relay → patch 05 → sync).

## Phase G — Post-migration tests (selective, agent-dependent)

### 14. Test Task subagent (if agent uses Task)

In TUI:
```
Use the Task tool with subagent_type='general-purpose'. Pass it the prompt:
'Reply with HELLO_POST_MIGRATION.' Wait via TaskOutput and report what the
subagent returned.
```

Should succeed cleanly with patches applied.

### 15. Test recall (if agent uses cross-channel history)

```
Use the Task tool with subagent_type='recall'. Pass it the prompt: 'Look
back at my recent activity and tell me one thing we discussed.'
```

### 16. (Optional) Test /doctor

Only if persona has Skill-awareness language (Phase A step 4). Otherwise
skip — `/doctor` will loop on web_search.

## Phase H — Soak

Let the migrated agent operate for a soak period (24h+ for non-critical
agents, longer for critical) before migrating the next one. Watch for:
- REST consumers reading stale content (would indicate webhook/sync
  pipeline issue)
- Subagent flows failing (would indicate Path C patch wipe — wrapper
  should self-heal but worth monitoring)
- Memory edits NOT propagating (verify the bridge's origin-remote setup
  is intact)

## Rollback

If anything fails irrecoverably:

```bash
# Drop git-memory-enabled tag
curl -s -X PATCH "$LETTA_BASE_URL/v1/agents/$AGENT_ID" \
  -H "Content-Type: application/json" \
  -d '{"tags": []}'

# Optionally remove bare repo (won't affect Postgres because tag is gone)
docker exec ai-pa-letta-1 rm -rf \
  "/root/.letta/memfs/repository/$LETTA_ORG_ID/$AGENT_ID"

# Re-attach previously-detached blocks
curl -s -X PATCH \
  "$LETTA_BASE_URL/v1/agents/$AGENT_ID/core-memory/blocks/attach/<block_id>"
```

Agent reverts to non-memfs Pattern-3 state. Conversation history intact
(same agent_id throughout).

## Known limitations

- letta-code auto-update can wipe Path C patch silently. Wrapper at
  `bin/letta-patched` self-heals, but invocations bypassing the wrapper
  (e.g., bare `letta` from a different shell) will hit the unpatched
  bundle. Mitigation: `export DISABLE_AUTOUPDATER=1` globally in shell rc.
- `/doctor` requires the agent's persona to know to invoke
  `Skill(context_doctor)`. Without that language, agent falls back to
  web_search and loops.
- Round-trip propagation (Edit → Postgres) only works for agents with
  `origin` configured on their bare repo. The bridge script handles this
  automatically; manual /memfs enable workflows skip it.
