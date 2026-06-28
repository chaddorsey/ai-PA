#!/usr/bin/env python3
"""
Reader audition — same packet (macro arc + facts + L3 connections) through every
candidate narrator, side-by-side, with latency + token cost. Build-time only.

  python3 audition.py packets   # write the identical packet per segment (for subagents)
  python3 audition.py proxy     # generate with the proxy readers (gpt-5.4/5.5, gemini-2.5-pro, kimi-k2p6)

Anthropic readers (Opus/Sonnet) are generated via Claude subagents (proxy credits
exhausted) using the packet files this writes. Outputs land in audition/.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narrate as N   # noqa: E402

DIR = Path(__file__).resolve().parent
OUT = DIR / 'audition'
OUT.mkdir(exist_ok=True)

SEGMENTS = {
    'raton':   ('3', 1050.0, 1110.0),    # dense history + deep-time geology
    'desert':  ('2', 560.0, 620.0),      # sparse SE-Arizona desert (thin-facts discipline)
    'glacier': ('27', 1540.0, 1600.0),   # Marias Pass / Glacier — biome+geology+divide turning
    'chicago': ('3', 0.0, 55.0),         # urban departure (restraint with abundance)
}
PROXY_MODELS = ['gpt-5.4', 'gpt-5.5', 'gemini-2.5-pro', 'kimi-k2p6']
TASK = ("\n\nWrite the continuous narration for this segment, weaving the near stories into the "
        "large arc AND the connective chains (cross-layer, recurring threads, contemporaneity).")


def packet(leg, lo, hi):
    return (N.macro_context(leg, lo) + "\n\n" + N.assemble(leg, lo, hi)
            + "\n\n" + N.connect_context(leg, lo, hi) + TASK)


NO_TEMP = {'gpt-5.5'}   # models that reject temperature != default(1)


def call(model, system, user):
    base = (N._env('LITELLM_BASE_URL') or 'http://localhost:4000').rstrip('/')
    key = N._env('LITELLM_MASTER_KEY') or ''
    payload = {'model': model,
               'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
    if model not in NO_TEMP:
        payload['temperature'] = 0.7
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + '/v1/chat/completions', data=body,
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    dt = time.perf_counter() - t0
    return d['choices'][0]['message']['content'], dt, d.get('usage', {})


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'packets'
    if mode == 'packets':
        for seg, (leg, lo, hi) in SEGMENTS.items():
            (OUT / f"{seg}__packet.txt").write_text(packet(leg, lo, hi))
            print(f"  wrote {seg}__packet.txt")
        (OUT / "SYSTEM.txt").write_text(N.SYSTEM)
        print("  wrote SYSTEM.txt")
        return
    only_model = sys.argv[2] if len(sys.argv) > 2 else None
    models = [only_model] if only_model else PROXY_MODELS
    rows = []
    for seg, (leg, lo, hi) in SEGMENTS.items():
        user = (OUT / f"{seg}__packet.txt").read_text() if (OUT / f"{seg}__packet.txt").exists() else packet(leg, lo, hi)
        for m in models:
            try:
                txt, dt, u = call(m, N.SYSTEM, user)
                (OUT / f"{seg}__{m}.md").write_text(txt)
                rows.append((seg, m, round(dt), u.get('completion_tokens', '?'), len(txt.split())))
                print(f"  {seg} / {m}: {round(dt)}s, {u.get('completion_tokens', '?')} out-tok, {len(txt.split())} words")
            except Exception as e:
                print(f"  {seg} / {m}: ERROR {str(e)[:100]}")
    print("\n=== PROXY METRICS (seg | model | sec | out_tok | words) ===")
    for r in rows:
        print("  " + " | ".join(map(str, r)))


if __name__ == '__main__':
    main()
