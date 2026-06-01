#!/usr/bin/env bash
# check-mc-pipeline-health.sh
#
# Host-side daily watchdog for Mission Control's pipeline health.
# Replaces the previous agentic self-check cron that ran in
# scheduler-service ("Pipeline-health: mc daily self-check"). Reason
# for swap: a health check that depends on the thing it's checking is
# the last thing that will catch a problem.
#
# Emits the same canonical signal MC was emitting itself —
# signals/<date>/mc-pipeline-health.md — so the steward's rollup is
# drop-in unaffected.
#
# Runs daily at 06:30 ET via launchd
# (com.ai-pa.mc-pipeline-health.plist). Decisions live in:
# docs/plans/2026-05-31-mc-migration-plan.md (Block B).

set -euo pipefail

ENV_FILE="${ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/check-mc-pipeline-health.log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

# Load canonical creds from .env
GITEA_MEMFS_TOKEN=$(grep ^GITEA_MEMFS_TOKEN= "$ENV_FILE" | cut -d= -f2-)
GITEA_BASE_URL="${GITEA_BASE_URL:-http://localhost:3030}"
export GITEA_MEMFS_TOKEN GITEA_BASE_URL

# Today's date in ET
TODAY_ET=$(TZ=America/New_York date +%Y-%m-%d)

log "MC pipeline-health watchdog start (date=$TODAY_ET)"

# ---- (1) MC's expected CLI surface ----
EXPECTED_CLIS=(granola slack omnifocus gws signal task drive-rag-curl atlassian)
MISSING_CLIS=()
for cli in "${EXPECTED_CLIS[@]}"; do
  if ! command -v "$cli" >/dev/null 2>&1; then
    MISSING_CLIS+=("$cli")
  fi
done

# ---- (2) Required env vars for MC's recipes ----
EXPECTED_ENV=(GITEA_MEMFS_TOKEN POSTGRES_PASSWORD SLACK_MCP_XOXP_TOKEN)
MISSING_ENV=()
for v in "${EXPECTED_ENV[@]}"; do
  if ! grep -q "^${v}=" "$ENV_FILE" 2>/dev/null; then
    MISSING_ENV+=("$v")
  fi
done

# ---- (3) MC Docker agent record reachability ----
# Once MC migrates to local, this section will swap to a memfs working
# tree check (currently still in Docker pre-migration).
MC_DOCKER_HEALTHY=true
mc_check=$(curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8283/v1/agents/agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef" 2>/dev/null || echo "000")
if [[ "$mc_check" != "200" ]]; then
  MC_DOCKER_HEALTHY=false
fi

# ---- (4) Canonical reachability (Gitea) ----
CANONICAL_HEALTHY=true
gitea_check=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical" 2>/dev/null || echo "000")
if [[ "$gitea_check" != "200" ]]; then
  CANONICAL_HEALTHY=false
fi

# ---- (5) Determine attention level ----
attention=routine
notes=()

if [[ "${#MISSING_CLIS[@]}" -gt 0 ]]; then
  notes+=("Missing CLIs: ${MISSING_CLIS[*]}")
  attention=elevated
fi
if [[ "${#MISSING_ENV[@]}" -gt 0 ]]; then
  notes+=("Missing env vars: ${MISSING_ENV[*]}")
  attention=elevated
fi
if [[ "$MC_DOCKER_HEALTHY" != "true" ]]; then
  notes+=("MC Docker record not reachable (HTTP $mc_check)")
  attention=urgent
fi
if [[ "$CANONICAL_HEALTHY" != "true" ]]; then
  notes+=("Canonical Gitea repo not reachable (HTTP $gitea_check)")
  attention=urgent
fi

if [[ "${#notes[@]}" -eq 0 ]]; then
  notes+=("All expected CLIs on PATH; required env vars set; MC record and canonical reachable.")
fi

# ---- (6) Build signal body ----
body=$(cat <<EOF
**Daily pipeline-health for $TODAY_ET** (host-side watchdog)

- CLIs: ${#EXPECTED_CLIS[@]} expected, $((${#EXPECTED_CLIS[@]} - ${#MISSING_CLIS[@]})) on PATH
- Env: ${#EXPECTED_ENV[@]} expected, $((${#EXPECTED_ENV[@]} - ${#MISSING_ENV[@]})) present
- MC Docker record: $(if [[ "$MC_DOCKER_HEALTHY" == "true" ]]; then echo "reachable"; else echo "UNREACHABLE"; fi)
- Canonical (Gitea): $(if [[ "$CANONICAL_HEALTHY" == "true" ]]; then echo "reachable"; else echo "UNREACHABLE"; fi)

$(for n in "${notes[@]}"; do echo "- $n"; done)

Emitted by \`scripts/check-mc-pipeline-health.sh\` (host-side watchdog).
Replaces the prior agentic self-check on 2026-06-01 as part of the MC
local-mode migration plan (Block B).
EOF
)

# ---- (7) Emit canonical signal ----
# Keep source='mc' so the file path is signals/<date>/mc-pipeline-health.md
# (matches what the steward rollup reads).
if ! command -v signal >/dev/null 2>&1; then
  log "WARN: signal CLI not on PATH; cannot emit"
  exit 2
fi

if echo "$body" | signal emit \
  --slug pipeline-health \
  --source mc \
  --date "$TODAY_ET" \
  --attention "$attention" \
  --description "Daily pipeline health for $TODAY_ET (host watchdog)" \
  --body-file - 2>>"$LOG"; then
  log "Emitted signal: signals/$TODAY_ET/mc-pipeline-health.md  attention=$attention"
else
  log "WARN: signal emit failed"
  exit 1
fi

if [[ "$attention" == "urgent" ]]; then
  exit 1
fi
exit 0
