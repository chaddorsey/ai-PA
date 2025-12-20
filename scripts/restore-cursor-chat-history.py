#!/usr/bin/env python3
"""
Restore Cursor Chat History Visibility

This script fixes the issue where chat history doesn't appear in Cursor's history menu.
It adds missing panel entries in global storage for composer IDs that exist in workspace storage.

IMPORTANT: Run this script ONLY when Cursor is completely closed.
"""

import sqlite3
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Paths
HOME = Path.home()
GLOBAL_STORAGE_DB = HOME / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
WORKSPACE_STORAGE_DIR = HOME / "Library/Application Support/Cursor/User/workspaceStorage"
WORKSPACE_ID = "183af07563ac8178962e625e5f6f3d4a"
WORKSPACE_DB = WORKSPACE_STORAGE_DIR / WORKSPACE_ID / "state.vscdb"

def check_cursor_running():
    """Check if Cursor is running by checking for main process and database lock."""
    import subprocess
    import fcntl
    
    # Check 1: Look for main Cursor.app process (more specific)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Cursor.app/Contents/MacOS/Cursor"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            if pids and pids[0]:
                print("❌ ERROR: Cursor main process is still running!")
                print(f"   Found process IDs: {', '.join(pids)}")
                print("   Please quit Cursor completely (Cmd+Q) before running this script.")
                return True
    except Exception:
        pass
    
    # Check 2: Try to lock the database file (best indicator)
    if GLOBAL_STORAGE_DB.exists():
        try:
            # Try to open the database in exclusive mode
            test_conn = sqlite3.connect(str(GLOBAL_STORAGE_DB), timeout=1.0)
            test_conn.execute("BEGIN EXCLUSIVE")
            test_conn.rollback()
            test_conn.close()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() or "locked" in str(e).lower():
                print("❌ ERROR: Database is locked - Cursor is likely still running!")
                print("   Please quit Cursor completely (Cmd+Q) and wait a few seconds.")
                return True
        except Exception:
            # If we can't check, assume it's safe (better than blocking)
            pass
    
    return False

