from envelope import Envelope
from outbox import Outbox


def test_append_list_mark(tmp_path):
    ob = Outbox(str(tmp_path))
    e1 = Envelope(target="email", verb="email.search", args={"q": "a"})
    e2 = Envelope(target="docs", verb="transcript.parse", args={"mid": "m"})
    ob.append(e1)
    ob.append(e2)
    assert set(ob.list_pending()) == {e1.id, e2.id}
    ob.mark_dispatched(e1.id)
    assert ob.list_pending() == [e2.id]


def test_append_is_idempotent_by_id(tmp_path):
    ob = Outbox(str(tmp_path))
    e = Envelope(target="email", verb="email.search", args={"q": "a"},
                 created_at="2026-01-01T00:00:00Z")
    same = Envelope(target="email", verb="email.search", args={"q": "a"},
                    created_at="2026-09-09T00:00:00Z")  # same content, later time
    ob.append(e)
    ob.append(same)
    assert ob.list_pending() == [e.id]  # one entry, not two


def test_get_roundtrips(tmp_path):
    ob = Outbox(str(tmp_path))
    e = Envelope(target="docs", verb="transcript.parse", args={"mid": "m1"},
                 reply_to="r1")
    ob.append(e)
    got = ob.get(e.id)
    assert got.id == e.id and got.verb == e.verb and got.reply_to == "r1"
