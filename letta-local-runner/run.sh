#!/bin/bash
# Wrapper for launchd. Sets up the env, cd's to the runner dir, then
# execs uvicorn directly from the project's poetry venv.
#
# Why not invoke poetry directly from launchd: the poetry shim is a
# Python 3.9 script; in launchd's minimal env it fails on Python's
# filesystem encoding init, and accessing /Volumes/main-drive triggers
# a PermissionError (no inherited PATH/locale/TCC context). This script
# fixes all three by setting locale, exporting PYTHONPATH, and using
# the venv's uvicorn binary directly.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export PYTHONPATH="${PYTHONPATH:-src}"

# Locate the poetry-managed venv by shell glob. Poetry's own
# `env info -p` is unreliable in non-interactive shells (returns empty
# stdout with our system Python 3.9 install). The glob is robust:
# poetry venvs live in a stable location named after the project +
# a hash + python version.
VENV_DIR=""
for candidate in "$HOME/Library/Caches/pypoetry/virtualenvs/letta-local-runner-"*; do
  if [[ -x "$candidate/bin/uvicorn" ]]; then
    VENV_DIR="$candidate"
    break
  fi
done

if [[ -z "$VENV_DIR" ]]; then
  echo "ERROR: no poetry venv with uvicorn found under" >&2
  echo "  $HOME/Library/Caches/pypoetry/virtualenvs/letta-local-runner-*" >&2
  echo "  Run 'poetry install' in $(pwd) to create one." >&2
  exit 2
fi

exec "$VENV_DIR/bin/uvicorn" \
  letta_local_runner.main:app \
  --host 0.0.0.0 \
  --port 8920 \
  --workers 1
