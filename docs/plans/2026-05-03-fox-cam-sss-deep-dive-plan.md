---
title: Fox Cam — SSS deep-dive integration plan
date: 2026-05-03
status: planned (not started)
related:
  - docs/followups/2026-05-02-fox-cam-improvements.md (F17/F18)
  - frigate-curator/frigate_curator/
  - fox-cam-public/
  - .env (SSS_* vars)
---

# Fox Cam — SSS deep-dive integration plan

## Summary

Family-facing "show me 30 seconds after this clip" capability that
pulls main-stream video from Synology Surveillance Station (SSS) on
demand, in addition to the short event clips Frigate already produces.

Driver: Frigate event clips are intentionally short (now 20+15s pre/post
post the 2026-05-03 bump). For most family review needs, that's enough.
For the residual 20% — multi-event sequences, sensitivity gaps, longer
observation windows — we want the option to draw arbitrary windows from
SSS, which retains main-stream video for the full fox season.

This is **deferred work**. Soak the new pre/post + threshold settings
for a week or two; pick this up when usage shows real demand.

## Levels of implementation

Three architectural levels along the easy↔great spectrum. We commit to
**Level A** with a clean upgrade path to **Level B** if real-world
usage warrants. Level C is documented for completeness but parked.

### Level A — Pull-then-serve (the v1 commitment)

Synchronous fetch: family clicks button → curator pulls SSS chunk →
ffmpeg cuts the requested window → cached MP4 served back. User sees
a spinner for 8–25s on cold cache, instant on warm.

**Latency budget (cold path):**
- SSS auth (cached SID): ~0ms
- Recording.List call: ~500ms
- Segment download (one ~5min chunk, 80–250MB): 1–5s on LAN, possibly 3–8s through Cloudflare Tunnel
- ffmpeg cut (`-ss N -t M -c copy`): ~2s
- Browser receive + start playback: 1–3s
- **Total worst-case: ~25s**

**Why this is acceptable as v1:**
- Idempotent caching means repeat clicks on the same window are instant
- Pre-warming on highlight save (Level A.1 below) eliminates cold-cache for high-likelihood events
- Single-flight per (event_id, before, after) prevents duplicate fetches under family-concurrent use

### Level A.1 — Pre-warming (small extension to A)

When the curator saves a highlight with `fox_likelihood >= 0.8` OR
`favorited=true`, fire-and-forget a background job that pulls a
default `±30s` window. By the time anyone clicks the deep-dive button,
the cache is warm. Eliminates the cold-path latency for the events
families actually care about.

Implementation: `notify.maybe_notify` already runs at the right point
in the lifecycle. Add a parallel `deep_dive.maybe_prewarm(highlight)`
call there.

### Level B — Streaming-while-fetching (deferred extension)

Pipe ffmpeg's output directly to the HTTP response (chunked transfer
or fragmented MP4). User starts watching at ~3s instead of waiting for
full segment download. Trades caching simplicity for perceived speed.

**Why deferred:**
- Caching is harder (need to tee stream to disk while serving)
- Mid-stream failures leave half-played clips with no clean resume
- Level A.1 pre-warming addresses most cold-cache pain anyway

**When to revisit:** If usage telemetry shows users frequently
requesting windows the pre-warmer didn't cover (e.g., older favorites,
non-default windows).

### Level C — Live-stream-from-SSS-RTSP (parked)

SSS exposes per-camera RTSP with seek-to-past capability. Treat
deep-dive as another stream like the live cam view. Real but a lot of
work — duplicates the WebRTC/MSE plumbing for SSS streams plus seek
handling plus auth proxying.

**Not committing to this.** If we ever want a "scrub through the SSS
timeline" experience, we'd start fresh on a different design.

## Architecture (Level A)

### Curator additions

**New module: `frigate_curator/sss_client.py`**

