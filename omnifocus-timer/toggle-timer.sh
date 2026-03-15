#!/bin/bash
# Toggle OmniFocus timer via Caps Lock
# Called by Karabiner-Elements

export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONPATH="/Users/chaddorsey/Dropbox/dev/omnifocus-cli/src:$PYTHONPATH"

STATUS=$(python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer status 2>/dev/null)
STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','idle'))" 2>/dev/null)

if [ "$STATE" = "running" ] || [ "$STATE" = "paused" ]; then
  python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer stop 2>/dev/null
else
  TASK_ID=$(osascript -e 'tell application "OmniFocus" to evaluate javascript "document.windows[0].selection.tasks[0].id.primaryKey"' 2>/dev/null)

  if [ -n "$TASK_ID" ]; then
    python3 -c "from omnifocus_cli.cli import cli; cli()" --format json timer start "$TASK_ID" 2>/dev/null
  fi
fi
