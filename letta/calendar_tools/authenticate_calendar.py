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
        print("NOTE: If you encounter a 'duplicate access_type' error in the browser,")
        print("this is likely because your OAuth client is configured as 'Web application'")
        print("instead of 'Desktop app'. You can either:")
        print("1. Create a new 'Desktop app' OAuth client in Google Cloud Console")
        print("2. Or check if the error persists (sometimes it works despite the warning)")
        print()
        
        try:
            # Use InstalledAppFlow for both client types
            # It should work with web clients, though Desktop app clients are preferred
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_KEY_FILE, SCOPES)
            
            # For web clients, we'll use a specific port if available
            import json
            with open(OAUTH_KEY_FILE, 'r') as f:
                client_config = json.load(f)
            
            is_web_client = 'web' in client_config
            port = 0  # Let it pick a random port by default
            
            if is_web_client:
                print("Detected 'Web application' client type.")
                print("Note: Desktop app client type is recommended for better compatibility.")
                print("Attempting authentication (may see duplicate access_type warning in browser)...")
                print()
                
                # Collect ports to try from redirect_uris
                ports_to_try = []
                client_info = client_config['web']
                if 'redirect_uris' in client_info and len(client_info['redirect_uris']) > 0:
                    import re
                    for uri in client_info['redirect_uris']:
                        match = re.search(r':(\d+)', uri)
                        if match:
                            ports_to_try.append(int(match.group(1)))
                
                if ports_to_try:
                    port = ports_to_try[0]
                    print(f"Will try ports from registered redirect URIs: {ports_to_try}")
            else:
                print("Detected 'Desktop app' client type.")
                ports_to_try = [port] if port != 0 else []
            
            # Try authentication - start local server
            creds = None
            last_error = None
            
            # Try each port in the list
            ports_to_attempt = ports_to_try if ports_to_try else [port]
            for attempt_port in ports_to_attempt:
                try:
                    print(f"Attempting to start local server on port {attempt_port}...")
                    creds = flow.run_local_server(port=attempt_port, open_browser=False)
                    print("✓ Authentication successful!")
                    break
                except OSError as port_error:
                    if "Address already in use" in str(port_error) or "address already in use" in str(port_error).lower():
                        print(f"⚠ Port {attempt_port} is already in use, trying next port...")
                        last_error = port_error
                        continue
                    else:
                        raise
                except Exception as e:
                    last_error = e
                    raise
            
            # If all registered ports failed and we haven't gotten credentials yet
            if not creds and is_web_client:
                print()
                print("⚠ All registered redirect URI ports are in use.")
                print("Trying random available port (this may cause redirect_uri_mismatch error)...")
                print()
                print("If authentication fails, you'll need to either:")
                print("1. Stop the service using the registered port(s), or")
                print("2. Add the redirect URI used below to your OAuth client in Google Cloud Console")
                print()
                creds = flow.run_local_server(port=0, open_browser=False)
                print("✓ Authentication successful!")
            except Exception as server_error:
                # If server start fails, try with auto-browser (for desktop clients)
                error_str = str(server_error).lower()
                if not is_web_client and ("browser" not in error_str and "runnable" not in error_str):
                    print("⚠ Local server failed, trying with browser auto-open...")
                    creds = flow.run_local_server(port=port, open_browser=True)
                    print("✓ Authentication successful via browser!")
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
