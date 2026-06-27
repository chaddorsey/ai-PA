#!/usr/bin/env python3
"""
F.2 POC — narration layer. Assembles the facts near a segment (lore points +
county demographics/land + terrain) and has an LLM weave them into a spoken-style
narration you'd hear looking out the window.

  python3 narrate.py 3 1050 1110            # narrate leg 3, mileposts 1050-1110
  python3 narrate.py 3 1050 1110 claude-opus-4-6   # pick a model

Build-time + network (hub LiteLLM at LITELLM_BASE_URL). Facts come from the
offline route_guide.json + route_lore.json; the narration is a transform over them.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_guide as RG   # noqa: E402

DIR = Path(__file__).resolve().parent
MODEL = 'gpt-4.1'  # Anthropic credits on the proxy are exhausted; gpt-4.1 is the strong non-Anthropic narrator


def _env(key):
    p = DIR
    for _ in range(5):
        f = p / '.env'
        if f.exists():
            for line in f.read_text().splitlines():
                if line.startswith(key + '='):
                    return line.split('=', 1)[1].strip()
        p = p.parent
    return os.environ.get(key)


def llm(system, user, model=MODEL, temperature=0.7):
    base = (_env('LITELLM_BASE_URL') or 'http://localhost:4000').rstrip('/')
    key = _env('LITELLM_MASTER_KEY') or ''
    body = json.dumps({'model': model, 'temperature': temperature,
                       'messages': [{'role': 'system', 'content': system},
                                    {'role': 'user', 'content': user}]}).encode()
    req = urllib.request.Request(base + '/v1/chat/completions', data=body,
                                 headers={'Authorization': 'Bearer ' + key,
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)['choices'][0]['message']['content']


LOOK_MI = 150.0   # lookahead/lookback horizon ~2-3 hrs


def load_science():
    f = DIR / 'data' / 'route_science.json'
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except Exception:
        return {}


def _at(prof, mile):
    v = None
    for m, x in prof:
        if m <= mile:
            v = x
        else:
            break
    return v


def _dominant(prof, lo, hi):
    from collections import Counter
    c = Counter(x for m, x in prof if lo <= m <= hi and x)
    return c.most_common(1)[0][0] if c else None


def _next_change(prof, mile, hi, key):
    cur = _at(prof, mile)
    cur_k = key(cur) if cur else None
    for m, x in prof:
        if m <= mile or m > hi:
            continue
        if x and key(x) != cur_k:
            return (m, x)
    return None


def macro_context(leg, mile):
    """The unfolding-country arc: current scientific setting + what's trending/coming
    over the next ~2-3 hrs + contrast with behind. Computed from the science + guide profiles."""
    g = RG.load_guide().get(leg, {})
    s = load_science().get(leg, {})
    hi = mile + LOOK_MI
    geo, eco, hyd = s.get('geology', []), s.get('ecoregion', []), s.get('hydrology', [])
    elev, lc = g.get('elevation_ft', []), g.get('landcover', [])
    areas = sorted([f for f in g.get('features', []) if f.get('class') == 'area'], key=lambda f: f['from_mi'])

    def state_at(m):
        for f in areas:
            if f['from_mi'] <= m <= f['to_mi']:
                return (f.get('stats', {}).get('geo', '').split(',')[-1].strip() or None)
        return None

    cg, ce, ch = _at(geo, mile), _at(eco, mile), _at(hyd, mile)
    cur_elev = _at(elev, mile)
    cur_lc = _dominant(lc, mile - 20, mile + 5)
    cur_state = state_at(mile)
    L = ["MACRO ARC (large gradients — weave these through; this is the unfolding country):"]
    now = []
    if ce:
        now.append(f"ecoregion {ce['l3']} ({ce['l4']})")
    if ch:
        now.append(f"{ch['region_name']} watershed")
    if cg:
        now.append(f"bedrock {cg['unit']} ({cg['period']}, {cg['b_age']}-{cg['t_age']} Ma; {cg['lith']})")
    if cur_elev is not None:
        now.append(f"~{cur_elev:,} ft")
    if cur_lc:
        now.append(f"land mostly {cur_lc}")
    L.append("- NOW: " + "; ".join(now))
    ahead = []
    if elev and cur_elev is not None:
        e_hi = _at(elev, hi)
        if e_hi is not None:
            d = e_hi - cur_elev
            win = [ft for m, ft in elev if mile < m <= hi] or [cur_elev]
            verb = 'climbs' if d > 200 else 'drops' if d < -200 else 'holds steady'
            ahead.append(f"elevation {verb} ~{abs(d):,} ft over the next {LOOK_MI:.0f} mi (high point ~{max(win):,} ft)")
    al = _dominant(lc, mile + 30, hi)
    if al and al != cur_lc:
        ahead.append(f"land shifts from {cur_lc} toward {al}")
    ne = _next_change(eco, mile, hi, key=lambda v: v.get('l3'))
    if ne:
        ahead.append(f"enter the {ne[1]['l3']} ecoregion ~mi {ne[0]:.0f}")
    ng = _next_change(geo, mile, hi, key=lambda v: v.get('period'))
    if ng:
        ahead.append(f"bedrock turns to {ng[1]['period']} (~{ng[1]['b_age']} Ma) ~mi {ng[0]:.0f}")
    nh = _next_change(hyd, mile, hi, key=lambda v: v.get('region'))
    if nh:
        ahead.append(f"cross into the {nh[1]['region_name']} watershed (a divide) ~mi {nh[0]:.0f}")
    for f in areas:
        if mile < f['from_mi'] <= hi:
            st = f.get('stats', {}).get('geo', '').split(',')[-1].strip()
            if st and st != cur_state:
                ahead.append(f"cross into {st} ~mi {f['from_mi']:.0f}")
                break
    if ahead:
        L.append("- NEXT 2-3 HRS: " + "; ".join(ahead))
    behind = []
    pe = _at(eco, max(0, mile - LOOK_MI))
    pl = _dominant(lc, mile - LOOK_MI, mile - 20)
    if pe and ce and pe.get('l3') != ce.get('l3'):
        behind.append(f"left the {pe['l3']} behind")
    if pl and pl != cur_lc:
        behind.append(f"the land was {pl}")
    if behind:
        L.append("- BEHIND: " + "; ".join(behind))
    return "\n".join(L)


def assemble(leg, lo, hi):
    guide, lore = RG.load_guide(), RG.load_lore()
    feats = RG.features_for(guide, leg)
    cnotes = lore.get(leg, {}).get('counties', {})
    L = [f"SEGMENT: leg {leg}, mileposts {lo:.0f}-{hi:.0f} (~{hi - lo:.0f} miles, traveling in order of increasing milepost)."]

    stations = [f for f in feats if f.get('kind') == 'station' and lo <= f['peak_mi'] <= hi]
    if stations:
        L.append("STATION STOPS: " + ", ".join(f"{s['name']} (mi {s['peak_mi']:.0f})" for s in stations))

    for c in [f for f in feats if f.get('class') == 'area' and not (f['to_mi'] < lo or f['from_mi'] > hi)]:
        s = c.get('stats', {})
        bits = []
        if s.get('population'):
            bits.append(f"pop ~{s['population']:,}")
        if s.get('median_hh_income'):
            bits.append(f"median income ${s['median_hh_income']:,}")
        if s.get('poverty_pct'):
            bits.append(f"poverty {s['poverty_pct']}%")
        if s.get('top_industries'):
            bits.append("industries: " + ", ".join(s['top_industries'][:2]))
        if s.get('top_crops'):
            bits.append("crops: " + ", ".join(s['top_crops']))
        if s.get('land_cover'):
            bits.append("land cover: " + ", ".join(f"{int(v * 100)}% {k}" for k, v in list(s['land_cover'].items())[:2]))
        L.append(f"AREA: {c['name']} (mi {c['from_mi']:.0f}-{c['to_mi']:.0f})" + (" — " + "; ".join(bits) if bits else ""))
        note = cnotes.get(c['id'], {})
        if note.get('summary'):
            L.append(f"  about {note['title']}: {note['summary'][:320]}")

    terrain = [f for f in feats if (f.get('class') in ('region', 'scenic', 'water')
               or f.get('kind') in ('summit', 'pass', 'tunnel', 'bridge'))
               and not (f.get('to_mi', f['peak_mi']) < lo or f.get('from_mi', f['peak_mi']) > hi)]
    if terrain:
        L.append("TERRAIN & SCENERY:")
        for t in terrain:
            L.append(f"  {t['name']} ({t.get('kind') or t.get('class')}, near mi {t['peak_mi']:.0f})")

    sci = load_science().get(leg, {})
    geo = [(m, v) for m, v in sci.get('geology', []) if lo <= m <= hi]
    if geo:
        L.append("GEOLOGY along segment (bedrock, in passing order):")
        last = None
        for m, v in geo:
            if v['unit'] != last:
                L.append(f"  mi {m:.0f}: {v['unit']} — {v['period']}, {v['b_age']}-{v['t_age']} Ma; {v['lith']}"
                         + (f" ({v['descrip']})" if v.get('descrip') else ""))
                last = v['unit']
    fos, seen = [], set()
    for m, v in sci.get('fossils', []):
        if lo <= m <= hi and v:
            for x in v[:3]:
                if x['taxon'] not in seen:
                    seen.add(x['taxon'])
                    fos.append(f"{x['taxon']} (~{x['ma']} Ma)")
    if fos:
        L.append("FOSSILS found near this stretch: " + ", ".join(fos[:10]))

    lps = [p for p in lore.get(leg, {}).get('lore', []) if lo <= p['peak_mi'] <= hi]
    L.append("POINTS OF INTEREST (in passing order; side = which window):")
    for p in lps:
        L.append(f"  mi {p['peak_mi']:.0f} [{p['side']}] {p['title']}: {p['summary'][:260]}")
    return "\n".join(L)


SYSTEM = """You are the narrator of a long-distance American train journey — a warm, literate, deeply knowledgeable companion who is at once a geologist, an ecologist, a historian, and a keen observer of how people live. The passenger is gazing out the window as the train rolls on for hours. Narrate what's passing NEARLY CONTINUOUSLY, so there is almost always something to listen to.

