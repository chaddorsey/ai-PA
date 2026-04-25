#!/bin/bash
# Wrapper that invokes the patched letta-code at letta-code-patched/.
# Set LETTA_CODE_BIN=<path-to-this-wrapper> to make subagent spawns use it too.
#
# Resolves the project root via the wrapper's own location, so this works
# regardless of where the repo is checked out or invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PATCHED_LETTA_JS="$REPO_ROOT/letta-code-patched/node_modules/@letta-ai/letta-code/letta.js"

if [ ! -f "$PATCHED_LETTA_JS" ]; then
  echo "[wrapper] ERROR: patched letta.js not found at $PATCHED_LETTA_JS" >&2
  echo "[wrapper] Run: cd $REPO_ROOT/letta-code-patched && ./build.sh" >&2
  exit 1
fi

exec /opt/homebrew/bin/node "$PATCHED_LETTA_JS" "$@"
