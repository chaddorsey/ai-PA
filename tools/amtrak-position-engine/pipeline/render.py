"""
pipeline/render.py — Task 3: Chirp3-HD MP3 render, content-hash cache, cost estimate.

Public API
----------
synth(text, custompron, voice="en-US-Chirp3-HD-Charon") -> bytes
    POST to Google TTS text:synthesize; returns raw MP3 bytes.
    Retries on 429/5xx with exponential backoff.

render_unit(unit, lexicon, outdir, voice) -> dict
    {"file": str, "bytes": int, "chars": int, "cached": bool}
    Content-hash filename <sha256(text+custompron+voice)>.mp3.
    Skips synth if the file already exists (cached=True).

estimate_cost(narration) -> dict
    {"chars": int, "usd_low": float, "usd_high": float}
    Total chars * Chirp3-HD rate range ($30/1M low, $45/1M high).
"""

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Chirp3-HD rate constants (USD per million chars)
# ---------------------------------------------------------------------------
_CHIRP3_RATE_LOW_PER_M = 30.0
_CHIRP3_RATE_HIGH_PER_M = 45.0

# Default voice
_DEFAULT_VOICE = "en-US-Chirp3-HD-Charon"

# Retry settings
_MAX_RETRIES = 4
_BACKOFF_BASE_S = 1.0


def synth(
    text: str,
    custompron: "List[Dict[str, Any]]",
    voice: str = _DEFAULT_VOICE,
) -> bytes:
    """
    Call Google TTS text:synthesize and return raw MP3 bytes.

    Parameters
    ----------
    text        : Narration text to synthesize.
    custompron  : List of customPronunciations dicts
                  [{"phrase": str, "phoneticEncoding": str, "pronunciation": str}].
    voice       : Chirp3-HD voice name (default en-US-Chirp3-HD-Charon).

    Returns
    -------
    bytes — raw MP3 audio data.
    """
    import base64
    import json
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    # ---- locate API key ----
    api_key = None
    p = Path(__file__).resolve().parent
    for _ in range(8):
        env_file = p / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GOOGLE_TTS_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
        if api_key:
            break
        p = p.parent

    if not api_key:
        raise RuntimeError("GOOGLE_TTS_API_KEY not found in any .env up the tree")

    # v1beta1 is required for customPronunciations support.
    # customPronunciations lives inside input as {"pronunciations": [...]}
    url = f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={api_key}"

    input_block: "Dict[str, Any]" = {"text": text}
    if custompron:
        input_block["customPronunciations"] = {"pronunciations": custompron}

    body: "Dict[str, Any]" = {
        "input": input_block,
        "voice": {
            "languageCode": "en-US",
            "name": voice,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
        },
    }

    payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return base64.b64decode(data["audioContent"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES - 1:
                sleep_s = _BACKOFF_BASE_S * (2 ** attempt)
                time.sleep(sleep_s)
                continue
            body_bytes = e.read()
            raise RuntimeError(
                f"Google TTS HTTP {e.code}: {body_bytes[:300].decode('utf-8', errors='replace')}"
            ) from e

    raise RuntimeError("synth: exhausted retries")  # pragma: no cover


def render_unit(
    unit: "Dict[str, Any]",
    lexicon: "Dict[str, Any]",
    outdir: "Any",  # str or Path
    voice: str = _DEFAULT_VOICE,
) -> "Dict[str, Any]":
    """
    Render one narration unit to an MP3 file with content-hash caching.

    Parameters
    ----------
    unit    : {"id": str, "text": str, ...}
    lexicon : Output of build_lexicon (term → entry dict).
    outdir  : Directory to write the .mp3 file into (created if absent).
    voice   : Chirp3-HD voice name.

    Returns
    -------
    {"file": str, "bytes": int, "chars": int, "cached": bool}
    """
    import hashlib
    import json
    from pathlib import Path

    from pipeline.lexicon import custompron_for

    text: str = unit.get("text", "")
    custompron: "List[Dict[str, Any]]" = custompron_for(text, lexicon)

    # Stable cache key: deterministic JSON of (text, custompron, voice)
    key_data = json.dumps(
        {"text": text, "custompron": custompron, "voice": voice},
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    content_hash = hashlib.sha256(key_data).hexdigest()

    out_path = Path(outdir) / f"{content_hash}.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        audio_bytes = out_path.read_bytes()
        return {
            "file": str(out_path),
            "bytes": len(audio_bytes),
            "chars": len(text),
            "cached": True,
        }

    audio_bytes = synth(text, custompron, voice=voice)
    out_path.write_bytes(audio_bytes)

    return {
        "file": str(out_path),
        "bytes": len(audio_bytes),
        "chars": len(text),
        "cached": False,
    }


def estimate_cost(narration: "Dict[str, Any]") -> "Dict[str, Any]":
    """
    Estimate Chirp3-HD render cost for the full narration corpus.

    Parameters
    ----------
    narration : {leg_id: [{"text": str, ...}, ...], ...}

    Returns
    -------
    {"chars": int, "usd_low": float, "usd_high": float}
    """
    total_chars = 0
    for _leg, units in narration.items():
        for unit in units:
            text = unit.get("text")
            if text:
                total_chars += len(text)

    usd_low = total_chars * _CHIRP3_RATE_LOW_PER_M / 1_000_000
    usd_high = total_chars * _CHIRP3_RATE_HIGH_PER_M / 1_000_000

    return {
        "chars": total_chars,
        "usd_low": round(usd_low, 4),
        "usd_high": round(usd_high, 4),
    }
