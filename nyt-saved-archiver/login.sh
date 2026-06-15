#!/usr/bin/env bash
# ONE-TIME (re-run only if the session expires): hand-login to NYT in a dedicated
# browser profile that the fetch loop then REUSES. This is the ONLY place we ever
# authenticate — never programmatic login (safety rule #1).
set -euo pipefail
PROFILE="$HOME/.letta/reference-archive/.nyt-profile"
~/.letta/pa-tools-venv/bin/python - "$PROFILE" <<'PY'
import sys
from playwright.sync_api import sync_playwright
profile = sys.argv[1]
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=False)
    page = ctx.new_page()
    page.goto("https://www.nytimes.com/saved")
    input("Log in fully in the opened window, confirm you can see your Saved page, then press Enter here...")
    ctx.close()
print("login session saved to", profile)
PY
