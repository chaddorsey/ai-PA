#!/usr/bin/env bash
# deploy-facade.sh — stage the LM Studio native-models facade onto the HOME disk.
#
# The launchd Caddy job must never touch /Volumes (an external USB drive: a
# launchd-spawned process hangs in open() on /Volumes paths). So the served
# Caddyfile + models.json live under ~/.config/lmstudio-facade, populated here
# from a normal shell (which CAN read /Volumes). Run this after editing the repo
# Caddyfile, litellm/config.yaml, or model-context-windows.json, then reload the
# job:  launchctl kickstart -k gui/$(id -u)/com.ai-pa.lmstudio-facade
# (Regenerating only lmstudio-models.json needs no reload — file_server reads it
# per request.)
set -euo pipefail
REPO="${PA_AI_REPO_ROOT:-/Volumes/main-drive/ai-PA}"
SRC="$REPO/litellm/lmstudio-facade"
RUNTIME="$HOME/.config/lmstudio-facade"

mkdir -p "$RUNTIME"
cp "$SRC/Caddyfile" "$RUNTIME/Caddyfile"
LMSTUDIO_MODELS_OUT="$RUNTIME/lmstudio-models.json" python3 "$SRC/gen-lmstudio-models.py"
echo "deployed Caddyfile + lmstudio-models.json -> $RUNTIME"
