import json

from bookmark_archiver import backfill, state


def test_state_meta_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    assert state.get_meta("backfill_cursor", p) is None
    state.set_meta("backfill_cursor", "abc", p)
    state.mark_seen(["1"], p)            # must not clobber meta
    assert state.get_meta("backfill_cursor", p) == "abc"
    assert json.loads(p.read_text())["seen_ids"] == ["1"]


def _make_pages(monkeypatch, pages):
    """pages: list of (tweets, next_cursor). Drives _fetch_page by call order."""
    calls = {"i": 0, "cursors": []}
    def fake_fetch(cursor):
        calls["cursors"].append(cursor)
        tw, nc = pages[calls["i"]]
        calls["i"] += 1
        return tw, nc
    monkeypatch.setattr(backfill, "_fetch_page", fake_fetch)
    archived = {"n": 0}
    def fake_archive(items):
        archived["n"] += len(items)
        return {"new": len(items), "archived": len(items), "knowledge": 0}
    monkeypatch.setattr(backfill.archiver, "archive_items", fake_archive)
    return calls


def test_backfill_paginates_until_no_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(backfill.archiver, "STATE_PATH", str(tmp_path / "s.json"))
    monkeypatch.setattr(backfill, "LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(backfill, "MAX_PAGES", 10)
    calls = _make_pages(monkeypatch, [
        ([{"id": "1"}, {"id": "2"}], "c1"),
        ([{"id": "3"}], "c2"),
        ([{"id": "4"}], None),   # last page
    ])
    out = backfill.backfill(sleeper=lambda s: None)
    assert out["status"] == "complete"
    assert out["pages"] == 3 and out["new"] == 4
    assert calls["cursors"] == [None, "c1", "c2"]   # resumed via persisted cursor
    assert state.get_meta("backfill_done", str(tmp_path / "s.json")) is True


def test_backfill_resumes_from_saved_cursor(tmp_path, monkeypatch):
    sp = str(tmp_path / "s.json")
    monkeypatch.setattr(backfill.archiver, "STATE_PATH", sp)
    monkeypatch.setattr(backfill, "LOCK_PATH", str(tmp_path / "lock"))
    state.set_meta("backfill_cursor", "resume_here", sp)
    calls = _make_pages(monkeypatch, [([{"id": "9"}], None)])
    backfill.backfill(sleeper=lambda s: None)
    assert calls["cursors"][0] == "resume_here"


def test_backfill_noop_when_done(tmp_path, monkeypatch):
    sp = str(tmp_path / "s.json")
    monkeypatch.setattr(backfill.archiver, "STATE_PATH", sp)
    monkeypatch.setattr(backfill, "LOCK_PATH", str(tmp_path / "lock"))
    state.set_meta("backfill_done", True, sp)
    out = backfill.backfill(sleeper=lambda s: None)
    assert out["status"] == "already_done"


def test_backfill_page_cap_leaves_cursor_for_resume(tmp_path, monkeypatch):
    sp = str(tmp_path / "s.json")
    monkeypatch.setattr(backfill.archiver, "STATE_PATH", sp)
    monkeypatch.setattr(backfill, "LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(backfill, "MAX_PAGES", 1)
    _make_pages(monkeypatch, [([{"id": "1"}], "more"), ([{"id": "2"}], None)])
    out = backfill.backfill(sleeper=lambda s: None)
    assert out["status"] == "page_cap_reached"
    assert state.get_meta("backfill_cursor", sp) == "more"
    assert state.get_meta("backfill_done", sp) is None
