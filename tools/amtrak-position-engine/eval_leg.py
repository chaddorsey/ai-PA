#!/usr/bin/env python3
"""
Scorecard for a generated leg (audition/leg<leg>/seg_*.md). Objective checks to
keep the full run on track: coverage, fill vs budget, concept-repetition cadence,
structure/voice lint, salience + theme balance.

  python3 eval_leg.py <leg>
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narrate as N   # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
OUT = Path(__file__).resolve().parent / 'audition'
FORBIDDEN = ('tapestry', 'testament', 'delve', 'beacon', 'hub', 'furthermore', 'moreover')
# big spanning concepts whose FULL re-explanation we want to be rare (intro + occasional refresh)
REPEAT_PROBES = {'inland sea/seabed': r'inland sea|shallow sea|seabed|western interior',
                 'ghost town (explain)': r'ghost town',
                 'Santa Fe Railway': r'santa fe railway|atchison',
                 'Laramide/uplift': r'laramide|rising rockies|uplift'}


def main():
    leg = sys.argv[1]
    legdir = OUT / f"leg{leg}"
    files = sorted(legdir.glob('seg_*.md'), key=lambda p: int(p.stem.split('_')[1]))
    if not files:
        print(f"  no segments in {legdir}")
        return
    units, sal, themes, fill_flags, lint = [], Counter(), Counter(), [], []
    full_text = ""
    for f in files:
        lo, hi = (int(x) for x in f.stem.split('_')[1:3])
        txt = f.read_text()
        full_text += "\n" + txt.lower()
        words = len(txt.split())
        budget = int((hi - lo) / N.AVG_MPH * 60 * N.FILL * N.TTS_WPM)
        if words > budget * 1.15:
            fill_flags.append(f"{lo}-{hi}: {words}w > budget {budget}w")
        for m in re.finditer(r'^@(mi|span)\b(.*)', txt, flags=re.M):
            kind, head = m.group(1), m.group(2)
            s = re.search(r's([1-5])\b', head)
            t = re.search(r't:\s*([^\n·]+)', head)
            units.append((kind, f.stem))
            if s:
                sal[s.group(1)] += 1
            else:
                lint.append(f"{f.stem}: unit missing salience")
            if t:
                themes[t.group(1).strip()[:24]] += 1
            else:
                lint.append(f"{f.stem}: unit missing theme tag")
    squibs = sum(1 for k, _ in units if k == 'mi')
    inter = sum(1 for k, _ in units if k == 'span')
    # POI coverage: each lore point near a squib?
    lore = json.loads((DATA / 'route_lore.json').read_text()).get(leg, {}).get('lore', [])
    sq_miles = []
    for f in files:
        for m in re.finditer(r'^@mi\s+(\d+)', f.read_text(), flags=re.M):
            sq_miles.append(int(m.group(1)))
    covered = sum(1 for p in lore if any(abs(p['peak_mi'] - sm) <= 3 for sm in sq_miles))
    # voice (we not you): count 2nd-person address
    you = len(re.findall(r'\byou\b|\byour\b', full_text))
    forb = {w: full_text.count(w) for w in FORBIDDEN if w in full_text}

    print(f"=== leg {leg} scorecard ({len(files)} segments) ===")
    print(f"  units: {len(units)} ({squibs} squibs + {inter} interstitials)")
    print(f"  POI coverage: {covered}/{len(lore)} lore points have a squib within 3 mi")
    print(f"  fill over-budget segments: {len(fill_flags)}" + (" — " + "; ".join(fill_flags[:4]) if fill_flags else ""))
    print(f"  salience spread: " + ", ".join(f"★{k}:{sal[k]}" for k in '54321'))
    print(f"  theme tags (top): " + ", ".join(f"{t}={c}" for t, c in themes.most_common(6)))
    print("  CONCEPT REPETITION (segments containing each — want a few, not most):")
    for name, pat in REPEAT_PROBES.items():
        n = sum(1 for f in files if re.search(pat, f.read_text(), re.I))
        print(f"    {name}: {n}/{len(files)} segments")
    print(f"  VOICE: 'you/your' occurrences (want ~0): {you}")
    print(f"  forbidden words: {forb or 'none'}")
    print(f"  lint issues: {len(lint)}" + (" — e.g. " + lint[0] if lint else ""))


if __name__ == '__main__':
    main()
