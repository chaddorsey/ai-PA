"""
pipeline/review_sheet.py — Task 2: Generate a risk-ranked HTML audio review sheet.

Public API
----------
build_review_sheet(lexicon, render_fn, out_html) -> None
    Writes an HTML file at out_html.
    lexicon: output of build_lexicon.
    render_fn: callable(name: str, ipa: str) -> bytes|None — INJECTED audio renderer.
               Pass None to skip audio column (audio wired in after Task 3).
    out_html: path to write the review sheet (str or Path).

Rows are sorted by risk × freq descending.
Columns: name | freq | source | confidence | IPA | audio (if render_fn) | override field.
"""

import base64
import html
import json
from pathlib import Path
from typing import Callable, Optional


def build_review_sheet(
    lexicon: "dict[str, dict]",
    render_fn: "Optional[Callable[[str, str], Optional[bytes]]]",
    out_html: str,
) -> None:
    """
    Write a risk-ranked pronunciation review sheet to out_html.

    Parameters
    ----------
    lexicon    : {term: {"ipa", "source", "confidence", "risk", "freq"}}
    render_fn  : (name, ipa) -> bytes|None. If None, audio column is omitted.
    out_html   : output file path.
    """
    # Sort by risk × freq descending
    rows = sorted(
        lexicon.items(),
        key=lambda kv: kv[1].get("risk", 0.0) * kv[1].get("freq", 0),
        reverse=True,
    )

    has_audio = render_fn is not None

    lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Pronunciation Review Sheet</title>",
        "<style>",
        "  body { font-family: system-ui, sans-serif; font-size: 16px; margin: 2em; }",
        "  table { border-collapse: collapse; width: 100%; }",
        "  th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; }",
        "  th { background: #f0f0f0; }",
        "  tr:nth-child(even) { background: #fafafa; }",
        "  .ipa { font-family: monospace; font-size: 1.1em; }",
        "  .hi-risk { background: #fff3cd; }",
        "  .trust { color: #1a6b1a; font-weight: bold; }",
        "  .untrust { color: #9a4a00; }",
        "  input.override { width: 15em; font-family: monospace; }",
        "  audio { vertical-align: middle; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Pronunciation Review Sheet</h1>",
        "<p>Sorted by <strong>risk × frequency</strong> (descending). "
        "High-risk names appear first. Add correct IPA to "
        "<code>data/pron_overrides.json</code> for any mispronounced name.</p>",
        "<table>",
        "<thead><tr>",
        "  <th>#</th>",
        "  <th>Name</th>",
        "  <th>Freq</th>",
        "  <th>Source</th>",
        "  <th>Confidence</th>",
        "  <th>IPA</th>",
        "  <th>Risk × Freq</th>",
    ]
    if has_audio:
        lines.append("  <th>Audio</th>")
    lines += [
        "  <th>Override IPA</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for i, (name, entry) in enumerate(rows, 1):
        ipa = entry.get("ipa") or ""
        source = entry.get("source", "none")
        confidence = entry.get("confidence", 0.0)
        risk = entry.get("risk", 0.0)
        freq = entry.get("freq", 0)
        score = risk * freq

        is_hi_risk = risk >= 0.7
        is_trusted = source == "override" or confidence >= 0.8

        row_class = " class='hi-risk'" if is_hi_risk else ""
        conf_class = "trust" if is_trusted else "untrust"
        conf_label = f"{confidence:.2f}"

        # Audio column
        audio_cell = ""
        if has_audio:
            if ipa:
                audio_bytes = render_fn(name, ipa)
                if audio_bytes:
                    b64 = base64.b64encode(audio_bytes).decode("ascii")
                    audio_cell = (
                        f"<audio controls src='data:audio/mpeg;base64,{b64}'></audio>"
                    )
                else:
                    audio_cell = "<em>—</em>"
            else:
                audio_cell = "<em>no IPA</em>"

        lines.append(f"<tr{row_class}>")
        lines.append(f"  <td>{i}</td>")
        lines.append(f"  <td><strong>{html.escape(name)}</strong></td>")
        lines.append(f"  <td>{freq}</td>")
        lines.append(f"  <td>{html.escape(source)}</td>")
        lines.append(f"  <td class='{conf_class}'>{conf_label}</td>")
        lines.append(f"  <td class='ipa'>{html.escape(ipa)}</td>")
        lines.append(f"  <td>{score:.2f}</td>")
        if has_audio:
            lines.append(f"  <td>{audio_cell}</td>")
        lines.append(
            f"  <td><input class='override' type='text' "
            f"placeholder='IPA override…' "
            f"data-name='{html.escape(name, quote=True)}'></td>"
        )
        lines.append("</tr>")

    lines += [
        "</tbody>",
        "</table>",
        "",
        "<script>",
        "// Copy overrides to clipboard as JSON for pasting into pron_overrides.json",
        "document.querySelectorAll('input.override').forEach(inp => {",
        "  inp.addEventListener('change', () => {",
        "    const name = inp.dataset.name;",
        "    const ipa = inp.value.trim();",
        "    if (ipa) console.log(JSON.stringify({[name]: ipa}));",
        "  });",
        "});",
        "</script>",
        "",
        "</body>",
        "</html>",
    ]

    out_path = Path(out_html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote review sheet ({len(rows)} entries) → {out_path}")
