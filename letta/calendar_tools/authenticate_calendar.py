#!/usr/bin/env python3
"""
Calendar OAuth Authentication Script

Run this script on your host machine (not in Docker) to authenticate
with Google Calendar API. The credentials will be saved to the mounted
directory so the Letta container can use them.

Usage:
    python3 authenticate_calendar.py
"""

import os
import sys
from pathlib import Path

# Import required modules
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

# Configuration - same paths as the tools use
OAUTH_KEY_FILE = os.getenv(
    "CALENDAR_OAUTH_PATH",
    os.getenv(
        "GMAIL_OAUTH_PATH",
        str(Path.home() / ".gmail-mcp" / "gcp-oauth.keys.json")
    )
)

TOKEN_PATH = os.getenv(
    "CALENDAR_CREDENTIALS_PATH",
    os.getenv(
        "GMAIL_CREDENTIALS_PATH",
        str(Path.home() / ".gmail-mcp" / "calendar.credentials.json")
    )
)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    """Authenticate with Google Calendar API."""
    
    print("="*60)
    print("Google Calendar OAuth Authentication")
    print("="*60)
    print()
    
    # Check if OAuth key file exists
    if not os.path.exists(OAUTH_KEY_FILE):
        print(f"❌ Error: OAuth key file not found at {OAUTH_KEY_FILE}")
        print()
        print("Please ensure the OAuth key file exists. You can:")
        print(f"1. Set CALENDAR_OAUTH_PATH or GMAIL_OAUTH_PATH environment variable")
        print(f"2. Place the OAuth key file at the default location: {OAUTH_KEY_FILE}")
        return 1
    
    print(f"✓ OAuth key file found: {OAUTH_KEY_FILE}")
    print(f"✓ Credentials will be saved to: {TOKEN_PATH}")
    print()
    
    # Check if credentials already exist
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            print("✓ Existing credentials found")
        except Exception as e:
            print(f"⚠ Could not load existing credentials: {e}")
    
    # Check if credentials are valid
    if creds and creds.valid:
        print("✓ Credentials are already valid!")
        print(f"  Token expires: {creds.expiry}")
        return 0
    
    # Try to refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            print("⚠ Credentials expired, attempting to refresh...")
            creds.refresh(Request())
            print("✓ Credentials refreshed successfully!")
            
            # Save refreshed credentials
            os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
            
            print(f"✓ Saved refreshed credentials to {TOKEN_PATH}")
            return 0
        except Exception as e:
            print(f"⚠ Could not refresh credentials: {e}")
            print("  Will perform new authentication...")
            creds = None
    
    # Need new authentication
    if not creds:
        print("Starting OAuth flow...")
        print()
        
        try:
            # Load client secrets
            import json
            with open(OAUTH_KEY_FILE, 'r') as f:
                client_config = json.load(f)
            
            # Determine client type (web or installed)
            client_info = client_config.get('web') or client_config.get('installed')
            if not client_info:
                raise ValueError("Invalid OAuth key file: missing 'web' or 'installed' section")
            
            # Create Flow with explicit redirect_uri to match client config
            # Use first redirect_uri from config, or default for installed apps
            redirect_uri = None
            if 'redirect_uris' in client_info and len(client_info['redirect_uris']) > 0:
                redirect_uri = client_info['redirect_uris'][0]
            elif 'web' in client_config:
                redirect_uri = 'http://localhost:8080/'  # Default for web apps
            
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            
            # Try local server first (works if browser is available)
            try:
                print("Attempting browser-based authentication...")
                # run_local_server automatically sets access_type='offline' for refresh tokens
                creds = flow.run_local_server(port=0, open_browser=True)
                print("✓ Authentication successful via browser!")
            except Exception as browser_error:
                # Fall back to console flow for headless environments
                error_str = str(browser_error).lower()
                if "browser" in error_str or "runnable" in error_str:
                    print("⚠ Browser not available, using console flow...")
                    print()
                    creds = flow.run_console()
                    print("✓ Authentication successful via console!")
                else:
                    raise
            
            # Save credentials
            os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
            
            print()
            print(f"✓ Credentials saved to {TOKEN_PATH}")
            print()
            print("="*60)
            print("Authentication Complete!")
            print("="*60)
            print()
            print("The calendar tools in Letta can now use these credentials.")
            print("If running in Docker, ensure ~/.gmail-mcp is mounted to /root/.gmail-mcp")
            
            return 0
            
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            import traceback
            traceback.print_exc()
            return 1

if __name__ == "__main__":
    sys.exit(main())
