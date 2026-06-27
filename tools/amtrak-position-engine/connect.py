#!/usr/bin/env python3
"""
L3 connections + temporal layer → data/route_connections.json.

For each Wikipedia lore point (id 'w<pageid>'), grounds the connective web:
  categories        — Wikipedia categories (maintenance cats stripped) → the recurring threads
  named_after   — Wikidata P138 (resolved label)
  part_of       — Wikidata P361 (resolved label)
  dates         — Wikidata inception/dissolved/point-in-time + category years + summary years
Plus per-leg theme aggregation. Feeds the connective/temporal narration (with timeline.yml).

Build-time, network, keyless; cached in .cache/wiki.json (shared with lore.py).
  python3 connect.py [leg ...]
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'
CACHE = Path(__file__).resolve().parent / '.cache'
CONN = DATA / 'route_connections.json'
LORE = DATA / 'route_lore.json'
UA = {'User-Agent': 'amtrak-route-guide/1.0 (personal trip project; github.com/chaddorsey)'}

_CAT_DROP = re.compile(
    r'^(Articles|All |Pages |Use |CS1|Webarchive|Commons|Wikipedia|Coordinates|Short description|'
    r'Hidden|Engvar|Featured|Good articles|Redirects|Webarchive)'
    r'|Wikidata|stub|template|dmy dates|mdy dates|EngvarB', re.I)
_YEAR = re.compile(r'\b(1[5-9]\d\d|20[0-2]\d)\b')
# admin/boilerplate categories to drop from CATEGORIES (keep evocative threads like
# "American frontier", "Ghost towns in Colorado", "Populated places in the Mojave Desert")
_ADMIN_DROP = re.compile(
    r'^(Cities|Towns|Villages|Census-designated places|Unincorporated communities|County seats|'
    r'Neighborhoods|Former municipalities|Former populated places in \w+ County|'
    r'Populated places in \w+ County|Populated places established|Geography of \w+ County|'
    r'History of \w+ County)'
    r'|metropolitan area|micropolitan area|establishments in|disestablishments in'
    r'|established in \d| counties$|^Lists? of|^Populated places established', re.I)

_CP = None
_F = 0


def _tick(c):
    global _F
    _F += 1
    if _CP is not None and _F % 20 == 0:
        _CP.write_text(json.dumps(c))


def _get(url, tries=3):
    import urllib.error
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and t < tries - 1:
                time.sleep(2 * (t + 1))
                continue
            raise
        except Exception:
            if t < tries - 1:
                time.sleep(1.5 * (t + 1))
                continue
            raise


def _cache():
    CACHE.mkdir(exist_ok=True)
    p = CACHE / 'wiki.json'
    return p, (json.loads(p.read_text()) if p.exists() else {})


def _qids(pageids, cache):
    todo = [p for p in pageids if f"pp:{p}" not in cache]
    for i in range(0, len(todo), 50):
        b = todo[i:i + 50]
        url = ("https://en.wikipedia.org/w/api.php?action=query&format=json"
               "&prop=pageprops&ppprop=wikibase_item&pageids=" + "|".join(map(str, b)))
        try:
            for pid, pg in _get(url)['query']['pages'].items():
                cache[f"pp:{pid}"] = pg.get('pageprops', {}).get('wikibase_item')
        except Exception:
            for p in b:
                cache[f"pp:{p}"] = None
        _tick(cache)
        time.sleep(0.1)
    return {p: cache.get(f"pp:{p}") for p in pageids}


def _categories(pageids, cache):
    todo = [p for p in pageids if f"cat:{p}" not in cache]
    for i in range(0, len(todo), 10):   # small batch: cllimit is shared across pages
        b = todo[i:i + 10]
        url = ("https://en.wikipedia.org/w/api.php?action=query&format=json&prop=categories"
               "&clshow=!hidden&cllimit=500&pageids=" + "|".join(map(str, b)))
        try:
            for pid, pg in _get(url)['query']['pages'].items():
                cats = [c['title'].replace('Category:', '') for c in pg.get('categories', [])]
                cache[f"cat:{pid}"] = [c for c in cats if not _CAT_DROP.search(c)]
        except Exception:
            for p in b:
                cache[f"cat:{p}"] = []
        _tick(cache)
        time.sleep(0.1)
    return {p: cache.get(f"cat:{p}", []) for p in pageids}


def _claims(qids, cache):
    todo = [q for q in qids if q and f"rc:{q}" not in cache]
    for i in range(0, len(todo), 50):
        b = todo[i:i + 50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
               "&props=claims&ids=" + "|".join(b))
        try:
            for q, e in _get(url)['entities'].items():
                cl = e.get('claims', {})

                def ent(p):
                    try:
                        return cl[p][0]['mainsnak']['datavalue']['value']['id']
                    except Exception:
                        return None

                def yr(p):
                    try:
                        return int(cl[p][0]['mainsnak']['datavalue']['value']['time'][1:5])
                    except Exception:
                        return None
                cache[f"rc:{q}"] = {'named_after': ent('P138'), 'part_of': ent('P361'),
                                    'inception': yr('P571'), 'dissolved': yr('P576'),
                                    'point_in_time': yr('P585')}
        except Exception:
            for q in b:
                cache[f"rc:{q}"] = {}
        _tick(cache)
        time.sleep(0.1)
    return {q: cache.get(f"rc:{q}", {}) for q in qids if q}


def _labels(qids, cache):
    todo = [q for q in qids if q and f"lbl:{q}" not in cache]
    for i in range(0, len(todo), 50):
        b = todo[i:i + 50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json"
               "&props=labels&languages=en&ids=" + "|".join(b))
        try:
            for q, e in _get(url)['entities'].items():
                cache[f"lbl:{q}"] = e.get('labels', {}).get('en', {}).get('value')
        except Exception:
            for q in b:
                cache[f"lbl:{q}"] = None
        _tick(cache)
        time.sleep(0.1)
    return {q: cache.get(f"lbl:{q}") for q in qids if q}


def build(leg, lore, cache):
    from collections import Counter
    pts = [p for p in lore.get(leg, {}).get('lore', []) if str(p['id']).startswith('w')]
    pageids = [int(p['id'][1:]) for p in pts]
    cats = _categories(pageids, cache)
    qmap = _qids(pageids, cache)
    rc = _claims([q for q in qmap.values() if q], cache)
    targets = {r[k] for r in rc.values() for k in ('named_after', 'part_of') if r.get(k)}
    labels = _labels(list(targets), cache)
    nodes = {}
    for p in pts:
        pid = int(p['id'][1:])
        q = qmap.get(pid)
        r = rc.get(q, {}) if q else {}
        c = cats.get(pid, [])
        dates = set()
        for k in ('inception', 'dissolved', 'point_in_time'):
            if r.get(k):
                dates.add(r[k])
        for cc in c:
            dates.update(int(y) for y in _YEAR.findall(cc))
        dates.update(int(y) for y in _YEAR.findall(p.get('summary', '')))
        categories = [t for t in c if not _ADMIN_DROP.search(t)]
        nodes[p['id']] = {'title': p['title'], 'mi': p['peak_mi'], 'categories': categories[:8],
                          'named_after': labels.get(r.get('named_after')) if r.get('named_after') else None,
                          'part_of': labels.get(r.get('part_of')) if r.get('part_of') else None,
                          'dates': sorted(dates)}
    th = Counter(t for n in nodes.values() for t in n['categories'])
    return {'nodes': nodes, 'categories': [t for t, _ in th.most_common(30)]}


def main():
    only = sys.argv[1:]
    lore = json.loads(LORE.read_text())
    cp, cache = _cache()
    global _CP
    _CP = cp
    conn = json.loads(CONN.read_text()) if CONN.exists() else {}
    for leg in lore:
        if only and leg not in only:
            continue
        conn[leg] = build(leg, lore, cache)
        cp.write_text(json.dumps(cache))
        CONN.write_text(json.dumps(conn))
        print(f"  leg {leg}: {len(conn[leg]['nodes'])} nodes | top categories: "
              + ", ".join(conn[leg]['categories'][:5]))
    print(f"Wrote {CONN}")


if __name__ == '__main__':
    main()
