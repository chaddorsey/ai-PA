"""Outbox — filesystem-only append/list/mark for the offline command bus.

Pure filesystem so it is trivially testable and so MC never blocks on I/O: MC
appends an Envelope locally and moves on. The connectivity-aware sync runner
(Phase 2) git-commits/pushes this directory; this module does NOT touch git or
the network. Dispatch state lives as marker files under `dispatched/` so it
survives the git sync and stays idempotent across replays.

Layout under base_dir:
    outbox/<id>.json     one Envelope per file
    dispatched/<id>      empty marker; presence == already dispatched
"""
from __future__ import annotations

import os
from typing import List

from envelope import Envelope


class Outbox:
    def __init__(self, base_dir: str) -> None:
        self.base = base_dir
        self.outbox_dir = os.path.join(base_dir, "outbox")
        self.dispatched_dir = os.path.join(base_dir, "dispatched")
        os.makedirs(self.outbox_dir, exist_ok=True)
        os.makedirs(self.dispatched_dir, exist_ok=True)

    def _path(self, eid: str) -> str:
        return os.path.join(self.outbox_dir, eid + ".json")

    def append(self, env: Envelope) -> str:
        """Write the envelope (atomic). Idempotent by id — a re-append of the
        same content is a no-op (same id => same file)."""
        p = self._path(env.id)
        if not os.path.exists(p):
            tmp = p + ".tmp"
            with open(tmp, "w") as f:
                f.write(env.to_json())
            os.replace(tmp, p)  # atomic rename
        return env.id

    def get(self, eid: str) -> Envelope:
        with open(self._path(eid)) as f:
            return Envelope.from_json(f.read())

    def is_dispatched(self, eid: str) -> bool:
        return os.path.exists(os.path.join(self.dispatched_dir, eid))

    def list_pending(self) -> List[str]:
        ids = []
        for fn in sorted(os.listdir(self.outbox_dir)):
            if fn.endswith(".json"):
                eid = fn[:-5]
                if not self.is_dispatched(eid):
                    ids.append(eid)
        return ids

    def mark_dispatched(self, eid: str) -> None:
        marker = os.path.join(self.dispatched_dir, eid)
        if not os.path.exists(marker):
            with open(marker, "w") as f:
                f.write("")
