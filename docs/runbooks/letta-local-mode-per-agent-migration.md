# Per-agent local-mode migration runbook

End-to-end procedure for migrating one Letta agent from Docker server
(`http://letta:8283`) to Letta Code local mode (`letta --backend local`).

Each migration is independent. Migrate one agent at a time, validate,
then move to the next. Rollback within a single agent is supported
during the soak window.

## When to use this runbook

- After the local-mode infrastructure is shipped (Track 2 W3, W14
  complete — see `docs/plans/2026-05-25-letta-code-local-mode-investigation.md`)
- After non-built-in tools used by the agent have CLI/skill replacements
  in place (W5/W9/W10/W11 partial-completion per agent)
- For one agent at a time. Do not parallelize.

## Reversibility envelope

**This is a fully reversible migration per-agent during the entire
migration arc.** The Docker server keeps running until all agents have
migrated AND soaked successfully. At any point before final decommission,
any individual agent can be rolled back to its Docker original.

### What's preserved by design

- The Docker `ai-pa-letta-1` server, its agent records, and the Gitea
  memfs repos all stay intact throughout. Nothing is deleted until the
  per-agent soak passes — and even then, the Docker server itself
  stays up until ALL agents have migrated.
- Each agent migration creates a NEW local-mode agent with a NEW id
  (`agent-local-*`); the Docker original is renamed `XXX-PRE-LOCAL-<name>`
  and detached, not deleted.
- scheduler-service cron records carry both old and new agent IDs
  (the route flip is a single column update). Bidirectional flip is
  trivial.
- pa-web-ui's conversation routing is per-conversation: existing
  conversations stay pinned to their original agent_id; new
  conversations against the new agent_id are opt-in.

### Per-agent rollback cost over time

| Time after migration | Rollback effort | State to merge back |
|---|---|---|
| **t=0** (immediately after Phase H) | <10 min — flip cron, rename Docker agent back | Nothing |
| **t=1 day** | ~30 min — also re-attach a few archival passages and a few memfs commits to the Docker agent | Small archive deltas + a few commits |
| **t=7 days** (typical soak window end) | 2-4 hours — meaningful state divergence; need to export local-mode state, transform, ingest into Docker agent | Archival passages + memfs commits + new conversation history |
| **t=30 days** | Plan-and-execute — risk of orphaned references in downstream signals/tasks | All of the above plus the agent may have written shared canonical files that other agents now reference |

### What's NOT cheap to roll back

Only one thing crosses an irreversibility threshold:

**Final decommission of the Docker server itself** (tearing down
`ai-pa-letta-1` + `memfs-sync-relay`, deleting Gitea agent repos,
removing legacy code paths from pa-web-ui and scheduler-service).
This is multi-week work to reverse. Do not decommission until ALL
agents have soaked successfully for at least 30 days each.

### The whole-arc abort case

If local mode reveals a fundamental problem at any point in the
migration:

1. Per-agent rollback any agents already migrated (Phase I per agent)
2. Stop migrating new agents
3. The Layer 1 infrastructure (letta-local-runner, scheduler-service
   `route=local` executor, the dropped MCPs) is all ADDITIVE — leave
   it sitting idle; nothing in Docker mode operation depends on it
4. Document the failure mode in
   `docs/followups/<date>-local-mode-migration-arc-aborted.md`

No code revert needed for Layer 1 — those changes are designed to be
inert when unused.

## Recommended order (lowest risk → highest)

1. **calendar-agent_copy** (4 tools, 1 cron, well-tested) — pilot
2. **work-packet-assembler** (11 tools, internal pipeline) — second pilot
3. **email-agent** (15 tools)
4. **tasks-agent** (18 tools)
5. **daily-schedule-agent-sleeptime** (19 tools, 4 crons) — sleeptime variant special-case
6. **docs-and-transcripts-agent** (31 tools, granola-heavy)
7. **pulse-monitor-agent_copy** (36 tools, atlassian-broken)
8. **Mission Control** (27 tools, user-facing chat via pa-web-ui) — last

Domain agents (sports_and_media_maven, auto_madden_agent,
main-assistant-agent-kinara, steward) can migrate anytime; they're not
on the critical path.

## Prerequisites (one-time per host)

