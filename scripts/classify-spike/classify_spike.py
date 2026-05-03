#!/usr/bin/env python3
"""Wildlife-classification research spike.

Goal: measure how accurately a VLM can identify wildlife species from
fox-cam clips before we commit to building Track 1 as a real feature.

Input layout — organize clips by ground-truth label as subdirectories:

    clips/
      fox/                # confirmed fox events
      dog/                # neighbor's dog or other domestic dog
      cat/                # cats (any)
      raccoon/            # raccoons
      deer/               # deer
      person/             # people / mail carriers
      ambiguous/          # genuinely unclear cases (label = "ambiguous")
      none/               # empty frames / shadows / false positives

The script extracts N evenly-spaced frames per clip, sends each to the
chosen VLM with a structured prompt, aggregates the per-frame species
votes, and writes two CSVs:

    out/spike-results.csv       # one row per clip (aggregated verdict)
    out/spike-frames.csv        # one row per frame (raw responses)

Plus a confusion matrix printed to stdout.

Usage:

    python classify_spike.py \\
        --input-dir ./clips \\
        --output-dir ./out \\
        --provider claude \\
        --frames 5 \\
        --max-clips 30
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Species we ask the VLM to choose from. Keep this list short — too many
# options confuses the model and yields more "other"s. Add as needed.
SPECIES_OPTIONS = [
    "fox", "coyote", "domestic dog", "domestic cat",
    "raccoon", "deer", "rabbit", "squirrel", "bird",
    "person", "vehicle", "none", "other",
]

# Map each ground-truth subdirectory name to the species label we expect.
# Directories not in this map are skipped with a warning.
GROUND_TRUTH_DIRS = {
    "fox": "fox",
    "dog": "domestic dog",
    "cat": "domestic cat",
    "raccoon": "raccoon",
    "deer": "deer",
    "person": "person",
    "ambiguous": "ambiguous",  # special handling: never counts as wrong
    "none": "none",
}

# Structured prompt — chain-of-thought first, then commit. The "list
# features" step keeps the model from pattern-matching the image as a
# whole (which produces hallucinations on hard cases) and forces it to
# attend to actual visible details.
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


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def get_clip_duration(path: Path) -> float:
    """Return clip duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def extract_frames(clip_path: Path, n_frames: int, out_dir: Path) -> list[Path]:
    """Extract N evenly-spaced frames as JPEGs. Returns list of paths."""
    duration = get_clip_duration(clip_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    # Skip the first 5% and last 5% — those frames often have padding
    # or partial visibility due to the pre/post capture buffer.
    margin = max(0.5, duration * 0.05)
    start, end = margin, max(margin + 0.1, duration - margin)
    for i in range(n_frames):
        t = start + (end - start) * (i / max(n_frames - 1, 1))
        frame_path = out_dir / f"{clip_path.stem}_f{i:02d}.jpg"
        if not frame_path.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-ss", f"{t:.2f}", "-i", str(clip_path),
                 "-frames:v", "1",
                 # Resize so the longest side is ~1024 — VLMs don't gain
                 # accuracy beyond that, and smaller payloads = faster.
                 "-vf", "scale='min(1024,iw)':'-2'",
                 "-q:v", "3",  # JPEG quality (1-31, lower = better)
                 str(frame_path)],
                check=True,
            )
        frames.append(frame_path)
    return frames


# ---------------------------------------------------------------------------
# VLM clients
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    species: str
    confidence: str  # low|medium|high
    raw: str         # full JSON response for debugging
    error: Optional[str] = None


def _b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


def _parse_verdict(text: str) -> Verdict:
    """Best-effort JSON extraction. VLMs sometimes wrap in ```json fences."""
    # Strip code fences if present.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return Verdict(species="error", confidence="low", raw=text, error="no JSON")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return Verdict(species="error", confidence="low", raw=text, error=str(e))
    species = (data.get("species") or "error").lower().strip()
    confidence = (data.get("confidence") or "low").lower().strip()
    return Verdict(species=species, confidence=confidence, raw=json.dumps(data))


def classify_claude(frame: Path, model: str = "claude-haiku-4-5-20251001") -> Verdict:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 600,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                  "media_type": "image/jpeg",
                                                  "data": _b64(frame)}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        },
        timeout=60.0,
    )
    if r.status_code != 200:
        return Verdict(species="error", confidence="low", raw=r.text,
                       error=f"http {r.status_code}")
    body = r.json()
    text = body["content"][0]["text"]
    return _parse_verdict(text)


def classify_openai(frame: Path, model: str = "gpt-4o-mini") -> Verdict:
    api_key = os.environ["OPENAI_API_KEY"]
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": 600,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{_b64(frame)}"}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        },
        timeout=60.0,
    )
    if r.status_code != 200:
        return Verdict(species="error", confidence="low", raw=r.text,
                       error=f"http {r.status_code}")
    body = r.json()
    text = body["choices"][0]["message"]["content"]
    return _parse_verdict(text)


def classify_gemini(frame: Path, model: str = "gemini-2.0-flash") -> Verdict:
    api_key = os.environ["GEMINI_API_KEY"]
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": _b64(frame)}},
                    {"text": PROMPT},
                ],
            }],
            "generationConfig": {"maxOutputTokens": 600, "temperature": 0.1},
        },
        timeout=60.0,
    )
    if r.status_code != 200:
        return Verdict(species="error", confidence="low", raw=r.text,
                       error=f"http {r.status_code}")
    body = r.json()
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return Verdict(species="error", confidence="low", raw=json.dumps(body),
                       error="empty response")
    return _parse_verdict(text)


PROVIDERS = {
    "claude": classify_claude,
    "openai": classify_openai,
    "gemini": classify_gemini,
}