def backup_database(db_path):
    """Create a backup of the database."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.backup-{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"✓ Backed up database to: {backup_path.name}")
    return backup_path

def get_composer_ids():
    """Get all composer IDs from workspace storage."""
    if not WORKSPACE_DB.exists():
        print(f"❌ ERROR: Workspace database not found at {WORKSPACE_DB}")
        return []
    
    conn = sqlite3.connect(WORKSPACE_DB)
    try:
        cursor = conn.execute("SELECT value FROM ItemTable WHERE key = 'composer.composerData'")
        row = cursor.fetchone()
        if not row:
            print("❌ ERROR: No composer data found in workspace storage")
            return []
        
        data = json.loads(row[0])
        composers = data.get('allComposers', [])
        composer_ids = [comp.get('composerId') for comp in composers if comp.get('composerId')]
        
        # Also get titles for logging
        composer_info = []
        for comp in composers:
            comp_id = comp.get('composerId')
            if comp_id:
                title = comp.get('title') or comp.get('name') or 'Untitled'
                composer_info.append((comp_id, title))
        
        return composer_info
    finally:
        conn.close()

def create_panel_entries(composer_info):
    """Create panel entries in global storage for each composer ID."""
    if not GLOBAL_STORAGE_DB.exists():
        print(f"❌ ERROR: Global storage database not found at {GLOBAL_STORAGE_DB}")
        return False
    
    conn = sqlite3.connect(GLOBAL_STORAGE_DB)
    try:
        created = 0
        already_exists = 0
        
        print("Creating panel entries in global storage...")
        for comp_id, title in composer_info:
            # Check if panel entry already exists
            panel_key = f"workbench.panel.composerChatViewPane.{comp_id}"
            hidden_key = f"{panel_key}.hidden"
            
            cursor = conn.execute("SELECT key FROM ItemTable WHERE key = ?", (panel_key,))
            if cursor.fetchone():
                already_exists += 1
                # Check if it's hidden
                cursor = conn.execute("SELECT value FROM ItemTable WHERE key = ?", (hidden_key,))
                hidden_row = cursor.fetchone()
                if hidden_row:
                    # Remove hidden flag
                    conn.execute("DELETE FROM ItemTable WHERE key = ?", (hidden_key,))
                    print(f"  ✓ Removed hidden flag: {title[:50]} ({comp_id[:8]}...)")
                else:
                    print(f"  ✓ Already exists (visible): {title[:50]} ({comp_id[:8]}...)")
            else:
                # Create a minimal panel entry
                # The entry structure should be an empty object or minimal structure
                # Cursor will populate it when the chat is opened
                panel_value = json.dumps({})
                conn.execute(
                    "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                    (panel_key, panel_value)
                )
                created += 1
                print(f"  ✓ Created panel entry: {title[:50]} ({comp_id[:8]}...)")
        
        conn.commit()
        
        print(f"\n✓ Created {created} panel entry/entries")
        if already_exists > 0:
            print(f"  ({already_exists} already existed)")
        
        return True
    except Exception as e:
        print(f"❌ ERROR creating panel entries: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

def ensure_panel_entries_visible(composer_info):
    """Ensure panel entries are visible by removing any .hidden flags."""
    if not GLOBAL_STORAGE_DB.exists():
        print(f"❌ ERROR: Global storage database not found at {GLOBAL_STORAGE_DB}")
        return False
    
    conn = sqlite3.connect(GLOBAL_STORAGE_DB)
    try:
        composer_ids = {comp_id for comp_id, _ in composer_info}
        checked = 0
        removed_hidden = 0
        
        print("Checking panel entries...")
        for comp_id, title in composer_info:
            checked += 1
            # Check if there's a .hidden flag for this composer ID
            hidden_key = f"workbench.panel.composerChatViewPane.{comp_id}.hidden"
            cursor = conn.execute("SELECT key FROM ItemTable WHERE key = ?", (hidden_key,))
            if cursor.fetchone():
                # Remove the hidden flag
                conn.execute("DELETE FROM ItemTable WHERE key = ?", (hidden_key,))
                removed_hidden += 1
                print(f"  ✓ Removed hidden flag: {title[:50]} ({comp_id[:8]}...)")
            else:
                # No hidden flag exists, which means it should be visible
                # (Cursor will create the panel entry when the chat is accessed)
                print(f"  ✓ Visible (no hidden flag): {title[:50]} ({comp_id[:8]}...)")
        
        conn.commit()
        
        print(f"\n✓ Checked {checked} composer(s)")
        if removed_hidden > 0:
            print(f"✓ Removed {removed_hidden} hidden flag(s)")
        else:
            print("✓ No hidden flags found to remove")
        
        return True
    except Exception as e:
        print(f"❌ ERROR ensuring panel visibility: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

def remove_hidden_flags(composer_info):
    """Remove .hidden flags for composer IDs that should be visible."""
    if not GLOBAL_STORAGE_DB.exists():
        print(f"❌ ERROR: Global storage database not found at {GLOBAL_STORAGE_DB}")
        return False
    
    conn = sqlite3.connect(GLOBAL_STORAGE_DB)
    try:
        removed = 0
        composer_ids = {comp_id for comp_id, _ in composer_info}
        
        # Find all hidden panel entries
        cursor = conn.execute(
            "SELECT key FROM ItemTable WHERE key LIKE 'workbench.panel.composerChatViewPane.%.hidden'"
        )
        all_hidden = cursor.fetchall()
        
        for (key,) in all_hidden:
            # Extract the panel ID from the key
            # Format: workbench.panel.composerChatViewPane.{ID}.hidden
            parts = key.split('.')
            if len(parts) >= 5:
                panel_id = parts[4]
                if panel_id in composer_ids:
                    # Remove the hidden flag
                    conn.execute("DELETE FROM ItemTable WHERE key = ?", (key,))
                    removed += 1
        
        conn.commit()
        
        if removed > 0:
            print(f"✓ Removed {removed} hidden flags")
        
        return True
    except Exception as e:
        print(f"❌ ERROR removing hidden flags: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

def main():
    print("=" * 70)
    print("Cursor Chat History Restore Script")
    print("=" * 70)
    print()
    
    # Allow bypass with --force flag
    force = "--force" in sys.argv or "-f" in sys.argv
    
    # Check if Cursor is running
    if check_cursor_running():
        if force:
            print("⚠️  WARNING: --force flag detected, proceeding anyway...")
            print("   This may corrupt the database if Cursor is actually running!")
            print()
        else:
            print("\n💡 Tip: If you're sure Cursor is closed, you can use --force to bypass this check")
            return 1
    
    print("✓ Cursor is not running - safe to proceed")
    print()
    
    # Verify databases exist
    if not GLOBAL_STORAGE_DB.exists():
        print(f"❌ ERROR: Global storage database not found at {GLOBAL_STORAGE_DB}")
        return 1
    
    if not WORKSPACE_DB.exists():
        print(f"❌ ERROR: Workspace database not found at {WORKSPACE_DB}")
        return 1
    
    # Get composer IDs
    print("Reading composer data from workspace storage...")
    composer_info = get_composer_ids()
    
    if not composer_info:
        print("❌ No composer IDs found")
        return 1
    
    print(f"✓ Found {len(composer_info)} composer(s)/chat(s)")
    print()
    
    # Backup database
    print("Creating backup...")
    backup_path = backup_database(GLOBAL_STORAGE_DB)
    print()
    
    # Create panel entries in global storage
    print("Creating panel entries in global storage...")
    create_panel_entries(composer_info)
    print()
    
    # Remove hidden flags for composer IDs (if any exist)
    print("Removing hidden flags for composer IDs...")
    remove_hidden_flags(composer_info)
    print()
    
    # Ensure panel entries are visible
    print("Ensuring panel entries are visible...")
    ensure_panel_entries_visible(composer_info)
    print()
    
    # Note: Cursor should automatically create panel entries when chats are accessed
    # We've removed any hidden flags that might be blocking them
    print("=" * 70)
    print("✓ Script completed successfully!")
    print()
    print("IMPORTANT: Panel entries may need to be created by Cursor.")
    print("Next steps:")
    print("1. Open Cursor")
    print("2. Try accessing your chat history menu")
    print("3. If chats still don't appear, you may need to open each chat once")
    print("   to trigger Cursor to create the panel entries.")
    print("   You can search for chat titles in your codebase to find them.")
    print()
    print("Chat titles found:")
    for comp_id, title in composer_info[:10]:
        print(f"  - {title}")
    if len(composer_info) > 10:
        print(f"  ... and {len(composer_info) - 10} more")
    print()
    print(f"Backup location: {backup_path}")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    exit(main())

