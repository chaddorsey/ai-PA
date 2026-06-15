#!/usr/bin/env bash
# MANUAL one-time/incremental NYT backfill. NOT a launchd job (account-safety).
# Usage: ./run-nyt-archive.sh <urls-file> [limit]
set -euo pipefail
URLS="${1:?path to NYT urls file required}"
LIMIT="${2:-0}"
cd "$(dirname "$0")"   # so `python -m nyt_saved_archiver` resolves (pkg not pip-installed)
~/.letta/pa-tools-venv/bin/python -m nyt_saved_archiver.fetch \
  --urls "$URLS" \
  --profile "$HOME/.letta/reference-archive/.nyt-profile" \
  --out "$HOME/.letta/reference-archive/raw/nyt-saved" \
  --state "$HOME/.letta/reference-archive/.state/nyt-saved.json" \
  --limit "$LIMIT"
