#!/usr/bin/env python3
"""Parse the generated leg segments (audition/leg*/seg_*.md) into the app-ready
artifact data/route_narration.json — milepost-ordered units per leg, each with
kind/mile(s)/side/salience/theme/text (the metadata the app needs for triggering,
highlight mode, fill level, theme-filter)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import position_engine as E   # noqa: E402

OUT = Path(__file__).resolve().parent / 'audition'
DATA = Path(__file__).resolve().parent / 'data'


def parse_unit(kind, head, body):
    sal = re.search(r's([1-5])\b', head)
    t = re.search(r't:\s*([^\n·]+)', head)
    u = {'kind': 'squib' if kind == 'mi' else 'interstitial', 'text': body.strip(),
         'salience': int(sal.group(1)) if sal else None,
         'theme': (t.group(1).strip() if t and t.group(1).strip() != '—' else None)}
    if kind == 'mi':
        m = re.match(r'\s*(\d+)\s*·\s*([^·]+?)\s*·\s*(left|right|both|ahead)', head)
        if m:
            u['mile'] = int(m.group(1))
            u['place'] = m.group(2).strip()
            u['side'] = m.group(3)
        else:
            mm = re.match(r'\s*(\d+)', head)
            u['mile'] = int(mm.group(1)) if mm else None
    else:
        m = re.match(r'\s*(\d+)\s*[–-]\s*(\d+)', head)
        if m:
            u['from_mi'], u['to_mi'] = int(m.group(1)), int(m.group(2))
    return u


def main():
    shapes = json.loads((DATA / 'leg_shapes.json').read_text())
    lore = json.loads((DATA / 'route_lore.json').read_text())
    out = {}
    for legdir in sorted(OUT.glob('leg*')):
        if not legdir.is_dir():
            continue
        leg = legdir.name[3:]
        units = []
        files = sorted(legdir.glob('seg_*.md'), key=lambda p: int(p.stem.split('_')[1]))
        for f in files:
            txt = f.read_text()
            for m in re.finditer(r'^@(mi|span)\b([^\n]*)\n(.*?)(?=^@(?:mi|span)\b|\Z)', txt, re.M | re.S):
                units.append(parse_unit(m.group(1), m.group(2), m.group(3)))
        units.sort(key=lambda u: u.get('mile', u.get('from_mi', 0)))
        # coordinates: on-track trigger position per unit + the POI's own point for squibs
        poly = shapes.get(leg)
        pts = sorted(lore.get(leg, {}).get('lore', []), key=lambda p: p['peak_mi'])
        for u in units:
            trig = u.get('mile') if u['kind'] == 'squib' else (u.get('from_mi', 0) + u.get('to_mi', 0)) / 2
            if poly and trig is not None:
                la, lo = E._milepost_latlon(poly, float(trig))
                u['lat'], u['lon'] = round(la, 5), round(lo, 5)   # train position when this fires
            if u['kind'] == 'squib' and u.get('mile') is not None and pts:
                near = min(pts, key=lambda p: abs(p['peak_mi'] - u['mile']))
                if abs(near['peak_mi'] - u['mile']) <= 2:
                    u['poi_lat'], u['poi_lon'] = near['lat'], near['lon']   # the feature itself
                    u['offtrack_mi'] = near.get('offtrack_mi')
        out[leg] = units
        print(f"  leg {leg}: {len(units)} units")
    (DATA / 'route_narration.json').write_text(json.dumps(out))
    total = sum(len(v) for v in out.values())
    print(f"  wrote route_narration.json — {total} units across {len(out)} legs, "
          f"{(DATA / 'route_narration.json').stat().st_size // 1024} KB")


if __name__ == '__main__':
    main()