Work at TWO scales at once:
- THE NEAR: the towns, ghost towns, landforms, rivers, fossils, and rock right outside — the specific stories, cued to the window (left/right) in passing order.
- THE LARGE: the slow gradients from the MACRO ARC — the deep-time geology and the mountain-building that shaped this land, the shift of biomes and climate, the rise and fall of terrain, the change of watersheds and states. FORESHADOW what's coming over the next 2-3 hours and CONTRAST it with what came before ("over the next two hours the prairie buckles up into the Front Range…"; "we've left the humid East behind — from here the rain thins and the grass shortens…").

Weave the near stories inside the large unfolding — that dual focus, granular and grand at once, is the gift of a long train.

Guidelines:
- Ground claims in the facts. You MAY add brief, well-known context — an orogeny's name, what a rock type or lithology means, a biome's character, a fossil's world — to enrich and explain, but never invent specific names, dates, or events the facts don't support.
- Be the geologist for deep time: tell the story of the rock — when and in what sea or rising range it formed, what it became — using the formations and ages given. Make 60 million years and 1.6 billion years feel real.
- Move in passing order (increasing milepost); cue the window. Past tense for history and deep time; present for what's out there now.
- Vivid but economical — dense with substance, not words. No filler, no brochure gush.
- This is the denser, nearly-continuous mode: cover the segment thoroughly in several rich paragraphs.
Return only the narration prose."""


def main():
    leg, lo, hi = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    model = sys.argv[4] if len(sys.argv) > 4 else MODEL
    macro = macro_context(leg, lo)
    facts = assemble(leg, lo, hi)
    print("===== MACRO ARC =====")
    print(macro)
    print("\n===== FACTS PACKET =====")
    print(facts)
    user = (macro + "\n\n" + facts
            + "\n\nWrite the continuous narration for this segment, weaving the near stories into the large arc.")
    print("\n===== NARRATION (" + model + ") =====")
    print(llm(SYSTEM, user, model))


if __name__ == '__main__':
    main()
