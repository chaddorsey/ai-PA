#!/usr/bin/env python3
"""
Live Amtrak position via the Amtraker v3 community feed, with a last-fix cache.

Amtraker (https://api-v3.amtraker.com) decrypts Amtrak's otherwise-obfuscated
Track-Your-Train feed into clean JSON. It is a community service and can break,
so EVERYTHING here is best-effort: any failure returns None (or a cached fix),
and the caller falls back to the historical predictor. Runtime deps: stdlib only.
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

AMTRAKER_URL = 'https://api-v3.amtraker.com/v3/trains'
CACHE_FILE = Path(__file__).resolve().parent / '.live_cache.json'  # gitignored
DEFAULT_TIMEOUT = 12


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def fetch_all(timeout=DEFAULT_TIMEOUT):
    """Return Amtraker's full {trainNum: [trainData, ...]} dict, or None on any failure."""
    try:
        req = urllib.request.Request(
            AMTRAKER_URL, headers={'User-Agent': 'amtrak-position-engine'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def _summarize(t):
    """Reduce one Amtraker trainData to the fields we report."""
    last_departed = None
    next_stop = None
    for s in t.get('stations', []):
        status = s.get('status')
        if status == 'Departed':
            last_departed = s
        elif next_stop is None and status in ('Enroute', 'Station'):
            next_stop = s
    delay_min = None
    if last_departed:
        a, b = _parse_iso(last_departed.get('dep')), _parse_iso(last_departed.get('schDep'))
    elif next_stop:
        a, b = _parse_iso(next_stop.get('arr')), _parse_iso(next_stop.get('schArr'))
    else:
        a = b = None
    if a and b:
        delay_min = round((a - b).total_seconds() / 60)
    return {
        'source': 'live',
        'train_num': t.get('trainNum'),
        'route': t.get('routeName'),
        'lat': t.get('lat'),
        'lon': t.get('lon'),
        'velocity_mph': round(t['velocity'], 1) if t.get('velocity') is not None else None,
        'heading': t.get('heading'),
        'state': t.get('trainState'),
        'next_code': t.get('eventCode'),
        'next_name': t.get('eventName'),
        'next_eta': next_stop.get('arr') if next_stop else None,
        'delay_min': delay_min,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
    }


def live_position(train_num, data=None, timeout=DEFAULT_TIMEOUT, use_cache=True):
    """Summarized live fix for train_num's Active instance; caches every success.
    Falls back to the cached fix (marked source='cache') if the fetch fails."""
    if data is None:
        data = fetch_all(timeout)
    if data is not None:
        arr = data.get(str(train_num)) or []
        active = [t for t in arr if t.get('trainState') == 'Active'] or arr
        if active:
            summ = _summarize(active[0])
            _write_cache(train_num, summ)
            return summ
    return _read_cache(train_num) if use_cache else None


def _write_cache(train_num, summ):
    try:
        cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
        cache[str(train_num)] = summ
        CACHE_FILE.write_text(json.dumps(cache))
    except Exception:
        pass


def _read_cache(train_num):
    try:
        if CACHE_FILE.exists():
            s = json.loads(CACHE_FILE.read_text()).get(str(train_num))
            if s:
                s = dict(s)
                s['source'] = 'cache'
                return s
    except Exception:
        pass
    return None


def cache_age_minutes(summ):
    """Minutes since a (cached) fix was fetched, or None."""
    t = _parse_iso(summ.get('fetched_at')) if summ else None
    if not t:
        return None
    return round((datetime.now(timezone.utc) - t).total_seconds() / 60)