- letta-code 0.26.1+ on host (`which letta` → `/opt/homebrew/bin/letta`)
- letta-local-runner installed under launchd (see `letta-local-runner/README.md`)
- scheduler-service rebuilt with `route=local` executor (commit 7c544069 or later)
- `.env` contains `LITELLM_MASTER_KEY` (for the Option A provider config)
- LiteLLM container healthy: `curl -sS http://localhost:4000/health/liveliness` returns 200
- (Optional) LiteLLM health-monitoring cron in place — see Operational Followups below

## Variables

For each agent migration, set:

```bash
# Docker-side source
export OLD_AGENT_ID="agent-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
export OLD_AGENT_NAME="<short-name>"            # e.g. "calendar-agent_copy"

# Local-mode target — fill in after Phase C runs
export NEW_AGENT_ID=""                          # populated by `letta agents create`
export LOCAL_BACKEND_DIR="$HOME/.letta/lc-local-backend"

# Model to use (preserve the agent's current model unless intentionally swapping)
export MODEL_HANDLE="lmstudio/gpt-4.1-mini/$OLD_AGENT_NAME"  # litellm alias path
export MODEL_CONTEXT_WINDOW="128000"            # set to actual model capacity

# LiteLLM endpoint
export LITELLM_BASE_URL="http://localhost:4000/v1"
export LITELLM_MASTER_KEY="$(grep ^LITELLM_MASTER_KEY= /Volumes/main-drive/ai-PA/.env | cut -d= -f2-)"
```

## Phase A — Pre-flight audit (read-only)

### A1. Inventory the Docker agent

```bash
curl -s "http://localhost:8283/v1/agents/$OLD_AGENT_ID" | jq '{
  name, agent_type, tags,
  model: .llm_config.model,
  context_window: .llm_config.context_window,
  tools_count: (.tools | length),
  blocks_count: (.memory.blocks | length)
}'
```

### A2. Classify every attached tool

```bash
curl -s "http://localhost:8283/v1/agents/$OLD_AGENT_ID" | \
  jq -r '.tools[] | "\(.name)\t\(.tool_type // "?")\t\(.description[0:80])"' > /tmp/tools-$OLD_AGENT_NAME.tsv
```

For each row, classify:

| Tool category | Local-mode strategy |
|---|---|
| **Built-in** (`Bash`, `Read`, `Edit`, `Write`, `Glob`, `Grep`, `Task`, `web_search`, `fetch_webpage`, `archival_memory_*`, `conversation_search`) | Available automatically — no migration work |
| **`run_*` CLI wrappers** (`run_slack`, `run_gws`, `run_omnifocus`, etc.) | Available via host PATH — no migration work for this agent, but verify the CLI is installed on the host |
| **MCP-attached** (prefix matches an MCP server name) | **Block migration** until the MCP is converted to a CLI/skill. See plan W4 audit table for current state per MCP |
| **Custom Python tool** (HTTP wrappers like `manage_widget_queue`, `emit_canonical_signal`, `write_packet_info`, etc.) | **Block migration** until each custom tool has a Bash+curl recipe documented in a system protocol file OR a CLI on the host PATH |

**Do not proceed past Phase A until every non-built-in tool has a
documented local-mode replacement.** Record the mapping in:
`/tmp/tool-mapping-$OLD_AGENT_NAME.md`

### A3. Inventory cron jobs targeting this agent

```bash
curl -s "http://localhost:8087/v1/jobs?limit=200" | \
  jq --arg AID "$OLD_AGENT_ID" -r '
    .[] // .jobs[] |
    select(.status == "scheduled") |
    select(.actions[]?.config?.agent_id == $AID) |
    "\(.job_id)\t\(.title)\t\(.schedule_expression)"
  ' > /tmp/crons-$OLD_AGENT_NAME.tsv
wc -l /tmp/crons-$OLD_AGENT_NAME.tsv
```

Save the list — you'll repoint these in Phase G.

### A4. Audit Task tool delegations in the agent's system prompt + memfs

```bash
# Search system prompt
curl -s "http://localhost:8283/v1/agents/$OLD_AGENT_ID" | jq -r '.system' | grep -niC2 -E "Task tool|spawn.*subagent|Agent tool"

# Search memfs system/ files
docker exec gitea git --git-dir=/data/git/repositories/agents/$OLD_AGENT_ID.git \
  grep -niE "Task tool|spawn.*subagent|Agent tool" HEAD -- 'system/*.md' || true
```

