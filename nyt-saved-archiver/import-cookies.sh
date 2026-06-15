#!/usr/bin/env bash
# Plan B: import a cookies.txt exported from your logged-in regular Chrome into the
# fetch profile. Usage: ./import-cookies.sh <path-to-nytimes-cookies.txt>
set -euo pipefail
COOKIES="${1:?path to exported nytimes cookies.txt required}"
PROFILE="$HOME/.letta/reference-archive/.nyt-profile"
cd "$(dirname "$0")"
exec ~/.letta/pa-tools-venv/bin/python import_cookies.py "$PROFILE" "$COOKIES"
