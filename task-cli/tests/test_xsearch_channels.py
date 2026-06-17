import os, importlib.util, json, types
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("xs", os.path.join(_REPO, "letta", "xsearch_tool.py"))
xs = importlib.util.module_from_spec(spec); spec.loader.exec_module(xs)

class _R:
    def __init__(self, out): self.returncode = 0; self.stdout = out; self.stderr = ""

def test_drive_channel_parses_gws(monkeypatch):
    payload = json.dumps({"files":[{"id":"d1","name":"Vernier SOW v3",
        "webViewLink":"https://docs.google.com/document/d/d1/edit","modifiedTime":"2026-05-01T00:00:00Z"}]})
    monkeypatch.setattr(xs.subprocess, "run", lambda *a, **k: _R("Using keyring\n"+payload))
    out = xs._search_drive(["Vernier SOW"], 5)
    assert out[0]["channel"] == "drive"
    assert out[0]["url"].startswith("https://docs.google.com/document/d/d1")
    assert out[0]["title"] == "Vernier SOW v3"

def test_slack_channel_registered():
    assert "slack" in xs._CHANNELS and "gmail" in xs._CHANNELS and "drive" in xs._CHANNELS


def test_drive_term_quotes_sanitized(monkeypatch):
    captured = {}
    def _fake_run(*a, **k):
        captured["argv"] = a[0]
        return _R(json.dumps({"files": []}))
    monkeypatch.setattr(xs.subprocess, "run", _fake_run)
    xs._search_drive(["O'Brien \"SOW\""], 5)
    params = captured["argv"][captured["argv"].index("--params") + 1]
    # No raw apostrophe/double-quote should survive inside the term portion of the q
    assert "O'Brien" not in params and 'O\\"Brien' not in params
    assert "OBrien" in params or "Brien" in params  # sanitized term still present


def test_clean_term_strips_quotes():
    assert xs._clean_term("O'Brien") == "OBrien" or "Brien" in xs._clean_term("O'Brien")
    assert '"' not in xs._clean_term('say "hi"')
