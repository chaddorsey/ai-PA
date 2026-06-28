#!/usr/bin/env python3
"""
L4 thematic spine. Scans a COMPACT per-leg fingerprint (aggregated L3 categories,
geology/ecoregion/watershed sequences, elevation arc, date spread, marquee POIs) —
never the prose — and synthesizes the crosscutting theses that knit the whole leg
together, plus a few 'movement' inflection points for occasional step-back essays.

Output → data/route_themes.json. Build-time; one cheap LLM pass per leg.
  python3 themes.py [leg ...] [--model M]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narrate as N   # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
THEMES = DATA / 'route_themes.json'
MODEL = 'gemini-2.5-pro'   # analytical synthesis (not the narration voice) — proxy is fine


def _distinct(seq, key):
    out, last = [], object()
    for m, v in seq:
        if not v:
            continue
        k = key(v)
        if k != last:
            out.append((round(m), k))
            last = k
    return out


def fingerprint(leg):
    conn = json.loads((DATA / 'route_connections.json').read_text()).get(leg, {})
    sci = json.loads((DATA / 'route_science.json').read_text()).get(leg, {})
    g = json.loads((DATA / 'route_guide.json').read_text()).get(leg, {})
    cats = conn.get('categories', [])[:30]
    geo = _distinct(sci.get('geology', []), lambda v: f"{v.get('unit')} ({v.get('period')}, {v.get('lith')})")
    eco = _distinct(sci.get('ecoregion', []), lambda v: v.get('l3'))
    hyd = _distinct(sci.get('hydrology', []), lambda v: v.get('region_name'))
    elev = [ft for _, ft in g.get('elevation_ft', [])]
    elarc = f"{elev[0]:,}→ low {min(elev):,} / high {max(elev):,} →{elev[-1]:,} ft" if elev else "?"
    nodes = list(conn.get('nodes', {}).values())
    dates = sorted(d for n in nodes for d in n.get('dates', []))
    poi = sorted(nodes, key=lambda n: -len(n.get('categories', [])))[:15]
    L = [f"LEG {leg} — fingerprint (~{g.get('leg_miles', 0):.0f} mi).",
         "RECURRING CATEGORIES: " + "; ".join(cats),
         "GEOLOGY in order: " + " → ".join(f"mi{m} {k}" for m, k in geo[:18]),
         "ECOREGIONS in order: " + " → ".join(f"mi{m} {k}" for m, k in eco),
         "WATERSHEDS/divides in order: " + " → ".join(f"mi{m} {k}" for m, k in hyd),
         "ELEVATION arc: " + elarc,
         "DATE spread: " + (f"{dates[0]}–{dates[-1]} (n={len(dates)})" if dates else "—"),
         "MARQUEE POIs: " + "; ".join(f"{n['title']} [{', '.join(n.get('categories', [])[:2])}]" for n in poi)]
    return "\n".join(L)


SYSTEM = """You are a documentary story editor planning a long train leg. From the compact FINGERPRINT of an entire leg (categories, geology/ecoregion/watershed sequences, elevation, dates, marquee places — NOT prose), identify the crosscutting THESES that knit the whole leg into one story, and a few inflection points where a step-back 'movement' essay would be earned.

Return STRICT JSON only:
{
  "overture": "<one or two sentences: what this whole leg is fundamentally about>",
  "theses": [
    {"name": "<short handle>", "thesis": "<one sentence>", "anchored_in": ["<category/place/feature>", ...], "strongest_mi": [<lo>, <hi>]}
  ],
  "movements": [
    {"mi": <milepost>, "at": "<the inflection — a divide, state line, biome threshold>", "why": "<the step-back worth taking here>"}
  ]
}
3–5 theses. 2–4 movements, only at genuinely earned inflections. Theses must be specific to THIS leg's evidence, not generic ('the West is big'). Return only the JSON."""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    model = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--model=')), MODEL)
    legs = args or list(json.loads((DATA / 'route_connections.json').read_text()).keys())
    out = json.loads(THEMES.read_text()) if THEMES.exists() else {}
    for leg in legs:
        fp = fingerprint(leg)
        raw = N.llm(SYSTEM, fp, model)
        txt = raw.strip()
        if txt.startswith('```'):
            txt = txt.split('```')[1].lstrip('json').strip()
        try:
            out[leg] = json.loads(txt)
            THEMES.write_text(json.dumps(out, indent=2))
            print(f"  leg {leg}: {len(out[leg].get('theses', []))} theses, {len(out[leg].get('movements', []))} movements")
            print("    overture:", out[leg].get('overture', '')[:160])
            for t in out[leg].get('theses', []):
                print(f"    · {t.get('name')}: {t.get('thesis','')[:120]}")
        except Exception as e:
            print(f"  leg {leg}: JSON parse failed ({e}); raw head: {txt[:160]}")
    print(f"Wrote {THEMES}")


if __name__ == '__main__':
    main()
