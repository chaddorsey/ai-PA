#!/usr/bin/env bash
# setup-laptop-minime.sh - create the laptop spoke #1 "mini-me": a DISTINCT agent ID
# whose memfs is a CLONE of the hub's canonical lineage (Spike A) on a per-spoke branch
# (decision 1: Gitea-URL clone + spoke/laptop off main, NOT travel/laptop).
#
# Self-contained + safe by default: creates the agent, clones canonical, checks out
# spoke/laptop, ensures the .letta/ git-guard ignore, sets message_buffer_autoclear:false.
# It does NOT push or fold to canonical 'main' (that fold is a HUB-coordinated step -
# T8 / acceptance - verified server-side). Pass --push to publish the spoke branch.
set -euo pipefail

HUB_AGENT="${HUB_AGENT_ID:-agent-local-8474bbbd-95fc-42f7-b586-eb0cf94a5a5d}"
STORE="${LETTA_LOCAL_BACKEND_DIR:-$HOME/.letta/lc-local-backend}"
ENV_FILE="${PA_ENV_FILE:-$HOME/ai-PA/.env}"
GITEA_BASE="${GITEA_BASE_URL:-http://127.0.0.1:3030}"
SPOKE_BRANCH="${SPOKE_BRANCH:-spoke/laptop}"
LOCAL_MODEL="${FAILOVER_LOCAL_MODEL:-ollama/GLM-4.5-Air-4bit}"   # offline/initial brain (validated daily driver)
BUS="${OFFLINE_BUS_DIR:-$HOME/.letta/offline-bus}"
PUSH=0; [ "${1:-}" = "--push" ] && PUSH=1

# Guard: don't silently create a second mini-me.
if [ -f "$BUS/minime.json" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "minime.json already exists; set FORCE=1 to make another." >&2
  exit 1
fi

TOKEN="$(grep '^GITEA_MEMFS_TOKEN=' "$ENV_FILE" | cut -d= -f2-)"
host="${GITEA_BASE#http://}"; host="${host#https://}"
GURL="http://${TOKEN}@${host}/agents/${HUB_AGENT}.git"   # token only ever crosses the SSH tunnel

# 1. Create the distinct local mini-me agent (own id + own model; persona shared via canonical memfs).
echo "[1/4] creating distinct mini-me agent..."
OUT=$(letta --backend local agents create --model "$LOCAL_MODEL" --personality blank \
  --name "Mission Control (laptop spoke)" \
  --description "Kinara facet - laptop spoke 1 (local-aware)" \
  --tags "spoke,laptop,kinara-facet,delete-with-care" 2>&1)
NEW=$(printf '%s' "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])") \
  || { echo "agent create failed:"; printf '%s\n' "$OUT" | head -5; exit 1; }
echo "      mini-me id: $NEW"

# 2. Mount canonical lineage as an independent CLONE (Spike A), on spoke/laptop off main.
echo "[2/4] cloning canonical lineage + checking out $SPOKE_BRANCH ..."
MEM="$STORE/memfs/$NEW/memory"
rm -rf "$MEM"
git clone -q "$GURL" "$MEM"
if git -C "$MEM" ls-remote --exit-code --heads origin "$SPOKE_BRANCH" >/dev/null 2>&1; then
  git -C "$MEM" checkout -q "$SPOKE_BRANCH"
else
  git -C "$MEM" checkout -q -B "$SPOKE_BRANCH" origin/main   # per-spoke branch off canonical main
fi

# 2b. Git-guard safeguard: ensure the .letta/ runtime cache is ignored in the memfs
#     (main lacks this; travel/laptop has it - replicate on spoke/laptop).
if ! grep -qxF '.letta/' "$MEM/.gitignore" 2>/dev/null; then
  printf '.letta/\n' >> "$MEM/.gitignore"
  git -C "$MEM" add .gitignore
  git -C "$MEM" -c user.name='laptop-spoke' -c user.email='spoke@local' \
    commit -q -m "spoke/laptop: ignore letta-code runtime cache (.letta/) in memfs"
  echo "      added .letta/ gitignore on $SPOKE_BRANCH"
fi

# 3. Agent settings required for memfs agents (gotcha 3) + confirm model.
echo "[3/4] setting message_buffer_autoclear=false + model..."
AJSON="$STORE/agents/$(printf '%s' "$NEW" | base64).json"
python3 -c "import json;d=json.load(open('$AJSON'));d['message_buffer_autoclear']=False;d['model']='$LOCAL_MODEL';json.dump(d,open('$AJSON','w'),indent=2)"

# 4. Record the mini-me identity for the mod/watcher/heartbeat to consume.
echo "[4/4] recording $BUS/minime.json ..."
mkdir -p "$BUS"
python3 -c "import json;json.dump({'minime_id':'$NEW','hub_agent':'$HUB_AGENT','spoke_branch':'$SPOKE_BRANCH','local_model':'$LOCAL_MODEL','memfs':'$MEM'}, open('$BUS/minime.json','w'), indent=2)"

if [ "$PUSH" = "1" ]; then
  echo "[+] pushing $SPOKE_BRANCH to canonical Gitea (side branch; does NOT touch main)..."
  git -C "$MEM" push -u origin "$SPOKE_BRANCH"
else
  echo "[i] NOT pushed (default). The first spoke/laptop->main fold is HUB-coordinated (T8)."
fi

echo "DONE  LAPTOP_MINIME_ID=$NEW"
echo "      branch=$(git -C "$MEM" branch --show-current)  HEAD=$(git -C "$MEM" rev-parse --short HEAD)  memfs=$MEM"