If any hit references a "subagent reads file X" pattern, **flag for
refactor** (local-mode subagents do not inherit parent memfs — see plan W6).
Refactor pattern: parent Reads file first, then passes content as the
subagent's prompt input.

### A5. Verify model is supported in local mode

The `lmstudio` provider type bypasses validation, but verify the
model_handle resolves via litellm first:

```bash
curl -sS -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  "$LITELLM_BASE_URL/v1/models" | \
  jq -r '.data[].id' | grep -F "$(echo $MODEL_HANDLE | sed 's,lmstudio/,,')"
```

If empty: the model isn't registered in litellm. Either register it in
`litellm/config.yaml` first, or pick a different model.

## Phase B — Snapshot Docker agent state

### B1. Export the agent

```bash
mkdir -p /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/$OLD_AGENT_NAME
cd /Volumes/main-filestore/ai-PA-backups/local-mode-migrations/$OLD_AGENT_NAME

curl -s "http://localhost:8283/v1/agents/$OLD_AGENT_ID/export" > agent.json
curl -s "http://localhost:8283/v1/agents/$OLD_AGENT_ID/archival-memory?limit=10000" > archival.json
```

### B2. Snapshot the Gitea memfs

```bash
docker exec gitea git --git-dir=/data/git/repositories/agents/$OLD_AGENT_ID.git \
  archive --format=tar HEAD > memfs.tar
```

### B3. Audit memfs for local-mode validation issues

```bash
mkdir -p memfs-extract && tar -xf memfs.tar -C memfs-extract

# Find .md files without frontmatter (will fail local-mode commit precondition)
for f in memfs-extract/system/*.md; do
  head -1 "$f" | grep -q '^---' || echo "MISSING FRONTMATTER: $f"
done

# Find protected fields (read_only, etc.) that local mode reserves
grep -lnE "^read_only:\s*true" memfs-extract/system/*.md 2>/dev/null
```

Note the offenders — you'll clean them up in Phase D.

## Phase C — Create local-mode agent shell

### C1. Ensure the provider config is present in the production backend dir

```bash
ls $LOCAL_BACKEND_DIR/providers/auth.json 2>/dev/null && \
  jq '.providers | keys' $LOCAL_BACKEND_DIR/providers/auth.json || \
  echo "MISSING — run prerequisite below"
```

If missing:

```bash
LETTA_LOCAL_BACKEND_DIR=$LOCAL_BACKEND_DIR letta --backend local connect lmstudio \
  --base-url "$LITELLM_BASE_URL" \
  --api-key "$LITELLM_MASTER_KEY"
```

### C2. Create the new agent

```bash
LETTA_LOCAL_BACKEND_DIR=$LOCAL_BACKEND_DIR letta --backend local agents create \
  --name "$OLD_AGENT_NAME-local" \
  --model "$MODEL_HANDLE" \
  --description "Local-mode migration of $OLD_AGENT_ID" \
  --tags "migrated,local-mode" \
  > /tmp/new-agent.json

export NEW_AGENT_ID=$(jq -r .id /tmp/new-agent.json)
echo "NEW_AGENT_ID=$NEW_AGENT_ID"
```

### C3. PATCH the agent record's context_window to match the model

Local mode defaults `llm_config.context_window` to 128000 regardless of
model capacity. Override:

```bash
# TODO: confirm the local-mode agent-update mechanism — may need to edit
# the agent record JSON directly at $LOCAL_BACKEND_DIR/agents/<base64-id>.json
# until letta-code exposes a CLI flag for this.
```

**OPEN: the exact mechanism for updating an existing local-mode agent's
context_window via CLI is not yet documented. May require direct JSON edit
of the agent record file. Investigate during the first migration; update
this runbook with the verified recipe.**

## Phase D — Import memfs

### D1. Clean up Docker-era artifacts that local mode rejects

```bash
cd memfs-extract

# Strip protected frontmatter fields
sed -i '' '/^read_only:\s*true$/d' system/*.md

# Remove files lacking frontmatter (these are usually historical
# migration stubs; verify before deleting)
for f in system/*.md; do
  head -1 "$f" | grep -q '^---' || rm -v "$f"
done
```

