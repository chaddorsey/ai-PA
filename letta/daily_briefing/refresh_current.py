"""Refresher for the 'current' daily-briefing materialized cell.

Owns the 'which day is current' policy (rollover), calls the pure
generate_daily_briefing renderer, and writes the date-less
signals/current/schedule.md cell. The renderer call + cell write are added in
a later task; this module currently provides the pure rollover helper.
"""
from datetime import datetime, date, timedelta


def current_briefing_date(now_et: datetime) -> date:
    """The schedule date that is 'current' for a given Eastern-time moment.

    Weekday before 18:00 ET -> today. Otherwise (evening on a weekday, or any
    time on a weekend) -> the next workday strictly after today
    (Fri/Sat/Sun -> Monday).
    """
    today = now_et.date()
    if today.weekday() < 5 and now_et.hour < 18:  # Mon..Fri before 6pm
        return today
    d = today + timedelta(days=1)
    while d.weekday() >= 5:  # skip Sat(5)/Sun(6)
        d += timedelta(days=1)
    return d
