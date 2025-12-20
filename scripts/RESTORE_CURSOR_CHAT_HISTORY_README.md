# Restore Cursor Chat History Visibility

## Problem

Your chat history exists in Cursor's workspace storage database, but the chats don't appear in Cursor's history menu. This happens when panel entries in global storage are missing or marked as hidden.

## Solution

This script removes hidden flags and ensures panel entries are visible so your chat history appears in the menu.

## ⚠️ IMPORTANT: Before Running

**You MUST close Cursor completely before running this script!**

1. **Quit Cursor completely:**
   - Press `Cmd+Q` (or go to Cursor → Quit Cursor)
   - Verify it's closed: Check Activity Monitor or run `pgrep -f Cursor` (should return nothing)

2. **Do NOT run this script while Cursor is running** - it will corrupt the database!

## How to Run

1. **Close Cursor completely** (see above)

2. **Run the script:**
   ```bash
   cd /Volumes/main-drive/ai-PA
   python3 scripts/restore-cursor-chat-history.py
   ```

   Or if you prefer:
   ```bash
   /Volumes/main-drive/ai-PA/scripts/restore-cursor-chat-history.py
   ```

3. **The script will:**
   - Check that Cursor is closed
   - Create a backup of your global storage database
   - Remove hidden flags for your composer IDs
   - Ensure panel entries are visible

4. **After the script completes:**
   - Open Cursor
   - Check your chat history menu
   - If chats still don't appear, you may need to open each chat once to trigger Cursor to create the panel entries

## What the Script Does

1. **Safety Check:** Verifies Cursor is not running
2. **Backup:** Creates a timestamped backup of `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
3. **Remove Hidden Flags:** Removes any `.hidden` flags for your composer IDs in global storage
4. **Verify Visibility:** Ensures panel entries are set to visible

## Restoring from Backup

If something goes wrong, you can restore from the backup:

```bash
# Find the backup (it will have a timestamp)
ls -la ~/Library/Application\ Support/Cursor/User/globalStorage/state.vscdb.backup-*

# Restore it (replace TIMESTAMP with actual timestamp)
cp ~/Library/Application\ Support/Cursor/User/globalStorage/state.vscdb.backup-TIMESTAMP \
   ~/Library/Application\ Support/Cursor/User/globalStorage/state.vscdb
```

## Troubleshooting

**If chats still don't appear after running the script:**

1. Panel entries may need to be created by Cursor when you access each chat
2. Try opening chats manually by searching for their titles in your codebase
3. The chat data is safe in workspace storage - it just needs to be linked to panel entries

**If you get an error about Cursor running:**
- Make sure Cursor is completely quit (not just minimized)
- Check Activity Monitor for any Cursor processes
- Try `killall Cursor` if needed, then wait a few seconds before running the script

## Files Modified

- `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` (backed up before modification)

## Files Read (Not Modified)

- `~/Library/Application Support/Cursor/User/workspaceStorage/183af07563ac8178962e625e5f6f3d4a/state.vscdb` (read-only)




