#!/usr/bin/env python3
"""
Upload Granola transcripts to Letta filesystem.

This script uploads all transcript files from the local granola-transcripts
directory to a Letta filesystem folder for agent access.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional
from letta_client import Letta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
LETTA_API_KEY = os.getenv("LETTA_API_KEY")  # May be None for self-hosted
SOURCE_DIR = Path("/Users/dorseyhomeserver/ai-PA/data-resources/granola-transcripts")
FOLDER_NAME = "meeting_notes_and_transcripts"

# Progress tracking
uploaded_count = 0
failed_count = 0
skipped_count = 0


def initialize_letta_client() -> Letta:
    """
    Initialize the Letta client.
    
    Returns:
        Letta: Initialized Letta client instance
    """
    print(f"🔌 Connecting to Letta at {LETTA_BASE_URL}")
    
    # For self-hosted Letta without auth, token can be None
    if LETTA_API_KEY:
        client = Letta(base_url=LETTA_BASE_URL, token=LETTA_API_KEY)
    else:
        client = Letta(base_url=LETTA_BASE_URL)
    
    print("✅ Connected to Letta successfully")
    return client


def get_or_create_folder(client: Letta, folder_name: str):
    """
    Get existing folder or create a new one.
    
    Args:
        client: Letta client instance
        folder_name: Name of the folder to create/retrieve
        
    Returns:
        Folder object
    """
    print(f"\n📁 Looking for folder '{folder_name}'...")
    
    try:
        # Try to retrieve existing folder
        # Handle SDK v1.0 pagination (returns page object with .items)
        folders_result = client.folders.list()
        folders = folders_result.items if hasattr(folders_result, 'items') else folders_result
        for folder in folders:
            if hasattr(folder, 'name') and folder.name == folder_name:
                print(f"✅ Found existing folder: {folder_name}")
                print(f"   ID: {folder.id}")
                if hasattr(folder, 'description') and folder.description:
                    print(f"   Description: {folder.description}")
                return folder
    except Exception as e:
        print(f"⚠️  Error listing folders: {e}")
    
    # Folder doesn't exist, create it
    print(f"📝 Creating new folder '{folder_name}'...")
    try:
        # Get available embedding models
        # Handle SDK v1.0 pagination (returns page object with .items)
        embedding_configs_result = client.embeddingModels.list()
        embedding_configs = embedding_configs_result.items if hasattr(embedding_configs_result, 'items') else embedding_configs_result
        if not embedding_configs:
            raise Exception("No embedding models available")
        
        embedding_config = embedding_configs[0]
        print(f"📊 Using embedding model: {embedding_config.embedding_model if hasattr(embedding_config, 'embedding_model') else 'default'}")
        
        folder = client.folders.create(
            name=folder_name,
            embeddingConfig=embedding_config
        )
        print(f"✅ Created folder: {folder_name} (ID: {folder.id})")
        return folder
    except Exception as e:
        print(f"❌ Error creating folder: {e}")
        raise


def upload_file(client: Letta, folder_id: str, file_path: Path) -> bool:
    """
    Upload a single file to the Letta folder.
    
    Args:
        client: Letta client instance
        folder_id: Target folder ID
        file_path: Path to the file to upload
        
    Returns:
        bool: True if successful, False otherwise
    """
    global uploaded_count, failed_count
    
    # Use the filename as the name in Letta
    file_name = file_path.name
    
    try:
        print(f"📤 Uploading: {file_name}... ", end="", flush=True)
        
        with open(file_path, "rb") as f:
            upload_job = client.folders.files.upload(
                file=f,
                folder_id=folder_id,
                name=file_name,
                duplicate_handling="replace"  # Replace if file already exists
            )
        
        # Wait for upload to complete
        max_retries = 60  # Wait up to 60 seconds
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                job = client.jobs.retrieve(upload_job.id)
                
                if job.status == "completed":
                    print(f"✅ Done")
                    uploaded_count += 1
                    return True
                elif job.status == "failed":
                    error_msg = job.metadata if hasattr(job, 'metadata') else "Unknown error"
                    print(f"❌ Failed: {error_msg}")
                    failed_count += 1
                    return False
                
                # Still processing
                retry_count += 1
                time.sleep(1)
                
            except Exception as e:
                print(f"⚠️  Error checking job status: {e}")
                time.sleep(1)
                retry_count += 1
        
        # Timeout
        print(f"⏱️  Timeout waiting for upload")
        failed_count += 1
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        failed_count += 1
        return False


def upload_all_files(client: Letta, folder_id: str, source_dir: Path):
    """
    Upload all files from source directory to Letta folder.
    
    Args:
        client: Letta client instance
        folder_id: Target folder ID
        source_dir: Source directory containing files
    """
    global uploaded_count, failed_count, skipped_count
    
    # Get all .txt files
    files = list(source_dir.glob("*.txt"))
    total_files = len(files)
    
    print(f"\n📊 Found {total_files} files to upload")
    print(f"📁 Source: {source_dir}")
    print(f"🎯 Target folder ID: {folder_id}")
    print("\n" + "=" * 70)
    
    start_time = time.time()
    
    for idx, file_path in enumerate(files, 1):
        print(f"[{idx}/{total_files}] ", end="")
        upload_file(client, folder_id, file_path)
        
        # Show progress every 10 files
        if idx % 10 == 0:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            remaining = (total_files - idx) / rate if rate > 0 else 0
            print(f"    📈 Progress: {idx}/{total_files} | Rate: {rate:.1f} files/sec | ETA: {remaining:.0f}s")
    
    print("=" * 70)
    
    # Final summary
    elapsed = time.time() - start_time
    print(f"\n📊 Upload Summary:")
    print(f"   ✅ Uploaded: {uploaded_count}")
    print(f"   ❌ Failed: {failed_count}")
    print(f"   ⏱️  Total time: {elapsed:.1f}s")
    print(f"   📈 Average rate: {uploaded_count/elapsed:.1f} files/sec")


def main():
    """Main execution function."""
    print("=" * 70)
    print("📝 Granola Transcripts Upload to Letta Filesystem")
    print("=" * 70)
    
    # Validate source directory
    if not SOURCE_DIR.exists():
        print(f"❌ Error: Source directory does not exist: {SOURCE_DIR}")
        sys.exit(1)
    
    if not SOURCE_DIR.is_dir():
        print(f"❌ Error: Source path is not a directory: {SOURCE_DIR}")
        sys.exit(1)
    
    try:
        # Initialize client
        client = initialize_letta_client()
        
        # Get or create folder
        folder = get_or_create_folder(client, FOLDER_NAME)
        
        # Upload all files
        upload_all_files(client, folder.id, SOURCE_DIR)
        
        print("\n✅ Upload process completed!")
        
        # Exit with error code if any failures
        if failed_count > 0:
            print(f"⚠️  {failed_count} files failed to upload")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Upload interrupted by user")
        print(f"📊 Partial results: {uploaded_count} uploaded, {failed_count} failed")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

