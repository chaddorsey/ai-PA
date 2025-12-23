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
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.auth.transport.requests import Request

# Configuration - same paths as the tools use
# Prefer CALENDAR_OAUTH_PATH for dedicated calendar OAuth client
# Falls back to GMAIL_OAUTH_PATH for shared client, then default
OAUTH_KEY_FILE = os.getenv(
    "CALENDAR_OAUTH_PATH",
    os.getenv(
        "GMAIL_OAUTH_PATH",
        str(Path.home() / ".gmail-mcp" / "gcp-oauth.calendar.desktop.json")
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
            # Check client type to provide helpful feedback
            import json
            with open(OAUTH_KEY_FILE, 'r') as f:
                client_config = json.load(f)
            
            is_web_client = 'web' in client_config
            is_desktop_client = 'installed' in client_config
            
            if is_web_client:
                print("⚠ WARNING: Detected 'Web application' client type.")
                print("Desktop app clients work better with InstalledAppFlow.")
                print("You may encounter duplicate access_type errors.")
                print("Consider creating a Desktop app OAuth client instead.")
                print("See docs/calendar-oauth-setup.md for instructions.")
                print()
            elif is_desktop_client:
                print("✓ Detected 'Desktop app' client type - optimal for this use case.")
                print()
            else:
                print("⚠ Unknown client type in OAuth key file.")
                print()
            
            # Use InstalledAppFlow (works with both types, but Desktop app is preferred)
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
            
            # For Desktop app clients, use random port (they handle redirect URIs flexibly)
            # For Web clients, try to use a specific port if registered
            port = 0  # Random port (default - works for Desktop app clients)
            
            if is_web_client:
                # Try to use port from redirect_uris if available
                client_info = client_config['web']
                if 'redirect_uris' in client_info and len(client_info['redirect_uris']) > 0:
                    import re
                    first_uri = client_info['redirect_uris'][0]
                    match = re.search(r':(\d+)', first_uri)
                    if match:
                        port = int(match.group(1))
                        print(f"Using port {port} from registered redirect URI")
            
            # Start local server for authentication
            print("Starting local server...")
            try:
                creds = flow.run_local_server(port=port, open_browser=False)
                print("✓ Authentication successful!")
            except OSError as port_error:
                if "Address already in use" in str(port_error) or "address already in use" in str(port_error).lower():
                    if port != 0:
                        print(f"⚠ Port {port} is already in use (likely by Docker/gmail-mcp).")
                        print("Trying random available port...")
                        creds = flow.run_local_server(port=0, open_browser=False)
                        print("✓ Authentication successful!")
                    else:
                        raise
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
