#!/usr/bin/env python3
"""
Re-authorize Google credentials to include Drive Activity API scope.

This will open a browser window for you to authorize access.
The new credentials will be saved to a new file first, then you can
replace the old credentials once confirmed working.
"""

import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Paths
OAUTH_KEY_FILE = os.getenv(
    "GMAIL_OAUTH_PATH",
    str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")  # Desktop client
)
NEW_TOKEN_PATH = str(Path.home() / ".gmail-mcp" / "admin-reports.credentials.NEW.json")

# All required scopes including Drive Activity API
SCOPES = [
    "https://www.googleapis.com/auth/admin.reports.audit.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.activity.readonly",
]

def main():
    print("=" * 60)
    print("Drive Activity API Re-Authorization")
    print("=" * 60)
    print()
    print(f"OAuth key file: {OAUTH_KEY_FILE}")
    print(f"New token will be saved to: {NEW_TOKEN_PATH}")
    print()
    print("Scopes to authorize:")
    for scope in SCOPES:
        print(f"  - {scope.split('/')[-1]}")
    print()
    
    if not os.path.exists(OAUTH_KEY_FILE):
        print(f"ERROR: OAuth key file not found at {OAUTH_KEY_FILE}")
        return 1
    
    print("Starting OAuth flow... A browser window should open.")
    print()
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
        # Desktop client allows auto port selection
        creds = flow.run_local_server(port=0)
        
        # Save new credentials
        with open(NEW_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
        
        print()
        print("✓ New credentials saved!")
        print()
        
        # Test the Drive Activity API
        print("Testing Drive Activity API...")
        activity_service = build("driveactivity", "v2", credentials=creds)
        
        # Simple test query
        response = activity_service.activity().query(body={
            "pageSize": 1
        }).execute()
        
        activities = response.get("activities", [])
        print(f"✓ Drive Activity API works! Found {len(activities)} activity.")
        print()
        
        # Instructions
        print("=" * 60)
        print("SUCCESS! New credentials are working.")
        print("=" * 60)
        print()
        print("To use the new credentials, run:")
        print()
        print(f"  mv ~/.gmail-mcp/admin-reports.credentials.json ~/.gmail-mcp/admin-reports.credentials.OLD.json")
        print(f"  mv ~/.gmail-mcp/admin-reports.credentials.NEW.json ~/.gmail-mcp/admin-reports.credentials.json")
        print()
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
