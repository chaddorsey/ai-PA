"""Presence-lease for a hub-and-spoke spoke (laptop spoke #1).

A spoke renews a heartbeat lease in a bus repo while present. The hub reads
`lease_state` to distinguish a connectivity blip (still present, within TTL)
from a real departure (expired). Pure logic + atomic file write; no I/O policy.
"""
import json
import os


def renew_lease(path: str, spoke_id: str, ttl_secs: int, now: float) -> dict:
    """Write the heartbeat lease atomically and return its contents."""
    data = {"spoke_id": spoke_id, "renewed_at": now, "ttl_secs": ttl_secs}
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)  # atomic on POSIX
    return data


def lease_state(path: str, now: float) -> str:
    """Return 'present' (within TTL), 'expired' (past TTL), or 'absent' (no file)."""
    if not os.path.exists(path):
        return "absent"
    with open(path) as f:
        d = json.load(f)
    return "present" if (now - d["renewed_at"]) < d["ttl_secs"] else "expired"
