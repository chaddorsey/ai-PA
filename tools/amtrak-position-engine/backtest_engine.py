#!/usr/bin/env python3
"""
Backtest harness for the Amtrak position engine.

Leave-one-run-out validation: for each historical run R and each station S it
actually reported (ground-truth milepost = route milepost of S), predict the
milepost at R's actual time-at-S using ALL OTHER runs, then compare.

Compares two offset-normalization methods:
  OLD = (actual - first_reported_station_scheduled)         [current engine]
  NEW = (scheduled_elapsed_from_origin) + delay             [proposed fix]

Metrics per method:
  - bias  = mean(p50_pred - true_miles)            (systematic error; ~0 is good)
  - MAE   = mean|p50_pred - true_miles|            (accuracy)
  - SDpos = mean cross-run SD of predictions       (inherent spread at that time)
  - MAE/SDpos ratio  (< 1.0 == agree within 1 SD)  ← the goal's criterion
  - coverage = fraction of true positions inside [p10,p90]  (~0.80 if calibrated)

Run with the venv python (3.11 + bs4 + pytz).
"""
import json, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from position_engine import load_asmad_runs, _data_path  # noqa: E402

# Which ASMAD train each run-set belongs to is the key in load_asmad_runs():
# '3','2','58','27','7','11','22'. route_mileposts has 3,58,27,7,11,22; milepost_2 has 2.

def build_route_tables():
    """Return {train: {'origin_dep': epoch, 'stations': {code: {'miles':m,'arr':epoch}}}}."""
    mp = json.load(open(_data_path('amtrak_route_mileposts.json')))
    m2 = json.load(open(_data_path('amtrak_milepost_2.json')))
    out = {}
    for t, d in mp.items():
        sts = d.get('stations', [])
        origin_dep = sts[0].get('sch_depart_epoch') if sts else None
        codes = {}
        for s in sts:
            arr = s.get('sch_arrive_epoch') or s.get('sch_depart_epoch')
            codes[s['code']] = {'miles': s.get('miles'), 'arr': arr}
        out[t] = {'origin_dep': origin_dep, 'stations': codes}
    # train 2 from milepost_2
    stops = m2.get('stops', [])
    origin_dep = None
    codes = {}
    for s in stops:
        arr = s.get('sched_arrive') or s.get('sched_depart')
        codes[s['code']] = {'miles': s.get('miles'), 'arr': arr}
        if origin_dep is None:
            origin_dep = s.get('sched_depart') or s.get('sched_arrive')
    out['2'] = {'origin_dep': origin_dep, 'stations': codes}
    return out


def run_offsets(run, route, method):
    """Return sorted list of (offset_h, miles) for a run under the chosen method.
    run = {station: {'sch','delay','act'}}; route = build_route_tables()[train]."""
    pts = []
    stations = route['stations']
    origin_dep = route['origin_dep']
    # OLD baseline: earliest-by-actual reported station's scheduled time
    base_sch = None
    if method == 'OLD':
        items = sorted(run.items(), key=lambda x: x[1]['act'])
        base_sch = items[0][1]['sch'] if items else None
    for code, d in run.items():
        st = stations.get(code)
        if not st or st['miles'] is None:
            continue
        if method == 'OLD':
            if base_sch is None:
                continue
            off = (d['act'] - base_sch) / 3600.0
        else:  # NEW: scheduled elapsed from origin + delay
            if st['arr'] is None or origin_dep is None:
                continue
            off = (st['arr'] - origin_dep) / 3600.0 + d['delay'] / 60.0
        pts.append((off, st['miles']))
    pts.sort()
    return pts


def interp_miles(pts, q):
    """Interpolate miles at offset q within a run's (offset,miles) points."""
    for i in range(len(pts) - 1):
        o1, m1 = pts[i]
        o2, m2 = pts[i + 1]
        if o1 <= q <= o2:
            frac = (q - o1) / (o2 - o1) if o2 != o1 else 0.5
            return m1 + frac * (m2 - m1)
    return None


def pct(sorted_vals, p):
    n = len(sorted_vals)
    return sorted_vals[min(n - 1, max(0, int(n * p)))]


def backtest(all_runs, routes, method):
    """The QUERY offset is always the true origin-relative time (= NEW formula,
    which equals elapsed-since-scheduled-origin-departure + measured delay — the
    same clock compute_schedule produces for a real query). Only the COMPARISON
    runs use `method`. This is what exposes the query-vs-historical misalignment."""
    results = []  # (true_miles, p10, p50, p90, sd)
    for train, runs in all_runs.items():
        route = routes.get(train)
        if not route:
            continue
        # comparison trajectories use `method`; held-out query points use truth (NEW)
        pred_pts = [(od, run_offsets(run, route, method)) for od, run in runs]
        pred_pts = [(od, p) for od, p in pred_pts if len(p) >= 2]
        truth_pts = {od: run_offsets(run, route, 'NEW') for od, run in runs}
        for held_od, _ in pred_pts:
            for q_off, true_m in truth_pts.get(held_od, []):
                run_pts = pred_pts  # comparison set (others) below
                preds = []
                for od2, other in run_pts:
                    if od2 == held_od:
                        continue
                    m = interp_miles(other, q_off)
                    if m is not None:
                        preds.append(m)
                if len(preds) >= 10:
                    preds.sort()
                    sd = statistics.pstdev(preds) if len(preds) > 1 else 0.0
                    results.append((true_m, pct(preds, 0.1), pct(preds, 0.5), pct(preds, 0.9), sd))
    if not results:
        return None
    bias = statistics.mean(p50 - tm for tm, _, p50, _, _ in results)
    mae = statistics.mean(abs(p50 - tm) for tm, _, p50, _, _ in results)
    sdpos = statistics.mean(sd for *_, sd in results)
    cov = statistics.mean(1.0 if p10 <= tm <= p90 else 0.0 for tm, p10, _, p90, _ in results)
    return {'n': len(results), 'bias': bias, 'mae': mae, 'sdpos': sdpos,
            'ratio': mae / sdpos if sdpos else float('inf'), 'coverage': cov}


def main():
    print('Loading ASMAD runs ...', file=sys.stderr)
    all_runs = load_asmad_runs()
    routes = build_route_tables()
    print(f'{"method":>5} | {"n":>5} | {"bias_mi":>8} | {"MAE_mi":>7} | {"SDpos":>7} | {"MAE/SD":>7} | {"cov80":>6}')
    print('-' * 62)
    for method in ('OLD', 'NEW'):
        r = backtest(all_runs, routes, method)
        if r:
            print(f'{method:>5} | {r["n"]:5d} | {r["bias"]:8.1f} | {r["mae"]:7.1f} | '
                  f'{r["sdpos"]:7.1f} | {r["ratio"]:7.2f} | {r["coverage"]:6.2f}')
        else:
            print(f'{method:>5} | (no results)')


if __name__ == '__main__':
    main()
