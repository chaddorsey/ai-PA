#!/bin/bash
# Wrapper for the LM Studio native-models facade (Caddy) under launchd.
# Runs caddy with a CLEAN, explicit environment (env -i) identical to the
# invocation that works from a shell. Launchd's injected environment made
# `caddy run` hang before config load; a pinned env avoids that.
# See docs/followups/2026-08-10-letta-code-byok-context-window-128k-default.md
exec /usr/bin/env -i \
  HOME=/Users/dorseyhomeserver \
  XDG_DATA_HOME="/Users/dorseyhomeserver/Library/Application Support" \
  XDG_CONFIG_HOME="/Users/dorseyhomeserver/Library/Application Support" \
  PATH=/opt/homebrew/bin:/usr/bin:/bin \
  /opt/homebrew/bin/caddy run \
    --config /Users/dorseyhomeserver/.config/lmstudio-facade/Caddyfile \
    --adapter caddyfile
