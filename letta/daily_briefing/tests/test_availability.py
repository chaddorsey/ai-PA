from daily_briefing.availability import (
    parse_available_blocks, filter_blocks, _to_minutes_12h,
)

SAMPLE = """**Friday's Schedule** (updated Jun. 11 at 6:30 PM)

• **9:00 AM–11:00 AM** — *Email & Tasks*

**Available Time Remaining** — 4h, 50 min remaining
• **8:00 AM–10:00 AM** - (2h)
• **10:50 AM–11:00 AM** - (10 min)
• **1:30 PM–3:00 PM** - (1h 30 min)
• **4:00 PM–5:00 PM** - (1h)

**Schedule JSON** (for time-remaining.py): {"work_end":"17:00"}
"""

def test_to_minutes_12h():
    assert _to_minutes_12h("8:00 AM") == 480
    assert _to_minutes_12h("12:00 PM") == 720
    assert _to_minutes_12h("12:30 AM") == 30
    assert _to_minutes_12h("1:30 PM") == 810

def test_parse_blocks_from_sample():
    blocks = parse_available_blocks(SAMPLE)
    assert blocks == [
        {"start": "08:00", "end": "10:00", "duration_min": 120},
        {"start": "10:50", "end": "11:00", "duration_min": 10},
        {"start": "13:30", "end": "15:00", "duration_min": 90},
        {"start": "16:00", "end": "17:00", "duration_min": 60},
    ]

def test_fully_booked_returns_empty():
    md = "**Available Time Remaining** — 0 min remaining\n*No available time blocks*\n"
    assert parse_available_blocks(md) == []

def test_workday_over_returns_empty():
    md = "**Available Time Remaining** — workday over (0 min remaining)\n"
    assert parse_available_blocks(md) == []

def test_filter_blocks_by_min():
    blocks = parse_available_blocks(SAMPLE)
    assert filter_blocks(blocks, 90) == [
        {"start": "08:00", "end": "10:00", "duration_min": 120},
        {"start": "13:30", "end": "15:00", "duration_min": 90},
    ]
