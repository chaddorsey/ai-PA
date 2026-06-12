import json
from bookmark_archiver import state

def test_new_bookmarks_filters_seen(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"seen_ids": ["1", "2"]}))
    items = [{"id": "1"}, {"id": "3"}, {"id": "4"}]
    fresh = state.new_bookmarks(items, p)
    assert [b["id"] for b in fresh] == ["3", "4"]

def test_mark_seen_appends_and_persists(tmp_path):
    p = tmp_path / "s.json"
    state.mark_seen(["3", "4"], p)
    state.mark_seen(["4", "5"], p)
    data = json.loads(p.read_text())
    assert sorted(data["seen_ids"]) == ["3", "4", "5"]

def test_missing_state_treats_all_new(tmp_path):
    p = tmp_path / "none.json"
    assert [b["id"] for b in state.new_bookmarks([{"id": "9"}], p)] == ["9"]
