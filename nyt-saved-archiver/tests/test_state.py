from nyt_saved_archiver.state import State


def test_state_roundtrip_and_skip(tmp_path):
    s = State(str(tmp_path / "st.json"))
    assert not s.seen("u1")
    s.mark("u1"); s.save()
    s2 = State(str(tmp_path / "st.json"))
    assert s2.seen("u1") and not s2.seen("u2")
