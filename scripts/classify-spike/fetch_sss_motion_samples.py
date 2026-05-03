#!/usr/bin/env python3
"""Pull representative motion-tagged samples from Synology Surveillance Station.

SSS records continuously in 30-min chunks. Chunks containing motion are
tagged via trigger_label=257. This script:

1. Lists motion-tagged chunks across all cameras for a time window
2. Picks a representative subset (day/night × camera mix)
3. Downloads each chunk
4. Runs ffmpeg scene-change detection to find motion bursts within
5. Extracts ~10-second windows around each detected scene change
6. Saves the candidates into <out-dir>/_unlabeled/

The user then reviews the candidates manually and moves them into the
ground-truth subdirs the spike script expects (fox/, dog/, raccoon/,
person/, ambiguous/, none/).

Requires SSS_BASE_URL, SSS_USER, SSS_PASS in the environment (.env).
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx


def login(base_url: str, user: str, password: str) -> str:
    r = httpx.get(
        f"{base_url}/webapi/auth.cgi",
        params={"api": "SYNO.API.Auth", "version": 6, "method": "login",
                "account": user, "passwd": password,
                "session": "SurveillanceStation", "format": "sid"},
        timeout=15.0,
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"SSS login failed: {body}")
    return body["data"]["sid"]


def list_motion_events(base_url: str, sid: str, camera_ids: list[int],
                       start_ts: int, end_ts: int) -> list[dict]:
    """Return events whose trigger_label includes 257 (motion + continuous)."""
    r = httpx.get(
        f"{base_url}/webapi/entry.cgi",
        params={"api": "SYNO.SurveillanceStation.Event", "version": 5,
                "method": "List", "cameraIds": ",".join(map(str, camera_ids)),
                "fromTime": start_ts, "toTime": end_ts,
                "limit": 1000, "_sid": sid},
        timeout=30.0,
    )
    r.raise_for_status()
    events = r.json().get("data", {}).get("events", [])
    return [e for e in events if e.get("trigger_label") == [257]]


def pick_representative(events: list[dict], n: int) -> list[dict]:
    """Stratified sample: try to spread across (camera, day/night) buckets."""
    buckets: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for e in events:
        hour = datetime.fromtimestamp(e["startTime"]).hour
        period = "day" if 6 <= hour < 18 else "night"
        buckets[(e["cameraId"], period)].append(e)

    picked: list[dict] = []
    # Round-robin across buckets so we don't bias toward whichever bucket
    # has the most events.
    keys = sorted(buckets.keys())
    while len(picked) < n and any(buckets[k] for k in keys):
        for k in keys:
            if not buckets[k]:
                continue
            picked.append(buckets[k].pop(random.randrange(len(buckets[k]))))
            if len(picked) >= n:
                break
    return picked


def download_chunk(base_url: str, sid: str, event_id: int, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading event {event_id} -> {dest.name}")
    with httpx.stream("GET",
                      f"{base_url}/webapi/entry.cgi",
                      params={"api": "SYNO.SurveillanceStation.Recording",
                              "version": 6, "method": "Download",
                              "id": event_id, "_sid": sid},
                      timeout=300.0) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
    return dest


def find_scene_changes(chunk_path: Path, threshold: float = 0.4) -> list[float]:
    """Use ffmpeg's scene filter to find timestamps of motion bursts.

    Returns a list of scene-change timestamps in seconds. ffmpeg writes
    them to stderr as 'pts_time:N.NN' lines under the showinfo filter.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(chunk_path),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    timestamps: list[float] = []
    for line in r.stderr.splitlines():
        if "pts_time:" in line and "showinfo" in line:
            # showinfo lines look like:
            # [Parsed_showinfo_1 @ ...] n: 0  pts: 12345  pts_time:13.71  ...
            for token in line.split():
                if token.startswith("pts_time:"):
                    try:
                        timestamps.append(float(token.split(":", 1)[1]))
                    except ValueError:
                        pass
    return timestamps


