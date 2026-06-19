from envelope import Envelope


def test_id_excludes_created_at_so_same_content_dedups():
    a = Envelope(target="email", verb="email.search", args={"q": "x"},
                 created_at="2026-01-01T00:00:00Z")
    b = Envelope(target="email", verb="email.search", args={"q": "x"},
                 created_at="2026-02-02T00:00:00Z")
    assert a.id == b.id  # created_at is metadata, not identity


def test_id_changes_with_content():
    a = Envelope(target="email", verb="email.search", args={"q": "x"})
    b = Envelope(target="email", verb="email.search", args={"q": "y"})
    assert a.id != b.id


def test_idempotency_key_distinguishes_otherwise_identical():
    a = Envelope(target="email", verb="email.draft", args={"to": "bob"},
                 idempotency_key="k1")
    b = Envelope(target="email", verb="email.draft", args={"to": "bob"},
                 idempotency_key="k2")
    assert a.id != b.id


def test_id_is_short_hex():
    e = Envelope(target="t", verb="v", args={})
    assert len(e.id) == 16 and all(c in "0123456789abcdef" for c in e.id)


def test_roundtrip_preserves_fields_and_id():
    a = Envelope(target="docs", verb="transcript.parse", args={"mid": "m1"},
                 reply_to="r1", created_at="2026-01-01T00:00:00Z")
    b = Envelope.from_json(a.to_json())
    assert (b.id, b.target, b.verb, b.args, b.reply_to, b.created_at) == \
           (a.id, a.target, a.verb, a.args, a.reply_to, a.created_at)
