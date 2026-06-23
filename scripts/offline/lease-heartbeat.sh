#!/usr/bin/env bash
# Renews the laptop presence lease in the bus dir. Run on a timer (cadence << TTL,
# e.g. every ~30-45s for a 180s TTL — see acceptance Check 4). launchd-friendly.
set -euo pipefail
BUS="${OFFLINE_BUS_DIR:-$HOME/.letta/offline-bus}"; mkdir -p "$BUS"
TTL="${LEASE_TTL_SECS:-180}"   # tune in Phase 3; heartbeat cadence MUST be << TTL
SPOKE="${SPOKE_ID:-laptop}"
cd "${PA_AI_REPO_ROOT:-$HOME/ai-PA}"   # repo root: lets `letta.offline.lease` import (namespace pkg)
python3 -c "import time; from letta.offline.lease import renew_lease; renew_lease('$BUS/lease.json', '$SPOKE', $TTL, time.time())"
