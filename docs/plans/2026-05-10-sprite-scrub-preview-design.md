---
title: Drag-to-scrub gallery preview via sprite sheets
status: draft
date: 2026-05-10
author: Chad Dorsey + Claude
related:
  - feat: HLS playback for clips (e6897601)
  - fix(card): disable scroll-autoplay (6aec7fe1)
---

# Drag-to-scrub gallery preview via sprite sheets

## Why this exists

The previous scroll-autoplay feature attached a `<video>` element streaming MP4 byte ranges to whichever gallery card was currently in the viewport center band. iOS Safari's HTTP/1.1 connection pool got starved by the in-flight Range requests across many recently-active cards — the user's modal opens routinely waited 30-90 seconds before iOS could free up a connection for HLS. After exhausting mitigations (single concurrent video, in-flight teardown on modal-open, cross-tab suspend), the cleanest fix was disabling scroll-autoplay entirely (commit `6aec7fe1`).

The user-visible regression: gallery cards no longer give a sense of what's in each clip until you tap to open the modal. That was the discovery affordance that "made the gallery feel alive."

This design replaces it with a **sprite-sheet preview**: a single JPG per clip containing 10-20 evenly-spaced frames stitched horizontally. The user drags a finger across a card to scrub through the frames, mimicking a video scrubber. Optional passive auto-cycle for users who don't drag.

The structural property that makes this safe: **gallery cards never load video bytes**. Each card's preview is one HTTP request for one image. iOS Safari's connection pool cannot be saturated by the gallery view, regardless of how many cards are visible.

## Goals

- Restore the "what's in this clip without tapping" discovery affordance.
- Map drag distance → frame index intuitively (linear, no acceleration).
- Static thumbnail when the card is idle (no JS, no animation cost).
- Tap behavior unchanged: opens modal with HLS playback.
- Per-clip sprite is generated once, cached forever, served immutably.

## Non-goals

