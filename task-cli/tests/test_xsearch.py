import os, sys, importlib.util, json
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("xs", os.path.join(_REPO, "letta", "xsearch_tool.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)

def test_dedup_and_normalize():
    rows = [
        {"channel":"tasks","title":"A","url":"u1","permalink":"","snippet":"s","date":"d","id":"1"},
        {"channel":"tasks","title":"A dup","url":"u1","permalink":"","snippet":"s","date":"d","id":"1"},
        {"channel":"drive","title":"B","url":"u2","permalink":"","snippet":"","date":"","id":"2"},
    ]
    out = xs._dedup(rows)
    assert len(out) == 2  # u1 collapsed

def test_failed_channel_is_reported_not_silent(monkeypatch):
    def raise_boom(terms, lim):
        raise RuntimeError("boom")
    monkeypatch.setitem(xs._CHANNELS, "tasks", raise_boom)
    res = xs.xsearch(["x"], channels=["tasks"])
    assert res["candidates"] == []
    assert res["failed_channels"] and res["failed_channels"][0]["channel"] == "tasks"

def test_tasks_channel_shape(monkeypatch):
    # _search_tasks returns normalized candidates; here feed a fake DB layer.
    fake_search = lambda terms, lim: [
        {"channel":"tasks","title":"Vernier SOW","url":"","permalink":"","snippet":"","date":"2026-06-16","id":"abc"}]
    monkeypatch.setitem(xs._CHANNELS, "tasks", fake_search)
    res = xs.xsearch(["Vernier"], channels=["tasks"])
    assert res["status"] == "ok"
    assert res["candidates"][0]["channel"] == "tasks"