### D2. Copy system/ into the new agent's memfs

```bash
CAN_MEMFS="$LOCAL_BACKEND_DIR/memfs/$NEW_AGENT_ID/memory"
cp -r memfs-extract/system/*.md "$CAN_MEMFS/system/"

# Optionally also copy non-system top-level dirs (skills/, reference/, etc.)
# if they exist and the agent uses them. Skip dated archival dirs by default.
```

### D3. Commit the baseline

```bash
cd "$CAN_MEMFS"
git add -A
git -c user.email="$OLD_AGENT_NAME@local" -c user.name="$OLD_AGENT_NAME" \
  commit -m "import: $OLD_AGENT_ID system/ baseline"
git log --oneline -3
```

If the commit fails on frontmatter/protected-field validation, fix the
offender and retry. Refer to W6 in the plan for the full validation
ruleset.

### D3b. Patch agent's `canonical_reference_protocol.md` for local mode (added 2026-05-30)

If the imported memfs has `system/canonical_reference_protocol.md`, it
likely contains pa-web-ui-specific language for the "Stop-and-surface
when prerequisites are missing" section. Patch it to the local-mode
wrapper-based language before the recompile in D4. Reference patches:
`agent-local-3898b33a…` (Docs) and `agent-local-cd5ed5cd…` (Calendar)
commits from 2026-05-30. Two specific updates:

1. **Add a "Checking env vars correctly" section** that warns against
   `echo "$X" >/dev/null` patterns (output discarded → false negatives)
   and shows the proper `${VAR:-UNSET}` check.

2. **Replace the pa-web-ui surfacing language** with:
   > "Canonical access requires GITEA_MEMFS_TOKEN + GITEA_BASE_URL in
   > my environment, but they're empty here. In local mode, these come
   > from the launcher wrapper at ~/bin/letta-<agent>. Check that the
   > wrapper exports them. Pausing here."

3. **Add a "People lookup recipe" section** with the canonical
   first-initial-lastname slug pattern and the work/external/board/
   family/personal fallback order.

### D4. Force system-prompt recompile (CRITICAL — added 2026-05-30)

**The agent's conversation `system-prompt.json` is compiled ONCE at agent
creation against the empty bootstrap memfs.** Subsequent memfs commits do
NOT trigger recompile until the conversation is reloaded. Smoke tests
will pass because tools can Read files on demand, but the agent runs
with stale defaults in its system prompt context — it won't "know"
anything from the imported memfs without explicit Reads.

The local backend doesn't support `agents.recompile` or `/recompile`
slash command (both throw "not supported by this backend yet"). Force
recompile by deleting the stale conversation system-prompt.json file:

```bash
# Locate the default conversation dir (base64-encoded "default:<agent-id>")
CONV_B64=$(echo -n "default:$NEW_AGENT_ID" | base64 | tr -d '=')
CONV_DIR="$LOCAL_BACKEND_DIR/conversations/$CONV_B64"

# Back up the stale prompt (preserve for forensics), then delete
cp "$CONV_DIR/system-prompt.json" "$CONV_DIR/system-prompt.json.stale-bak"
rm "$CONV_DIR/system-prompt.json"

# Trigger recompile via a no-op headless call
cd /Volumes/main-drive/letta-launchpad
LETTA_LOCAL_BACKEND_DIR=$LOCAL_BACKEND_DIR letta --backend local \
  --agent $NEW_AGENT_ID --conversation default \
  -p "What is the one-line description of your system/persona.md?"

# Verify the new prompt picked up the import
jq -r '"size=\(.content | length), memfsRev=\(.memfsRevision)"' "$CONV_DIR/system-prompt.json"
# memfsRev should match: git -C $LOCAL_BACKEND_DIR/memfs/$NEW_AGENT_ID/memory rev-parse HEAD
```

A correctly-recompiled prompt will be ~35-40KB (vs ~10KB for the
empty-memfs default) and `memfsRevision` will match the current HEAD.

## Phase E — Smoke test the migrated agent

### E1. Identity check

```bash
LETTA_LOCAL_BACKEND_DIR=$LOCAL_BACKEND_DIR letta --backend local \
  --agent "$NEW_AGENT_ID" \
  -p "In one sentence: who are you, and what's the most important thing in your system/ directory?"
```

