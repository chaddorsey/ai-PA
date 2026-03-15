#!/bin/bash
# Widget Queue Manager — called by Rover/LettaBot to manage the timer widget queue
# Usage:
#   widget-queue.sh set id1 id2 id3       — replace entire queue with these task IDs
#   widget-queue.sh push id1 [id2 ...]    — append task(s) to end of queue
#   widget-queue.sh insert N id           — insert task at position N (0-indexed)
#   widget-queue.sh remove id             — remove a task from the queue
#   widget-queue.sh clear                 — clear the queue
#   widget-queue.sh list                  — show current queue (JSON)
#   widget-queue.sh move id N             — move task to position N

QUEUE_FILE="$HOME/.omnifocus-timer-widget/queue.json"
mkdir -p "$(dirname "$QUEUE_FILE")"

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
    ;;

  clear)
    echo '{"tasks":[]}' > "$QUEUE_FILE"
    echo '{"status": "ok", "queue": []}'
    ;;

  list)
    cat "$QUEUE_FILE"
    ;;

  *)
    echo '{"status": "error", "message": "Unknown command: '"$CMD"'. Use: set, push, insert, remove, move, clear, list"}'
    exit 1
    ;;
esac