```python
class SSSClient:
    """Thin HTTP client for SSS Web API. ~80 lines.

    DSM 6.2.4 quirk: after Auth.Login returns 200, you must call
    SurveillanceStation.Info.GetInfo before the session is usable.
    Otherwise downstream calls return 105 (no permission).
    """
    def __init__(self, base_url: str, user: str, password: str): ...
    def login(self) -> str: ...                       # cached SID, ~12h TTL
    def list_recordings(camera_id: str, start_ts: float, end_ts: float) -> list[Recording]: ...
    def download_recording(rec_id: str, dest: Path) -> Path: ...
    def get_motion_events(camera_id: str, since: float) -> list[MotionEvent]: ...
```

**New module: `frigate_curator/deep_dive.py`**

```python
def fetch_window(highlight: dict, before_s: int, after_s: int) -> Path:
    """Idempotent. Returns cached path if exists, else fetches + cuts.

    Cache key: (event_id, before_s, after_s).
    Cache path: HIGHLIGHTS_ROOT/<day>/deep-dive/<event_id>_-{before}+{after}.mp4

    Single-flight via per-key asyncio lock so simultaneous family
    clicks don't fire duplicate SSS calls.
    """
```

**Camera-name mapping**

SSS uses its own camera IDs (1, 2, 3...) while Frigate uses names
(`fox_den_1`, `fox_den_2`, `fox_den_3`). Add a config map:

```python
SSS_CAMERA_MAP = {
    "fox_den_1": int(os.environ.get("SSS_CAM_ID_FOX_DEN_1", "1")),
    "fox_den_2": int(os.environ.get("SSS_CAM_ID_FOX_DEN_2", "2")),
    "fox_den_3": int(os.environ.get("SSS_CAM_ID_FOX_DEN_3", "3")),
}
```

Camera IDs are visible in SSS's web UI under Camera List; one-time
configuration in `.env`.

**New endpoints in `main.py`**

```python
POST /highlights/{event_id}/deep-dive
     body: { "before_s": 0, "after_s": 30 }
     202 { "job_id": "...", "status": "fetching", "estimated_seconds": 12 }
     idempotent on (event_id, before_s, after_s)

GET  /deep-dive/{job_id}
     200 { "status": "ready", "url": "/highlights/<eid>/deep-dive/-0+30.mp4" }
     200 { "status": "fetching", "progress": 0.6 }
     200 { "status": "failed", "error": "sss_unreachable" | "expired" }

GET  /highlights/{event_id}/deep-dive/{spec}.mp4
     FileResponse — cached chunk; supports HTTP 206 range requests
```

### Viewer additions (fox-cam-public)

**New action buttons on each card** (next to ⭐ 🚫 🔗):

```
[+30s] [+1m] [-30s before]
```

Click handler:
1. POST `/api/highlights/<id>/deep-dive` with the window spec
2. Poll `/api/deep-dive/<job_id>` every 1s
3. On `ready`, swap the inline `<video>` to the new URL with autoplay
4. On `expired`, show inline "Archive too old — clip is past SSS retention"
5. On `failed:sss_unreachable`, show "Archive temporarily unavailable"

Spinner shows elapsed seconds during fetch ("fetching… 7s") so it
feels alive. Falls back to the original Frigate clip if user clicks
away.

### Auth model

The fox-cam-public viewer already gates everything behind Cloudflare
Access. The deep-dive endpoint inherits that policy — no new auth
surface. Family-member email passes through via
`cf-access-authenticated-user-email` for attribution
("Mary requested a 30s deep-dive on this clip"; useful telemetry,
optional to show).

## Configuration

Add to `.env`:

```bash
# SSS deep-dive (Phase 13)
SSS_BASE_URL=http://192.168.7.81:9900
SSS_USER=frigate-curator
SSS_PASS=<see-secrets-vault>
SSS_CAM_ID_FOX_DEN_1=1
SSS_CAM_ID_FOX_DEN_2=2
SSS_CAM_ID_FOX_DEN_3=3
DEEP_DIVE_PREWARM_THRESHOLD=0.8   # fox_likelihood at which to auto-pre-warm
```

