#!/usr/bin/env python3
"""
List All Cursor Chats

This script lists all chats in your workspace storage with their titles,
first messages, and composer IDs. Use this to find chats you want to open manually.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

# Paths
HOME = Path.home()
WORKSPACE_STORAGE_DIR = HOME / "Library/Application Support/Cursor/User/workspaceStorage"
WORKSPACE_ID = "183af07563ac8178962e625e5f6f3d4a"
WORKSPACE_DB = WORKSPACE_STORAGE_DIR / WORKSPACE_ID / "state.vscdb"

def format_timestamp(ts):
    """Convert timestamp to readable date."""
    try:
        if isinstance(ts, (int, float)):
            # Timestamp in milliseconds
            dt = datetime.fromtimestamp(ts / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        pass
    return str(ts)

def extract_first_message(composer):
    """Extract the first user message from a composer."""
    messages = composer.get('messages', [])
    if not messages:
        return None
    
    # Look for the first user message
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get('role', '')
            content = msg.get('content', '') or msg.get('text', '') or str(msg.get('message', ''))
            
            if role == 'user' and content:
                # Truncate long messages
                if len(content) > 200:
                    return content[:200] + "..."
                return content
    
    # If no user message found, return first message content
    first = messages[0]
    if isinstance(first, dict):
        content = first.get('content', '') or first.get('text', '') or str(first.get('message', ''))
        if content:
            if len(content) > 200:
                return content[:200] + "..."
            return content
    
    return None

def list_all_chats():
    """List all chats with details."""
    if not WORKSPACE_DB.exists():
        print(f"❌ ERROR: Workspace database not found at {WORKSPACE_DB}")
        return
    
    conn = sqlite3.connect(WORKSPACE_DB)
    try:
        cursor = conn.execute("SELECT value FROM ItemTable WHERE key = 'composer.composerData'")
        row = cursor.fetchone()
        if not row:
            print("❌ No composer data found")
            return
        
        data = json.loads(row[0])
        composers = data.get('allComposers', [])
        
        if not composers:
            print("❌ No chats found")
            return
        
        # Sort by creation date (newest first)
        composers.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        
        print("=" * 80)
        print(f"Found {len(composers)} chat(s)")
        print("=" * 80)
        print()
        
        for i, comp in enumerate(composers, 1):
            comp_id = comp.get('composerId', 'unknown')
            title = comp.get('title') or comp.get('name') or 'Untitled'
            created = format_timestamp(comp.get('createdAt', 0))
            updated = format_timestamp(comp.get('lastUpdatedAt', comp.get('createdAt', 0)))
            first_msg = extract_first_message(comp)
            
            print(f"{i}. {title}")
            print(f"   ID: {comp_id}")
            print(f"   Created: {created}")
            if updated != created:
                print(f"   Updated: {updated}")
            
            if first_msg:
                # Clean up the message for display
                first_msg_clean = first_msg.replace('\n', ' ').strip()
                print(f"   First message: {first_msg_clean}")
            
            # Additional info
            files_changed = comp.get('filesChangedCount', 0)
            if files_changed > 0:
                print(f"   Files changed: {files_changed}")
            
            print()
        
        print("=" * 80)
        print("How to find these chats in Cursor:")
        print("=" * 80)
        print()
        print("1. Open Cursor")
        print("2. Use Cmd+P (Quick Open) or Cmd+Shift+F (Search)")
        print("3. Search for text from the 'First message' field above")
        print("4. Or search for the chat title")
        print()
        print("Alternatively, you can try:")
        print("- Opening the Composer (Cmd+I) and checking the history dropdown")
        print("- Looking in the chat panel sidebar")
        print()
        print("If chats still don't appear, they may need to be recreated or")
        print("the panel entries may need to be manually added to global storage.")
        print()
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def export_to_markdown(output_file=None):
    """Export chat list to a markdown file for easy reference."""
    if output_file is None:
        output_file = Path.home() / "cursor-chats-reference.md"
    
    if not WORKSPACE_DB.exists():
        print(f"❌ ERROR: Workspace database not found at {WORKSPACE_DB}")
        return
    
    conn = sqlite3.connect(WORKSPACE_DB)
    try:
        cursor = conn.execute("SELECT value FROM ItemTable WHERE key = 'composer.composerData'")
        row = cursor.fetchone()
        if not row:
            print("❌ No composer data found")
            return
        
        data = json.loads(row[0])
        composers = data.get('allComposers', [])
        
        if not composers:
            print("❌ No chats found")
            return
        
        # Sort by creation date (newest first)
        composers.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        
        with open(output_file, 'w') as f:
            f.write("# Cursor Chat History Reference\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total chats: {len(composers)}\n\n")
            f.write("---\n\n")
            
            for i, comp in enumerate(composers, 1):
                comp_id = comp.get('composerId', 'unknown')
                title = comp.get('title') or comp.get('name') or 'Untitled'
                created = format_timestamp(comp.get('createdAt', 0))
                updated = format_timestamp(comp.get('lastUpdatedAt', comp.get('createdAt', 0)))
                first_msg = extract_first_message(comp)
                
                f.write(f"## {i}. {title}\n\n")
                f.write(f"- **ID**: `{comp_id}`\n")
                f.write(f"- **Created**: {created}\n")
                if updated != created:
                    f.write(f"- **Updated**: {updated}\n")
                
                if first_msg:
                    f.write(f"- **First Message**: {first_msg}\n")
                
                files_changed = comp.get('filesChangedCount', 0)
                if files_changed > 0:
                    f.write(f"- **Files Changed**: {files_changed}\n")
                
                f.write("\n---\n\n")
        
        print(f"✓ Exported chat list to: {output_file}")
        print(f"  You can open this file to search for chat content")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    
    if "--export" in sys.argv or "-e" in sys.argv:
        export_to_markdown()
    else:
        list_all_chats()
        print()
        print("💡 Tip: Run with --export to create a markdown reference file:")
        print("   python3 scripts/list-cursor-chats.py --export")


