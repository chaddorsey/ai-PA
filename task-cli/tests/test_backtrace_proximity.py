import os, sys, importlib.util, types
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
spec = importlib.util.spec_from_file_location("bt", os.path.join(_REPO, "letta", "backtrace_task_tool.py"))
bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)


class _FakeCur:
    def __init__(self, row): self._row = row
    def execute(self, *a, **k): pass
    def fetchone(self): return self._row
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeConn:
    def __init__(self, row): self._row = row
    def cursor(self): return _FakeCur(self._row)
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_slack_anchors_come_from_proximity_window(monkeypatch):
    # pa_web.tasks row for a slack task: raw_description, suggested_title, source,
    # source_ref, source_metadata, task_body, origin
    row = ("ping", "Ping about thing", "slack",
           "slack-C123-1700000000.000100", {}, "ping", "userA")
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(row))
    # The proximity window surfaces a distinctive noun + URL absent from the row body.
    windowed = ("[*** ANCHOR ***] ping\n[reply] We should reuse the Brontosaurus "
                "spec: https://docs.google.com/document/d/ZZZ/edit")
    import letta.fetch_source_content_tool as fsc
    monkeypatch.setattr(fsc, "fetch_source_content",
                        lambda **k: {"status": "ok", "content": windowed})
    out = bt.backtrace_task("abc123ef")
    assert out["status"] == "ok"
    # anchors["urls"] carries harvested URLs; search_terms carries proper nouns / phrases.
    # "Brontosaurus" is a single capitalized word captured by the proper-noun regex and
    # flows into search_terms. The docs.google.com URL lands in anchors["urls"].
    # Both are absent from the thin row excerpt ("ping") — they prove the window was used.
    blob = " ".join(out.get("search_terms", [])) + " " + " ".join(
        out.get("anchors", {}).get("urls", []))
    assert "Brontosaurus" in blob or "docs.google.com/document/d/ZZZ" in blob
