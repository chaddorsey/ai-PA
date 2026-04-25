#!/bin/bash
# Wrapper that invokes the patched letta-code at ~/code/letta-code-memfs/.
# Set LETTA_CODE_BIN=<path-to-this-wrapper> to make subagent spawns use it too.
exec /opt/homebrew/bin/node "$HOME/code/letta-code-memfs/node_modules/@letta-ai/letta-code/letta.js" "$@"