# ---------------------------------------------------------------------------
# Aggregation per clip
# ---------------------------------------------------------------------------

CONF_RANK = {"high": 3, "medium": 2, "low": 1, "": 0}


def aggregate(per_frame: list[Verdict]) -> tuple[str, str, str]:
    """Pick the best per-frame verdict for a clip.

    Strategy: highest-confidence non-'none' species wins. If all frames
    return 'none', return 'none'. Returns (species, confidence, why).
    """
    non_none = [v for v in per_frame if v.species not in ("none", "error", "")]
    if not non_none:
        return ("none", "high" if all(v.species == "none" for v in per_frame) else "low",
                f"all {len(per_frame)} frames returned none/error")

    # Sort by confidence rank, then by species frequency among non-none frames.
    counts = collections.Counter(v.species for v in non_none)
    non_none.sort(key=lambda v: (CONF_RANK[v.confidence], counts[v.species]), reverse=True)
    top = non_none[0]
    why = f"top of {len(non_none)} non-none frames; species counts={dict(counts)}"
    return (top.species, top.confidence, why)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="VLM wildlife classification spike")
    ap.add_argument("--input-dir", type=Path, required=True,
                    help="directory containing ground-truth subdirectories of MP4s")
    ap.add_argument("--output-dir", type=Path, default=Path("out"),
                    help="where to write CSVs and extracted frames")
    ap.add_argument("--provider", choices=PROVIDERS.keys(), default="claude")
    ap.add_argument("--model", default=None,
                    help="override default model for the chosen provider")
    ap.add_argument("--frames", type=int, default=5,
                    help="frames to extract per clip (default 5)")
    ap.add_argument("--max-clips", type=int, default=0,
                    help="stop after N clips (0 = no limit)")
    ap.add_argument("--dry-run", action="store_true",
                    help="extract frames but don't call the VLM")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = args.output_dir / "frames"

    # Discover clips by ground-truth subdirectory.
    clips: list[tuple[Path, str]] = []  # (path, ground_truth_label)
    for sub in sorted(args.input_dir.iterdir()):
        if not sub.is_dir():
            continue
        truth = GROUND_TRUTH_DIRS.get(sub.name)
        if truth is None:
            print(f"  skipping unrecognized dir: {sub.name}/", file=sys.stderr)
            continue
        for mp4 in sorted(sub.glob("*.mp4")):
            clips.append((mp4, truth))

    if args.max_clips:
        clips = clips[:args.max_clips]

    if not clips:
        print("No clips found. Check --input-dir layout.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(clips)} clips. Provider: {args.provider}.")
    if args.dry_run:
        print("Dry run — extracting frames only, no VLM calls.")

    classifier = PROVIDERS[args.provider]
    classifier_kwargs = {"model": args.model} if args.model else {}

    clip_csv = args.output_dir / "spike-results.csv"
    frame_csv = args.output_dir / "spike-frames.csv"

    with clip_csv.open("w", newline="") as cf, frame_csv.open("w", newline="") as ff:
        cw = csv.writer(cf)
        fw = csv.writer(ff)
        cw.writerow(["clip", "ground_truth", "predicted_species",
                     "predicted_confidence", "correct", "aggregation_note"])
        fw.writerow(["clip", "ground_truth", "frame", "species",
                     "confidence", "error", "raw_response"])

        for idx, (clip_path, truth) in enumerate(clips, 1):
            print(f"[{idx}/{len(clips)}] {clip_path.relative_to(args.input_dir)} "
                  f"(truth={truth})")
            try:
                frames = extract_frames(clip_path, args.frames, frames_dir)
            except Exception as e:
                print(f"  frame extraction failed: {e}", file=sys.stderr)
                cw.writerow([str(clip_path), truth, "error", "low", "", str(e)])
                continue

            verdicts: list[Verdict] = []
            for frame in frames:
                if args.dry_run:
                    v = Verdict("none", "low", "dry-run")
                else:
                    v = classifier(frame, **classifier_kwargs)
                verdicts.append(v)
                fw.writerow([str(clip_path), truth, frame.name,
                             v.species, v.confidence, v.error or "", v.raw])

            species, conf, why = aggregate(verdicts)
            correct = (
                "n/a" if truth == "ambiguous"
                else "yes" if (truth == species or
                               (truth == "none" and species == "none"))
                else "no"
            )
            cw.writerow([str(clip_path), truth, species, conf, correct, why])
            print(f"  -> predicted={species} ({conf}); "
                  f"truth={truth}; correct={correct}")

    # Confusion matrix.
    print()
    print("=== Confusion matrix ===")
    matrix: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    correct_count = total_count = 0
    with clip_csv.open() as f:
        next(f)  # skip header
        for row in csv.reader(f):
            _, truth, pred, _, correct, _ = row
            if truth == "ambiguous":
                continue
            matrix[truth][pred] += 1
            total_count += 1
            if correct == "yes":
                correct_count += 1
    if total_count == 0:
        print("(no scoreable rows)")
    else:
        # Print compact matrix.
        all_preds = sorted({p for row in matrix.values() for p in row})
        truths = sorted(matrix.keys())
        col_w = max(8, max(len(p) for p in all_preds) + 1)
        header_label = "truth\\pred"
        print(f"{header_label:<14}" + "".join(f"{p:<{col_w}}" for p in all_preds))
        for t in truths:
            print(f"{t:<14}" + "".join(f"{matrix[t][p]:<{col_w}}" for p in all_preds))
        print(f"\nAccuracy: {correct_count}/{total_count} "
              f"= {correct_count / total_count * 100:.1f}%")
        print(f"Detail CSVs: {clip_csv}, {frame_csv}")


if __name__ == "__main__":
    main()
