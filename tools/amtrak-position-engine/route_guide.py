#!/usr/bin/env python3
"""
Route-guide runtime — "what's around me" / "what's coming" over the compiled
data/route_guide.json. Stdlib-only; the heavy compile lives in build_route_guide.py.

Every function takes the leg's anchor-relative milepost (the same axis the engine
and eta_to_mile use), so the guide composes with prediction and the live feed.
"""
import json
from pathlib import Path

GUIDE_FILE = Path(__file__).resolve().parent / 'data' / 'route_guide.json'


def load_guide():
    try:
        return json.loads(GUIDE_FILE.read_text()) if GUIDE_FILE.exists() else {}
    except Exception:
        return {}


def features_for(guide, leg):
    return guide.get(leg, {}).get('features', [])


def around(guide, leg, mile, radius_mi=25.0, min_salience=1):
    """Features whose span contains `mile`, or whose peak is within radius_mi.
    Each annotated with rel_mi (− behind / + ahead) and `inside`."""
    out = []
    for f in features_for(guide, leg):
        if f['salience'] < min_salience:
            continue
        inside = f['from_mi'] < f['to_mi'] and f['from_mi'] <= mile <= f['to_mi']
        if inside or (mile - radius_mi <= f['peak_mi'] <= mile + radius_mi):
            out.append({**f, 'rel_mi': round(f['peak_mi'] - mile, 1), 'inside': inside})
    out.sort(key=lambda x: (not x['inside'], abs(x['rel_mi'])))
    return out


def current_context(guide, leg, mile):
    """Spans you are inside right now (in this park / desert / on this bridge / county)."""
    return [f for f in features_for(guide, leg)
            if f['from_mi'] < f['to_mi'] and f['from_mi'] <= mile <= f['to_mi']]


def area_at(guide, leg, mile):
    """The statistical area (county) span containing `mile`, or None — carries `stats`."""
    for f in features_for(guide, leg):
        if f.get('class') == 'area' and f['from_mi'] <= mile <= f['to_mi']:
            return f
    return None


def lookahead(ctx, guide, leg, mile, ref_dt, observed=None, horizon_min=120,
              min_salience=2, eta_fn=None):
    """Upcoming features (peak ahead of `mile`) arriving within horizon_min of ref_dt,
    each with a conditioned ETA from eta_to_mile. ref_dt is the current/query time."""
    import position_engine as E
    fn = eta_fn or E.eta_to_mile
    out = []
    for f in features_for(guide, leg):
        if f['salience'] < min_salience or f['peak_mi'] <= mile:
            continue
        eta = fn(ctx, leg, f['peak_mi'], observed=observed)
        if not eta:
            continue
        mins = (eta['p50'] - ref_dt).total_seconds() / 60.0
        if 0 < mins <= horizon_min:
            out.append({**f, 'eta': eta, 'mins_ahead': round(mins)})
    out.sort(key=lambda x: x['mins_ahead'])
    return out


def alerts(ctx, guide, leg, mile, ref_dt, observed=None, within_min=30, min_salience=4):
    """High-salience features arriving within `within_min` — for proactive notices."""
    return lookahead(ctx, guide, leg, mile, ref_dt, observed, within_min, min_salience)
