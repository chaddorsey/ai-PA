"""Persistent seen-URL set so re-runs never re-fetch (caching requirement)."""
import json
from pathlib import Path


class State:
    def __init__(self, path: str):
        self.path = Path(path)
        self._seen = set(json.loads(self.path.read_text())["seen"]) if self.path.exists() else set()

    def seen(self, url: str) -> bool:
        return url in self._seen

    def mark(self, url: str) -> None:
        self._seen.add(url)

    def save(self) -> None:
        self.path.write_text(json.dumps({"seen": sorted(self._seen)}, indent=2))
