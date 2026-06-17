"""Tests for qmd-backed memory channels in xsearch."""
import os
import importlib.util
import json

_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("xs", os.path.join(_REPO, "letta", "xsearch_tool.py"))
xs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xs)


class _R:
    """Mock subprocess.run result."""
    def __init__(self, out):
        self.returncode = 0
        self.stdout = out
        self.stderr = ""


def test_qmd_channels_registered():
    """All four qmd memory channels must be registered in _CHANNELS."""
    for c in ("canonical", "history", "reference", "meetings"):
        assert c in xs._CHANNELS, f"Channel '{c}' not registered in _CHANNELS"


def test_qmd_parse(monkeypatch):
    """Parse bare JSON array from qmd search with file/docid/title/snippet shape."""
    # Bare JSON array (not wrapped in {"results":[...]})
    payload = json.dumps([
        {
            "file": "qmd://canonical/people/tom.md",
            "title": "Tom — Vernier",
            "snippet": "Vernier biology lead",
            "score": 0.8,
            "docid": "#abc"
        }
    ])
    monkeypatch.setattr(xs.subprocess, "run", lambda *a, **k: _R(payload))
    out = xs._search_qmd("canonical", "canonical")(["Vernier"], 5)
    assert len(out) == 1
    assert out[0]["channel"] == "canonical"
    assert "Tom" in out[0]["title"]
    assert "Vernier" in out[0]["title"]
    assert out[0]["url"].startswith("qmd://canonical")
    assert "biology" in out[0]["snippet"]