Verify the response reflects the imported persona, not the default
"Letta Code" framing. (The bundle's hard-coded system prompt is always
sent in addition to imported persona; the agent should still
self-identify with the imported persona's role.)

### E2. Memfs read + edit round-trip

```bash
LETTA_LOCAL_BACKEND_DIR=$LOCAL_BACKEND_DIR letta --backend local \
  --agent "$NEW_AGENT_ID" \
  -p "Append the line '# migration-canary-$(date +%Y-%m-%d)' to your system/persona.md, commit the change with Bash, and confirm by reporting the new last line."
```

Verify the commit lands in the local git log:

```bash
git -C "$CAN_MEMFS" log --oneline -3
```

### E3. Tool-calling spot check

Pick a representative tool the agent uses and verify it works through the
new Bash+CLI path. For an agent that used `run_slack`:

```bash
LETTA_LOCAL_BACKEND_DIR=$LOCAL_BACKEND_DIR letta --backend local \
  --agent "$NEW_AGENT_ID" \
  -p "Use Bash to run 'run_slack --help' and report the first 10 lines of output."
```

### E4. (Optional) Long-context check

If the agent normally runs near its context limit, send a synthetic
50K-token prompt and confirm the response succeeds without truncation
errors. Skip if the agent's typical workload is short.

## Phase F — End-to-end test through pa-web-ui + letta-local-runner

### F1. Pa-web-ui chat test

Open http://localhost:5200, start a new conversation against the new
agent (the conversation switcher should expose it). Send a routine
message that exercises one of its CLI tools. Verify response correctness
and latency.

### F2. Trigger a cron job manually

Repoint ONE of the agent's cron jobs (the lowest-stakes one):

```bash
JOB_ID="<from /tmp/crons-$OLD_AGENT_NAME.tsv>"
curl -s -X PATCH http://localhost:8087/v1/jobs/$JOB_ID \
  -H "Content-Type: application/json" \
  -d "{\"actions\": [{...with route=local and agent_id=$NEW_AGENT_ID...}]}"

# Manually trigger
curl -s -X POST http://localhost:8087/v1/jobs/$JOB_ID/executions
```

Verify the execution succeeds and the letta-local-runner JSONL log
shows the invocation:

```bash
tail -1 ~/Library/Logs/letta-local-runner/$(date +%Y-%m-%d).jsonl | jq .
```

## Phase G — Cron repoint (all jobs)

Once Phase F passes, repoint the remaining cron jobs:

```bash
# Iterate /tmp/crons-$OLD_AGENT_NAME.tsv
while IFS=$'\t' read -r JOB_ID TITLE REST; do
  curl -s -X PATCH http://localhost:8087/v1/jobs/$JOB_ID \
    -H "Content-Type: application/json" \
    -d "@<(jq -n --arg AID \"$NEW_AGENT_ID\" '{actions: [{action_type: \"agent_message\", config: {agent_id: $AID, route: \"local\"}}]}')"
done < /tmp/crons-$OLD_AGENT_NAME.tsv
```

(Adapt for each job's existing message + timeout settings — this is a
sketch, not a complete one-liner.)

## Phase H — Switchover

### H1. Disable the Docker agent (don't delete yet)

Either detach all its tools to render it effectively inert, or rename
it with an `XXX-PRE-LOCAL-` prefix so it's visibly retired but
recoverable.

### H2. Update any system protocols referring to Docker-mode tools

Search canonical reference files and pa-web-ui routing for the old
agent_id; update or document references.

## Phase I — Soak + rollback

### Soak window

Watch for 5-7 days:
- Daily: check `letta-local-runner` JSONL for errors or `race_recovered`
  events involving this agent
- Daily: check scheduler-service execution records for this agent's
  cron jobs — all should be `status=succeeded`
- Daily: check pa-web-ui logs for any user-facing errors with the agent
- Weekly: review any new archival passages the agent inserted to
  confirm shape

### Rollback (if needed)

See the **Reversibility envelope** section at the top of this runbook
for the cost matrix over time. The mechanical steps:

1. **Repoint cron jobs back.** For each row in `/tmp/crons-$OLD_AGENT_NAME.tsv`,
   PATCH back to `route=letta` and `agent_id=$OLD_AGENT_ID`. SQL
   equivalent if iterating is preferable:

   ```sql
   UPDATE jobs
   SET actions = jsonb_set(
     jsonb_set(actions, '{0,config,route}', '"letta"'),
     '{0,config,agent_id}', '"<OLD_AGENT_ID>"'
   )
   WHERE actions->0->'config'->>'agent_id' = '<NEW_AGENT_ID>';
   ```

2. **Restore the Docker agent.** Rename it back (drop the
   `XXX-PRE-LOCAL-` prefix from H1); re-attach the tool set from
   `agent.json` (Phase B1 backup).

3. **Merge back any new state from the local-mode agent.** Skip if
   t<1 day; otherwise:
   - Export new archival passages from local-mode agent (post-Phase B
     timestamp), ingest into Docker agent's archival store via API
   - Diff the local-mode memfs commit log against the Phase B baseline
     snapshot; cherry-pick any agent-authored commits back to the
     Docker Gitea repo
   - Conversations stay where they are (browser-level state); users
     just see them as historical when they switch back

4. **Document.** Append to `docs/migrations/local-mode/$OLD_AGENT_NAME.md`
   (created at final teardown — create now if doing rollback before
   teardown). Include: failure mode, what was rolled back, what state
   was merged back, lessons for future migrations.

5. **Leave the local-mode agent record alone** (don't delete) until
   you've confirmed the rollback works end-to-end. Final cleanup:
   `rm $LOCAL_BACKEND_DIR/agents/<base64-id>.json` and
   `rm -rf $LOCAL_BACKEND_DIR/memfs/<agent-id>/`.

### When NOT to roll back

Some failure modes look bad but don't actually warrant rollback:

- **A single cron job execution fails** with a runner timeout or 500 —
  scheduler-service's retry policy + the runner's race-loss heuristic
  handle the common transient cases. Investigate the JSONL log first.
- **The agent responds more slowly than the Docker version** — this is
  expected for some model+context combos; the LiteLLM/cold-start
  variance is normal. Measure before rolling back.
- **One Task tool delegation fails** that was reading parent memfs —
  this is the expected behavior per W6. Refactor the delegation
  pattern; don't roll back.

Rollback when:
- Repeated cron failures across multiple jobs over hours
- Memfs corruption (git state diverges from expected; commits fail
  preconditions repeatedly)
- The agent loses its persona / acts as bare Letta Code
- A downstream signal or task pipeline breaks because the agent's
  outputs changed shape

### Final teardown (after successful soak)

1. Export the Docker agent's final archival memory for archival
2. Delete the Docker agent record
3. Delete the Gitea memfs repo (`docker exec gitea rm -rf /data/git/repositories/agents/$OLD_AGENT_ID.git`)
4. Commit a per-agent migration log to `docs/migrations/local-mode/$OLD_AGENT_NAME.md`

## Operational followups

These are not gating per-agent migrations but should be in place
before migrating MC (the user-facing chat agent):

- **LiteLLM health monitoring**: a scheduler-service cron that probes
  `http://litellm:4000/v1/models` every 5 min and restarts the
  container on sustained failure. The Prisma DB watchdog bug surfaced
  in W14 can brick all chat completions for hours without explicit
  intervention.
- **letta-local-runner observability dashboard**: aggregate JSONL logs
  to a single view; alert on `race_recovered` rates above a threshold
  (indicates concurrent-invocation pressure).
- **Embedding provider config**: when migrating an agent that uses
  archival memory, configure a separate embedding provider in local
  mode (TBD mechanism — investigate during first archival-using
  agent's migration).

## References

- Plan doc: `docs/plans/2026-05-25-letta-code-local-mode-investigation.md`
- letta-local-runner README: `letta-local-runner/README.md`
- Existing memfs migration runbook (for context, since superseded):
  `docs/runbooks/memfs-migration-per-agent.md`
- agent-memfs-conventions: `docs/runbooks/agent-memfs-conventions.md`
- MCP audit (which agents use what): plan W4 section
- Provider routing (Option A LiteLLM via lmstudio): plan W14 section
- Subagent caveats: plan W6 section
- Custom Python tool replacements: plan W7 section
