from datetime import datetime, date
import pytz
from daily_briefing.refresh_current import current_briefing_date

ET = pytz.timezone("America/New_York")

def _et(y, m, d, hh, mm=0):
    return ET.localize(datetime(y, m, d, hh, mm))

def test_weekday_before_6pm_is_today():
    assert current_briefing_date(_et(2026, 6, 9, 9)) == date(2026, 6, 9)

def test_weekday_1759_is_today():
    assert current_briefing_date(_et(2026, 6, 9, 17, 59)) == date(2026, 6, 9)

def test_weekday_evening_is_tomorrow():
    assert current_briefing_date(_et(2026, 6, 9, 18)) == date(2026, 6, 10)

def test_friday_evening_is_monday():
    assert current_briefing_date(_et(2026, 6, 12, 18, 30)) == date(2026, 6, 15)

def test_saturday_is_monday():
    assert current_briefing_date(_et(2026, 6, 13, 10)) == date(2026, 6, 15)

def test_sunday_evening_is_monday():
    assert current_briefing_date(_et(2026, 6, 14, 23)) == date(2026, 6, 15)

def test_monday_early_is_monday():
    assert current_briefing_date(_et(2026, 6, 15, 6)) == date(2026, 6, 15)
