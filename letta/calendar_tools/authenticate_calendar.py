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
import http.server
import socketserver
import webbrowser
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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
            
            # Use Flow directly to have full control over authorization URL parameters
            # This avoids duplicate access_type issues with InstalledAppFlow
            client_info = client_config.get('installed') or client_config.get('web')
            if not client_info:
                raise ValueError("Invalid OAuth key file: missing 'installed' or 'web' section")
            
            # Use localhost redirect URI for Desktop app clients
            port = 0  # Will use random available port
            redirect_uri = "http://localhost"
            
            # Create Flow with explicit redirect_uri
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            
            # Generate authorization URL - only specify access_type once
            # Don't pass it if Flow might add it automatically
            auth_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # Parse and inspect the authorization URL
            parsed = urlparse(auth_url)
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            
            # Debug: Print what scopes are actually being requested
            if 'scope' in query_params:
                scopes_list = query_params['scope']
                if isinstance(scopes_list, list) and len(scopes_list) > 0:
                    scopes = scopes_list[0].split(' ')
                    print(f"DEBUG: Scopes in authorization URL: {scopes}")
                    # Filter out any unexpected scopes (only keep calendar scope)
                    filtered_scopes = [s for s in scopes if 'calendar' in s]
                    if len(filtered_scopes) != len(scopes):
                        print(f"⚠ WARNING: Found unexpected scopes: {[s for s in scopes if 'calendar' not in s]}")
                        print(f"   Filtering to only calendar scope: {filtered_scopes}")
                        query_params['scope'] = [' '.join(filtered_scopes)]
            
            # Check for and remove duplicate access_type parameter
            if 'access_type' in query_params:
                if len(query_params['access_type']) > 1:
                    print("⚠ Detected duplicate access_type parameter, fixing...")
                # Ensure only one access_type with value 'offline'
                query_params['access_type'] = ['offline']
            
            # Reconstruct URL with cleaned parameters
            clean_query = urlencode([(k, v[0] if isinstance(v, list) and len(v) > 0 else v) 
                                    for k, v in query_params.items()], doseq=False)
            clean_auth_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                clean_query,
                parsed.fragment
            ))
            
            # Start local server for OAuth callback
            print("Starting local server...")
            
            class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed_path = urlparse(self.path)
                    query_params = parse_qs(parsed_path.query)
                    
                    if 'code' in query_params:
                        auth_code = query_params['code'][0]
                        try:
                            # Update redirect_uri to match what the server is using
                            flow.redirect_uri = f"http://localhost:{self.server.server_address[1]}"
                            flow.fetch_token(code=auth_code)
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html')
                            self.end_headers()
                            self.wfile.write(b'<html><body><h1>Authentication successful!</h1><p>You can close this window.</p></body></html>')
                            self.server.should_shutdown = True
                            self.server.auth_success = True
                        except Exception as e:
                            self.send_response(400)
                            self.send_header('Content-type', 'text/plain')
                            self.end_headers()
                            self.wfile.write(f'Error: {str(e)}'.encode())
                            self.server.should_shutdown = True
                            self.server.auth_error = str(e)
                    else:
                        error_msg = query_params.get('error', ['Unknown error'])[0]
                        self.send_response(400)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(f'Authorization failed: {error_msg}'.encode())
                        self.server.should_shutdown = True
                        self.server.auth_error = error_msg
                
                def log_message(self, format, *args):
                    pass  # Suppress default logging
            
            # Start server
            with socketserver.TCPServer(("", port), OAuthCallbackHandler) as httpd:
                actual_port = httpd.server_address[1]
                actual_redirect_uri = f"http://localhost:{actual_port}"
                
                # Update the authorization URL with the actual redirect URI
                parsed_clean = urlparse(clean_auth_url)
                query_params_clean = parse_qs(parsed_clean.query, keep_blank_values=True)
                query_params_clean['redirect_uri'] = [actual_redirect_uri]
                final_query = urlencode([(k, v[0] if isinstance(v, list) and len(v) > 0 else v) 
                                        for k, v in query_params_clean.items()], doseq=False)
                final_auth_url = urlunparse((
                    parsed_clean.scheme,
                    parsed_clean.netloc,
                    parsed_clean.path,
                    parsed_clean.params,
                    final_query,
                    parsed_clean.fragment
                ))
                
                print(f"\nPlease visit this URL to authorize the application:\n{final_auth_url}\n")
                print(f"(Listening on {actual_redirect_uri} for callback)\n")
                
                try:
                    webbrowser.open(final_auth_url)
                    print("(Browser should have opened automatically)")
                except Exception:
                    print("(Could not open browser automatically - please copy/paste the URL above)")
                
                print("\nWaiting for authorization...")
                
                httpd.timeout = 600
                httpd.should_shutdown = False
                httpd.auth_success = False
                
                while not httpd.should_shutdown:
                    httpd.handle_request()
                
                if hasattr(httpd, 'auth_error'):
                    raise Exception(f"Authentication failed: {httpd.auth_error}")
                
                creds = flow.credentials
                print("✓ Authentication successful!")
            
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
