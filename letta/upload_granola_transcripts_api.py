#!/usr/bin/env python3
"""
Upload Granola transcripts to Letta filesystem using REST API.

This script uploads all transcript files from the local granola-transcripts
directory to a Letta filesystem folder using direct REST API calls.
"""

import os
import sys
import time
import json
import requests
from pathlib import Path

# Configuration
LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
SOURCE_DIR = Path("/Users/dorseyhomeserver/ai-PA/data-resources/granola-transcripts")
FOLDER_NAME = "meeting_notes_and_transcripts"
FOLDER_ID = "source-f06917e9-2874-4ce4-8697-4dfed6a2d844"  # Existing folder ID

# Progress tracking
uploaded_count = 0
failed_count = 0


def upload_file(folder_id: str, file_path: Path) -> bool:
    """
    Upload a single file to the Letta folder via REST API.
    
    Args:
        folder_id: Target folder ID
        file_path: Path to the file to upload
        
    Returns:
        bool: True if successful, False otherwise
    """
    global uploaded_count, failed_count
    
    file_name = file_path.name
    
    try:
        print(f"📤 Uploading: {file_name}... ", end="", flush=True)
        
        # Upload file to Letta
        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "text/plain")}
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
            
            if file_id and processing_status:
                # File uploaded, check if processing is complete
                if processing_status == "completed":
                    print(f"✅ Done")
                    uploaded_count += 1
                    return True
                elif processing_status == "failed":
                    error_msg = result.get("error_message", "Unknown error")
                    print(f"❌ Failed: {error_msg}")
                    failed_count += 1
                    return False
                elif processing_status == "parsing":
                    # Wait for parsing to complete
                    max_retries = 30
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
                                print(f"✅ Done")
                                uploaded_count += 1
                                return True
                            elif status == "failed":
                                error_msg = file_data.get("error_message", "Unknown error")
                                print(f"❌ Failed: {error_msg}")
                                failed_count += 1
                                return False
                        
                        retry_count += 1
                    
                    print(f"⏱️  Timeout")
                    failed_count += 1
                    return False
            else:
                # Assume success if we got a good response
                print(f"✅ Done")
                uploaded_count += 1
                return True
        else:
            print(f"❌ HTTP {response.status_code}: {response.text[:100]}")
            failed_count += 1
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        failed_count += 1
        return False


def upload_all_files(folder_id: str, source_dir: Path):
    """
    Upload all files from source directory to Letta folder.
    
    Args:
        folder_id: Target folder ID
        source_dir: Source directory containing files
    """
    global uploaded_count, failed_count
    
    # Get all .txt files
    files = sorted(list(source_dir.glob("*.txt")))
    total_files = len(files)
    
    print(f"\n📊 Found {total_files} files to upload")
    print(f"📁 Source: {source_dir}")
    print(f"🎯 Target folder: {FOLDER_NAME}")
    print(f"🔑 Folder ID: {folder_id}")
    print("\n" + "=" * 70)
    
    start_time = time.time()
    
    for idx, file_path in enumerate(files, 1):
        print(f"[{idx}/{total_files}] ", end="")
        upload_file(folder_id, file_path)
        
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
    if uploaded_count > 0:
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
        sys.exit(1)
    
    # Verify folder exists
    print(f"\n📁 Verifying folder '{FOLDER_NAME}'...")
    try:
        response = requests.get(f"{LETTA_BASE_URL}/v1/folders/", timeout=10)
        if response.status_code == 200:
            folders = response.json()
            folder_found = any(f.get("id") == FOLDER_ID for f in folders)
            if folder_found:
                print(f"✅ Found folder: {FOLDER_NAME}")
            else:
                print(f"❌ Error: Folder not found with ID: {FOLDER_ID}")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Error verifying folder: {e}")
        sys.exit(1)
    
    try:
        # Upload all files
        upload_all_files(FOLDER_ID, SOURCE_DIR)
        
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

