#!/bin/bash
# Widget Queue Manager — called by Rover/LettaBot to manage the timer widget queue
# Usage:
#   widget-queue.sh set id1 id2 id3       — replace entire queue with these task IDs
#   widget-queue.sh push id1 [id2 ...]    — append task(s) to end of queue
#   widget-queue.sh insert N id           — insert task at position N (0-indexed)
#   widget-queue.sh remove id             — remove a task from the queue
#   widget-queue.sh clear                 — clear the queue
#   widget-queue.sh list                  — show current queue (JSON)
#   widget-queue.sh next id               — smart-insert: behind running task, or front if paused/idle
#   widget-queue.sh move id N             — move task to position N

QUEUE_FILE="$HOME/.omnifocus-timer-widget/queue.json"
mkdir -p "$(dirname "$QUEUE_FILE")"

# Signal widget to reload queue (SIGHUP restarts it, picking up new file contents)
notify_widget() {
  pkill -HUP -f 'TimerWidget' 2>/dev/null || true
}

# Ensure file exists
if [ ! -f "$QUEUE_FILE" ]; then
  echo '{"tasks":[]}' > "$QUEUE_FILE"
fi

CMD="${1:-list}"
shift 2>/dev/null

case "$CMD" in
  set)
    # Replace entire queue
    python3 -c "
import json, sys
ids = sys.argv[1:]
json.dump({'tasks': ids}, open('$QUEUE_FILE', 'w'))
print(json.dumps({'status': 'ok', 'queue': ids}))
" "$@"
    notify_widget
    ;;

  push)
    # Append task(s) to end
    python3 -c "
import json, sys
ids = sys.argv[1:]
data = json.load(open('$QUEUE_FILE'))
for i in ids:
    if i not in data['tasks']:
        data['tasks'].append(i)
json.dump(data, open('$QUEUE_FILE', 'w'))
print(json.dumps({'status': 'ok', 'queue': data['tasks']}))
" "$@"
    notify_widget
    ;;

  insert)
    # Insert at position
    POS="$1"
    ID="$2"
    python3 -c "
import json
data = json.load(open('$QUEUE_FILE'))
task_id = '$ID'
pos = int('$POS')
if task_id in data['tasks']:
    data['tasks'].remove(task_id)
data['tasks'].insert(pos, task_id)
json.dump(data, open('$QUEUE_FILE', 'w'))
print(json.dumps({'status': 'ok', 'queue': data['tasks']}))
"
    notify_widget
    ;;

  remove)
    # Remove a task
    python3 -c "
import json
data = json.load(open('$QUEUE_FILE'))
task_id = '$1'
data['tasks'] = [t for t in data['tasks'] if t != task_id]
json.dump(data, open('$QUEUE_FILE', 'w'))
print(json.dumps({'status': 'ok', 'queue': data['tasks']}))
"
    notify_widget
    ;;

  move)
    # Move task to position
    ID="$1"
    POS="$2"
    python3 -c "
import json
data = json.load(open('$QUEUE_FILE'))
task_id = '$ID'
pos = int('$POS')
if task_id in data['tasks']:
    data['tasks'].remove(task_id)
    data['tasks'].insert(pos, task_id)
    json.dump(data, open('$QUEUE_FILE', 'w'))
    print(json.dumps({'status': 'ok', 'queue': data['tasks']}))
else:
    print(json.dumps({'status': 'error', 'message': 'Task not in queue'}))
"
    notify_widget
    ;;

  clear)
    echo '{"tasks":[]}' > "$QUEUE_FILE"
    echo '{"status": "ok", "queue": []}'
    notify_widget
    ;;

  list)
    cat "$QUEUE_FILE"
    ;;

  next)
    # Smart-insert: behind running task, or at front if paused/idle
    ID="$1"
    if [ -z "$ID" ]; then
      echo '{"status": "error", "message": "next requires a task ID"}'
      exit 1
    fi
    # Check OmniFocus timer state via AppleScript
    TIMER_RUNNING=$(osascript -e '
      tell application "OmniFocus"
        try
          set taskTimers to every task timer of default document
          repeat with t in taskTimers
            if running of t then return "yes"
          end repeat
        end try
        return "no"
      end tell
    ' 2>/dev/null || echo "no")

    if [ "$TIMER_RUNNING" = "yes" ]; then
      POS=1
    else
      POS=0
    fi
    python3 -c "
import json
data = json.load(open('$QUEUE_FILE'))
task_id = '$ID'
pos = $POS
timer_running = ('$TIMER_RUNNING' == 'yes')
if task_id in data['tasks']:
    data['tasks'].remove(task_id)
data['tasks'].insert(pos, task_id)
json.dump(data, open('$QUEUE_FILE', 'w'))
print(json.dumps({'status': 'ok', 'queue': data['tasks'], 'position': pos, 'timer_running': timer_running}))
"
    notify_widget
    ;;

  *)
    echo '{"status": "error", "message": "Unknown command: '"$CMD"'. Use: set, push, insert, remove, next, move, clear, list"}'
    exit 1
    ;;
esac
