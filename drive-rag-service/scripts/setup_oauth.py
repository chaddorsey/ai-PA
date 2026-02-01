#!/usr/bin/env python3
"""Generate OAuth token for Google Drive and Docs APIs.

Run this script on the host (not in Docker) to complete the OAuth flow.
The resulting token will be saved and used by the drive-rag-service.

Usage:
    python scripts/setup_oauth.py

Requirements:
    pip install google-auth-oauthlib google-api-python-client
"""

import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes required for Drive and Docs access
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]

# Default paths
DEFAULT_CREDS_DIR = Path.home() / ".gmail-mcp"
CLIENT_SECRETS_FILE = "gcp-oauth.calendar.desktop.json"  # Desktop app type
TOKEN_FILE = "drive-docs-token.json"


def main():
    creds_dir = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH", DEFAULT_CREDS_DIR))
    client_secrets = creds_dir / CLIENT_SECRETS_FILE
    token_path = creds_dir / TOKEN_FILE

    print(f"Credentials directory: {creds_dir}")
    print(f"Client secrets file: {client_secrets}")
    print(f"Token output file: {token_path}")
    print()

    # Check for existing token
    if token_path.exists():
        print(f"Token file already exists at {token_path}")
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds.valid:
                print("Existing token is valid!")
                return
            elif creds.expired and creds.refresh_token:
                print("Token expired, refreshing...")
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                print("Token refreshed and saved!")
                return
        except Exception as e:
            print(f"Could not use existing token: {e}")
            print("Running new OAuth flow...")

    # Check for client secrets
    if not client_secrets.exists():
        print(f"ERROR: Client secrets file not found at {client_secrets}")
        print()
        print("To create one:")
        print("1. Go to Google Cloud Console > APIs & Services > Credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop app type)")
        print("3. Download JSON and save to the path above")
        return

    # Run OAuth flow
    print("Starting OAuth flow...")
    print("A browser window will open for authentication.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print()
    print(f"Token saved to {token_path}")
    print()
    print("You can now restart drive-rag-service to use the new token.")


if __name__ == "__main__":
    main()
