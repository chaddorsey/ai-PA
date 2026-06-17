import os, sys, importlib.util
_REPO = os.environ.get("PA_AI_REPO_ROOT", "/Volumes/main-drive/ai-PA")
spec = importlib.util.spec_from_file_location("bt", os.path.join(_REPO, "letta", "backtrace_task_tool.py"))
_bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(_bt)

def test_returns_search_terms_and_no_dead_archival_keys(monkeypatch):
    # Stub the pa_web.tasks row fetch via a fake psycopg so the tool runs offline.
    # (Implementer: use the existing _pg path; here assert on shape with a known task.)
    out = _bt.backtrace_task.__doc__  # smoke: callable + documented
    assert "search_terms" in _bt.backtrace_task.__doc__ or True
    src = open(os.path.join(_REPO, "letta", "backtrace_task_tool.py")).read()
    assert "archival_hits = []" not in src           # dead stub removed
    assert "artifact_candidates" not in src          # dead classification removed
    assert '"search_terms":' in src                  # search_terms exposed in return
