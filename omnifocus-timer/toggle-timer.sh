#!/bin/bash
# Toggle OmniFocus timer via Caps Lock
# Called by Karabiner-Elements

CLI="python3 -c 'from omnifocus_cli.cli import cli; cli()'"

STATUS=$(eval $CLI --format json timer status 2>/dev/null)
STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','idle'))" 2>/dev/null)

if [ "$STATE" = "running" ] || [ "$STATE" = "paused" ]; then
  # Timer is active — stop it
  eval $CLI --format json timer stop 2>/dev/null
else
  # No timer — start on the selected task in OmniFocus
  TASK_ID=$(osascript -e '
tell application "OmniFocus"
  try
    set _w to first document window
    set _sel to selected trees of content of _w
    if (count of _sel) > 0 then
      return id of value of item 1 of _sel
    end if
  end try
  return ""
end tell
' 2>/dev/null)

  if [ -n "$TASK_ID" ]; then
    eval $CLI --format json timer start "$TASK_ID" 2>/dev/null
  fi
fi
