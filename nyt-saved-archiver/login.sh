#!/usr/bin/env bash
# ONE-TIME (re-run only if the session expires): hand-login to NYT in a dedicated
# browser profile that the fetch loop then REUSES. This is the ONLY place we ever
# authenticate — never programmatic login (safety rule #1).
set -euo pipefail
PROFILE="$HOME/.letta/reference-archive/.nyt-profile"
cd "$(dirname "$0")"
# Run login.py as a FILE so stdin stays the terminal (input() needs it).
exec ~/.letta/pa-tools-venv/bin/python login.py "$PROFILE"
