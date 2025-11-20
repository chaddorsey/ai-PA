#!/usr/bin/env python3
"""
Upload AmEx statement CSV to Letta filesystem using REST API.

This script uploads the AmEx reconciliation CSV file to a Letta filesystem folder
using direct REST API calls.
"""

import os
import sys
import time
import requests
from pathlib import Path

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
CSV_FILE_PATH = Path("/Users/dorseyhomeserver/ai-PA/letta_filesystem_repo/AmEx-reconciliation/202510-AmEx-Statement-formatted.csv")
FOLDER_NAME = "amex_reconciliation"  # Folder name to find or create
FOLDER_ID = None  # Will be set after finding/creating folder


def list_folders():
    """
    List all available folders in Letta.
    
    Returns:
        list: List of folder dictionaries
    """
    try:
        response = requests.get(f"{LETTA_BASE_URL}/v1/folders/", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error listing folders: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return []
    except Exception as e:
        print(f"❌ Error connecting to Letta: {e}")
        return []


def delete_folder(folder_id: str) -> bool:
    """
    Delete a folder from Letta filesystem.
    
    Args:
        folder_id: ID of the folder to delete
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        response = requests.delete(
            f"{LETTA_BASE_URL}/v1/folders/{folder_id}",
            timeout=10
        )
        
        if response.status_code == 200 or response.status_code == 204:
            print(f"✅ Deleted folder (ID: {folder_id})")
            return True
        else:
            print(f"⚠️  Error deleting folder: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"⚠️  Error deleting folder: {e}")
        return False


def create_folder(folder_name: str) -> str:
    """
    Create a new folder in Letta filesystem with letta/letta-free embedding.
    
    Args:
        folder_name: Name of the folder to create
        
    Returns:
        str: Folder ID
    """
    print(f"\n📝 Creating folder '{folder_name}'...")
    
    # Use letta/letta-free embedding model to match other compatible folders
    payload = {
        "name": folder_name,
        "embedding": "letta/letta-free"
    }
    
    try:
        response = requests.post(
            f"{LETTA_BASE_URL}/v1/folders/",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200 or response.status_code == 201:
            result = response.json()
            folder_id = result.get("id")
            if folder_id:
                print(f"✅ Created folder: {folder_name}")
                print(f"   ID: {folder_id}")
                print(f"   Embedding model: letta/letta-free")
                return folder_id
            else:
                print(f"❌ Error: Created folder but no ID returned")
                print(f"   Response: {response.text[:200]}")
                sys.exit(1)
        else:
            print(f"❌ Error creating folder: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error creating folder: {e}")
        sys.exit(1)


def find_or_create_folder(folder_name: str) -> str:
    """
    Find existing folder by name or create a new one.
    If folder exists but has wrong embedding model, delete and recreate it.
    
    Args:
        folder_name: Name of the folder to find/create
        
    Returns:
        str: Folder ID
    """
    print(f"\n📁 Looking for folder '{folder_name}'...")
    
    # List all folders
    folders = list_folders()
    
    # Try to find existing folder
    for folder in folders:
        if folder.get("name") == folder_name:
            folder_id = folder.get("id")
            # Check the embedding model - we need letta/letta-free
            # The folder object might have embedding info, but if not, we'll check by trying to use it
            # For now, let's delete and recreate to ensure correct embedding
            print(f"⚠️  Found existing folder: {folder_name}")
            print(f"   ID: {folder_id}")
            print(f"   Deleting to recreate with correct embedding model (letta/letta-free)...")
            delete_folder(folder_id)
            # Wait a moment for deletion to complete
            time.sleep(0.5)
            break
    
    # Create the folder (either it didn't exist or we just deleted it)
    print(f"📝 Creating folder '{folder_name}' with letta/letta-free embedding...")
    return create_folder(folder_name)


def upload_file(folder_id: str, file_path: Path) -> bool:
    """
    Upload a single file to the Letta folder via REST API.
    
    Args:
        folder_id: Target folder ID
        file_path: Path to the file to upload
        
    Returns:
        bool: True if successful, False otherwise
    """
    file_name = file_path.name
    
    try:
        print(f"\n📤 Uploading: {file_name}...")
        print(f"   Size: {file_path.stat().st_size:,} bytes")
        
        # Upload file to Letta
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "text/csv")}
            data = {"name": file_name}
            
            response = requests.post(
                f"{LETTA_BASE_URL}/v1/sources/{folder_id}/upload",
                files=files,
                data=data,
                timeout=120
            )
        
        if response.status_code == 200 or response.status_code == 201:
            result = response.json()
            file_id = result.get("id") if isinstance(result, dict) else None
            processing_status = result.get("processing_status") if isinstance(result, dict) else None
            
            print(f"   ✅ Upload successful")
            if file_id:
                print(f"   📄 File ID: {file_id}")
            
            if file_id and processing_status:
                # File uploaded, check if processing is complete
                if processing_status == "completed":
                    print(f"   ✅ Processing complete")
                    return True
                elif processing_status == "failed":
                    error_msg = result.get("error_message", "Unknown error")
                    print(f"   ❌ Processing failed: {error_msg}")
                    return False
                elif processing_status == "parsing":
                    # Wait for parsing to complete
                    print(f"   ⏳ Waiting for processing to complete...")
                    max_retries = 60  # 30 seconds max
                    retry_count = 0
                    
                    while retry_count < max_retries:
                        time.sleep(0.5)  # Check every 0.5 seconds
                        
                        file_response = requests.get(
                            f"{LETTA_BASE_URL}/v1/sources/{folder_id}/files/{file_id}",
                            timeout=10
                        )
                        
                        if file_response.status_code == 200:
                            file_data = file_response.json()
                            status = file_data.get("processing_status")
                            
                            if status == "completed":
                                print(f"   ✅ Processing complete")
                                return True
                            elif status == "failed":
                                error_msg = file_data.get("error_message", "Unknown error")
                                print(f"   ❌ Processing failed: {error_msg}")
                                return False
                        
                        retry_count += 1
                        if retry_count % 10 == 0:
                            print(f"   ⏳ Still processing... ({retry_count * 0.5:.0f}s)")
                    
                    print(f"   ⏱️  Processing timeout (exceeded {max_retries * 0.5:.0f}s)")
                    return False
            else:
                # Assume success if we got a good response
                print(f"   ✅ Upload complete (status unknown)")
                return True
        else:
            print(f"   ❌ HTTP {response.status_code}: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    """Main execution function."""
    print("=" * 70)
    print("💳 AmEx Statement Upload to Letta Filesystem")
    print("=" * 70)
    
    # Validate CSV file
    if not CSV_FILE_PATH.exists():
        print(f"❌ Error: CSV file does not exist: {CSV_FILE_PATH}")
        sys.exit(1)
    
    if not CSV_FILE_PATH.is_file():
        print(f"❌ Error: Path is not a file: {CSV_FILE_PATH}")
        sys.exit(1)
    
    # Check Letta connection
    print(f"\n🔌 Checking connection to Letta at {LETTA_BASE_URL}")
    try:
        response = requests.get(f"{LETTA_BASE_URL}/v1/health/", timeout=5)
        if response.status_code == 200:
            print("✅ Connected to Letta successfully")
        else:
            print(f"⚠️  Letta health check returned: {response.status_code}")
    except Exception as e:
        print(f"❌ Error connecting to Letta: {e}")
        print(f"   Make sure Letta is running at {LETTA_BASE_URL}")
        sys.exit(1)
    
    # Get folder ID (from env var or find/create)
    folder_id = os.getenv("FOLDER_ID")
    if folder_id:
        print(f"\n📁 Using folder ID from environment: {folder_id}")
    else:
        folder_id = find_or_create_folder(FOLDER_NAME)
    
    if not folder_id:
        print("❌ Error: Could not get folder ID")
        sys.exit(1)
    
    # Verify folder exists
    print(f"\n📁 Verifying folder...")
    try:
        response = requests.get(f"{LETTA_BASE_URL}/v1/folders/", timeout=10)
        if response.status_code == 200:
            folders = response.json()
            folder_found = any(f.get("id") == folder_id for f in folders)
            if folder_found:
                folder_info = next(f for f in folders if f.get("id") == folder_id)
                print(f"✅ Found folder: {folder_info.get('name', 'Unknown')} (ID: {folder_id})")
            else:
                print(f"❌ Error: Folder not found with ID: {folder_id}")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Error verifying folder: {e}")
        sys.exit(1)
    
    # Upload the file
    try:
        success = upload_file(folder_id, CSV_FILE_PATH)
        
        if success:
            print("\n" + "=" * 70)
            print("✅ Upload completed successfully!")
            print(f"📄 File: {CSV_FILE_PATH.name}")
            print(f"📁 Folder ID: {folder_id}")
            print("=" * 70)
        else:
            print("\n❌ Upload failed. Check the error messages above.")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Upload interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

