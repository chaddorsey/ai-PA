#!/usr/bin/env python3
"""Assemble audition/*.md into one readable HTML booklet (audition/audition.html)."""
import html
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'audition'
SEGMENTS = [('raton', 'Raton Pass (SW Chief, mi 1050–1110) — dense history + deep-time geology'),
            ('desert', 'SE-Arizona desert (Sunset Ltd, mi 560–620) — sparse, thin-facts discipline'),
            ('glacier', 'Glacier / Marias Pass (Empire Builder, mi 1540–1600) — biome+geology+divide'),
            ('chicago', 'Chicago departure (SW Chief, mi 0–55) — restraint with urban abundance')]
READERS = [('opus', 'Claude Opus'), ('sonnet', 'Claude Sonnet'),
           ('gpt-5.4', 'GPT-5.4'), ('gpt-5.5', 'GPT-5.5'),
           ('gemini-2.5-pro', 'Gemini 2.5 Pro'), ('kimi-k2p6', 'Kimi 2.6')]

CSS = """body{font:20px/1.6 Georgia,serif;max-width:860px;margin:0 auto;padding:2rem;color:#1a1a1a;background:#faf8f5}
h1{font-size:2rem} h2{font-size:1.5rem;margin-top:3rem;border-bottom:2px solid #c9a86a;padding-bottom:.3rem}
h3{font-size:1.15rem;color:#7a5c2e;margin-top:2rem;font-family:-apple-system,sans-serif}
.meta{font:14px -apple-system,sans-serif;color:#888} .narr{white-space:pre-wrap}
nav{font:15px -apple-system,sans-serif;position:sticky;top:0;background:#faf8f5;padding:.5rem 0;border-bottom:1px solid #ddd}
nav a{margin-right:1rem;color:#7a5c2e}"""


def main():
    parts = [f"<!doctype html><meta charset=utf-8><title>Narrator Audition</title><style>{CSS}</style>",
             "<h1>Narrator Audition</h1>",
             "<p class=meta>Same packet (macro arc + facts + L3 connections) through every reader. "
             "Pick by voice; metrics (speed/cost/length) are in the chat.</p>",
             "<nav>" + " ".join(f"<a href='#{s}'>{s}</a>" for s, _ in SEGMENTS) + "</nav>"]
    for seg, title in SEGMENTS:
        parts.append(f"<h2 id='{seg}'>{html.escape(title)}</h2>")
        for rid, rname in READERS:
            f = OUT / f"{seg}__{rid}.md"
            if not f.exists():
                parts.append(f"<h3>{rname}</h3><p class=meta>(missing)</p>")
                continue
            txt = f.read_text().strip()
            wc = len(txt.split())
            parts.append(f"<h3>{rname} <span class=meta>· {wc} words</span></h3>"
                         f"<div class=narr>{html.escape(txt)}</div>")
    (OUT / 'audition.html').write_text("\n".join(parts))
    print(f"  wrote {OUT / 'audition.html'} ({sum((OUT/f'{s}__{r}.md').exists() for s,_ in SEGMENTS for r,_ in READERS)}/24 readers)")


if __name__ == '__main__':
    main()
