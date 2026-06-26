#!/usr/bin/env python3
"""
Google Earth fly-ahead tour generator — a pure transform of the route-guide contract.

Reads the committed data/leg_shapes.json (the on-track polyline) and
data/route_guide.json (features), and emits a KML with:
  • the route as a Path,
  • every feature as a Placemark (folders for Sights and Stations),
  • a gx:Tour that flies the route forward-looking and pauses at marquee sights.

Open the .kml in Google Earth (desktop or web) and press play. Stdlib only.

Usage:
  python3 kml_tour.py 11            # one leg -> kml/coast-starlight.kml
  python3 kml_tour.py all           # all six legs -> kml/<corridor>.kml
  python3 kml_tour.py 11 --min-salience 4   # only the big-ticket sights as placemarks
"""
import json
import math
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
OUTDIR = Path(__file__).resolve().parent / 'kml'

ICON = {  # Google-hosted paddle/marker icons by feature class
    'scenic': 'http://maps.google.com/mapfiles/kml/paddle/ylw-stars.png',
    'natural': 'http://maps.google.com/mapfiles/kml/paddle/grn-blank.png',
    'protected': 'http://maps.google.com/mapfiles/kml/paddle/grn-diamond.png',
    'engineering': 'http://maps.google.com/mapfiles/kml/shapes/triangle.png',
    'place': 'http://maps.google.com/mapfiles/kml/paddle/wht-circle.png',
    'station': 'http://maps.google.com/mapfiles/kml/shapes/rail.png',
}


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _bearing(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dl = lon2 - lon1
    x = math.sin(dl) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _latlon_at(poly, mile):
    if mile <= poly[0][0]:
        return poly[0][1], poly[0][2]
    if mile >= poly[-1][0]:
        return poly[-1][1], poly[-1][2]
    for i in range(len(poly) - 1):
        m1, la1, lo1 = poly[i]
        m2, la2, lo2 = poly[i + 1]
        if m1 <= mile <= m2:
            f = (mile - m1) / (m2 - m1) if m2 != m1 else 0.0
            return la1 + f * (la2 - la1), lo1 + f * (lo2 - lo1)
    return poly[-1][1], poly[-1][2]


def _styles():
    out = ['<Style id="route"><LineStyle><color>ff1e90ff</color><width>4</width></LineStyle></Style>']
    for cls, url in ICON.items():
        scale = 1.2 if cls in ('scenic', 'protected') else 0.9
        out.append(f'<Style id="{cls}"><IconStyle><scale>{scale}</scale>'
                   f'<Icon><href>{url}</href></Icon></IconStyle></Style>')
    return '\n'.join(out)


def _placemarks(features, min_salience):
    sights, stations = [], []
    for f in features:
        if f['salience'] < min_salience and f['class'] != 'station':
            continue
        side = {'left': 'left window', 'right': 'right window', 'both': 'both sides',
                'ahead': 'ahead'}.get(f['side'], f['side'])
        desc = f"{_esc(f.get('blurb', ''))}<br/>mile {f['peak_mi']:.0f} · {side}"
        pm = (f'<Placemark><name>{_esc(f["name"])}</name>'
              f'<description><![CDATA[{desc}]]></description>'
              f'<styleUrl>#{f["class"]}</styleUrl>'
              f'<Point><coordinates>{f["lon"]},{f["lat"]},0</coordinates></Point></Placemark>')
        (stations if f['class'] == 'station' else sights).append(pm)
    return (f'<Folder><name>Sights ({len(sights)})</name>{"".join(sights)}</Folder>'
            f'<Folder><name>Stations ({len(stations)})</name>'
            f'<visibility>0</visibility>{"".join(stations)}</Folder>')


def _tour(poly, features, step_mi=18.0, alt_m=5500.0):
    """Fly the route forward-looking, with a LookAt + pause at salience≥4 sights."""
    legmi = poly[-1][0]
    stops = sorted([f for f in features if f['salience'] >= 4 and f['class'] != 'station'],
                   key=lambda x: x['peak_mi'])
    items = []
    si = 0
    mile = 0.0
    while mile <= legmi:
        la, lo = _latlon_at(poly, mile)
        nxt = _latlon_at(poly, min(mile + step_mi, legmi))
        hdg = _bearing((la, lo), nxt)
        items.append(
            f'<gx:FlyTo><gx:duration>1.6</gx:duration><gx:flyToMode>smooth</gx:flyToMode>'
            f'<Camera><longitude>{lo:.5f}</longitude><latitude>{la:.5f}</latitude>'
            f'<altitude>{alt_m}</altitude><heading>{hdg:.1f}</heading><tilt>67</tilt>'
            f'<altitudeMode>relativeToGround</altitudeMode></Camera></gx:FlyTo>')
        # pause at any marquee sight we just passed
        while si < len(stops) and stops[si]['peak_mi'] <= mile:
            s = stops[si]
            items.append(
                f'<gx:FlyTo><gx:duration>2.0</gx:duration><gx:flyToMode>smooth</gx:flyToMode>'
                f'<LookAt><longitude>{s["lon"]:.5f}</longitude><latitude>{s["lat"]:.5f}</latitude>'
                f'<altitude>0</altitude><heading>{hdg:.1f}</heading><tilt>75</tilt>'
                f'<range>22000</range></LookAt></gx:FlyTo>'
                f'<gx:Wait><gx:duration>2.2</gx:duration></gx:Wait>')
            si += 1
        mile += step_mi
    return (f'<gx:Tour><name>Fly the route</name><gx:Playlist>{"".join(items)}</gx:Playlist></gx:Tour>')


def build_leg_kml(leg, corridor, poly, features, min_salience=3):
    coords = ' '.join(f'{lo:.5f},{la:.5f},0' for _m, la, lo in poly)
    route = (f'<Placemark><name>Route</name><styleUrl>#route</styleUrl>'
             f'<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString></Placemark>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">\n'
        f'<Document><name>{_esc(corridor)} (leg {leg})</name>\n'
        f'{_styles()}\n{route}\n{_placemarks(features, min_salience)}\n{_tour(poly, features)}\n'
        '</Document></kml>\n')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    min_sal = 3
    if '--min-salience' in sys.argv:
        min_sal = int(sys.argv[sys.argv.index('--min-salience') + 1])
    target = args[0] if args else 'all'
    shapes = json.loads((DATA / 'leg_shapes.json').read_text())
    guide = json.loads((DATA / 'route_guide.json').read_text())
    OUTDIR.mkdir(exist_ok=True)
    legs = list(guide) if target == 'all' else [target]
    for leg in legs:
        if leg not in guide or leg not in shapes:
            print(f"  leg {leg}: no data")
            continue
        corridor = guide[leg].get('corridor', f'leg {leg}')
        slug = corridor.lower().replace(' ', '-')
        kml = build_leg_kml(leg, corridor, shapes[leg], guide[leg]['features'], min_sal)
        path = OUTDIR / f'{slug}.kml'
        path.write_text(kml)
        n_sight = sum(1 for f in guide[leg]['features'] if f['salience'] >= min_sal and f['class'] != 'station')
        print(f"  leg {leg}: {path}  ({len(shapes[leg])} path pts, {n_sight} sights)")
    print(f"Open the .kml file(s) in {OUTDIR} with Google Earth and press play.")


if __name__ == '__main__':
    main()
