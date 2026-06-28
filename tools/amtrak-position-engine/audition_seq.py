#!/usr/bin/env python3
"""
Consecutive-segment comparison: generate a leg's adjacent segments WITH the L4 spine
+ spaced concept-ledger vs WITHOUT (plain L3), to see anti-repetition + theme coherence.
Writes packet files; Sonnet generation is dispatched via subagents by the controller.

  python3 audition_seq.py            # write with/without packets for the test segments
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narrate as N   # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'
OUT = Path(__file__).resolve().parent / 'audition'
OUT.mkdir(exist_ok=True)

# adjacent segments where the Cretaceous-seaway + ghost-town concepts recur (leg 3)
SEGS = [('seq1', '3', 1044.0, 1072.0), ('seq2', '3', 1072.0, 1100.0)]
TASK = ("\n\nWrite the milepost-triggered SEQUENCE (squibs + interstitial stories) in the marked "
        "@mi / @span format, honoring the timing budget, the style rules, and the memory/spine notes above.")


def spine_block(leg, lo, hi):
    t = json.loads((DATA / 'route_themes.json').read_text()).get(leg) if (DATA / 'route_themes.json').exists() else None
    if not t:
        return ""
    L = ["LEG SPINE (L4 — let these theses shape WHICH stories you choose and how you frame them; carry them "
         "implicitly, state a thesis openly at most rarely):",
         "  Overture: " + t.get('overture', '')]
    for th in t.get('theses', []):
        rng = th.get('strongest_mi', [0, 0])
        live = rng[0] - 60 <= lo <= rng[1] + 60
        L.append(f"  - {th.get('name')}{' [LIVE here]' if live else ''}: {th.get('thesis')}")
    mv = [m for m in t.get('movements', []) if lo <= m.get('mi', -1) <= hi]
    if mv:
        L.append("  MOVEMENT here (a step-back essay is earned): "
                 + "; ".join(f"mi {m['mi']} — {m.get('at')}: {m.get('why')}" for m in mv))
    return "\n".join(L)


def main():
    state = {}   # concept -> last-touched mile (data-derived; advances across segments)
    for tag, leg, lo, hi in SEGS:
        base = (N.macro_context(leg, lo) + "\n\n" + N.assemble(leg, lo, hi)
                + "\n\n" + N.connect_context(leg, lo, hi) + "\n\n" + N.timing_note(lo, hi))
        # WITHOUT: plain L3
        (OUT / f"{tag}__without__packet.txt").write_text(base + TASK)
        # WITH: spine + spaced memory brief (from running state)
        present = N.concepts_in_segment(leg, lo, hi)
        brief = N.memory_brief(present, state, lo)
        withp = base + "\n\n" + spine_block(leg, lo, hi) + ("\n\n" + brief if brief else "") + TASK
        (OUT / f"{tag}__with__packet.txt").write_text(withp)
        for c in present:
            state[c] = hi   # mark touched at segment end
        print(f"  {tag} ({lo:.0f}-{hi:.0f}): concepts={list(present)[:6]}")
        print(f"     brief: {brief[:200] or '(none — all new)'}")
    (OUT / "SYSTEM.txt").write_text(N.SYSTEM)
    print("  wrote with/without packets + SYSTEM.txt")


if __name__ == '__main__':
    main()
