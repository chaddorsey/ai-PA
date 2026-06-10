#!/usr/bin/env bash
# sync-slack-channel-directory.sh
#
# Sync the workspace channel directory (name → ID, visibility, archived,
# member count) to canonical at refs/slack/channels.json. All agents can
# then resolve channel names to IDs via a single Gitea read instead of
# paginating Slack's API live every time.
#
# Run on cron (daily) + on-demand when a new channel is created.

set -euo pipefail

ENV_FILE="${ENV_FILE:-/Volumes/main-drive/ai-PA/.env}"
LOG_DIR="${LOG_DIR:-/Volumes/main-drive/ai-PA/logs/health}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync-slack-channel-directory.log"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

SLACK_MCP_XOXP_TOKEN=$(grep ^SLACK_MCP_XOXP_TOKEN= "$ENV_FILE" | cut -d= -f2-)
GITEA_MEMFS_TOKEN=$(grep ^GITEA_MEMFS_TOKEN= "$ENV_FILE" | cut -d= -f2-)
# Use 127.0.0.1, NOT localhost: localhost resolves ::1 (IPv6) first and Gitea
# binds IPv4-only, so localhost silently fails (this is why the 5am launchd job,
# which doesn't set GITEA_BASE_URL, stopped refreshing after 2026-05-31).
GITEA_BASE_URL="${GITEA_BASE_URL:-http://127.0.0.1:3030}"
export SLACK_MCP_XOXP_TOKEN

log "Starting channel directory sync"

# Paginate through all channels (public + private), build a flat array.
tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

python3 <<'PY' > "$tmpfile"
import json, os, subprocess, sys

def page(cursor):
    body = {
        "types": "public_channel,private_channel",
        "exclude_archived": True,
        "limit": 1000,
    }
    if cursor:
        body["cursor"] = cursor
    r = subprocess.run(
        ["slack", "--as-user", "conversations", "list", "--body", json.dumps(body)],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        sys.exit(f"slack call failed: {r.stderr[:500]}")
    return json.loads(r.stdout)

cursor = ""
all_chans = []
pages = 0
while True:
    pages += 1
    d = page(cursor)
    for c in d.get("channels", []):
        all_chans.append({
            "id": c["id"],
            "name": c.get("name"),
            "is_private": c.get("is_private", False),
            "is_archived": c.get("is_archived", False),
            "num_members": c.get("num_members"),
            "topic": (c.get("topic") or {}).get("value", "") or None,
            "purpose": (c.get("purpose") or {}).get("value", "") or None,
            "created": c.get("created"),
        })
    cursor = (d.get("response_metadata") or {}).get("next_cursor", "")
    if not cursor or pages >= 20:
        break

# Sort by name for stable diffs
all_chans.sort(key=lambda c: (c.get("name") or "").lower())

out = {
    "synced_at_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    "total": len(all_chans),
    "pages_fetched": pages,
    "channels": all_chans,
}
print(json.dumps(out, indent=2))
PY

count=$(python3 -c "import json,sys; print(json.load(open('$tmpfile'))['total'])")
log "Fetched $count channels"

# Upload to canonical via Gitea contents API (PUT for update, falls back to POST for create)
REPO_API="$GITEA_BASE_URL/api/v1/repos/agents/agents-canonical"
SIGNAL_PATH="refs/slack/channels.json"

# Get current sha if file exists (needed for update)
sha=$(curl -s -H "Authorization: token $GITEA_MEMFS_TOKEN" \
  "$REPO_API/contents/$SIGNAL_PATH" \
  | python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get('sha','') if isinstance(d,dict) else '')
except Exception:
    print('')")

content_b64=$(base64 < "$tmpfile" | tr -d '\n')

if [ -n "$sha" ]; then
  # Update existing
  body=$(python3 -c "import json; print(json.dumps({'message':'chore: refresh slack channel directory','content':'$content_b64','sha':'$sha'}))")
  resp=$(curl -s -X PUT -H "Authorization: token $GITEA_MEMFS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$body" "$REPO_API/contents/$SIGNAL_PATH")
else
  # Create new
  body=$(python3 -c "import json; print(json.dumps({'message':'chore: create slack channel directory','content':'$content_b64'}))")
  resp=$(curl -s -X POST -H "Authorization: token $GITEA_MEMFS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "$body" "$REPO_API/contents/$SIGNAL_PATH")
fi

html_url=$(echo "$resp" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
    print((d.get('content') or {}).get('html_url',''))
except Exception:
    print('')")

if [ -n "$html_url" ]; then
  log "Wrote $count channels → $SIGNAL_PATH"
  log "  url: $html_url"
else
  log "WARN: upload may have failed; response: $(echo "$resp" | head -c 400)"
  exit 1
fi
