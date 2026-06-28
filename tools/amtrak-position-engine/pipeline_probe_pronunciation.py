#!/usr/bin/env python3
"""Coverage probe: how many of the route's proper nouns can we auto-source IPA for
(Wikipedia by exact pageid, Wiktionary by name), and how big is the human-review tail?
Sizing only — not the production pipeline."""
import json, re, urllib.request, urllib.parse, random
from pathlib import Path
DIR = Path(__file__).resolve().parent
random.seed(42)
UA = {'User-Agent': 'amtrak-companion-pronunciation-probe/0.1 (cdorsey@concord.org)'}

def get(url):
    try:
        r = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(r, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception:
        return None

def wikitext_by_pageid(pid):
    d = get(f'https://en.wikipedia.org/w/api.php?action=parse&pageid={pid}&prop=wikitext&format=json')
    try: return d['parse']['wikitext']['*']
    except Exception: return None

def wiktionary_wikitext(term):
    d = get(f'https://en.wiktionary.org/w/api.php?action=parse&page={urllib.parse.quote(term)}&prop=wikitext&format=json')
    try: return d['parse']['wikitext']['*']
    except Exception: return None

WP_IPA = re.compile(r'\{\{IPAc?-?en|\{\{IPA\b|\{\{respell', re.I)
WT_IPA = re.compile(r'\{\{IPA\|en', re.I)

# ---- 1. enumerate unique proper nouns ----
narr = json.loads((DIR/'data/route_narration.json').read_text())
lore = json.loads((DIR/'data/route_lore.json').read_text())
conn = json.loads((DIR/'data/route_connections.json').read_text())

def core(title):
    return title.split(',')[0].split(' (')[0].strip()

names = {}  # core_name -> {pageid, kind, full}
for leg, d in lore.items():
    for poi in d.get('lore', []):
        c = core(poi['title']); pid = poi['id'][1:] if str(poi.get('id','')).startswith('w') else None
        e = names.setdefault(c, {'pageid': None, 'kind': 'place', 'full': poi['title']})
        if pid and not e['pageid']: e['pageid'] = pid
for leg, d in conn.items():
    for nid, node in d.get('nodes', {}).items():
        c = core(node.get('title',''));
        if c: names.setdefault(c, {'pageid': None, 'kind':'place', 'full': node['title']})
        na = node.get('named_after')
        if na: names.setdefault(core(na), {'pageid': None, 'kind':'person', 'full': na})
for leg, units in narr.items():
    for u in units:
        p = u.get('place')
        if p: names.setdefault(core(p), {'pageid': None, 'kind':'place', 'full': p})

# ---- 2. spoken frequency (occurrences across all unit text) ----
blob = ' '.join(u['text'] for units in narr.values() for u in units)
for c, e in names.items():
    e['freq'] = blob.count(c)

uniq = [c for c in names if len(c) > 2]   # drop 1-2 char noise
withpid = [c for c in uniq if names[c]['pageid']]
spoken = [c for c in uniq if names[c]['freq'] > 0]
print(f"  UNIQUE proper nouns: {len(uniq)}")
print(f"   with Wikipedia pageid (lore POIs): {len(withpid)}")
print(f"   actually spoken (appear in unit text): {len(spoken)}")
print(f"   persons (named_after): {sum(1 for c in uniq if names[c]['kind']=='person')}")

# ---- 3. Wikipedia IPA coverage on a sample of pageid-bearing names ----
sample_wp = sorted(withpid, key=lambda c: -names[c]['freq'])[:60] + random.sample(withpid, min(60, len(withpid)))
sample_wp = list(dict.fromkeys(sample_wp))
wp_hit = wp_n = 0
for c in sample_wp:
    wt = wikitext_by_pageid(names[c]['pageid'])
    if wt is None: continue
    wp_n += 1; wp_hit += 1 if WP_IPA.search(wt) else 0
print(f"\n  WIKIPEDIA IPA coverage: {wp_hit}/{wp_n} sampled = {100*wp_hit/max(wp_n,1):.0f}%  -> est ~{int(len(withpid)*wp_hit/max(wp_n,1))} of {len(withpid)} POIs")

# ---- 4. Wiktionary IPA coverage on a sample of bare names ----
sample_wt = random.sample(spoken, min(60, len(spoken)))
wt_hit = wt_n = 0
for c in sample_wt:
    wt = wiktionary_wikitext(c)
    if wt is None: continue
    wt_n += 1; wt_hit += 1 if WT_IPA.search(wt) else 0
print(f"  WIKTIONARY IPA coverage: {wt_hit}/{wt_n} sampled = {100*wt_hit/max(wt_n,1):.0f}%")

# ---- 5. review-burden estimate + top high-freq names preview ----
wp_rate = wp_hit/max(wp_n,1)
auto_est = int(len(withpid)*wp_rate)
review_est = len(spoken) - auto_est
print(f"\n  ESTIMATE: ~{auto_est} auto-sourced via Wikipedia IPA; ~{max(review_est,0)} spoken names need Wiktionary/CMUdict/G2P + review")
print("  top-20 most-spoken proper nouns (review priority preview):")
for c in sorted(spoken, key=lambda c: -names[c]['freq'])[:20]:
    print(f"    {names[c]['freq']:4d}x  {c}  (pageid={'Y' if names[c]['pageid'] else 'n'}, {names[c]['kind']})")
