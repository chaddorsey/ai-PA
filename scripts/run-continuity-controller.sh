#!/bin/bash
# launchd wrapper for the Continuity Controller (plan docs/plans/2026-08-15-006, Unit C3).
# One wrapper, two roles: `run-continuity-controller.sh worker` / `… anchor` — the two
# separately-supervised halves of the controller's dual subscription.
#
# NOT deployed live by this change — clone validation runs it with CONTINUITY_WS_URL
# pointing at a clone server; the production cutover (Unit C10b) loads the plists against
# :4577 only after the incumbent writers are quiesced.
set -euo pipefail

# launchd hands us a minimal env; pin locale + PATH (never rely on inheritance).
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="${HOME:-/Users/dorseyhomeserver}"

ROLE="${1:-worker}"

# Wiring (defaults match src/config.ts; override in the LOCAL plist copy only — the
# single-writer-safety idiom from run-letta-app-server.sh).
export CONTINUITY_WS_URL="${CONTINUITY_WS_URL:-ws://127.0.0.1:4577/ws}"
# CONTINUITY_STATE_DIR intentionally unset here (defaults to
# ~/Library/Application Support/continuity-controller). Only a clone-validation launcher
# sets it — in its own env — so a leaked value can never repoint the production authority.

cd /Volumes/main-drive/ai-PA/clients/continuity-controller
exec /opt/homebrew/bin/npx tsx src/main.ts "$ROLE"
