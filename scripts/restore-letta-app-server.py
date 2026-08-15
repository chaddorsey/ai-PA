"""
STOPGAP supervisor for the sole-owner Letta App Server.

WHY THIS EXISTS, AND WHY IT SHOULD NOT EXIST FOR LONG. On 2026-08-15 the App Server on :4577 was
discovered to be an ORPHAN: a `letta server` process whose parent (an older generation of
letta-push-receiver) no longer supervised it, running a build (0.30.19) that no longer existed on
disk. Nothing would have restarted it. Killing it to pick up 0.30.20 therefore took :4577 down
with no path back, and exposed a second problem: the `npm install -g @letta-ai/letta-code@0.30.20`
of that morning had been interrupted, leaving the package without `letta.js`, `package.json` or
`docs/` and with npm's temp-named bin symlink never renamed to `letta`. There was no `letta`
binary on PATH at all.

Both are repaired: the package was reinstalled (0.30.20) and this script restored the server.

This is NOT the intended deployment. The real artifact is
`letta-push-receiver/launchd/com.ai-pa.letta-app-server.plist` plus
`scripts/run-letta-app-server.sh`, which run the `letta-app-server` console script (a proper
supervisor with a backend lock, health checks and stall detection). Loading that plist is the M1
Unit 8 cutover and is deliberately gated on quiescing the other writers first.

Until then this keeps :4577 up, using the project's own AppServer class so the command line,
environment and backend dir are the ones the codebase intends rather than a hand-rolled guess.
It does NOT take the backend lock, exactly as the orphan it replaces did not.

    nohup ~/.local/pipx/venvs/letta-push-receiver/bin/python \
        scripts/restore-letta-app-server.py > /tmp/restore-app-server.log 2>&1 &
"""

import sys
import time

sys.path.insert(0, "/Volumes/main-drive/ai-PA/letta-push-receiver/src")

from letta_push_receiver.app_server import AppServer  # noqa: E402


def log(msg: str) -> None:
    print(f"[restore] {msg}", flush=True)


server = AppServer(log)
server.ensure()
log(f"started; alive={server.is_alive()} base_url={server.base_url}")

# Minimal supervision: the process this replaces was an orphan with no parent
# watching it, which is why killing it left :4577 down with nothing to notice.
while True:
    time.sleep(20)
    if not server.is_alive():
        log("child died — restarting")
        server.ensure()
