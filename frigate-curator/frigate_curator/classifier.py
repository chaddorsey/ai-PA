"""Wildlife classifier — Track 1 of the detection pipeline.

Runs after Frigate fires an event and the curator copies the clip. Pulls
a few frames from the saved MP4, sends them through a vision model via
litellm, and stores species + confidence in the highlights DB.

Calibrated against a 22-clip spike (2026-05-03):
  - GPT-4o-mini: 91% overall accuracy, 100% wildlife recall, 100% empty
    specificity.
  - Gemini 2.0 Flash: 86% overall, 100% wildlife recall, 78% empty
    specificity. Cheaper but more false-positive-prone on empty frames.

Default provider is gpt-4o-mini (via litellm route gpt-4o-mini/fox-cam)
because of the better specificity.

Disabled (no-op) if CLASSIFIER_ENABLED is not 'true'.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


SPECIES_OPTIONS = [
    "fox", "coyote", "domestic dog", "domestic cat",
    "raccoon", "deer", "rabbit", "squirrel", "bird",
    "person", "vehicle", "none", "other",
]

PROMPT = f"""You are looking at a frame from a wildlife camera in a residential yard. Your job is to identify what (if anything) is in the frame.

Analyze step by step:

1. Describe what you see — lighting, scene, any subjects.
2. If there is an animal or person, list every visible feature: ears (shape, size, position), tail (length, fluffiness), fur color and pattern, body shape and size, leg length, posture, any visible collar or markings.
3. Based ONLY on those features, identify the subject from this list: {', '.join(SPECIES_OPTIONS)}. Pick "none" if no subject. Pick "other" only if it's clearly an animal but not in the list.
4. Rate your confidence: "high" (multiple features clearly support the answer), "medium" (some features support it, others ambiguous), or "low" (mostly guessing).

Reply with JSON only, no other text. Schema:

{{"description": "<1 sentence>",
  "features": "<bullet-style list>",
  "species": "<one of the species options>",
  "confidence": "<low|medium|high>",
  "reasoning": "<1 sentence explaining the choice>"}}"""


# Module-level config (set by main.py at startup).
_BASE_URL: str = "http://localhost:4000"
_API_KEY: str = ""
_MODEL: str = "gpt-4o-mini/fox-cam"
_FRAMES_PER_CLIP: int = 5
_ENABLED: bool = False


def configure(base_url: str, api_key: str, model: str,
              frames_per_clip: int, enabled: bool) -> None:
    global _BASE_URL, _API_KEY, _MODEL, _FRAMES_PER_CLIP, _ENABLED
    _BASE_URL = base_url.rstrip("/")
    _API_KEY = api_key
    _MODEL = model
    _FRAMES_PER_CLIP = frames_per_clip
    _ENABLED = enabled


@dataclass
class FrameVerdict:
    species: str
    confidence: str
    description: str
    raw: str


@dataclass
class ClipVerdict:
    species: str             # aggregated species across frames
    confidence: str          # low|medium|high
    is_wildlife: bool        # convenience: species not in {none, person, vehicle}
    frames: list[FrameVerdict]  # per-frame for debugging
    error: Optional[str] = None


def _extract_frames(clip_path: Path, n: int) -> list[Path]:
    """Pull N evenly-spaced frames from the MP4 as JPEGs."""
    out_dir = Path(tempfile.mkdtemp(prefix="classifier-"))
    # ffprobe duration
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(r.stdout.strip())
    margin = max(0.3, duration * 0.05)
    start, end = margin, max(margin + 0.1, duration - margin)
    frames: list[Path] = []
    for i in range(n):
        t = start + (end - start) * (i / max(n - 1, 1))
        out = out_dir / f"f{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-ss", f"{t:.2f}", "-i", str(clip_path),
             "-frames:v", "1",
             "-vf", "scale='min(1024,iw)':'-2'",
             "-q:v", "3", str(out)],
            check=True,
        )
        frames.append(out)
    return frames


def _b64(p: Path) -> str:
    return base64.standard_b64encode(p.read_bytes()).decode()


def _classify_frame(frame: Path) -> FrameVerdict:
    """Send a single frame to litellm and parse the JSON verdict."""
    url = f"{_BASE_URL}/v1/chat/completions"
    body = {
        "model": _MODEL,
        "max_tokens": 600,
        "messages": [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{_b64(frame)}"}},
            {"type": "text", "text": PROMPT},
        ]}],
    }
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {_API_KEY}",
                 "Content-Type": "application/json"},
        json=body,
        timeout=60.0,
    )
    if r.status_code != 200:
        return FrameVerdict("error", "low", "", f"http {r.status_code}: {r.text[:200]}")
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return FrameVerdict("error", "low", text, "no JSON")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return FrameVerdict("error", "low", text, f"json: {e}")
    return FrameVerdict(
        species=(d.get("species") or "error").lower().strip(),
        confidence=(d.get("confidence") or "low").lower().strip(),
        description=(d.get("description") or "")[:200],
        raw=json.dumps(d),
    )


_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}


def _aggregate(frames: list[FrameVerdict]) -> tuple[str, str]:
    """Best non-none verdict across frames; falls back to 'none' if all empty."""
    non_none = [f for f in frames if f.species not in ("none", "error", "")]
    if not non_none:
        return ("none", "high" if all(f.species == "none" for f in frames) else "low")
    # Sort by confidence rank, then by species frequency.
    from collections import Counter
    counts = Counter(f.species for f in non_none)
    non_none.sort(key=lambda f: (_CONF_RANK[f.confidence], counts[f.species]),
                  reverse=True)
    return (non_none[0].species, non_none[0].confidence)


def classify_clip(clip_path: Path) -> Optional[ClipVerdict]:
    """Run the full classification pipeline on a saved clip.

    Returns None if the classifier is disabled. Returns a ClipVerdict
    with `error` set if frame extraction or VLM calls fail — caller
    can still record the partial result.
    """
    if not _ENABLED:
        return None
    if not _API_KEY:
        logger.warning("Classifier enabled but no LITELLM_API_KEY set; skipping")
        return None

    try:
        frame_paths = _extract_frames(clip_path, _FRAMES_PER_CLIP)
    except Exception as e:
        logger.exception("Frame extraction failed for %s", clip_path)
        return ClipVerdict("error", "low", False, [], error=str(e))

    frames: list[FrameVerdict] = []
    for fp in frame_paths:
        try:
            frames.append(_classify_frame(fp))
        except Exception as e:
            logger.exception("VLM call failed for %s", fp)
            frames.append(FrameVerdict("error", "low", "", str(e)))

    # Cleanup temp frames.
    for fp in frame_paths:
        try: fp.unlink()
        except Exception: pass
    try: frame_paths[0].parent.rmdir()
    except Exception: pass

    species, confidence = _aggregate(frames)
    is_wildlife = species not in ("none", "person", "vehicle", "error")
    return ClipVerdict(
        species=species,
        confidence=confidence,
        is_wildlife=is_wildlife,
        frames=frames,
    )
