"""Drainer — SERVER-SIDE router for the offline command bus.

Runs where the fleet lives (the home server). After the sync runner pulls the
laptop's outbox, the drainer routes each pending Envelope by verb:

    verb startswith "task."  ->  pa_web.task_queue  (existing path; DB-level
                                 dedup via ON CONFLICT (source, source_ref))
    everything else          ->  push-receiver :8099/push  (routes the prompt
                                 to the target agent; mirrors send_to_tasks.py)

It is the ONLY new processing component and it adds NO database tables. The two
side-effects are injected so the routing logic is unit-testable without touching
the live push-receiver or Postgres; the module-level defaults wire the real
ones for production use.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Dict, List

from envelope import Envelope
from outbox import Outbox

TASK_PREFIX = "task."
PUSH_RECEIVER_URL = os.environ.get("PA_PUSH_RECEIVER_URL", "http://localhost:8099/push")
PUSH_SOURCE = "mc-offline"


def drain(
    outbox: Outbox,
    dispatch_push: Callable[[Envelope], None],
    enqueue_task: Callable[[Envelope], None],
) -> List[Dict]:
    """Route every pending envelope exactly once. Idempotent: list_pending()
    excludes already-dispatched ids, so replaying drain() is a no-op."""
    results: List[Dict] = []
    for eid in outbox.list_pending():
        env = outbox.get(eid)
        if env.verb.startswith(TASK_PREFIX):
            enqueue_task(env)
            routed = "task_queue"
        else:
            dispatch_push(env)
            routed = "push"
        outbox.mark_dispatched(eid)
        results.append({"id": eid, "routed": routed})
    return results


# ---- production wiring (not exercised by unit tests; imports are local) ----

def default_dispatch_push(env: Envelope) -> None:
    """POST the envelope to the push-receiver, mirroring send_to_tasks.py."""
    import requests

    body = {
        "source": PUSH_SOURCE,
        "source_ref": env.id,
        "prompt": env.args.get("prompt") or f"[{env.verb}] {json.dumps(env.args)}",
        "priority": env.args.get("priority", "normal"),
    }
    if env.target:
        body["agent"] = env.target
    resp = requests.post(PUSH_RECEIVER_URL, json=body, timeout=10)
    resp.raise_for_status()


def default_enqueue_task(env: Envelope) -> None:
    """Insert into the EXISTING pa_web.task_queue (no schema change). The
    UNIQUE(source, source_ref) constraint gives DB-level idempotency."""
    import psycopg
    from psycopg.types.json import Jsonb

    pw = os.environ.get("POSTGRES_PASSWORD", "")
    pg_url = os.environ.get(
        "PA_WEB_POSTGRES_URL",
        f"postgresql://postgres:{pw}@supabase-db:5432/postgres",
    )
    with psycopg.connect(pg_url, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pa_web.task_queue (source, source_ref, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (source, source_ref) DO NOTHING
                """,
                (PUSH_SOURCE, env.id, Jsonb(env.args)),
            )


def drain_default(outbox: Outbox) -> List[Dict]:
    return drain(outbox, default_dispatch_push, default_enqueue_task)
