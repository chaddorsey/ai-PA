from datetime import date
import daily_briefing.lookahead_prewrite as lp

def test_lookahead_dates_weekdays_only():
    # 2026-06-11 is a Thursday. D+2..D+13, weekdays only.
    got = lp.lookahead_dates(date(2026, 6, 11))
    assert date(2026, 6, 13) not in got  # Sat
    assert date(2026, 6, 14) not in got  # Sun
    assert date(2026, 6, 15) in got      # Mon
    assert got[0] == date(2026, 6, 15)   # first weekday at/after D+2
    assert all(d.weekday() < 5 for d in got)

def test_lookahead_dates_includes_weekends_when_disabled():
    got = lp.lookahead_dates(date(2026, 6, 11), weekdays_only=False)
    assert date(2026, 6, 13) in got
    assert len(got) == 12  # D+2..D+13 inclusive

def test_prewrite_aggregates_ok_and_fail(monkeypatch):
    calls = []
    def fake_tool(target_date=None, **kw):
        calls.append(target_date)
        if target_date == "2026-06-16":
            return {"status": "error", "error_message": "boom", "signal_written": False}
        return {"status": "ok", "signal_written": True}
    monkeypatch.setattr(lp, "generate_daily_briefing", fake_tool)
    results = lp.prewrite_lookahead(today=date(2026, 6, 11))
    by_date = {r["date"]: r for r in results}
    assert by_date["2026-06-15"]["ok"] is True
    assert by_date["2026-06-16"]["ok"] is False
    assert by_date["2026-06-16"]["error"] == "boom"
    assert "2026-06-15" in calls
