from envelope import Envelope
from outbox import Outbox
from drainer import drain


def test_command_routes_to_push_not_queue(tmp_path):
    ob = Outbox(str(tmp_path))
    ob.append(Envelope(target="email", verb="email.search",
                       args={"prompt": "find X"}))
    pushes, tasks = [], []
    drain(ob, dispatch_push=lambda e: pushes.append(e),
          enqueue_task=lambda e: tasks.append(e))
    assert len(pushes) == 1 and len(tasks) == 0


def test_task_verb_routes_to_queue_not_push(tmp_path):
    ob = Outbox(str(tmp_path))
    ob.append(Envelope(target="tasks", verb="task.extract", args={"x": 1}))
    pushes, tasks = [], []
    drain(ob, dispatch_push=lambda e: pushes.append(e),
          enqueue_task=lambda e: tasks.append(e))
    assert len(tasks) == 1 and len(pushes) == 0


def test_replay_is_idempotent(tmp_path):
    ob = Outbox(str(tmp_path))
    ob.append(Envelope(target="email", verb="email.search",
                       args={"prompt": "x"}))
    pushes = []
    drain(ob, dispatch_push=lambda e: pushes.append(e), enqueue_task=lambda e: None)
    drain(ob, dispatch_push=lambda e: pushes.append(e), enqueue_task=lambda e: None)
    assert len(pushes) == 1  # second drain dispatches nothing


def test_drain_returns_routing_records(tmp_path):
    ob = Outbox(str(tmp_path))
    c = Envelope(target="email", verb="email.search", args={"prompt": "x"})
    t = Envelope(target="tasks", verb="task.extract", args={"x": 1})
    ob.append(c)
    ob.append(t)
    out = drain(ob, dispatch_push=lambda e: None, enqueue_task=lambda e: None)
    routed = {r["id"]: r["routed"] for r in out}
    assert routed[c.id] == "push" and routed[t.id] == "task_queue"
