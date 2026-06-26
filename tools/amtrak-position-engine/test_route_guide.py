#!/usr/bin/env python3
"""Unit tests for the route-guide layer: schema invariants, milepost projection, and
runtime behavior. Stdlib only — runs under pytest or directly (`python3 test_route_guide.py`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E   # noqa: E402
import route_guide as RG      # noqa: E402

REQUIRED = ('id', 'name', 'kind', 'class', 'from_mi', 'to_mi', 'peak_mi',
            'lat', 'lon', 'side', 'salience')


def test_schema_invariants():
    g = RG.load_guide()
    assert g, "route_guide.json missing/empty — run build_route_guide.py"
    for leg, d in g.items():
        ids, last = set(), -1e9
        for f in d['features']:
            for k in REQUIRED:
                assert k in f, f"{leg}:{f.get('id')} missing field {k}"
            assert f['from_mi'] <= f['peak_mi'] <= f['to_mi'], f"{leg}:{f['id']} milepost order"
            assert 1 <= f['salience'] <= 5, f"{leg}:{f['id']} salience out of range"
            assert f['id'] not in ids, f"{leg}:{f['id']} duplicate id"
            ids.add(f['id'])
            assert f['peak_mi'] >= last - 1e-6, f"{leg}:{f['id']} not sorted by peak_mi"
            last = f['peak_mi']
            assert f['side'] in ('left', 'right', 'both', 'ahead'), f"{leg}:{f['id']} bad side"


def test_projection_roundtrip():
    ctx = E.load_engine()
    rs = E.build_route_sched()
    sched = ctx['all_schedules']['3']
    frame = E.build_leg_frame('3', sched, rs)
    anchor = next(s['code'] for s in sched if s['code'] in frame)
    amile = frame[anchor]['miles']
    for code in ('KCY', 'ABQ', 'FLG'):
        fr = frame[code]
        mi = E.project_to_leg(ctx['leg_shapes']['3'], fr['lat'], fr['lon'])[0]
        assert abs(mi - (fr['miles'] - amile)) < 3.0, f"{code} projects {mi}, expected {fr['miles']-amile}"


def test_coverage_and_marquee():
    g = RG.load_guide()
    for leg, d in g.items():
        curated = [f for f in d['features'] if f['source'] == 'curated']
        assert len(curated) >= 5, f"leg {leg} has only {len(curated)} curated features (<5)"
        assert 'coverage_gaps' in d, f"leg {leg} missing coverage_gaps annotation"


def test_runtime_around_and_context():
    g = RG.load_guide()
    near = RG.around(g, '3', 1094.0, radius_mi=20)   # Raton Pass milepost
    assert any(f['id'] == 'raton-pass' for f in near), "around() missed Raton Pass"
    inside = RG.current_context(g, '27', 1400.0)      # inside the Montana Hi-Line span
    assert any('hi-line' in f['id'] for f in inside), "current_context() missed Montana Hi-Line"


LANDMARKS = [
    ('3', 'raton-pass', 'both'),
    ('2', 'pecos-river-high-bridge', 'both'),
    ('58', 'mississippi-memphis', 'left'),       # river to the west, going north
    ('27', 'marias-pass', 'both'),
    ('27', 'glacier-national-park', 'right'),     # park to the north, going west
    ('27', 'columbia-river-gorge', 'left'),       # river to the south, going west
    ('11', 'pacific-coast-gaviota', 'right'),     # ocean to the west, going south
    ('422', 'mississippi-river-stlouis', 'both'),
]


def test_landmark_spotchecks():
    g = RG.load_guide()
    for leg, fid, side in LANDMARKS:
        f = next((x for x in g[leg]['features'] if x['id'] == fid), None)
        assert f is not None, f"{leg}:{fid} missing"
        assert f['side'] == side, f"{leg}:{fid} side={f['side']} expected {side}"
        assert 0 <= f['peak_mi'] <= g[leg]['leg_miles'], f"{leg}:{fid} milepost off-leg"


def main():
    tests = [test_schema_invariants, test_projection_roundtrip,
             test_coverage_and_marquee, test_runtime_around_and_context,
             test_landmark_spotchecks]
    fails = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n  {len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
