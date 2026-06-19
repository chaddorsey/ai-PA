#!/usr/bin/env bash
# travel-mode.sh on|off|status — flip laptop-primary vs home-automation-only.
#
# `on`  : the laptop hosts the live conversational MC + shapes memory; the
#         authority flag is set so outward side-effects (send/post/book) are
#         ONLY executed by home on reconnect — the offline laptop drafts/queues,
#         never sends directly (design §6 authority rule).
# `off` : reverse to home-primary; trigger a final sync; laptop returns to thin
#         client.
#
# State is a single JSON the drainer (authority enforcement) and MC's
# offline-awareness read. This is the lightweight manual flip; presence/network
# auto-trigger is deferred (design §10).
set -euo pipefail

BUS_DIR="${OFFLINE_BUS_DIR:-$HOME/.letta/offline-bus}"
STATE="$BUS_DIR/travel-mode.json"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$BUS_DIR"

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

write_state() { # $1=mode $2=authority
  cat > "$STATE" <<JSON
{
  "mode": "$1",
  "authority": "$2",
  "live_conversation_owner": "$([ "$1" = "laptop-primary" ] && echo laptop || echo home)",
  "memory_shaper": "$([ "$1" = "laptop-primary" ] && echo laptop || echo home)",
  "since": "$(now_iso)"
}
JSON
}

case "${1:-status}" in
  on)
    write_state "laptop-primary" "home-sends"
    echo "travel-mode ON: laptop-primary; authority=home-sends (laptop drafts/queues only)."
    ;;
  off)
    write_state "home-primary" "home-sends"
    echo "travel-mode OFF: home-primary. Running final sync…"
    bash "$HERE/sync-runner.sh" || true
    echo "Final sync attempted; laptop is thin-client again."
    ;;
  status)
    if [ -f "$STATE" ]; then cat "$STATE"; else echo '{"mode":"home-primary","authority":"home-sends","note":"default (no travel-mode set)"}'; fi
    ;;
  *)
    echo "usage: travel-mode.sh on|off|status" >&2; exit 2;;
esac
