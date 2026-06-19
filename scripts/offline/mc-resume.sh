#!/usr/bin/env bash
# mc-resume.sh — undo mc-quiesce.sh: SIGCONT the frozen MC agent node (+ its
# descendants). Safe to run even if not quiesced (SIGCONT on a running process
# is a no-op). Pairs with the corrected mc-quiesce.sh (which freezes only the
# agent node, not the supervise bash / pane leader).
set -uo pipefail
SESSION=kinara
AGENT=agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d
STATE="$HOME/.letta/mc-quiesce.state"
export TMUX_TMPDIR=/tmp

if [ -f "$STATE" ]; then
  PIDS=$(cat "$STATE")
else
  # Fallback: re-find the MC agent node under the kinara pane + its descendants.
  PANE=$(tmux list-panes -t "$SESSION" -F '#{pane_pid}' 2>/dev/null | head -1)
  is_under_pane() { local a="$1"; while a=$(ps -o ppid= -p "$a" 2>/dev/null|tr -d ' '); [ -n "$a" ] && [ "$a" != 1 ]; do [ "$a" = "$PANE" ] && return 0; done; return 1; }
  collect() { local p=$1; echo "$p"; local c; for c in $(pgrep -P "$p" 2>/dev/null); do collect "$c"; done; }
  NODE=""; for p in $(pgrep -f -- "letta --backend local --agent $AGENT" 2>/dev/null); do is_under_pane "$p" && { NODE="$p"; break; }; done
  [ -n "$NODE" ] && PIDS=$(collect "$NODE" | sort -un)
fi
[ -n "${PIDS:-}" ] || { echo "nothing to resume"; exit 0; }

# shellcheck disable=SC2086
kill -CONT $PIDS 2>/dev/null
CSV=$(echo "$PIDS" | tr '\n' ',' | sed 's/,$//')
echo "RESUMED → SIGCONT sent. Current state (no 'T' = running):"
ps -o pid,stat,command= -p "$CSV" 2>/dev/null | cut -c1-92
rm -f "$STATE"
