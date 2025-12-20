#!/usr/bin/env python3
"""
Export Cursor Chat Content

This script exports all chat conversations to individual markdown files
so you can reference them even if they don't show in Cursor's UI.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
import re

# Paths
HOME = Path.home()
WORKSPACE_STORAGE_DIR = HOME / "Library/Application Support/Cursor/User/workspaceStorage"
WORKSPACE_ID = "183af07563ac8178962e625e5f6f3d4a"
WORKSPACE_DB = WORKSPACE_STORAGE_DIR / WORKSPACE_ID / "state.vscdb"
EXPORT_DIR = Path.home() / "cursor-chats-export"

def sanitize_filename(name):
    """Create a safe filename from a chat title."""
    # Remove or replace invalid filename characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name or "Untitled"

def format_timestamp(ts):
    """Convert timestamp to readable date."""
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        pass
    return str(ts)

def format_message(msg):
    """Format a message for display."""
    if not isinstance(msg, dict):
        return str(msg)
    
    role = msg.get('role', 'unknown')
    content = msg.get('content', '') or msg.get('text', '') or str(msg.get('message', ''))
    
    # Format code blocks if present
    if '```' in content:
        # Already formatted
        pass
    elif content.startswith('```') or '\n```' in content:
        # Code block
        pass
    else:
        # Regular text
        pass
    
    return {
        'role': role,
        'content': content
    }

def export_chat(composer, export_dir):
    """Export a single chat to a markdown file."""
    comp_id = composer.get('composerId', 'unknown')
    title = composer.get('title') or composer.get('name') or 'Untitled'
    created = format_timestamp(composer.get('createdAt', 0))
    updated = format_timestamp(composer.get('lastUpdatedAt', composer.get('createdAt', 0)))
    
    # Create safe filename
    safe_title = sanitize_filename(title)
    filename = f"{safe_title} ({comp_id[:8]}).md"
    filepath = export_dir / filename
    
    messages = composer.get('messages', [])
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n")
        f.write(f"**Composer ID**: `{comp_id}`\n\n")
        f.write(f"**Created**: {created}\n")
        if updated != created:
            f.write(f"**Updated**: {updated}\n")
        
        files_changed = composer.get('filesChangedCount', 0)
        if files_changed > 0:
            f.write(f"**Files Changed**: {files_changed}\n")
        
        f.write("\n---\n\n")
        
        if not messages:
            f.write("*No messages in this chat.*\n")
        else:
            f.write("## Conversation\n\n")
            
            for i, msg in enumerate(messages, 1):
                formatted = format_message(msg)
                if isinstance(formatted, dict):
                    role = formatted['role']
                    content = formatted['content']
                    
                    f.write(f"### Message {i}: {role.title()}\n\n")
                    f.write(f"{content}\n\n")
                    f.write("---\n\n")
                else:
                    f.write(f"### Message {i}\n\n")
                    f.write(f"{formatted}\n\n")
                    f.write("---\n\n")
    
    return filepath

def export_all_chats():
    """Export all chats to markdown files."""
    if not WORKSPACE_DB.exists():
        print(f"❌ ERROR: Workspace database not found at {WORKSPACE_DB}")
        return
    
    # Create export directory
    EXPORT_DIR.mkdir(exist_ok=True)
    
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
        
        print(f"Exporting {len(composers)} chat(s) to {EXPORT_DIR}...\n")
        
        exported = []
        for comp in composers:
            try:
                filepath = export_chat(comp, EXPORT_DIR)
                title = comp.get('title') or comp.get('name') or 'Untitled'
                exported.append((title, filepath))
                print(f"✓ {title}")
            except Exception as e:
                title = comp.get('title') or comp.get('name') or 'Untitled'
                print(f"❌ Error exporting '{title}': {e}")
        
        print(f"\n{'='*80}")
        print(f"✓ Exported {len(exported)} chat(s) to:")
        print(f"  {EXPORT_DIR}")
        print(f"\nYou can now:")
        print(f"  1. Open this directory: open {EXPORT_DIR}")
        print(f"  2. Search the files for content you remember")
        print(f"  3. Reference the conversations even if they don't show in Cursor")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    export_all_chats()


