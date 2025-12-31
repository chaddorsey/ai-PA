#!/usr/bin/env python3
"""
Upload JQL documentation to Letta and attach to pulse-monitoring agent.
"""

import requests
import json
from pathlib import Path
import sys

LETTA_BASE_URL = "http://localhost:8283"
JQL_DOCS_DIR = Path("/Volumes/main-drive/ai-PA/docs/reference/jql-docs")

def find_agent_by_name(name_pattern: str):
    """Find agent by name pattern."""
    response = requests.get(f"{LETTA_BASE_URL}/v1/agents/")
    response.raise_for_status()
    agents = response.json()
    
    for agent in agents:
        if name_pattern.lower() in agent.get('name', '').lower():
            return agent
    
    return None

def create_folder(name: str, description: str = None):
    """Create a folder in Letta."""
    # Check existing folders to see what embedding config they use
    existing_folders = requests.get(f"{LETTA_BASE_URL}/v1/folders/")
    existing_folders.raise_for_status()
    folders = existing_folders.json()
    
    # Get embedding config from existing folder
    embedding_config = None
    embedding_handle = None
    if isinstance(folders, list) and len(folders) > 0:
        existing_folder = folders[0]
        embedding_handle = existing_folder.get('embedding')
        embedding_config = existing_folder.get('embedding_config')
    
    folder_data = {
        "name": name,
        "description": description
    }
    
    # Use embedding handle if available, otherwise use embedding_config
    if embedding_handle:
        folder_data["embedding"] = embedding_handle
    elif embedding_config:
        # Use the same embedding config as existing folders
        folder_data["embedding_config"] = embedding_config
    
    response = requests.post(
        f"{LETTA_BASE_URL}/v1/folders/",
        json=folder_data
    )
    
    # If it still fails, show the error
    if not response.ok:
        error_detail = response.json()
        print(f"Error creating folder: {error_detail}")
        response.raise_for_status()
    
    return response.json()

def upload_file_to_folder(folder_id: str, file_path: Path):
    """Upload a file to a folder."""
    with open(file_path, 'rb') as f:
        files = {'file': (file_path.name, f, 'text/markdown')}
        # Try upload endpoint first
        response = requests.post(
            f"{LETTA_BASE_URL}/v1/folders/{folder_id}/upload",
            files=files
        )
        if response.status_code == 404:
            # Fallback to files endpoint
            response = requests.post(
                f"{LETTA_BASE_URL}/v1/folders/{folder_id}/files",
                files=files
            )
        response.raise_for_status()
        return response.json()

def attach_folder_to_agent(agent_id: str, folder_id: str):
    """Attach a folder to an agent."""
    response = requests.patch(
        f"{LETTA_BASE_URL}/v1/agents/{agent_id}/folders/attach/{folder_id}"
    )
    response.raise_for_status()
    return response.json()

def main():
    """Upload JQL docs and attach to agent."""
    print("Uploading JQL documentation to Letta...")
    print()
    
    # Find pulse-monitoring agent
    print("Finding pulse-monitoring agent...")
    agent = find_agent_by_name("pulse-monitor")
    if not agent:
        print("ERROR: Could not find pulse-monitoring agent")
        sys.exit(1)
    
    agent_id = agent['id']
    agent_name = agent['name']
    print(f"✓ Found agent: {agent_name} (ID: {agent_id})")
    print()
    
    # Create folder
    print("Creating folder 'jql-docs'...")
    folder = create_folder(
        "jql-docs",
        description="Jira Query Language (JQL) documentation for writing JQL queries"
    )
    folder_id = folder['id']
    print(f"✓ Created folder: {folder['name']} (ID: {folder_id})")
    print()
    
    # Upload all markdown files
    md_files = sorted(JQL_DOCS_DIR.glob("*.md"))
    print(f"Uploading {len(md_files)} files...")
    
    uploaded = []
    failed = []
    
    for md_file in md_files:
        try:
            print(f"  Uploading: {md_file.name}...", end=" ")
            result = upload_file_to_folder(folder_id, md_file)
            uploaded.append(md_file.name)
            print("✓")
        except Exception as e:
            failed.append((md_file.name, str(e)))
            print(f"✗ Error: {e}")
    
    print()
    
    # Attach folder to agent
    print(f"Attaching folder to agent '{agent_name}'...")
    try:
        attach_folder_to_agent(agent_id, folder_id)
        print("✓ Folder attached successfully")
    except Exception as e:
        print(f"✗ Error attaching folder: {e}")
        sys.exit(1)
    
    # Summary
    print()
    print("="*60)
    print("Upload Summary:")
    print("="*60)
    print(f"Folder: {folder['name']} (ID: {folder_id})")
    print(f"Agent: {agent_name} (ID: {agent_id})")
    print(f"Files uploaded: {len(uploaded)}/{len(md_files)}")
    
    if uploaded:
        print("\nUploaded files:")
        for name in uploaded:
            print(f"  ✓ {name}")
    
    if failed:
        print("\nFailed files:")
        for name, error in failed:
            print(f"  ✗ {name}: {error}")
    
    print()
    print("✓ JQL documentation is now available to the agent!")

if __name__ == "__main__":
    main()

