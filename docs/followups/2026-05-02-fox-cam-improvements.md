---
title: Fox Cam — open improvements queue
date: 2026-05-02
status: living document
related:
  - frigate/config/config.yml
  - frigate-curator/frigate_curator/
  - fox-cam-public/
  - deployment/launchd/com.ai-pa.frigate-detector.plist
  - deployment/launchd/com.ai-pa.go2rtc.plist
  - deployment/launchd/com.ai-pa.frigate-curator.plist
  - deployment/launchd/com.ai-pa.orbstack-engine.plist
---

# Fox Cam — open improvements queue

Living list of known issues, tuning items, and capability work for the
fox-cam stack (Frigate + curator + public viewer + ntfy push). Add new
items at the bottom of the relevant section. When you start one, mark
it `IN PROGRESS`; when done, move to "Shipped" with date + commit.

## High priority — correctness / observable bugs

**F1 — Curator reads `top_score` from list endpoint, which is null.**
`curator._process_event` uses `event.get("top_score") or event.get("score")` against the list response, but Frigate only populates `top_score` on the per-event detail endpoint. As a result, every saved highlight has `score=0.0` in the DB, which feeds into `fox_likelihood` and into the meta line in the UI ("fox 0%"). Fix: after listing, fetch each event's detail (`/api/events/<id>`) before scoring, OR use `data.score` from the list response (which Frigate does populate, just under a different key in 0.17). Verify with `curl -s https://localhost:8971/api/events?limit=5 | jq '.[] | {id, top_score, score, data}'`.

**F2 — Pre-MegaDetector-revert person events have `has_clip=true` but no MP4 on disk.**
During the MegaDetector experiment, score=0 caused Frigate's `false_positive` flag to set, and the recorder never wrote the MP4 even though the API claims a clip exists. Affects events from ~2026-04-29 to revert. Curator's "no clip" path handles it but logs as warnings every poll. Mitigation: filter by `(end_time > revert_ts)` in the curator's bootstrap-since clamp, or mark these event_ids as permanently-skip in the DB.

## Medium priority — capability / UX

**F3 — Notification cooldown / dedup per fox sequence.**
A single fox visit often produces 3–8 Frigate events (motion blip, then re-detect, then re-detect). Each fires a separate ntfy push. Add a per-camera cooldown in `notify.maybe_notify`: if the most recent `notified_at` for the same camera is within N seconds (default 120), skip the push. Notification still records; user just doesn't get spammed. Tunable via `NOTIFY_COOLDOWN_S` env.

**F4 — Per-camera notification opt-out.**
Camera 3 (sidewalk-facing) generates the most non-fox events. Add `NOTIFY_CAMERAS=fox_den_1,fox_den_2` env to allowlist; default to all if unset.

**F5 — Zones into fox_likelihood.**
Now that zones are configured (`den_entrance` etc.), in-zone events should weight much higher than out-of-zone. Update `heuristics.fox_likelihood` to take `event["entered_zones"]` and add a multiplier (e.g., 1.5× if entered_zones ∩ den_zones, 0.5× otherwise). Coordinate with F3 — a high-confidence in-zone event should bypass cooldown.

**F6 — VLM Stage 2: fox vs pet discriminator.**
On promotion to highlights (or above some likelihood threshold), run the snapshot through a small VLM (MoonDream2 or Florence-2) with a prompt like "Is this a fox or a domestic dog/cat?" and store the verdict + confidence. Surface as a badge on the card. Lets us auto-demote pet events without family clicks. Probably runs on ANE via CoreML if we can find a packaged model.

**F7 — MegaDetector v5a revisit.**
Patched ONNX hung CoreML inference (1.4×10¹¹ms). Two paths to try: (a) bake the YOLOv5→v8 conversion into a separate post-processing ONNX run after the main inference, OR (b) write a custom Frigate detector plugin that handles YOLOv5 output natively. See `frigate/tools/patch_megadetector_to_yolov8.py` for the failed approach.

**F8 — Highlights gallery: group by sequence.**
Multiple events from one fox visit show as N separate cards. Group by camera + tight time window into a single "visit" card with a thumbnail strip + total duration. Reduces clutter, especially on the Favorites tab.

**F9 — Clip permalink: prev/next nav.**
On `/clip/<id>`, add ← / → buttons that walk through the highlights list at the same bucket+filter. Currently family members have to bounce back to /highlights, find their place, and click another.

**F10 — PWA install for fox-cam-public.**
`manifest.json` + service worker + apple-touch-icon so family can "Add to Home Screen" and get a chromeless app. Also unlocks iOS web push later if we ever want to phase out ntfy.

## Low priority — hygiene / infra

