#!/usr/bin/env python3
"""
Solar position (elevation, azimuth) for the route tours — stdlib only, ~0.01° accuracy
(low-precision NOAA/Meeus algorithm; no atmospheric refraction). Used to annotate
"where's the sun" and "which window" on predicted positions.
"""
import math
from datetime import timezone

_RAD = math.pi / 180.0
_COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
            'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def sun_position(dt, lat, lon):
    """Return (elevation_deg, azimuth_deg_from_north) of the sun at datetime `dt`
    (tz-aware or naive-UTC) and location (lat, lon)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    h = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    y, m, d = dt.year, dt.month, dt.day
    if m <= 2:
        y -= 1
        m += 12
    A = y // 100
    B = 2 - A + A // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5 + h / 24.0
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = (357.528 + 0.9856003 * n) % 360
    lam = (L + 1.915 * math.sin(g * _RAD) + 0.020 * math.sin(2 * g * _RAD)) % 360
    eps = 23.439 - 0.0000004 * n
    decl = math.asin(math.sin(eps * _RAD) * math.sin(lam * _RAD))
    ra = math.degrees(math.atan2(math.cos(eps * _RAD) * math.sin(lam * _RAD),
                                 math.cos(lam * _RAD))) % 360
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    lst = (gmst + lon) % 360
    ha = ((lst - ra + 180) % 360 - 180) * _RAD
    latr = lat * _RAD
    el = math.asin(math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(ha))
    az = math.atan2(math.sin(ha), math.cos(ha) * math.sin(latr) - math.tan(decl) * math.cos(latr))
    return math.degrees(el), (math.degrees(az) + 180) % 360


def compass(az):
    return _COMPASS[int((az % 360) / 22.5 + 0.5) % 16]


def side_of(az, heading):
    """Which side of travel the sun is on, given route heading (deg from north)."""
    if heading is None:
        return None
    rel = (az - heading + 360) % 360
    if 30 <= rel < 150:
        return 'right'
    if 210 <= rel < 330:
        return 'left'
    return 'ahead' if rel < 30 or rel >= 330 else 'behind'


def describe(dt, lat, lon, heading=None):
    """Human summary: 'sun WNW 9° (golden hour), on your right' / 'night (sun down)'."""
    el, az = sun_position(dt, lat, lon)
    if el < -6:
        return 'night (sun down)'
    state = ('twilight' if el < 0 else 'golden hour' if el < 8
             else 'low' if el < 25 else 'high')
    s = f"sun {compass(az)} {el:.0f}° ({state})"
    side = side_of(az, heading)
    if side in ('left', 'right'):
        s += f", on your {side}"
    elif side == 'ahead':
        s += ", ahead (into the sun)"
    elif side == 'behind':
        s += ", behind you"
    return s


if __name__ == '__main__':  # quick self-check against known geometry
    from datetime import datetime
    # Summer-solstice solar noon, Denver (40N,105W): sun ~due south, very high (~73°)
    el, az = sun_position(datetime(2026, 6, 21, 19, 0, tzinfo=timezone.utc), 40.0, -105.0)
    print(f"  solstice noon Denver: el={el:.1f}° az={az:.0f}° ({compass(az)})  [expect ~73°, ~S]")
    # Evening: sun should be west and low
    el, az = sun_position(datetime(2026, 7, 16, 3, 0, tzinfo=timezone.utc), 34.5, -120.5)
    print(f"  ~8pm PDT CA coast: el={el:.1f}° az={az:.0f}° ({compass(az)})  [expect low, ~W/NW]")
