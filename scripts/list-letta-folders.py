#!/usr/bin/env python3
"""
List all Letta folders with their IDs and embedding configurations.
"""

import os
import sys
import json
import requests

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_API_KEY = os.getenv("LETTA_API_KEY")  # Optional for self-hosted

def get_folders():
    """Get all folders from Letta API."""
    # Try both endpoints
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
            if url == urls[-1]:  # Last URL, show error
                print(f"❌ ERROR fetching folders: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"   Response: {e.response.text}")
            continue
    
    return []

def main():
    print("=" * 70)
    print("📁 Letta Folders")
    print("=" * 70)
    print(f"Letta URL: {LETTA_BASE_URL}")
    print()
    
    folders = get_folders()
    
    if not folders:
        print("No folders found or API error")
        print("\nTrying database query instead...")
        return
    
    print(f"Found {len(folders)} folder(s):\n")
    
    for i, folder in enumerate(folders, 1):
        folder_id = folder.get("id", "unknown")
        folder_name = folder.get("name", "unnamed")
        embedding_config = folder.get("embedding_config", {})
        
        print(f"{i}. {folder_name}")
        print(f"   ID: {folder_id}")
        
        if embedding_config:
            if isinstance(embedding_config, dict):
                model = embedding_config.get("embedding_model", "unknown")
                endpoint = embedding_config.get("embedding_endpoint", "unknown")
                api_key = embedding_config.get("api_key") or embedding_config.get("openai_api_key")
                
                print(f"   Model: {model}")
                print(f"   Endpoint: {endpoint}")
                if api_key:
                    print(f"   ⚠️  Has embedded API key: {api_key[:20]}...{api_key[-10:]}")
                else:
                    print(f"   ✅ Uses environment variable or letta-free")
            else:
                print(f"   Config: {str(embedding_config)[:100]}")
        else:
            print(f"   No embedding config")
        
        print()

if __name__ == "__main__":
    main()