**F11 — Verify resource limits actually hold under load.**
We added `mem_limit: 4g` + `cpus: 4` to the Frigate container after the AppleAVD panic. Should run a soak test (`yes > /dev/null &` x4 in container, `vm_stat` on host) to confirm the limits actually clamp and we don't get OOM-killed at 4G in normal operation. If 4G is too tight, raise to 6G; if Frigate runs comfortably at 2G, drop the cap.

**F12 — Self-host ntfy.**
ntfy.sh is fine for now (free, reliable) but topic-based auth is weak. Eventually run our own ntfy server behind Cloudflare Tunnel + Cloudflare Access so notifications go through the same auth as the viewer. Low priority — ntfy.sh hasn't burned us yet.

**F13 — Fox-cam highlights in automated backup.**
Verify `/Volumes/main-filestore/frigate-highlights/` (clips + index.db) is included in the daily 2am backup wrapper. Clips are nice-to-have; the SQLite DB is the irreplaceable part (favorites, demotions, attribution).

**F14 — Domain swap from `foxes.cd-ai-pa.work` to dedicated domain.**
Currently using a subdomain of the PA work domain. Long-term: dedicated public domain (TBD) so external sharing doesn't expose a "cd-ai-pa.work" string. Update Cloudflare Tunnel ingress, Access policies, ASSET_VERSION cache-bust, and `FOX_PUBLIC_BASE_URL` in `.env`.

**F15 — Remove dead MegaDetector revert artifacts.**
`frigate/tools/patch_megadetector_to_yolov8.py` is committed but unused. Decide: keep as documented future-work breadcrumb (link from F7) or delete and reference via git history. Lean toward keep with a comment header explaining it's parked.

**F16 — Curator: distinguish "still in progress" from stale events.**
`_tick` skips events with `end_time is None` ("still in progress; we'll see it again next tick when ended"). For very-long-running events (hours-long person on porch), this can hold up the bootstrap window. Add a max-age cutoff (e.g., events with `start_time < now - 1h` and still no end_time get force-finalized at start_time + max_duration). Edge case but real.

**F17 — SSS deep-dive integration (planned, deferred soak).**
Pull arbitrary-window MP4 from Synology Surveillance Station on demand, cached + idempotent. Family-facing "+30s after this clip" button. Full plan written: `docs/plans/2026-05-03-fox-cam-sss-deep-dive-plan.md`. Levels A (sync pull-then-serve), A.1 (pre-warm on save), B (stream-while-fetching, deferred), C (live RTSP, parked). Pick up after pre/post + threshold soak shows where deep-dive demand actually lives.

## Architectural / deferred

**FA — Fox-vs-cat-vs-dog-vs-deer multi-class auto-tagging.**
Beyond F6's binary fox/not-fox, train (or fine-tune) a classifier on the curated highlights once we have ~500+ family-tagged samples. Could feed back into the detector itself eventually. Long-horizon.

**FB — Multi-week activity dashboard.**
Page showing "fox visits per day, last 30 days," favorite cameras over time, time-of-day histogram. Pure SQL on the existing index.db. Could live at `/dashboard`.

**FC — Family attribution leaderboard / activity feed.**
"Mary favorited 3, demoted 1 this week." Lightweight social signal; helps family stay engaged with curation. Already have `last_action_by` column.

## Shipped (recent)

| Date | What | Commit |
|---|---|---|
| 2026-05-02 | ntfy push for fox-likely events (threshold-gated, dedup'd via notified_at) | `aa61f016` |
| 2026-05-02 | Reboot-survival LaunchAgent for OrbStack engine + resource ceilings (Frigate 4G/4cpu, detector Nice=5 + 8G data cap) after AppleAVD watchdog panic | `c4186822` |
| 2026-05-02 | card.js refactor — fixes "window.makeCard is not a function" on /clip/<id> permalinks | `d2b89456` |
| 2026-05-01 | Highlights v2: ⭐ favorites / 🚫 demote / 🔗 share-permalinks / family attribution / day-night / date-range / camera filters | `7c5b4013` |
| 2026-04-30 | MegaDetector ONNX → YOLOv8 output patch (committed but reverted — caused CoreML hang) | `7707069f` |
| 2026-04-30 | MegaDetector v5a switch (later reverted to YOLO11-S) | `71aef4a4` |
| 2026-04-30 | launchd-survivable go2rtc (escapes Sequoia App Translocation + /Volumes TCC) | `8b530aae` |
| 2026-04-29 | Phase-1 fox-cam: Frigate + curator + public viewer + Cloudflare Access + WebRTC/MSE | `05d401f0` |

## How to use this doc

Pick an item, search for its number, read related code, do the work,
move it to "Shipped" with date + commit hash. New items go to the
relevant priority section with a brief problem statement and a fix
sketch. Keep entries tight — one paragraph + one fix bullet.
