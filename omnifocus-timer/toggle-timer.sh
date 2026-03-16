#!/bin/bash
# Toggle OmniFocus timer via Caps Lock
# Called by Karabiner-Elements
#
# Running → Complete task (stop timer + mark done), LED off
# Paused  → Resume timer, LED on
# Idle    → Start timer on selected OmniFocus task, LED on

export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONPATH="/Users/chaddorsey/Dropbox/dev/omnifocus-cli/src:$PYTHONPATH"

# Function to set Caps Lock LED state via osascript
caps_on() {
  osascript -e 'tell application "System Events" to key code 57 using {}' 2>/dev/null
  # If caps lock is already on, this toggles it off then on — check and correct
  local current
  current=$(hidutil property --get 'CapsLockState' 2>/dev/null | grep -o '[01]')
  if [ "$current" = "0" ]; then
    osascript -e 'tell application "System Events" to key code 57 using {}' 2>/dev/null
  fi
}

caps_off() {
  local current
  current=$(hidutil property --get 'CapsLockState' 2>/dev/null | grep -o '[01]')
  if [ "$current" = "1" ]; then
    osascript -e 'tell application "System Events" to key code 57 using {}' 2>/dev/null
  fi
}

STATUS=$(python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer status 2>/dev/null)
STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','idle'))" 2>/dev/null)
TASK_ID=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('taskId',''))" 2>/dev/null)

if [ "$STATE" = "running" ]; then
  # Complete the task: stop timer + mark complete in OmniFocus
  python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer stop 2>/dev/null
  osascript -e "tell application \"OmniFocus\" to evaluate javascript \"var t=Task.byIdentifier('$TASK_ID');if(t)t.markComplete();'done'\"" 2>/dev/null
  caps_off
elif [ "$STATE" = "paused" ]; then
  # Resume the paused task
  python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer resume 2>/dev/null
  caps_on
else
  # No timer — start on the selected task in OmniFocus
  TASK_ID=$(osascript -e 'tell application "OmniFocus" to evaluate javascript "document.windows[0].selection.tasks[0].id.primaryKey"' 2>/dev/null)
  if [ -n "$TASK_ID" ]; then
    python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer start "$TASK_ID" 2>/dev/null
    caps_on
  fi
fi
