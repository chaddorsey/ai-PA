#!/bin/bash
# Toggle OmniFocus timer via Caps Lock
# Called by Karabiner-Elements

# Adjust this path to where omnifocus-cli is installed on the laptop
OMNIFOCUS_CLI="${OMNIFOCUS_CLI:-omnifocus-cli}"

STATUS=$($OMNIFOCUS_CLI timer status --format json 2>/dev/null)
STATE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','idle'))" 2>/dev/null)

if [ "$STATE" = "running" ] || [ "$STATE" = "paused" ]; then
  # Timer is active — stop it
  $OMNIFOCUS_CLI timer stop --format json 2>/dev/null
else
  # No timer — start on the most recently selected task
  # Get the selected task from OmniFocus via AppleScript
  TASK_ID=$(osascript -e '
    tell application "OmniFocus"
      set _sel to selected trees of content of first document window
      if (count of _sel) > 0 then
        set _task to value of item 1 of _sel
        return id of _task
      else
        return ""
      end if
    end tell
  ' 2>/dev/null)

  if [ -n "$TASK_ID" ]; then
    $OMNIFOCUS_CLI timer start "$TASK_ID" --format json 2>/dev/null
  fi
fi