Pre-create an SSS user `frigate-curator` with **Surveillance Station
Manager** role limited to view + recording-export permissions on the
three fox cameras only. No admin, no other features.

## Failure modes and mitigations

| Failure | Detection | Mitigation |
|---|---|---|
| SSS down (DSM update, crash) | Auth.Login or Info.GetInfo fails | Return `{ "status": "sss_unavailable" }`, exponential backoff in client, primary 10s clip remains playable |
| SSS session expired mid-call | API returns 105 or 401 | One-shot re-auth + retry; surface failure if second attempt fails |
| Recording past retention (404) | Recording.List returns empty | Return `{ "status": "expired" }` with retention boundary date |
| Concurrent family clicks | Multiple POST deep-dive in flight | Single-flight via `(event_id, before, after)` lock; subsequent callers join the existing job |
| Tunnel saturation under heavy use | Cloudflared metrics show queue depth growing | Add ffmpeg re-encode to ~1.5 Mbps (10s CPU per 30s clip; 5–7MB instead of 15–30MB) |
| Cache disk balloon | janitor cron | Drop deep-dive caches >60d old not associated with a favorited highlight |

## Pre-flight checks (before starting)

- [ ] Verify SSS retention is currently spanning the full fox season (user confirmed 2026-05-03)
- [ ] Identify SSS camera IDs for each Frigate camera (`fox_den_1` → SSS ID ?)
- [ ] Create dedicated SSS user with limited permissions
- [ ] Test SSS Web API auth from the Mac mini: `curl 'http://192.168.7.81:9900/webapi/auth.cgi?api=SYNO.API.Auth&version=6&method=login&account=USER&passwd=PASS&session=SurveillanceStation&format=cookie'`
- [ ] Verify Recording.List returns recent records: `curl '/webapi/entry.cgi?api=SYNO.SurveillanceStation.Recording&method=List&version=6&fromTime=...&toTime=...'`

## Implementation order (when picked up)

1. **`sss_client.py`** with login() + list_recordings() + download_recording(). Smoke test from a REPL: pull a known recording window, save MP4, play it.
2. **`deep_dive.py`** with fetch_window(). Test with a hard-coded event, verify caching + idempotence + ffmpeg cut.
3. **`main.py` endpoints** + curator-side polling/job state. Test via curl.
4. **viewer button** with one hardcoded `+30s` action. Real family flow.
5. **Pre-warming hook** in the curator's save path (Level A.1).
6. **Other window options** (`+1m`, `-30s before`, etc.) once the basic flow is validated.

Each step lands as its own commit; the feature is not user-visible
until step 4. Pre-step rollback is just deleting the new files.

## Out of scope (revisit only if pain emerges)

- Streaming-while-fetching (Level B)
- Live RTSP scrubbing (Level C)
- SSS motion-event correlation as an independent index ("show me SSS-detected motion that Frigate missed")
- Re-encoding to lower bitrate before serving (only if tunnel saturates)
- Per-family-member deep-dive history / "things you've reviewed"
- Fancier window UI (slider, named presets like "before/after/full visit")
- Cross-camera composite ("show all 3 cameras at this timestamp side-by-side")

## Open questions

1. **Default window sizes** — `+30s` after seems right for "where did it go." Should "before" be a separate button or merge into a single `[full visit]` that's `-15+30s`?
2. **Pre-warming aggressiveness** — only at `fox_likelihood >= 0.8`? Or also on every favorite click? Or every demote click (so we can review what was wrong)?
3. **Attribution display** — do we surface "Mary deep-dived this clip" anywhere, or just record it silently?
4. **Multi-window caching** — do we cache `±30s` separately from `±60s`, or always cache the larger and serve subsets via Range requests? Larger-cache approach is simpler but uses more disk.

These are addressable when the work starts — listing them so we don't
forget to revisit.
