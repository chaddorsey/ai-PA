#!/usr/bin/env python3
"""
Fix Letta folder embedding_config API keys.

This script finds folders with incorrect OpenAI API keys in their embedding_config
and updates them to use the current OPENAI_API_KEY from environment variables.
"""

import os
import sys
import json
import requests
from typing import List, Dict, Optional

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_API_KEY = os.getenv("LETTA_API_KEY")  # Optional for self-hosted
CURRENT_OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not CURRENT_OPENAI_KEY:
    print("❌ ERROR: OPENAI_API_KEY environment variable not set")
    print("   Set it with: export OPENAI_API_KEY=your-key")
    sys.exit(1)

def get_folders() -> List[Dict]:
    """Get all folders from Letta API."""
    # Try /v1/folders first, then /v1/sources if that doesn't work
    urls = [
        f"{LETTA_BASE_URL}/v1/folders",
        f"{LETTA_BASE_URL}/v1/sources"
    ]
    
    headers = {"Content-Type": "application/json"}
    if LETTA_API_KEY:
        headers["Authorization"] = f"Bearer {LETTA_API_KEY}"
    
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            # Handle both list and dict responses
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, dict):
                return [data]
            return data
        except requests.exceptions.RequestException as e:
            continue
    
    print(f"❌ ERROR: Could not fetch folders from Letta API")
    return []

def check_folder_embedding_config(folder: Dict) -> Optional[str]:
    """Check if folder has an API key in embedding_config. Returns the key if found."""
    embedding_config = folder.get("embedding_config", {})
    
    # Check for API key in various possible locations
    api_key = None
    if isinstance(embedding_config, dict):
        api_key = embedding_config.get("api_key") or embedding_config.get("openai_api_key")
    
    return api_key

def update_folder_embedding_config(folder_id: str, new_config: Dict) -> bool:
    """Update a folder's embedding_config via PATCH request."""
    # Try both endpoints
    urls = [
        f"{LETTA_BASE_URL}/v1/folders/{folder_id}",
        f"{LETTA_BASE_URL}/v1/sources/{folder_id}"
    ]
    
    headers = {"Content-Type": "application/json"}
    if LETTA_API_KEY:
        headers["Authorization"] = f"Bearer {LETTA_API_KEY}"
    
    payload = {"embedding_config": new_config}
    
    for url in urls:
        try:
            response = requests.patch(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            continue
    
    print(f"   ❌ Failed to update folder {folder_id}")
    return False

def main():
    print("=" * 70)
    print("🔧 Fix Letta Folder Embedding API Keys")
    print("=" * 70)
    print(f"Letta URL: {LETTA_BASE_URL}")
    print(f"Current OpenAI Key: {CURRENT_OPENAI_KEY[:20]}...{CURRENT_OPENAI_KEY[-10:]}")
    print()
    
    # Get all folders
    print("📁 Fetching folders...")
    folders = get_folders()
    
    if not folders:
        print("   No folders found or API error")
        return
    
    print(f"   Found {len(folders)} folder(s)")
    print()
    
    # Check each folder
    folders_with_keys = []
    for folder in folders:
        folder_id = folder.get("id", "unknown")
        folder_name = folder.get("name", "unnamed")
        api_key = check_folder_embedding_config(folder)
        
        if api_key:
            folders_with_keys.append({
                "id": folder_id,
                "name": folder_name,
                "current_key": api_key,
                "embedding_config": folder.get("embedding_config", {})
            })
            print(f"⚠️  Folder '{folder_name}' ({folder_id[:8]}...)")
            print(f"   Has API key: {api_key[:20]}...{api_key[-10:]}")
    
    if not folders_with_keys:
        print("✅ No folders found with embedded API keys")
        print("   All folders appear to use environment variables or letta-free")
        return
    
    print()
    print(f"Found {len(folders_with_keys)} folder(s) with embedded API keys")
    print()
    
    # Update folders
    print("🔧 Updating folders...")
    for folder_info in folders_with_keys:
        folder_id = folder_info["id"]
        folder_name = folder_info["name"]
        current_config = folder_info["embedding_config"]
        
        # Update the API key in the config
        if isinstance(current_config, dict):
            new_config = current_config.copy()
            # Remove old API key fields
            new_config.pop("api_key", None)
            new_config.pop("openai_api_key", None)
            
            # If using OpenAI directly (not letta-free), add the new key
            if new_config.get("embedding_endpoint_type") == "openai" and \
               new_config.get("embedding_model") != "letta-free":
                new_config["api_key"] = CURRENT_OPENAI_KEY
                print(f"   Updating '{folder_name}' with new API key...")
            else:
                # For letta-free, just remove the key
                print(f"   Removing API key from '{folder_name}' (uses letta-free)...")
            
            if update_folder_embedding_config(folder_id, new_config):
                print(f"   ✅ Updated '{folder_name}'")
            else:
                print(f"   ❌ Failed to update '{folder_name}'")
        else:
            print(f"   ⚠️  Skipping '{folder_name}' - unexpected config format")
    
    print()
    print("✅ Done!")

if __name__ == "__main__":
    main()

