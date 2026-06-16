#!/usr/bin/env bash
# Prune staged work-packet materials older than N days. Safe: only touches the
# staged tree, never the rest of letta-shared-files.
set -euo pipefail
STAGE_DIR="${STAGE_BASE_DIR:-/Users/dorseyhomeserver/Dropbox/letta-shared-files/staged}"
DAYS="${STAGE_PRUNE_DAYS:-30}"
[ -d "$STAGE_DIR" ] || { echo "no staged dir"; exit 0; }
find "$STAGE_DIR" -type f -mtime +"$DAYS" -print -delete
# Remove now-empty ref_id / category dirs.
find "$STAGE_DIR" -mindepth 1 -type d -empty -delete
