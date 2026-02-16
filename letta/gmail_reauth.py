#!/usr/bin/env python3
"""Re-authorize Gmail OAuth credentials.

When Gmail tokens expire or get revoked, run this script to open a browser,
complete the OAuth flow, and save fresh tokens to ~/.gmail-mcp/credentials.json.

The tokens are saved in Node.js format (access_token, refresh_token) which is
what the Letta gmail_tools.py functions expect. The credential directory is
bind-mounted into the Letta container at /root/.gmail-mcp/, so new tokens
take effect immediately — no container restart needed.

Usage:
    python letta/gmail_reauth.py

Requirements:
    - ~/.gmail-mcp/gcp-oauth.keys.json (OAuth client config from GCP console)
    - Port 3000 available (used for OAuth callback)
    - Browser access to accounts.google.com
"""

import json
import os
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen

CREDS_DIR = os.path.expanduser("~/.gmail-mcp")
CLIENT_CONFIG_PATH = os.path.join(CREDS_DIR, "gcp-oauth.keys.json")
TOKEN_PATH = os.path.join(CREDS_DIR, "credentials.json")

REDIRECT_URI = "http://localhost:3000/oauth2callback"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]


def load_client_config():
    """Load OAuth client config from gcp-oauth.keys.json."""
    with open(CLIENT_CONFIG_PATH) as f:
        keys = json.load(f)
    config = keys.get("web") or keys.get("installed")
    if not config:
        print("Error: gcp-oauth.keys.json must have a 'web' or 'installed' key")
        sys.exit(1)
    return config


def exchange_code(code, client_config):
    """Exchange authorization code for tokens."""
    data = urlencode({
        "code": code,
        "client_id": client_config["client_id"],
        "client_secret": client_config["client_secret"],
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = Request(client_config["token_uri"], data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    if not os.path.exists(CLIENT_CONFIG_PATH):
        print(f"Error: {CLIENT_CONFIG_PATH} not found")
        print("Download OAuth client credentials from GCP console first.")
        sys.exit(1)

    client_config = load_client_config()

    # Build authorization URL
    auth_params = urlencode({
        "client_id": client_config["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"{client_config['auth_uri']}?{auth_params}"

    # Capture the authorization code via a local HTTP server
    captured_code = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if "code" in params:
                captured_code["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Authorization successful!</h2><p>You can close this tab.</p>")
            elif "error" in params:
                captured_code["error"] = params["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<h2>Error: {params['error'][0]}</h2>".encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress request logging

    server = HTTPServer(("localhost", 3000), CallbackHandler)

    print("Opening browser for Google authorization...")
    print(f"\nIf the browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization callback on http://localhost:3000 ...")
    server.handle_request()  # Handle exactly one request
    server.server_close()

    if "error" in captured_code:
        print(f"\nAuthorization failed: {captured_code['error']}")
        sys.exit(1)

    if "code" not in captured_code:
        print("\nNo authorization code received.")
        sys.exit(1)

    # Exchange code for tokens
    print("Exchanging authorization code for tokens...")
    tokens = exchange_code(captured_code["code"], client_config)

    if "error" in tokens:
        print(f"\nToken exchange failed: {tokens['error']}")
        if "error_description" in tokens:
            print(f"  {tokens['error_description']}")
        sys.exit(1)

    # Save tokens
    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "scope": tokens.get("scope", " ".join(SCOPES)),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in", 3600),
    }

    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\nTokens saved to {TOKEN_PATH}")
    print(f"  access_token: {token_data['access_token'][:20]}...")
    print(f"  refresh_token: {'yes' if token_data['refresh_token'] else 'MISSING'}")
    print(f"  expires_in: {token_data['expires_in']}s")
    print("\nGmail tools should work immediately (no restart needed).")


if __name__ == "__main__":
    main()
