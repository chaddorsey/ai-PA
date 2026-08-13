#!/bin/bash
# launchd wrapper for the sole-owner Letta App Server supervisor
# (plan docs/plans/2026-08-12-multi-surface-continuity-m1-web-terminal-plan.md,
# Units 2-3). Runs the `letta-app-server` console script (pipx-installed from
# letta-push-receiver), which supervises the ONE `letta server --backend local
# --openai-api` that solely owns ~/.letta/lc-local-backend.
#
# NOT deployed live by this change — the production cutover is plan Unit 8
# (clone-and-validate). This wrapper + the tracked plist are the artifacts;
# loading them against the live backend happens only at cutover, after the
# other writers are quiesced.
set -euo pipefail

# launchd hands us a minimal env; set locale so Python's filesystem-encoding
# init doesn't choke, and a deterministic PATH (do not rely on inheritance).
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PATH="/Users/dorseyhomeserver/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="${HOME:-/Users/dorseyhomeserver}"

# App Server wiring (defaults match config.py; override in the local plist copy).
export PA_APP_SERVER_LISTEN="${PA_APP_SERVER_LISTEN:-ws://127.0.0.1:4577}"
# PA_APP_SERVER_BACKEND_DIR is intentionally UNSET here (defaults to prod).
# Only a clone-validation launcher sets it — and only in its own env — so a
# leaked value can never repoint the warm pool (single-writer safety).

cd /Volumes/main-drive/ai-PA
exec /Users/dorseyhomeserver/.local/bin/letta-app-server
