from datetime import date
import daily_briefing.query_available_time as q

CANNED = {
    "2026-06-15": "**Available Time Remaining** — 2h remaining\n• **8:00 AM–10:00 AM** - (2h)\n",
    "2026-06-16": "**Available Time Remaining** — 0 min remaining\n*No available time blocks*\n",
}

def test_query_filters_and_skips_empty(monkeypatch):
    monkeypatch.setattr(q, "_fetch_schedule_md",
                        lambda d: (CANNED.get(d), "2099-01-01T00:00:00-05:00"))  # never stale
    out = q.query(date(2026, 6, 15), date(2026, 6, 16), min_minutes=60,
                  weekdays_only=True, allow_refresh=False)
    assert len(out) == 1
    assert out[0]["date"] == "2026-06-15"
    assert out[0]["blocks"][0]["duration_min"] == 120

def test_query_skips_weekends(monkeypatch):
    monkeypatch.setattr(q, "_fetch_schedule_md",
                        lambda d: ("**Available Time Remaining** — 8h remaining\n• **9:00 AM–5:00 PM** - (8h)\n",
                                   "2099-01-01T00:00:00-05:00"))
    # 2026-06-13 = Sat, 2026-06-14 = Sun
    out = q.query(date(2026, 6, 13), date(2026, 6, 14), min_minutes=30, allow_refresh=False)
    assert out == []

def test_lazy_refresh_on_missing(monkeypatch):
    state = {"generated": False}
    def fake_fetch(d):
        if not state["generated"]:
            return (None, None)            # first call: missing
        return ("**Available Time Remaining** — 1h remaining\n• **4:00 PM–5:00 PM** - (1h)\n",
                "2099-01-01T00:00:00-05:00")
    def fake_gen(target_date=None, **kw):
        state["generated"] = True
        return {"status": "ok", "signal_written": True}
    monkeypatch.setattr(q, "_fetch_schedule_md", fake_fetch)
    monkeypatch.setattr(q, "generate_daily_briefing", fake_gen)
    blocks = q.get_day_blocks("2026-06-15", allow_refresh=True)
    assert state["generated"] is True
    assert blocks == [{"start": "16:00", "end": "17:00", "duration_min": 60}]
