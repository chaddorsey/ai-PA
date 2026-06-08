import json
from datetime import datetime
import pytz
import daily_briefing.refresh_current as rc

ET = pytz.timezone("America/New_York")

def test_refresh_calls_tool_with_rollover_date_and_writes_cell(monkeypatch):
    calls = {}
    def fake_tool(target_date=None, **kw):
        calls["target_date"] = target_date
        return {"status": "ok",
                "briefing": "[VERBATIM_USER_OUTPUT]\n**Wednesday's Schedule**\n\n**Schedule JSON** (x): {\"work_end\":\"17:00\",\"busy_blocks\":[]}\n[/VERBATIM_USER_OUTPUT]",
                "signal_written": True}
    def fake_put_cell(date_str, body):
        calls["cell_date"] = date_str
        calls["cell_body"] = body
        return "https://example/current"
    monkeypatch.setattr(rc, "generate_daily_briefing", fake_tool)
    monkeypatch.setattr(rc, "_put_current_cell", fake_put_cell)

    out = rc.refresh_current_briefing(now_et=ET.localize(datetime(2026, 6, 9, 18)))

    assert calls["target_date"] == "2026-06-10"
    assert calls["cell_date"] == "2026-06-10"
    assert "Schedule JSON" in calls["cell_body"]
    assert out["status"] == "ok"
    assert out["target_date"] == "2026-06-10"
    assert "[VERBATIM_USER_OUTPUT]" not in calls["cell_body"]
    assert "[/VERBATIM_USER_OUTPUT]" not in calls["cell_body"]
    assert calls["cell_body"].startswith("**Wednesday's Schedule**")

def test_refresh_raises_on_tool_error(monkeypatch):
    monkeypatch.setattr(rc, "generate_daily_briefing",
                        lambda target_date=None, **kw: {"status": "error", "error_message": "boom"})
    monkeypatch.setattr(rc, "_put_current_cell", lambda *a, **k: "")
    try:
        rc.refresh_current_briefing(now_et=ET.localize(datetime(2026, 6, 9, 9)))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "boom" in str(e)
