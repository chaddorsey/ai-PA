#!/usr/bin/env python3
"""
Attach the meeting_notes_and_transcripts folder to a Letta agent.

This script finds the uploaded transcripts folder and attaches it to the specified agent,
enabling the agent to use file tools (open_file, grep_file, search_file) on the transcripts.
"""

import os
import sys
from letta_client import Letta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_API_KEY = os.getenv("LETTA_API_KEY")
LETTA_AGENT_ID = os.getenv("LETTA_AGENT_ID")
FOLDER_NAME = "meeting_notes_and_transcripts"


def main():
    """Main execution function."""
    print("=" * 70)
    print("📎 Attach Folder to Letta Agent")
    print("=" * 70)
    
    # Check for agent ID
    if not LETTA_AGENT_ID:
        print("❌ Error: LETTA_AGENT_ID environment variable not set")
        print("   Set it with: export LETTA_AGENT_ID=your_agent_id")
        sys.exit(1)
    
    print(f"🤖 Target Agent ID: {LETTA_AGENT_ID}")
    print(f"📁 Folder Name: {FOLDER_NAME}")
    print(f"🔌 Letta URL: {LETTA_BASE_URL}")
    
    try:
        # Initialize client
        print("\n🔌 Connecting to Letta...")
        if LETTA_API_KEY:
            client = Letta(base_url=LETTA_BASE_URL, token=LETTA_API_KEY)
        else:
            client = Letta(base_url=LETTA_BASE_URL)
        print("✅ Connected successfully")
        
        # Find the folder
        print(f"\n📁 Looking for folder '{FOLDER_NAME}'...")
        # Handle SDK v1.0 pagination (returns page object with .items)
        folders_result = client.folders.list()
        folders = folders_result.items if hasattr(folders_result, 'items') else folders_result
        
        folder = None
        for f in folders:
            if hasattr(f, 'name') and f.name == FOLDER_NAME:
                folder = f
                break
        
        if not folder:
            print(f"❌ Error: Folder '{FOLDER_NAME}' not found")
            print("\nAvailable folders:")
            for f in folders:
                if hasattr(f, 'name'):
                    print(f"   - {f.name} (ID: {f.id})")
            sys.exit(1)
        
        print(f"✅ Found folder: {folder.name} (ID: {folder.id})")
        
        # Check if already attached
        print(f"\n🔍 Checking current agent attachments...")
        try:
            agent = client.agents.retrieve(agent_id=LETTA_AGENT_ID)
            print(f"✅ Agent found: {agent.name if hasattr(agent, 'name') else LETTA_AGENT_ID}")
        except Exception as e:
            print(f"❌ Error: Agent not found: {e}")
            sys.exit(1)
        
        # Attach folder to agent
        print(f"\n📎 Attaching folder to agent...")
        try:
            client.agents.folders.attach(agent_id=LETTA_AGENT_ID, folder_id=folder.id)
            print("✅ Folder successfully attached to agent!")
            
            print("\n🎉 Success! Your agent can now access the meeting transcripts.")
            print("\nAvailable file tools for the agent:")
            print("   📂 open_file(file_path) - Read a specific transcript")
            print("   🔍 search_file(query) - Search across all transcripts")
            print("   📝 grep_file(pattern) - Find specific patterns in transcripts")
            
        except Exception as e:
            if "already attached" in str(e).lower():
                print("ℹ️  Folder is already attached to this agent")
                print("✅ No action needed!")
            else:
                print(f"❌ Error attaching folder: {e}")
                sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()



