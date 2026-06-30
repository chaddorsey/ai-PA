#!/usr/bin/env python3
"""Render all leg-3 (Southwest Chief) narration units to MP3 with Chirp3-HD Iapetus.

- Pronunciations applied via custompron_for (the locked lexicon/overrides).
- Audio written to bundles/leg3/audio/<sha256(text)>.mp3 — the exact name
  build_bundle(proxy=False) looks for (it hashes text only).
- Resumable: skips any file already present.
"""
import json, hashlib, sys, re
from pathlib import Path
from pipeline.render import synth
from pipeline.lexicon import custompron_for

VOICE = "en-US-Chirp3-HD-Iapetus"

# Strip delimiters / syllable dots / tie-bars the Chirp3 customPronunciations API rejects.
_STRIP = str.maketrans("", "", "/[]()." + "͡")
def _sanitize(cp):
    out = []
    for c in cp:
        c = dict(c)
        c["pronunciation"] = c["pronunciation"].translate(_STRIP).strip()
        if c["pronunciation"]:
            out.append(c)
    return out

DROPPED = set()
def synth_safe(text, cp):
    """Synth with custom prons; on an 'invalid pronunciation phrases' 400, drop the
    named phrases and retry (those words fall back to Iapetus' native pronunciation)."""
    cp = _sanitize(cp)
    for _ in range(6):
        try:
            return synth(text, cp, voice=VOICE)
        except RuntimeError as e:
            m = re.search(r"invalid:\s*(.+?)\.\s*Please", str(e))
            if not m:
                raise
            bad = {p.strip() for p in m.group(1).split(",")}
            DROPPED.update(bad)
            cp = [c for c in cp if c["phrase"] not in bad]
    return synth(text, [], voice=VOICE)  # last resort: no custom prons
HERE = Path(__file__).resolve().parent
lex = json.load(open(HERE / "data" / "pron_lexicon.json"))
units = json.load(open(HERE / "data" / "route_narration.json"))["3"]
audio_dir = HERE / "bundles" / "leg3" / "audio"
audio_dir.mkdir(parents=True, exist_ok=True)

# Sanity check on the first unit before committing to the batch.
texts = [u.get("text", "") for u in units if u.get("text", "").strip()]
uniq = list(dict.fromkeys(texts))  # dedup, preserve order
print(f"  leg-3: {len(units)} units, {len(uniq)} unique texts", flush=True)

rendered = cached = errors = chars = 0
for i, text in enumerate(uniq):
    h = hashlib.sha256(text.encode()).hexdigest()
    out = audio_dir / f"{h}.mp3"
    if out.exists() and out.stat().st_size > 500:
        cached += 1
        continue
    try:
        cp = custompron_for(text, lex)
        audio = synth_safe(text, cp)
        out.write_bytes(audio)
        rendered += 1
        chars += len(text)
    except Exception as e:
        errors += 1
        print(f"  ERR unit {i}: {str(e)[:120]}", flush=True)
        if rendered == 0 and i == 0:
            print("  ABORT: first render failed", flush=True)
            sys.exit(1)
    if (rendered + cached) % 50 == 0:
        print(f"  progress {rendered+cached}/{len(uniq)} (rendered={rendered} cached={cached} err={errors})", flush=True)

print(f"  DONE rendered={rendered} cached={cached} errors={errors} chars={chars} "
      f"est_cost=${chars/1_000_000*30:.2f}", flush=True)
if DROPPED:
    print(f"  dropped {len(DROPPED)} custom-pron phrases (fell back to native voice): "
          f"{sorted(DROPPED)}", flush=True)
