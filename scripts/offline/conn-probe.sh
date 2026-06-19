#!/usr/bin/env bash
# conn-probe.sh — single source-of-truth link/capability state for the offline MC.
#
# Writes ~/.letta/offline-bus/link.json which the sync-runner, the model-swap
# (Phase 4), and MC's capability-awareness all read. "online" here means "home is
# reachable for git sync", i.e. the SSH tunnel to the server's Gitea is up and
# answering — that is the only thing the laptop needs the network for (it never
# calls Gmail/Slack/etc directly; those are queued via the outbox).
#
# Simulated drops (acceptance "≥N simulated drops"): create the flag file
#   ~/.letta/offline-bus/force-offline
# to force online=false WITHOUT tearing down the real tunnel (which we need for
# SSH). Remove it to "reconnect". This is the supported drop-simulation hook.
set -euo pipefail

BUS_DIR="${OFFLINE_BUS_DIR:-$HOME/.letta/offline-bus}"
LINK_JSON="$BUS_DIR/link.json"
FORCE_OFFLINE="$BUS_DIR/force-offline"
GITEA_PROBE_URL="${GITEA_PROBE_URL:-http://127.0.0.1:3030/api/v1/version}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-4}"

mkdir -p "$BUS_DIR"

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Real reachability: Gitea via the tunnel answers 200.
http_code="$(curl -s -o /dev/null -m "$PROBE_TIMEOUT" -w '%{http_code}' "$GITEA_PROBE_URL" 2>/dev/null || echo 000)"
if [ "$http_code" = "200" ]; then
  server_reachable=true; tunnel_up=true
else
  server_reachable=false; tunnel_up=false
fi

# Forced-offline simulation overrides "online" but not the real tunnel state.
online="$server_reachable"
forced=false
if [ -f "$FORCE_OFFLINE" ]; then
  online=false; forced=true
fi

# Capability map: the laptop MC never calls these directly — always "queue via outbox".
cat > "$LINK_JSON" <<JSON
{
  "online": $online,
  "server_reachable": $server_reachable,
  "tunnel_up": $tunnel_up,
  "forced_offline": $forced,
  "services": { "gmail": false, "slack": false, "drive": false, "calendar": false, "tasks": false, "docs": false },
  "checked_at": "$(now_iso)"
}
JSON

echo "link: online=$online server_reachable=$server_reachable forced_offline=$forced (http=$http_code)"
