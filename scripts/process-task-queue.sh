#!/usr/bin/env bash
# process-task-queue.sh
#
# Periodically drains pa_web.task_queue task-creation rows by invoking
# the local Tasks agent in headless mode. Gates the agent invocation on
# a cheap psql pre-check so we don't burn tokens on empty queues.
#
# Sources handled here are the ones that should become pa_web.tasks
# entries:
#   - slack, email, meeting, meeting_marker, google-docs-comment,
#     docs-meeting, drive
#
# Sources NOT handled here (have their own consumers):
#   - email-watch    → Email agent acts on watch events; not a task source
#   - mc-completion  → MC reads its own completion notifications
#
# Runs every 15 min via launchd (~/Library/LaunchAgents/com.ai-pa.task-queue-processor.plist).

set -euo pipefail

ENV_FILE="${ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/process-task-queue.log"

# Tasks agent — local mode (per docs/migrations/local-mode/tasks-agent.md)
TASKS_AGENT_ID="agent-local-30c45759-6bdd-4253-8134-9d4e69e6e8f4"

# Sources eligible for task creation
QUEUE_SOURCES="slack email meeting meeting_marker google-docs-comment docs-meeting drive"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Load creds
POSTGRES_PASSWORD=$(grep ^POSTGRES_PASSWORD= "$ENV_FILE" | cut -d= -f2-)
GITEA_MEMFS_TOKEN=$(grep ^GITEA_MEMFS_TOKEN= "$ENV_FILE" | cut -d= -f2-)
SLACK_MCP_XOXP_TOKEN=$(grep ^SLACK_MCP_XOXP_TOKEN= "$ENV_FILE" | cut -d= -f2-)
export POSTGRES_PASSWORD GITEA_MEMFS_TOKEN SLACK_MCP_XOXP_TOKEN

# ---- (1) Cheap pre-check: any unclaimed rows in task-creation sources? ----
quoted=$(printf "'%s'," $QUEUE_SOURCES | sed 's/,$//')
psql_query="SELECT source, COUNT(*) FROM pa_web.task_queue WHERE claimed_at IS NULL AND source IN ($quoted) GROUP BY source ORDER BY 2 DESC"

depth_report=$(PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -p 5433 -U postgres -d postgres -At -c "$psql_query" 2>/dev/null || echo "")

if [[ -z "$depth_report" ]]; then
  log "queue empty (no unclaimed rows in task-creation sources) — skipping agent invocation"
  exit 0
fi

total=$(echo "$depth_report" | awk -F'|' '{sum += $2} END {print sum+0}')
log "queue has $total unclaimed row(s): $(echo "$depth_report" | tr '\n' ' ')"

# ---- (2) Invoke Tasks agent in headless mode to claim + process ----
prompt_file=$(mktemp)
cat > "$prompt_file" <<'PROMPTEOF'
Process pending pa_web.task_queue rows.

Sources to process (try each one; skip if no rows):
  slack, email, meeting, meeting_marker, google-docs-comment, docs-meeting, drive

For each source:
  1. Claim up to 10 rows: `task queue-claim --source <source> --limit 10`
  2. For EACH returned row, do BOTH actions below (in this order):

     STEP A — task creation decision:
       - If the row's payload represents an actionable task: create a
         pa_web.tasks entry via `task write` using the
         task_extraction_process_<source>.md rules in your memfs.
       - If NOT actionable (test data, duplicate of existing task,
         already-handled, no clear ask, expired ask): do nothing
         here — just go to Step B.

     STEP B — MANDATORY queue marking (do this for EVERY claimed row,
              whether you created a task or not):

       PA_WEB_POSTGRES_URL="postgresql://postgres:${POSTGRES_PASSWORD}@localhost:5433/postgres" \
       psql "$PA_WEB_POSTGRES_URL" -c \
         "UPDATE pa_web.task_queue SET processed_at = NOW() WHERE id = <ROW_ID>"

       Failing to do Step B for a row creates a ZOMBIE (claimed but
       never processed) that won't be re-tried by anything. EVERY claimed
       row MUST have processed_at set before you move on.

  3. Be decisive with historical backlog. Don't ask the user for
     clarification — apply your best judgment and move on.

When done with all sources, your FINAL message must be exactly one line
in this format (so the wrapper script can parse it):

  PROCESSED: claimed=K1 created=K2 skipped=K3 errors=K4

Where:
  K1 = total rows you claimed across all sources
  K2 = number of pa_web.tasks rows you created
  K3 = number of rows you skipped (not actionable)
  K4 = number of rows where Step A or B errored

Do NOT surface individual task details. Do NOT delegate to subagents.
PROMPTEOF
prompt=$(cat "$prompt_file")
rm -f "$prompt_file"

# Use Bash to dispatch; no web/fetch tools needed
log "invoking Tasks agent (this may take 30-90s)…"

# Persist full agent output to a timestamped debug log alongside the main log
debug_log="$LOG_DIR/process-task-queue.agent-$(date +%Y%m%d-%H%M%S).log"

agent_response=$(env \
  LETTA_LOCAL_BACKEND_DIR="$HOME/.letta/lc-local-backend" \
  GITEA_BASE_URL="${GITEA_BASE_URL:-http://localhost:3030}" \
  GITEA_MEMFS_TOKEN="$GITEA_MEMFS_TOKEN" \
  POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  SLACK_MCP_XOXP_TOKEN="$SLACK_MCP_XOXP_TOKEN" \
  PA_AI_REPO_ROOT="/Volumes/main-drive/ai-PA" \
  PA_WEB_POSTGRES_PORT=5433 \
  letta --backend local --agent "$TASKS_AGENT_ID" \
    -p "$prompt" \
    --output-format json --new --yolo \
    --disallowedTools 'web_search,fetch_webpage' 2>&1 | tee "$debug_log")

log "agent output saved to: $debug_log"

# Parse the structured PROCESSED: line we now require, or fall back to
# the result event from stream-json. Print whatever we found.
parse_script=$(mktemp)
cat > "$parse_script" <<'PYEOF'
import json, re, sys
data = sys.stdin.read()
# First-pass: look for a literal PROCESSED: line in the result text
m = re.search(r"PROCESSED:\s*claimed=\d+\s+created=\d+\s+skipped=\d+\s+errors=\d+", data)
if m:
    print(m.group(0))
    sys.exit(0)
# Second-pass: hunt for the result event from stream-json
for line in reversed(data.splitlines()):
    try:
        obj = json.loads(line)
        if obj.get("type") == "result" and "result" in obj:
            print(obj["result"][:500])
            sys.exit(0)
    except Exception:
        pass
print("(no PROCESSED: line and no result event found — check debug log)")
PYEOF
result_line=$(echo "$agent_response" | python3 "$parse_script" 2>/dev/null || echo "(could not parse)")
rm -f "$parse_script"

log "agent result: $result_line"

# ---- (3) Post-run snapshot ----
post_depth=$(PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -p 5433 -U postgres -d postgres -At -c "$psql_query" 2>/dev/null || echo "")
if [[ -z "$post_depth" ]]; then
  log "post-run: queue fully drained"
else
  log "post-run: still unclaimed: $(echo "$post_depth" | tr '\n' ' ')"
fi
