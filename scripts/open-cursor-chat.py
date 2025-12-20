#!/usr/bin/env python3
"""
Open a Cursor Chat by Composer ID

This script helps you open a specific chat in Cursor by creating the necessary
panel entries and providing instructions.
"""

import sqlite3
import json
import sys
import subprocess
from pathlib import Path

# Paths
HOME = Path.home()
GLOBAL_STORAGE_DB = HOME / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
WORKSPACE_STORAGE_DIR = HOME / "Library/Application Support/Cursor/User/workspaceStorage"
WORKSPACE_ID = "183af07563ac8178962e625e5f6f3d4a"
WORKSPACE_DB = WORKSPACE_STORAGE_DIR / WORKSPACE_ID / "state.vscdb"

def find_chat_by_id_or_title(search_term):
    """Find a chat by ID or title."""
    if not WORKSPACE_DB.exists():
        print(f"❌ ERROR: Workspace database not found")
        return None
    
    conn = sqlite3.connect(WORKSPACE_DB)
    try:
        cursor = conn.execute("SELECT value FROM ItemTable WHERE key = 'composer.composerData'")
        row = cursor.fetchone()
        if not row:
            return None
        
        data = json.loads(row[0])
        composers = data.get('allComposers', [])
        
        search_lower = search_term.lower()
        for comp in composers:
            comp_id = comp.get('composerId', '')
            title = (comp.get('title') or comp.get('name') or 'Untitled').lower()
            
            if search_lower in comp_id.lower() or search_lower in title:
                return comp
        
        return None
    finally:
        conn.close()

def create_panel_entry(comp_id):
    """Create a panel entry for a composer ID."""
    if not GLOBAL_STORAGE_DB.exists():
        print(f"❌ ERROR: Global storage database not found")
        return False
    
    conn = sqlite3.connect(GLOBAL_STORAGE_DB)
    try:
        panel_key = f"workbench.panel.composerChatViewPane.{comp_id}"
        hidden_key = f"{panel_key}.hidden"
        
        # Create panel entry if it doesn't exist
        cursor = conn.execute("SELECT key FROM ItemTable WHERE key = ?", (panel_key,))
        if not cursor.fetchone():
            panel_value = json.dumps({})
            conn.execute(
                "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                (panel_key, panel_value)
            )
            print(f"✓ Created panel entry for {comp_id[:8]}...")
        else:
            print(f"✓ Panel entry already exists for {comp_id[:8]}...")
        
        # Remove hidden flag if it exists
        cursor = conn.execute("SELECT key FROM ItemTable WHERE key = ?", (hidden_key,))
        if cursor.fetchone():
            conn.execute("DELETE FROM ItemTable WHERE key = ?", (hidden_key,))
            print(f"✓ Removed hidden flag")
        
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False
    finally:
        conn.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 open-cursor-chat.py <chat-id-or-title>")
        print("\nExample:")
        print("  python3 open-cursor-chat.py 'Initial greeting'")
        print("  python3 open-cursor-chat.py aabdb90d-8276-4e04-ab15-e12e369b86f8")
        print("  python3 open-cursor-chat.py aabdb90d")
        return 1
    
    search_term = ' '.join(sys.argv[1:])
    
    print(f"Searching for chat: {search_term}...")
    chat = find_chat_by_id_or_title(search_term)
    
    if not chat:
        print(f"❌ Chat not found: {search_term}")
        print("\n💡 Tip: Run 'python3 scripts/list-cursor-chats.py' to see all available chats")
        return 1
    
    comp_id = chat.get('composerId')
    title = chat.get('title') or chat.get('name') or 'Untitled'
    
    print(f"✓ Found: {title}")
    print(f"  ID: {comp_id}")
    print()
    
    # Check if Cursor is running
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Cursor.app/Contents/MacOS/Cursor"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("⚠️  WARNING: Cursor is running!")
            print("   You should close Cursor before modifying the database.")
            print("   However, we'll proceed with creating the panel entry...")
            print()
    except:
        pass
    
    # Create panel entry
    print("Creating panel entry in global storage...")
    if create_panel_entry(comp_id):
        print()
        print("=" * 70)
        print("✓ Panel entry created!")
        print()
        print("Next steps:")
        print("1. If Cursor was running, restart it")
        print("2. Open Cursor")
        print("3. The chat should now appear in your chat history menu")
        print("4. If it doesn't appear, try:")
        print("   - Opening the Composer (Cmd+I)")
        print("   - Checking the chat history dropdown")
        print("   - Searching for the chat title in Cursor")
        print()
        print(f"Chat: {title}")
        print(f"ID: {comp_id}")
        print("=" * 70)
        return 0
    else:
        print("❌ Failed to create panel entry")
        return 1

if __name__ == "__main__":
    exit(main())


