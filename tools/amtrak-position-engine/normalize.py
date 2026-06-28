#!/usr/bin/env python3
"""Mechanical cleanup of generated leg segments: strip forbidden words (case-preserving)
and canonicalize theme tags to the spine's exact handles. Cheap; no regeneration."""
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'audition'
DATA = Path(__file__).resolve().parent / 'data'
# forbidden -> replacement (whole-word, case-insensitive, case-preserving)
FORBID = {'tapestries': 'weaves', 'tapestry': 'weave', 'delves': 'digs', 'delve': 'dig',
          'beacons': 'landmarks', 'beacon': 'landmark', 'hubs': 'junctions', 'hub': 'junction',
          'testaments': 'hallmarks', 'testament': 'hallmark', 'furthermore': 'still', 'moreover': 'still'}
themes = json.loads((DATA / 'route_themes.json').read_text())


def case_repl(repl):
    def f(m):
        w = m.group(0)
        return repl.capitalize() if w[0].isupper() else repl
    return f


def main():
    changed = 0
    for legdir in sorted(OUT.glob('leg*')):
        leg = legdir.name[3:]
        names = [t['name'] for t in themes.get(leg, {}).get('theses', [])]
        for f in sorted(legdir.glob('seg_*.md')):
            s = orig = f.read_text()
            s = re.sub(r'\btestament to\b', 'hallmark of', s, flags=re.I)
            for w, repl in FORBID.items():
                s = re.sub(r'\b' + w + r'\b', case_repl(repl), s, flags=re.I)

            def norm(m):
                tag = m.group(1).strip()
                base = tag.lower().removeprefix('the ').strip()
                for nm in names:
                    if base == nm.lower().removeprefix('the ').strip():
                        return 't:' + nm
                return m.group(0)
            s = re.sub(r't:\s*([^\n·]+)', norm, s)
            if s != orig:
                f.write_text(s)
                changed += 1
    print(f"  normalized {changed} segment files")


if __name__ == '__main__':
    main()
