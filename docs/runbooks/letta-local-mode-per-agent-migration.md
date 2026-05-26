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

1. Revert cron jobs to `route=letta` with `agent_id=$OLD_AGENT_ID`
   (the Docker record still exists since H1 didn't delete it)
2. Detach any tools we added during migration; restore the Docker
   agent's pre-migration tool inventory from `agent.json` (B1)
3. Re-rename it (drop the `XXX-PRE-LOCAL-` prefix)
4. Document the failure mode in the per-agent migration log and
   update this runbook

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
