"""Detect NYT bot-block so the fetch loop aborts immediately (safety rule #4)."""
SIGNALS = ("suspect that you're a robot", "pardon our interruption",
           "confirm you are a human", "access denied", "unusual activity")


def is_blocked(html: str, status: int) -> bool:
    if status in (403, 429):
        return True
    low = html.lower()
    return any(s in low for s in SIGNALS)
