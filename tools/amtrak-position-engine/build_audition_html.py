#!/usr/bin/env python3
"""Assemble audition/*.md (structured @mi/@span sequences) into a readable HTML booklet."""
import html
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'audition'
SEGMENTS = [('raton', 'Raton heart (SW Chief, mi 1072–1100) — coal towns → Morley → Raton Pass → Raton'),
            ('desert', 'Sparse SE-Arizona desert (Sunset Ltd, mi 562–595) — interstitials must carry it'),
            ('glacier', 'Glacier / Marias Pass (Empire Builder, mi 1540–1600)'),
            ('chicago', 'Chicago departure (SW Chief, mi 0–55)')]
READERS = [('sonnet', 'Claude Sonnet'), ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
           ('opus', 'Claude Opus'), ('gpt-5.5', 'GPT-5.5')]

CSS = """body{font:20px/1.65 Georgia,serif;max-width:820px;margin:0 auto;padding:2rem;color:#1a1a1a;background:#faf8f5}
h1{font-size:2rem} h2{font-size:1.5rem;margin-top:3rem;border-bottom:2px solid #c9a86a;padding-bottom:.3rem}
h3{font:600 1.2rem -apple-system,sans-serif;color:#7a5c2e;margin-top:2.5rem}
.meta{font:13px -apple-system,sans-serif;color:#999}
.squib{border-left:4px solid #c9a86a;padding:.2rem 0 .2rem 1rem;margin:1.4rem 0}
.inter{background:#f1ece2;border-radius:8px;padding:.8rem 1.1rem;margin:1.4rem 0}
.hd{font:600 14px -apple-system,sans-serif;color:#7a5c2e;margin-bottom:.3rem}
.inter .hd{color:#5a6b3a} .sal{color:#b07a2a;font-weight:700}
nav{font:15px -apple-system,sans-serif;position:sticky;top:0;background:#faf8f5;padding:.5rem 0;border-bottom:1px solid #ddd}
nav a{margin-right:1rem;color:#7a5c2e}"""


def render(txt):
    blocks, cur = [], []
    for line in txt.splitlines():
        if line.startswith('@mi') or line.startswith('@span'):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        head, prose = b[0], html.escape("\n".join(b[1:]).strip())
        sal = (re.search(r's(\d)\b', head) or [None, '?'])[1]
        if head.startswith('@mi'):
            label = html.escape(head[3:].split('· s')[0].strip())
            out.append(f"<div class=squib><div class=hd>▸ MP {label} <span class=sal>★{sal}</span></div>{prose}</div>")
        else:
            label = html.escape(head[5:].split('· s')[0].strip())
            out.append(f"<div class=inter><div class=hd>↔ {label} <span class=sal>★{sal}</span> · interstitial</div>{prose}</div>")
    return "\n".join(out)


def main():
    present = [(s, r) for s, _ in SEGMENTS for r, _ in READERS if (OUT / f"{s}__{r}.md").exists()]
    segs = [(s, t) for s, t in SEGMENTS if any(s == ps for ps, _ in present)]
    parts = [f"<!doctype html><meta charset=utf-8><title>Narrator Audition — structured</title><style>{CSS}</style>",
             "<h1>Narrator Audition — structured shape</h1>",
             "<p class=meta>Milepost-triggered squibs (gold bar) + interstitial stories (shaded). ★ = salience. "
             "Same packet + timing budget per reader.</p>",
             "<nav>" + " ".join(f"<a href='#{s}'>{s}</a>" for s, _ in segs) + "</nav>"]
    for seg, title in segs:
        parts.append(f"<h2 id='{seg}'>{html.escape(title)}</h2>")
        for rid, rname in READERS:
            f = OUT / f"{seg}__{rid}.md"
            if not f.exists():
                continue
            txt = f.read_text().strip()
            nsq, nin = txt.count('\n@mi') + txt.startswith('@mi'), txt.count('\n@span') + txt.startswith('@span')
            parts.append(f"<h3>{rname} <span class=meta>· {len(txt.split())} words · "
                         f"{int(nsq)} squibs + {int(nin)} interstitials</span></h3>{render(txt)}")
    (OUT / 'audition-structured.html').write_text("\n".join(parts))
    print(f"  wrote {OUT / 'audition-structured.html'}")


if __name__ == '__main__':
    main()
