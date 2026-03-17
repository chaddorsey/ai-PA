#!/bin/bash
# Deploy the timer widget from server to laptop
# Run this on the LAPTOP

set -e

SERVER="dorseyhomeserver@100.99.171.119"
REMOTE_BASE="/Volumes/main-drive/ai-PA/omnifocus-timer"
LOCAL_BASE="$HOME/Dropbox/dev/omnifocus-timer"
PLUGIN_DEST="$HOME/Library/Containers/com.omnigroup.OmniFocus4/Data/Library/Application Support/Plug-Ins/com.dorsey.omnifocus-timer.omnifocusjs"

echo "=== OmniFocus Timer Deploy ==="

# 1. Sync widget source
echo "[1/6] Syncing widget source..."
rsync -az --delete "$SERVER:$REMOTE_BASE/TimerWidget/" "$LOCAL_BASE/TimerWidget/"

# 2. Sync toggle script
echo "[2/6] Syncing toggle script..."
scp -q "$SERVER:$REMOTE_BASE/toggle-timer.sh" "$LOCAL_BASE/toggle-timer.sh"
chmod +x "$LOCAL_BASE/toggle-timer.sh"

# 3. Sync plugin timerLib.js
echo "[3/6] Syncing OmniFocus plugin..."
scp -q "$SERVER:$REMOTE_BASE/omnifocus-timer.omnifocusjs/Resources/timerLib.js" "$PLUGIN_DEST/Resources/timerLib.js"

# 4. Build widget
echo "[4/6] Building widget (release)..."
cd "$LOCAL_BASE/TimerWidget"
swift build -c release 2>&1 | tail -3

# 5. Sync supporting files
echo "[5/8] Syncing queue manager and Karabiner config..."
scp -q "$SERVER:$REMOTE_BASE/widget-queue.sh" "$LOCAL_BASE/widget-queue.sh" 2>/dev/null || true
chmod +x "$LOCAL_BASE/widget-queue.sh" 2>/dev/null || true
scp -q "$SERVER:$REMOTE_BASE/karabiner-timer-toggle.json" "$HOME/.config/karabiner/assets/complex_modifications/timer-toggle.json" 2>/dev/null || true

# 6. Install launchd plist if not present
echo "[6/8] Checking launchd plist..."
PLIST_DEST="$HOME/Library/LaunchAgents/com.dorsey.timer-widget.plist"
if [ ! -f "$PLIST_DEST" ]; then
    scp -q "$SERVER:$REMOTE_BASE/com.dorsey.timer-widget.plist" "$PLIST_DEST"
    echo "    Installed launchd plist"
fi

# 7. Restart widget via launchd or direct
echo "[7/8] Restarting widget..."
if launchctl list | grep -q "com.dorsey.timer-widget"; then
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    launchctl load "$PLIST_DEST"
    echo "    Restarted via launchd"
else
    pkill -f "TimerWidget" 2>/dev/null || true
    sleep 1
    launchctl load "$PLIST_DEST" 2>/dev/null || {
        nohup "$LOCAL_BASE/TimerWidget/.build/release/TimerWidget" > /tmp/timer-widget.log 2>&1 &
        echo "    PID: $!"
    }
fi

# 8. Done
echo "[8/8] Done!"
echo ""
echo "    Widget is running (managed by launchd)."
echo "    If you updated timerLib.js, restart OmniFocus to reload the plugin."
echo ""
