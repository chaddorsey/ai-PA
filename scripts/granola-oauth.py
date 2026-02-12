#!/usr/bin/env python3
"""
Granola MCP OAuth Token Acquisition

Performs the OAuth 2.0 Authorization Code + PKCE flow against Granola's
MCP auth server to obtain access and refresh tokens.

Usage:
    python3 scripts/granola-oauth.py              # Initial auth (opens browser)
    python3 scripts/granola-oauth.py --refresh     # Refresh existing token
    python3 scripts/granola-oauth.py --status      # Check token status

Tokens are saved to .granola-tokens.json (gitignored).
After obtaining tokens, run: python3 letta/configure_mcp_servers.py
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---
AUTH_SERVER = "https://mcp-auth.granola.ai"
MCP_SERVER = "https://mcp.granola.ai/mcp"
AUTHORIZE_URL = f"{AUTH_SERVER}/oauth2/authorize"
TOKEN_URL = f"{AUTH_SERVER}/oauth2/token"
REGISTER_URL = f"{AUTH_SERVER}/oauth2/register"

SCOPES = "openid email offline_access"
CALLBACK_PORT = 19473  # Arbitrary high port for localhost callback
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# File paths (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent
TOKENS_FILE = PROJECT_ROOT / ".granola-tokens.json"
CLIENT_FILE = PROJECT_ROOT / ".granola-client.json"
ENV_FILE = PROJECT_ROOT / ".env"


def generate_pkce_pair():
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def register_client():
    """Dynamically register an OAuth client with Granola's auth server."""
    import urllib.request

    if CLIENT_FILE.exists():
        with open(CLIENT_FILE) as f:
            client_data = json.load(f)
        print(f"  Using existing client: {client_data['client_id'][:16]}...")
        return client_data

    print("  Registering dynamic OAuth client...")
    registration_data = json.dumps({
        "client_name": "ai-PA Letta Integration",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # Public client
        "scope": SCOPES,
    }).encode("utf-8")

    req = urllib.request.Request(
        REGISTER_URL,
        data=registration_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            client_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  Registration failed: {e.code} {body}")
        sys.exit(1)

    # Save client registration
    with open(CLIENT_FILE, "w") as f:
        json.dump(client_data, f, indent=2)
    os.chmod(CLIENT_FILE, 0o600)

    print(f"  Client registered: {client_data['client_id'][:16]}...")
    return client_data


def authorize(client_id):
    """Run the Authorization Code + PKCE flow. Opens browser, captures callback."""
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    # Set up callback server
    result = {"code": None, "error": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/callback":
                if "error" in query:
                    result["error"] = query["error"][0]
                    desc = query.get("error_description", [""])[0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        f"<h2>Authorization Failed</h2><p>{result['error']}: {desc}</p>"
                        "<p>You can close this tab.</p>".encode()
                    )
                elif "code" in query:
                    returned_state = query.get("state", [""])[0]
                    if returned_state != state:
                        result["error"] = "state_mismatch"
                        self.send_response(400)
                        self.send_header("Content-Type", "text/html")
                        self.end_headers()
                        self.wfile.write(b"<h2>State mismatch</h2>")
                    else:
                        result["code"] = query["code"][0]
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html")
                        self.end_headers()
                        self.wfile.write(
                            b"<h2>Authorization Successful!</h2>"
                            b"<p>You can close this tab and return to the terminal.</p>"
                        )
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h2>Unexpected callback</h2>")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress HTTP server logs

    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    server.timeout = 120  # 2 minute timeout

    print(f"\n  Opening browser for Granola login...")
    print(f"  (If browser doesn't open, visit this URL manually):\n")
    print(f"  {auth_url}\n")
    webbrowser.open(auth_url)

    print("  Waiting for authorization callback...")

    # Handle one request (the callback)
    while result["code"] is None and result["error"] is None:
        server.handle_request()

    server.server_close()

    if result["error"]:
        print(f"\n  Authorization failed: {result['error']}")
        sys.exit(1)

    return result["code"], verifier


def exchange_code(client_id, code, verifier):
    """Exchange authorization code for access + refresh tokens."""
    import urllib.request

    token_data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  Token exchange failed: {e.code} {body}")
        sys.exit(1)


def refresh_token(client_id, refresh_tok):
    """Use refresh token to get a new access token."""
    import urllib.request

    token_data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_tok,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  Token refresh failed: {e.code} {body}")
        return None


def save_tokens(token_response):
    """Save token response to file with metadata."""
    data = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "token_type": token_response.get("token_type", "Bearer"),
        "expires_in": token_response.get("expires_in"),
        "scope": token_response.get("scope", SCOPES),
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }

    # Calculate expiry if expires_in is provided
    if data["expires_in"]:
        expires_at = datetime.now(timezone.utc).timestamp() + data["expires_in"]
        data["expires_at"] = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()

    with open(TOKENS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(TOKENS_FILE, 0o600)

    return data


def load_tokens():
    """Load saved tokens."""
    if not TOKENS_FILE.exists():
        return None
    with open(TOKENS_FILE) as f:
        return json.load(f)


def load_client():
    """Load saved client registration."""
    if not CLIENT_FILE.exists():
        return None
    with open(CLIENT_FILE) as f:
        return json.load(f)


def update_env_file(access_token):
    """Update .env file with the Granola OAuth token."""
    env_key = "GRANOLA_OAUTH_TOKEN"

    if not ENV_FILE.exists():
        print(f"  Warning: {ENV_FILE} not found, skipping .env update")
        return

    lines = ENV_FILE.read_text().splitlines()
    found = False
    new_lines = []

    for line in lines:
        if line.startswith(f"{env_key}="):
            new_lines.append(f"{env_key}={access_token}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        # Add after a blank line at the end
        new_lines.append(f"\n# Granola MCP OAuth token (auto-managed by scripts/granola-oauth.py)")
        new_lines.append(f"{env_key}={access_token}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n")
    print(f"  Updated .env with {env_key}")


def update_letta_mcp_config(access_token):
    """Update Letta's granola-tools MCP server with the new token via API."""
    import urllib.request

    letta_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")

    server_config = {
        "server_name": "granola-tools",
        "type": "streamable_http",
        "server_url": MCP_SERVER,
        "auth_header": "Authorization",
        "auth_token": f"Bearer {access_token}",
        "custom_headers": {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {access_token}",
        },
    }

    req = urllib.request.Request(
        f"{letta_url}/v1/tools/mcp/servers",
        data=json.dumps(server_config).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                print(f"  Updated Letta MCP server: granola-tools")
                return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  Warning: Failed to update Letta MCP ({e.code}): {body}")
        print(f"  You can manually run: python3 letta/configure_mcp_servers.py")
    except Exception as e:
        print(f"  Warning: Could not reach Letta ({e})")
        print(f"  Run configure_mcp_servers.py after Letta is available")

    return False


def cmd_authorize(args):
    """Initial authorization flow."""
    print("=" * 60)
    print("Granola MCP OAuth Setup")
    print("=" * 60)

    # Step 1: Register client (or load existing)
    print("\n1. Client Registration")
    client_data = register_client()
    client_id = client_data["client_id"]

    # Step 2: Authorization Code + PKCE flow
    print("\n2. Authorization")
    code, verifier = authorize(client_id)
    print("  Authorization code received!")

    # Step 3: Exchange code for tokens
    print("\n3. Token Exchange")
    token_response = exchange_code(client_id, code, verifier)

    token_data = save_tokens(token_response)
    print(f"  Access token: {token_data['access_token'][:20]}...")
    if token_data.get("refresh_token"):
        print(f"  Refresh token: {token_data['refresh_token'][:20]}...")
    if token_data.get("expires_at"):
        print(f"  Expires at: {token_data['expires_at']}")

    # Step 4: Update .env
    print("\n4. Environment Update")
    update_env_file(token_data["access_token"])

    # Step 5: Update Letta MCP config (if Letta is running)
    print("\n5. Letta MCP Config")
    update_letta_mcp_config(token_data["access_token"])

    print(f"\n{'=' * 60}")
    print("Setup complete!")
    print(f"{'=' * 60}")
    print(f"\nTokens saved to: {TOKENS_FILE}")
    print(f"Client saved to: {CLIENT_FILE}")


def cmd_refresh(args):
    """Refresh the access token using the stored refresh token."""
    print("Granola MCP Token Refresh")
    print("-" * 40)

    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run without --refresh first.")
        sys.exit(1)

    if not tokens.get("refresh_token"):
        print("No refresh token available. Re-authorize with: python3 scripts/granola-oauth.py")
        sys.exit(1)

    client_data = load_client()
    if not client_data:
        print("No client registration found. Re-authorize with: python3 scripts/granola-oauth.py")
        sys.exit(1)

    print(f"  Refreshing token...")
    token_response = refresh_token(client_data["client_id"], tokens["refresh_token"])

    if not token_response:
        print("  Refresh failed. Re-authorize with: python3 scripts/granola-oauth.py")
        sys.exit(1)

    # Preserve refresh token if not returned in response
    if "refresh_token" not in token_response and tokens.get("refresh_token"):
        token_response["refresh_token"] = tokens["refresh_token"]

    token_data = save_tokens(token_response)
    print(f"  New access token: {token_data['access_token'][:20]}...")
    if token_data.get("expires_at"):
        print(f"  Expires at: {token_data['expires_at']}")

    update_env_file(token_data["access_token"])
    update_letta_mcp_config(token_data["access_token"])

    print("  Token refresh complete!")


def cmd_status(args):
    """Check current token status."""
    print("Granola MCP Token Status")
    print("-" * 40)

    client_data = load_client()
    if client_data:
        print(f"  Client ID: {client_data['client_id'][:16]}...")
    else:
        print("  Client: Not registered")

    tokens = load_tokens()
    if not tokens:
        print("  Tokens: Not found")
        print("\n  Run: python3 scripts/granola-oauth.py")
        return

    print(f"  Access token: {tokens['access_token'][:20]}...")
    print(f"  Refresh token: {'Yes' if tokens.get('refresh_token') else 'No'}")
    print(f"  Obtained at: {tokens.get('obtained_at', 'unknown')}")

    if tokens.get("expires_at"):
        expires = datetime.fromisoformat(tokens["expires_at"])
        now = datetime.now(timezone.utc)
        remaining = expires - now
        if remaining.total_seconds() > 0:
            hours = remaining.total_seconds() / 3600
            print(f"  Expires at: {tokens['expires_at']} ({hours:.1f}h remaining)")
        else:
            print(f"  Expires at: {tokens['expires_at']} (EXPIRED)")
            print("  Run: python3 scripts/granola-oauth.py --refresh")
    elif tokens.get("expires_in"):
        print(f"  Expires in: {tokens['expires_in']}s from obtain time")


def main():
    parser = argparse.ArgumentParser(description="Granola MCP OAuth token management")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing token")
    parser.add_argument("--status", action="store_true", help="Check token status")
    args = parser.parse_args()

    if args.status:
        cmd_status(args)
    elif args.refresh:
        cmd_refresh(args)
    else:
        cmd_authorize(args)


if __name__ == "__main__":
    main()
