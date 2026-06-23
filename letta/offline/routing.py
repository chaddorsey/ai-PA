"""Action-routing decision for a hub-and-spoke spoke (Invariant 1: exactly one executor).

At action time, the spoke chooses where an irreversible/external action runs:
  - online AND capable (action reachable via the Letta API :8283 + LETTA_API_KEY) → act directly;
  - otherwise (offline, or not spoke-callable) → draft + queue to the outbox for the hub
    to drain exactly-once.
Mutually exclusive — this is what makes split-brain double-execution structurally impossible.
`capable` is decided per-action from Spike C's spoke-callable list (see spike-findings §C).
"""


def route_action(link: str, capable: bool) -> str:
    """Return 'direct' if (link == 'online' and capable), else 'queue'."""
    return "direct" if (link == "online" and capable) else "queue"
