from datetime import datetime, timedelta
import pytz
from daily_briefing.check_current_freshness import is_stale

ET = pytz.timezone("America/New_York")

def test_fresh_within_threshold():
    now = ET.localize(datetime(2026, 6, 9, 12, 0))
    last = now - timedelta(minutes=20)
    assert is_stale(last, now) is False  # daytime threshold 40min

def test_stale_in_daytime():
    now = ET.localize(datetime(2026, 6, 9, 12, 0))
    last = now - timedelta(minutes=60)
    assert is_stale(last, now) is True

def test_overnight_relaxed():
    # 05:30 ET, last refresh 22:50 prior night (~6.6h) -> NOT stale overnight
    now = ET.localize(datetime(2026, 6, 9, 5, 30))
    last = ET.localize(datetime(2026, 6, 8, 22, 50))
    assert is_stale(last, now) is False
