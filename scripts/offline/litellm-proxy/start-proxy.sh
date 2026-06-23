#!/usr/bin/env bash
# Start the laptop LiteLLM failover proxy (Option C). Mini-me points at http://127.0.0.1:4000.
# Primary = server LiteLLM (tailnet); fallback = local GLM (oMLX). See config.yaml.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${LITELLM_VENV:-$HOME/.letta/litellm-venv}"
PORT="${PROXY_PORT:-4000}"
ENV_FILE="${PA_ENV_FILE:-$HOME/ai-PA/.env}"

# Primary (server LiteLLM over the tailnet) — SERVER_LITELLM_KEY + SERVER_MODEL_HANDLE
# must be provisioned (server secret). Until then the primary errors and the proxy
# serves the local GLM fallback (the offline path), which is exactly the offline behavior.
export SERVER_LITELLM_BASE="${SERVER_LITELLM_BASE:-http://dorseys-mac-mini:4000/v1}"
export SERVER_MODEL_HANDLE="${SERVER_MODEL_HANDLE:-openai/gpt-5.5}"   # TODO: confirm server model alias
export SERVER_LITELLM_KEY="${SERVER_LITELLM_KEY:-$(grep -E '^LITELLM_MASTER_KEY=' "$ENV_FILE" 2>/dev/null | cut -d= -f2-)}"
export SERVER_LITELLM_KEY="${SERVER_LITELLM_KEY:-sk-missing-server-key}"

# Fallback (local GLM via oMLX).
export LOCAL_GLM_BASE="${LOCAL_GLM_BASE:-http://127.0.0.1:8000/v1}"
export LOCAL_GLM_KEY="${LOCAL_GLM_KEY:-sk-local-omlx}"

# The proxy's own key (the letta provider authenticates with this).
export PROXY_MASTER_KEY="${PROXY_MASTER_KEY:-sk-mc-local}"

exec "$VENV/bin/litellm" --config "$HERE/config.yaml" --host 127.0.0.1 --port "$PORT"