def extract_windows(chunk_path: Path, timestamps: list[float],
                    pre_s: float, post_s: float, out_dir: Path,
                    max_per_chunk: int) -> list[Path]:
    """Cut N short windows from a chunk centered on the timestamps."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Deduplicate timestamps that are too close together (within 5s of
    # an already-picked one) so we get spread across the chunk.
    chosen: list[float] = []
    for t in timestamps:
        if any(abs(t - x) < 5.0 for x in chosen):
            continue
        chosen.append(t)
        if len(chosen) >= max_per_chunk:
            break

    out: list[Path] = []
    for i, t in enumerate(chosen):
        start = max(0, t - pre_s)
        dest = out_dir / f"{chunk_path.stem}_{i:02d}_t{int(t)}s.mp4"
        if dest.exists():
            out.append(dest)
            continue
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.2f}", "-i", str(chunk_path),
            "-t", f"{pre_s + post_s:.2f}",
            # Drop audio — SSS records pcm_alaw which won't repackage
            # cleanly in MP4. We don't need audio for VLM analysis.
            "-an", "-c:v", "copy", str(dest),
        ]
        subprocess.run(cmd, check=True)
        out.append(dest)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="root for spike clips (will write to <out>/_unlabeled/)")
    ap.add_argument("--days", type=int, default=7,
                    help="lookback window for motion events (default 7)")
    ap.add_argument("--chunks", type=int, default=5,
                    help="number of 30-min chunks to fetch")
    ap.add_argument("--cameras", default="10,11,12",
                    help="comma-separated SSS camera IDs")
    ap.add_argument("--windows-per-chunk", type=int, default=4,
                    help="max candidate windows to extract per chunk")
    ap.add_argument("--pre-s", type=float, default=4.0,
                    help="seconds before scene change to include")
    ap.add_argument("--post-s", type=float, default=8.0,
                    help="seconds after scene change to include")
    ap.add_argument("--scene-threshold", type=float, default=0.4,
                    help="ffmpeg scene filter threshold (0-1; lower = more sensitive)")
    ap.add_argument("--keep-chunks", action="store_true",
                    help="don't delete the 30-min chunk files after extraction")
    args = ap.parse_args()

    base_url = os.environ.get("SSS_BASE_URL")
    user = os.environ.get("SSS_USER")
    password = os.environ.get("SSS_PASS")
    if not all([base_url, user, password]):
        sys.exit("Missing SSS_BASE_URL / SSS_USER / SSS_PASS in environment")

    cam_ids = [int(x) for x in args.cameras.split(",")]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = args.out_dir / "_chunks"
    candidates_dir = args.out_dir / "_unlabeled"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir.mkdir(parents=True, exist_ok=True)

    print("Logging in to SSS...")
    sid = login(base_url, user, password)

    end_ts = int(datetime.now().timestamp())
    start_ts = end_ts - args.days * 86400

    print(f"Listing motion events (last {args.days}d, cameras {cam_ids})...")
    events = list_motion_events(base_url, sid, cam_ids, start_ts, end_ts)
    print(f"  {len(events)} motion-tagged chunks found")

    if not events:
        sys.exit("No motion events found — nothing to fetch.")

    picked = pick_representative(events, args.chunks)
    print(f"Picked {len(picked)} chunks for sampling:")
    for e in picked:
        t = datetime.fromtimestamp(e["startTime"])
        size_mb = e["event_size_bytes"] / 1_000_000
        print(f"  cam={e['cameraId']} {t:%Y-%m-%d %H:%M} size={size_mb:.0f}MB id={e['id']}")

    all_candidates: list[Path] = []
    for e in picked:
        chunk_path = chunks_dir / f"sss_{e['cameraId']}_{e['id']}.mp4"
        if not chunk_path.exists():
            download_chunk(base_url, sid, e["id"], chunk_path)
        else:
            print(f"  reusing cached chunk {chunk_path.name}")

        print(f"  scanning {chunk_path.name} for scene changes...")
        timestamps = find_scene_changes(chunk_path, args.scene_threshold)
        print(f"    {len(timestamps)} scene changes detected")

        if not timestamps:
            print("    (none — chunk may be very static; skipping)")
            continue

        windows = extract_windows(
            chunk_path, timestamps, args.pre_s, args.post_s,
            candidates_dir, args.windows_per_chunk,
        )
        print(f"    extracted {len(windows)} candidate windows")
        all_candidates.extend(windows)

        if not args.keep_chunks:
            chunk_path.unlink()

    print()
    print(f"=== {len(all_candidates)} candidate clips written to {candidates_dir} ===")
    print()
    print("Next: review them in QuickTime, then move each into the right")
    print("ground-truth subdirectory under the spike input dir:")
    print(f"  mv {candidates_dir}/<file>.mp4 {args.out_dir}/fox/")
    print(f"  mv {candidates_dir}/<file>.mp4 {args.out_dir}/dog/")
    print(f"  ...etc (fox, dog, cat, raccoon, deer, person, ambiguous, none)")
    print()
    print("Then run the spike:")
    print(f"  python3 scripts/classify-spike/classify_spike.py \\")
    print(f"      --input-dir {args.out_dir} \\")
    print(f"      --output-dir {args.out_dir}/results \\")
    print(f"      --provider gemini --frames 5")


if __name__ == "__main__":
    main()
