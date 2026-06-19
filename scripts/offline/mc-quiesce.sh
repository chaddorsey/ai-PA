#!/usr/bin/env bash
# mc-quiesce.sh [--dry-run]
#
# Freeze ONLY the MC agent process (the `node letta … --agent 8474bbbd …` that
# is a descendant of the `kinara` tmux pane — the interactive Mission Control),
# so the offline laptop is the SINGLE writer of MC's memory + live conversation
# during a fold-in / acceptance window.
#
# IMPORTANT: we SIGSTOP only the AGENT NODE (+ its descendants), NOT the
# agent-supervise bash / pane leader. Stopping the process-group leader orphans
# the group and the kernel auto-SIGCONTs it (POSIX orphaned-stopped-group rule),
# so the freeze wouldn't hold. The node is a non-leader whose parent stays alive,
# so SIGSTOP sticks. agent-supervise won't relaunch (the child is stopped, not
# exited). mc-resume.sh SIGCONTs it back.
#
# Untouched: the letta-local-runner (automation keeps running → namespaced =
# Check 4), the other 7 fleet agents, the guardian, the tmux server, the
# supervise bash, and the pane.
set -uo pipefail
SESSION=kinara
AGENT=agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d
STATE="$HOME/.letta/mc-quiesce.state"
export TMUX_TMPDIR=/tmp
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

command -v tmux >/dev/null || { echo "ERROR: tmux not found"; exit 1; }
tmux has-session -t "$SESSION" 2>/dev/null || { echo "ERROR: no '$SESSION' tmux session"; exit 1; }
PANE=$(tmux list-panes -t "$SESSION" -F '#{pane_pid}' 2>/dev/null | head -1)
[ -n "$PANE" ] || { echo "ERROR: no pane pid for '$SESSION'"; exit 1; }

# Is candidate $1 a descendant of $PANE? (so we target the KINARA interactive MC,
# never the runner's MC subprocess, which has different ancestry.)
is_under_pane() {
  local a="$1"
  while a=$(ps -o ppid= -p "$a" 2>/dev/null | tr -d ' '); [ -n "$a" ] && [ "$a" != 1 ]; do
    [ "$a" = "$PANE" ] && return 0
  done
  return 1
}

NODE=""
for p in $(pgrep -f -- "letta --backend local --agent $AGENT" 2>/dev/null); do
  if is_under_pane "$p"; then NODE="$p"; break; fi
done
[ -n "$NODE" ] || { echo "ABORT: no MC agent node found under '$SESSION' pane $PANE — refusing."; exit 1; }

collect() { local p=$1; echo "$p"; local c; for c in $(pgrep -P "$p" 2>/dev/null); do collect "$c"; done; }
TARGET=$(collect "$NODE" | sort -un)          # the node + its descendants (NOT the supervise bash)
CSV=$(echo "$TARGET" | tr '\n' ',' | sed 's/,$//')

echo "MC agent node + descendants (to freeze; supervise bash/pane left running):"
ps -o pid,stat,command= -p "$CSV" 2>/dev/null | cut -c1-92
if [ "$DRY" = 1 ]; then echo "[dry-run] would SIGSTOP the above; nothing changed."; exit 0; fi

echo "$TARGET" > "$STATE"
# shellcheck disable=SC2086
kill -STOP $TARGET 2>/dev/null
echo "QUIESCED → SIGSTOP sent to MC agent node. Supervise bash, runner/automation, other 7 agents, guardian, tmux: untouched."
echo "Resume with: ~/bin/mc-resume.sh"
