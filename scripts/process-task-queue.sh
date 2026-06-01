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
Process pending pa_web.task_queue rows for task creation.

For each of these sources, claim up to 10 rows and turn them into
pa_web.tasks entries using the task_extraction_process_<source>.md
rules in your memfs:

  - slack
  - email
  - meeting
  - meeting_marker
  - google-docs-comment
  - docs-meeting
  - drive

Skip sources with no unclaimed rows. For each row:
  1. Claim it: `task queue-claim --source <source> --limit 10`
  2. For each returned row, decide if it's actionable:
     - If actionable: create the pa_web.tasks entry via `task write`
       per the extraction rules in your memfs
     - If not actionable (test data, duplicate, already-handled, no
       clear task): skip and mark it processed via
       `UPDATE pa_web.task_queue SET processed_at = NOW() WHERE id = <id>`
  3. Be lenient with the historical backlog. Triage decisively rather
     than asking for clarification.

When done, reply concisely with ONLY:
  "Processed N rows: created K tasks, skipped S, errors E."

Do NOT surface individual task details unless errors occurred.
Do NOT delegate to subagents - handle this directly.
PROMPTEOF
prompt=$(cat "$prompt_file")
rm -f "$prompt_file"

# Use Bash to dispatch; no web/fetch tools needed
log "invoking Tasks agent (this may take 30-90s)…"
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
    --disallowedTools 'web_search,fetch_webpage' 2>&1)

# Extract the result line (best-effort) — use heredoc to avoid shell quoting hell
parse_script=$(mktemp)
cat > "$parse_script" <<'PYEOF'
import json, sys
data = sys.stdin.read()
try:
    for line in reversed(data.splitlines()):
        try:
            obj = json.loads(line)
            if obj.get("type") == "result" and "result" in obj:
                print(obj["result"][:500])
                sys.exit(0)
        except Exception:
            pass
    print("(no result line found)")
except Exception as e:
    print(f"(parse error: {e})")
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