- Live preview during scroll (that's the scroll-autoplay design that just failed).
- Audio preview.
- Any client-side frame extraction.

## Storage layout

Sprite lives next to the source MP4 and the HLS bundle:

```
/Volumes/main-filestore/frigate-highlights/
  YYYY-MM-DD/
    {event_id}.mp4              source clip
    {event_id}.jpg              static thumbnail (existing)
    {event_id}_hls/             HLS bundle (existing)
    {event_id}_sprite.jpg       NEW: drag-to-scrub frame strip
```

Why a single JPG instead of N individual frames:
- One HTTP request per card load instead of one per frame.
- iOS browser-cache friendliness: one cache entry, simpler invalidation.
- Disk-I/O friendliness: one file open instead of N.

## Sprite specifications

| Parameter | Value | Rationale |
|---|---|---|
| Frame count | **15** | Smooth enough at any reasonable card width, not so many that the sprite gets unwieldy |
| Frame width | 320 px | Matches existing card thumbnail render width |
| Frame height | derived from source aspect ratio | Most clips are 16:9 → 180 px |
| Layout | horizontal strip (15 × 320 = 4800 px wide) | CSS `background-position-x` is what the drag handler manipulates |
| Encoding | JPEG quality 75 | ~6-10 KB per frame → ~90-150 KB per sprite |
| Frame timing | evenly spaced across full clip duration | Frame 0 ≈ 0%, frame 14 ≈ 100% |

Estimated total storage for 966 clips: ~100-150 MB. Negligible against the 4.4 TB free on main-filestore.

## ffmpeg command

```bash
ffmpeg -hide_banner -loglevel error -y \
  -i "$SRC" \
  -vf "select='not(mod(n\,$STEP))',scale=320:-2,tile=15x1" \
  -frames:v 1 \
  -q:v 5 \
  "$OUT/${event_id}_sprite.jpg"
```

Where `$STEP = total_frames / 15` (computed via ffprobe first), or simpler with a time-based selector:

```bash
ffmpeg -i "$SRC" \
  -vf "fps=15/${duration},scale=320:-2,tile=15x1" \
  -frames:v 1 -q:v 5 \
  "$OUT/${event_id}_sprite.jpg"
```

Render time: ~0.5-2 sec per clip. Cheaper than HLS rendering (re-mux + audio re-encode); just a sparse frame extraction.

The ffmpeg invocation goes through the same `_render_semaphore` + `fcntl.flock` machinery as HLS rendering in `frigate_curator/hls.py`, so sprite renders never overlap with HLS renders or with each other across processes. One ffmpeg at a time, system-wide.

## New module: `frigate_curator/sprite.py`

Mirrors the structure of `hls.py` for consistency:

```python
def sprite_path_for(highlights_root, clip_relpath) -> Path: ...
def is_rendered(highlights_root, clip_relpath) -> bool: ...
def ensure_sprite_rendered(highlights_root, clip_relpath) -> Optional[Path]: ...
def prewarm_sprite_async(highlights_root, clip_relpath) -> None: ...
```

Shares the same render lock as HLS. Atomic publish via tmp + os.replace.

## Curator endpoints

```
GET /highlights/{event_id}/sprite.jpg
```

Response:
- 200: `Cache-Control: private, max-age=3600, immutable`, `Content-Type: image/jpeg`
- 404: sprite not rendered yet. Same non-blocking pattern as HLS — curator fires `prewarm_sprite_async` and returns 404 immediately. Browser falls through to static thumbnail.

## Proxy endpoint

```
GET /api/highlights/{event_id}/sprite.jpg
```

Reuses existing `_proxy_curator` — gets ETag forwarding, Range support, and cache-header passthrough for free. Same CF Access bypass posture as `/clip` and `/thumbnail` (anonymous featured viewers can see sprites for promoted clips).

## Pre-warm + backfill

**At ingest:** `curator.py` `_process_event` already fires `hls.prewarm_hls_async`. Add `sprite.prewarm_sprite_async` immediately after. Both render in series via the shared lock. New clips get both a sprite and an HLS bundle within seconds of being saved.

**Backfill:** new script `scripts/backfill_sprites.py`, parallel to `scripts/backfill_hls.py`. Walks the DB newest-first, calls `ensure_sprite_rendered` for each. Resumable. Skips clips that already have sprites. Run once, ~10-15 minutes wall for 966 clips.

## Client integration

### Card markup

The existing card thumbnail is an `<img>`. The sprite version uses a `<div>` with a CSS background, so we can shift `background-position-x` cheaply on touch:

```html
<div class="thumb-wrap"
     data-sprite-url="/api/highlights/{event_id}/sprite.jpg"
     data-frame-count="15"
     data-duration="29.5">
  <img class="thumb-static" src="/api/highlights/{event_id}/thumbnail">
  <!-- on first touch, JS replaces this with a div backed by the sprite -->
</div>
```

Static thumbnail loads first (fastest). Sprite fetches lazily on first user interaction with the card OR when the card enters the viewport (whichever we prefer; lazy-on-touch saves bandwidth).

### Drag handler (high-level)

```js
// On touchstart over a card:
//   1. Fetch the sprite (if not already cached). Show a thin progress indicator.
//   2. On each touchmove, compute (touchX - cardLeft) / cardWidth → fraction.
//   3. frameIndex = floor(fraction * frameCount), clamped to [0, frameCount-1].
//   4. Set background-position-x: -(frameIndex * 320px).
//   5. On touchend without significant horizontal movement (< 8px): treat as tap → openCardModal.
```

Touch event handling needs to coexist with the existing tap-to-open and double-tap-to-favorite logic in `card.js`. The discriminator is **horizontal movement during touchmove**:

| Gesture | Detection | Outcome |
|---|---|---|
| Tap (no movement, <300ms) | dx<8, dy<8, dt<300 | open modal |
| Double-tap | second tap within 280ms | favorite (existing behavior) |
| Horizontal drag | dx>=8 with |dy| < |dx| | scrub frames |
| Vertical scroll | |dy| > |dx| | let the page handle (don't capture) |

The detection is a state machine on the touchstart→touchmove→touchend sequence. Implementation in card.js, ~80 lines.

### Visual affordance

A thin pill at the bottom of the card shows current scrub position:

```
[━━━━━●━━━━━━━━]
       ^ thumb at frame N
```

Appears on first touchmove, fades out 400ms after touchend. Pure CSS transitions.

## Open questions

1. **Frame count.** 15 frames is a guess that balances smoothness against sprite size. Could be 10 (smaller sprite, jumpier scrub) or 20 (smoother, larger). Suggest starting at 15 and tuning after testing on real touch hardware.

2. **Optional passive auto-cycle.** Once sprites exist, we could *optionally* tween through 4-5 frames every few seconds when a card is visible — animated-thumbnail style without network cost beyond the one-time sprite fetch. This would re-introduce *some* of the "gallery feels alive" affordance for users who don't drag. Off by default. Decided post-MVP.

3. **Long clips.** Manual-recovery clips can be 5-10 minutes. 15 evenly-spaced frames = one frame per 20-40 seconds. May feel coarse. Could conditionally use more frames for longer clips, capped at e.g. 30 frames (still ~200 KB sprite).

4. **Featured-clip permalinks.** The `/clip/{id}` page is single-clip and HLS-driven; do users benefit from the sprite there? Probably not — they're already past the discovery point. Skip.

5. **Remix gallery.** Remix tab cards are a different surface. Sprites don't apply to remixes naturally (a remix is already a 5-30s curated clip). Out of scope.

## Failure modes

| Scenario | Behavior |
|---|---|
| Sprite render fails (corrupt source, weird codec) | Sprite endpoint 404s. Card falls back to static thumbnail. Drag is a no-op. Self-healing. |
| Sprite missing because backfill hasn't reached this clip | Endpoint 404s, fires async prewarm, card uses static thumbnail. Next visit (post-render) gets the sprite. |
| Slow disk during sprite fetch | Sprite is ~100 KB, single request. Worst case: 1-2 second delay before drag is responsive. Static thumbnail visible throughout. |
| User on saveData connection | Skip sprite fetch entirely. Drag is a no-op. Static thumbnail only. Already standard pattern in the codebase. |
| iOS Safari connection pool stress (post-feature) | Impossible to recreate the scroll-autoplay starvation: each sprite is exactly one HTTP request. Even 100 visible cards = 100 image fetches, well within iOS's HTTP/2 multiplexing capacity through CF tunnel. |

## Implementation phases

| Phase | Scope | Time |
|---|---|---|
| 1. `sprite.py` module + ffmpeg command | core renderer with shared lock | ~1 hour |
| 2. Curator endpoint | `GET /highlights/{id}/sprite.jpg` with non-blocking prewarm | ~30 min |
| 3. Proxy endpoint | reuse `_proxy_curator` | ~15 min |
| 4. Auto-prewarm at ingest | one line in `_process_event` | ~10 min |
| 5. JS drag handler | touch state machine + scrub UI | ~2-3 hours |
| 6. Backfill script | `scripts/backfill_sprites.py` | ~30 min code + ~15 min runtime |
| 7. SW cache strategy | precache nothing extra; sprites benefit from browser HTTP cache | ~5 min |
| 8. Testing | iOS Safari, desktop, gallery scroll, modal interaction | ~1-2 hours |
| **Total** | | **~6-8 hours** |

Pull request: a single feature commit. The sprite module + endpoint + JS handler + backfill all share the same shape and ship together. Optional auto-cycle is deferred to a follow-up if wanted.

## Out of scope

- Re-introducing scroll-autoplay in any form.
- Server-pushed live preview.
- Audio preview.
- Per-user customization of frame count or scrub sensitivity.

## Decision

Pending user approval. Recommend scheduling for a focused half-day session after the WD enclosure is replaced (current hardware can handle the sprite render cost cleanly, but doing it during a stable hardware window minimizes confounding variables).
