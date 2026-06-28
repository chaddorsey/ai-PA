#!/usr/bin/env python3
"""Minimal Markdown → styled HTML for readable review docs (headers, bold, code,
fenced code, tables, lists, blockquote, hr, links). Stdlib only.

  python3 scripts/md2html.py <in.md> <out.html> ["Title"]
"""
import html
import re
import sys
from pathlib import Path

CSS = """body{font:21px/1.7 Georgia,'Iowan Old Style',serif;max-width:880px;margin:0 auto;padding:2.5rem 1.4rem;color:#1c1c1c;background:#faf8f5}
h1{font-size:2.2rem;line-height:1.2;border-bottom:3px solid #c9a86a;padding-bottom:.4rem}
h2{font-size:1.6rem;margin-top:2.6rem;color:#5a3e16;border-bottom:1px solid #e0d3b8;padding-bottom:.2rem}
h3{font-size:1.25rem;margin-top:1.8rem;color:#7a5c2e} h4{font-size:1.08rem;color:#7a5c2e}
code{font:0.9em ui-monospace,Menlo,monospace;background:#efe9dd;padding:.08em .35em;border-radius:4px}
pre{background:#f1ece2;padding:1rem;border-radius:8px;overflow-x:auto;font-size:.85rem;line-height:1.45}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:1.2rem 0;font-size:.92em}
th,td{border:1px solid #d8cab0;padding:.5rem .7rem;text-align:left;vertical-align:top} th{background:#efe6d4}
blockquote{border-left:4px solid #c9a86a;margin:1rem 0;padding:.3rem 1rem;color:#444;background:#f4efe6}
strong{color:#3a2e1a} a{color:#7a5c2e} hr{border:none;border-top:1px solid #ddd;margin:2rem 0}
ul,ol{padding-left:1.5rem} li{margin:.3rem 0}"""


def _inline(t):
    t = html.escape(t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    return t


def to_html(text, title):
    src = text.split('\n')
    H, i, n = [], 0, len(src)
    cell = lambda c: _inline(c.strip())
    while i < n:
        L = src[i]
        if L.strip().startswith('```'):
            i += 1
            buf = []
            while i < n and not src[i].strip().startswith('```'):
                buf.append(html.escape(src[i]))
                i += 1
            i += 1
            H.append('<pre><code>' + '\n'.join(buf) + '</code></pre>')
            continue
        if re.match(r'^\s*\|', L):
            rows = []
            while i < n and re.match(r'^\s*\|', src[i]):
                rows.append(src[i])
                i += 1
            cells = [[c for c in r.strip().strip('|').split('|')] for r in rows]
            body = cells[2:] if len(cells) > 1 and set(''.join(cells[1]).strip()) <= set('-: ') else cells[1:]
            H.append('<table><thead><tr>' + ''.join(f'<th>{cell(c)}</th>' for c in cells[0]) + '</tr></thead><tbody>')
            for r in body:
                H.append('<tr>' + ''.join(f'<td>{cell(c)}</td>' for c in r) + '</tr>')
            H.append('</tbody></table>')
            continue
        m = re.match(r'^(#{1,4})\s+(.*)', L)
        if m:
            H.append(f'<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>')
            i += 1
            continue
        if re.match(r'^---\s*$', L):
            H.append('<hr>')
            i += 1
            continue
        if L.startswith('> '):
            H.append(f'<blockquote>{_inline(L[2:])}</blockquote>')
            i += 1
            continue
        if re.match(r'^\s*([-*]|\d+\.)\s+', L):
            tag = 'ol' if re.match(r'^\s*\d', L) else 'ul'
            items = []
            while i < n and re.match(r'^\s*([-*]|\d+\.)\s+', src[i]):
                items.append('<li>' + _inline(re.match(r'^\s*([-*]|\d+\.)\s+(.*)', src[i]).group(2)) + '</li>')
                i += 1
            H.append(f'<{tag}>' + ''.join(items) + f'</{tag}>')
            continue
        if L.strip() == '':
            i += 1
            continue
        H.append(f'<p>{_inline(L)}</p>')
        i += 1
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style>\n" + "\n".join(H))


if __name__ == '__main__':
    inp, outp = Path(sys.argv[1]), Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else inp.stem
    outp.write_text(to_html(inp.read_text(), title))
    print(f"  wrote {outp} ({outp.stat().st_size // 1024} KB)")
