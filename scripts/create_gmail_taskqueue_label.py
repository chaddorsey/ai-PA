#!/usr/bin/env python3
"""Create the TaskQueue Gmail label (one-time setup).

Creates a 'TaskQueue' label in the authenticated Gmail account and prints
its label ID. This ID is needed for Gmail Watch registration (Phase 2).

Usage:
    python scripts/create_gmail_taskqueue_label.py

Prerequisites:
    - ~/.gmail-mcp/gcp-oauth.keys.json (OAuth client config)
    - ~/.gmail-mcp/credentials.json (access/refresh tokens)
    - pip install google-api-python-client google-auth
"""

import json
import os
import sys

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CREDS_DIR = os.path.expanduser("~/.gmail-mcp")
LABEL_NAME = "TaskQueue"


def main():
    # Auth
    with open(f"{CREDS_DIR}/gcp-oauth.keys.json") as f:
        keys = json.load(f)
        client_config = keys.get("installed") or keys.get("web")

    with open(f"{CREDS_DIR}/credentials.json") as f:
        tokens = json.load(f)

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=client_config["token_uri"],
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=[
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.settings.basic",
        ],
    )

    if not creds.valid:
        creds.refresh(Request())
        tokens["access_token"] = creds.token
        with open(f"{CREDS_DIR}/credentials.json", "w") as f:
            json.dump(tokens, f, indent=2)

    gmail = build("gmail", "v1", credentials=creds)

    # Check if label already exists
    labels = gmail.users().labels().list(userId="me").execute().get("labels", [])
    for lbl in labels:
        if lbl["name"] == LABEL_NAME:
            print(f"TaskQueue label already exists: {lbl['id']}")
            print(f"\nSave this label ID for Gmail Watch registration.")
            return 0

    # Create label
    result = gmail.users().labels().create(
        userId="me",
        body={
            "name": LABEL_NAME,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()

    print(f"Created TaskQueue label: {result['id']}")
    print(f"\nSave this label ID for Gmail Watch registration.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
