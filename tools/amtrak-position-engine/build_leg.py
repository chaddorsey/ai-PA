#!/usr/bin/env python3
"""
Precompute every segment packet for a full leg — macro arc + facts + L3 connections
+ timing budget + L4 spine + the spaced concept-ledger (state advanced across the leg,
data-derived so no model dependency → segments can generate in parallel).

  python3 build_leg.py <leg> [seg_mi]

Writes audition/leg<leg>/seg_<lo>_<hi>.txt + SYSTEM.txt; generation is a fan-out over them.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narrate as N          # noqa: E402
import audition_seq as A     # noqa: E402  (spine_block, TASK)

DATA = Path(__file__).resolve().parent / 'data'
OUT = Path(__file__).resolve().parent / 'audition'
SEG_MI = 40.0


def main():
    leg = sys.argv[1]
    seg_mi = float(sys.argv[2]) if len(sys.argv) > 2 else SEG_MI
    legmi = json.loads((DATA / 'route_guide.json').read_text())[leg]['leg_miles']
    outdir = OUT / f"leg{leg}"
    outdir.mkdir(parents=True, exist_ok=True)
    state, segs, lo = {}, [], 0.0
    while lo < legmi - 1:
        hi = min(lo + seg_mi, legmi)
        base = (N.macro_context(leg, lo) + "\n\n" + N.assemble(leg, lo, hi)
                + "\n\n" + N.connect_context(leg, lo, hi) + "\n\n" + N.timing_note(lo, hi))
        present = N.concepts_in_segment(leg, lo, hi)
        brief = N.memory_brief(present, state, lo)
        pkt = base + "\n\n" + A.spine_block(leg, lo, hi) + ("\n\n" + brief if brief else "") + A.TASK
        (outdir / f"seg_{int(lo)}_{int(hi)}.txt").write_text(pkt)
        for c in present:
            state[c] = hi
        segs.append((int(lo), int(hi)))
        lo = hi
    (outdir / "SYSTEM.txt").write_text(N.SYSTEM)
    tot = int(legmi / seg_mi * 60 / N.AVG_MPH * 60 * N.FILL * N.TTS_WPM)
    print(f"  leg {leg}: {len(segs)} segments of ~{seg_mi:.0f} mi → {outdir}")
    print(f"  full-leg talking target ≈ {tot:,} words (~{int(legmi/N.AVG_MPH*60*N.FILL)} min at 60% fill)")


if __name__ == '__main__':
    main()
