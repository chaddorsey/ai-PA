import os
import sys
import importlib.util

import pytest

# Load the tool module directly from the repo (same path the CLI uses).
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location(
    "stage_resource_tool", os.path.join(_REPO, "letta", "stage_resource_tool.py"))
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
stage_resource = _mod.stage_resource


def test_inline_text_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("STAGE_OPENFILE_BASE", str(tmp_path))
    r = stage_resource(text="Body text", label="My Note", ref_id="abc123ef")
    assert r["status"] == "ok"
    assert r["openfile_url"].startswith(f"openfile://{tmp_path}")
    assert r["openfile_url"].endswith("My-Note.md")
    written = r["local_path"]
    assert os.path.exists(written)
    with open(written) as f:
        assert f.read() == "# My Note\n\nBody text"


def test_inline_text_preserves_existing_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("STAGE_OPENFILE_BASE", str(tmp_path))
    r = stage_resource(text="# Already Titled\n\nx", label="L", ref_id="abc123ef")
    with open(r["local_path"]) as f:
        assert f.read() == "# Already Titled\n\nx"


def test_web_page_url_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    r = stage_resource(url="https://example.com/article", label="Page")
    assert r["status"] == "skipped"


def test_requires_url_or_text(tmp_path, monkeypatch):
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    r = stage_resource(label="L")
    assert r["status"] == "error"


def test_openfile_base_translation(tmp_path, monkeypatch):
    # Simulate container write-path -> host openfile-path mapping.
    monkeypatch.setenv("STAGE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("STAGE_OPENFILE_BASE", "/HOST/staged")
    r = stage_resource(text="x", label="L", ref_id="r")
    assert r["openfile_url"] == "openfile:///HOST/staged/notes/r/L.md"
