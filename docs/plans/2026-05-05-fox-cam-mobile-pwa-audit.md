# Our Foxes — Mobile/PWA Cross-Device Audit + Remediation Plan

**Date:** 2026-05-05
**Scope:** Full surface audit of fox-cam-public (`/`, `/live`, `/highlights`, `/clip/*`,
`/highlights/{id}/remix`, `/remix/{id}`) targeting **iPhone Safari**, **iPad Safari**, and
**iOS PWA (Add-to-Home-Screen)**.

The site currently runs well on desktop Chrome/Safari with our recent feature push
(modal carousel, archive, slideToCard, MegaDetector clips, 4MP record, faststart,
panzoom-everywhere, Group Faves, contextual filters, replay button, delete-as-link).
None of that work has been validated on touch devices. This doc enumerates every
device-boundary issue I can identify and groups fixes by impact + effort.

---

## How to read this doc

Each item has:

- **Surface** — where it shows up (page / element)
- **Status now** — what exists today and how it behaves on iOS
- **Problem** — concretely what fails or feels wrong on iPhone/iPad
- **Fix direction** — the proposed change
- **Effort** — S (≤30min), M (1-2h), L (half day+)
- **Priority** — P0 (broken on touch), P1 (visible regression), P2 (polish/native convention)

---

## 0. PWA install + chrome on iOS

### 0.1 Apple-specific meta tags + icons

| Item | Status | Fix |
|---|---|---|
| `apple-touch-icon` (180×180) | ✅ present in `<head>` of all 4 templates | none |
| `apple-mobile-web-app-capable` | ✅ "yes" | none |
| `apple-mobile-web-app-title` "Our Foxes" | ✅ | none |
| `apple-mobile-web-app-status-bar-style` | ✅ "default" | Switch to **"black-translucent"** so the hero gradient runs under the status bar on the landing page. **P2 / S** |
| Splash screens (iOS launch images) | ❌ none | iOS uses launch images for PWA cold start; without them the user sees a white flash. Generate splash PNGs at the iPhone resolutions Apple expects (at least 1170×2532 = iPhone 13 Pro). **P2 / M** |
| `theme-color` | ✅ `#f05a28` everywhere | none |
| `manifest.webmanifest` | ✅ name/short_name/icons/start_url | Add `"display_override": ["fullscreen", "standalone", "minimal-ui"]` and `"orientation": "portrait-primary"` for phones (iPad stays free). **P2 / S** |
| `viewport-fit=cover` | ✅ | But we never use `env(safe-area-inset-*)` consistently. See §0.3. |

### 0.2 Service Worker behavior on iOS

- **iOS Safari is stricter** about SW eviction (~7 days idle, ~50MB cache cap).
- We use `cache-first` for `/static/*` and `network-first` for HTML routes.
- The recent `our-foxes-v31-filter-faves` cache name guarantees clients pick up the new code on next visit, BUT iOS may re-evict it during idle stretches and the user gets a momentary network round trip.

| Issue | Fix | Priority |
|---|---|---|
| iOS SW eviction during idle weeks | Add a weekly "warm-up" navigation hint via Web Periodic Background Sync (works in PWA mode on iOS 16.4+) | **P2 / M** |
| No offline fallback page | Cache `/highlights` HTML so an offline cold-start at least shows the gallery shell. Currently the SW does this via network-first + cache-fallback, but we never tested. | **P1 / S** verify only |

### 0.3 Safe-area insets (notch + home indicator)

| Surface | Issue | Fix |
|---|---|---|
| Landing hero CTA | Bottom 28px doesn't account for home indicator on iPhone with notch (visual content can be cut by the bar) | Add `env(safe-area-inset-bottom)` to the hero `<a class="hero-cta">` margin / footer padding. **P0 / S** |
| `/live` 2×2 grid | Calc `100vh - 88px` ignores the notch on landscape iPad and the home indicator on portrait iPhone | Use `100dvh` or `calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom))`. **P0 / S** |
| `/highlights` header sticky | Header sits flush with status bar in PWA mode → text overlaps | Add `padding-top: max(8px, env(safe-area-inset-top))` to `.landing-header` and authed `header`. **P0 / S** |
| Modal `<dialog>` | On iPhone the dialog can extend under the home indicator | Inside `.card-modal` add `padding-bottom: env(safe-area-inset-bottom)`. **P1 / S** |

---

## 1. Hover-only UI elements break on touch

Every "show on hover" interaction is **invisible on iOS** until the user taps the element by accident. This is the #1 cross-device parity issue.

### Inventory of hover-only affordances

| Element | File | Current behavior | Touch-device problem |
|---|---|---|---|
| Archive icon (top-right of card) | `card.js` `.archive-toggle` | `opacity: 0` until `.highlight:hover` | Invisible on iOS |
| Modal prev/next arrows | `modal.js` `.modal-nav` | `opacity: 0` until `.modal-video-wrap:hover` | Invisible on iOS |
| Modal zoom controls | `modal.js` `.zoom-controls` | `opacity: 0` until wrap hover | Invisible on iOS |
| Live cam zoom controls | `live.js` cam tile | `opacity: 0` until tile hover | Invisible on iOS |
| Card hover-autoplay video preview | `card.js` `.preview` | mouseenter/leave swap | No play preview on iOS |
| Featured card hover-autoplay (landing) | `landing.js` | mouseenter/leave | No preview on iOS |
| Modal close × hover scale | warm-theme.css | `transform: scale(1.15)` on hover | No scale feedback on iOS but X is always visible |
| Animals peeking on live tiles | `peeks.js` | runs always; only visual | OK — no hover dependency |

### Fix direction (P0 / M)

Detect touch primary input and switch the affected elements to **always-visible** with reduced visual weight:

```css
@media (hover: none), (pointer: coarse) {
  .archive-toggle             { opacity: 0.7; }   /* always visible */
  .modal-nav                  { opacity: 0.55; }
  .zoom-controls              { opacity: 0.7; }
  .modal-video-wrap .zoom-controls { opacity: 0.55; pointer-events: auto; }
  .cam .video-wrap .zoom-controls  { opacity: 0.6; pointer-events: auto; }
}
```

Plus the autoplay-preview replacement covered in §3.

---

## 2. Modal `<dialog>` vs. iOS sheet conventions

The card-detail modal is implemented as a centered `<dialog>` with backdrop click + ESC + close X. On phones this is **functionally fine** but violates the iOS convention. Native iOS apps use:

1. **Bottom sheets** that drag down to dismiss (mail, photos, share)
2. **Full-screen presentations** with a distinct close affordance
3. **Swipe gestures** between siblings (photos library)

### What I'd change

| Surface | Current | iOS-native swap | Effort | Priority |
|---|---|---|---|---|
| `.card-modal` | Centered dialog at `width: min(960px, 92vw)` | On phones (`<= 720px`): full viewport with rounded top corners, slides up from bottom. iPad keeps the centered dialog. | **P1 / M** | |
| Backdrop click to close | ✅ works on iOS | none | | |
| ESC to close | works only with hardware keyboard | Add a draggable handle at top with downward swipe → close | **P1 / M** | |
| Prev/next arrows | ‹ / › buttons + ←/→ keys | **Horizontal swipe** between cards. Reuse `slideToCard()` engine. | **P0 / M** | |
| Pinch-to-zoom on video | Bound via panzoom (lowercase) lib | Test on iOS — iOS Safari has its own pinch behavior on `<video>`. May need `touch-action: none` on `.modal-video-wrap` to prevent native interception. | **P0 / S verify** | |
| Modal nav arrows visible on touch | hover-only | See §1. On touch, render at low opacity always; OR remove entirely once swipe is wired. | **P0 / S** | |

### Sheet-style modal CSS sketch

```css
@media (max-width: 720px) {
  .card-modal {
    width: 100vw !important;
    max-width: 100vw !important;
    max-height: 92dvh !important;
    border-radius: 24px 24px 0 0;
    margin: 0 0 0 0;
    position: fixed; bottom: 0; left: 0; right: 0;
    transform: translateY(0);
    animation: sheet-up 0.32s cubic-bezier(.34,1.4,.64,1);
  }
  .card-modal::backdrop { background: rgba(42,24,16,0.55); }
  .card-modal-close { top: 14px; right: 14px; }
  /* Drag handle */
  .card-modal::before {
    content: "";
    position: absolute; top: 8px; left: 50%;
    transform: translateX(-50%);
    width: 40px; height: 4px;
    background: rgba(42,24,16,0.3);
    border-radius: 999px;
  }
}
@keyframes sheet-up {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}
```

---

## 3. Hover-autoplay → tap-to-preview (or scroll-into-view autoplay)

Highlight cards and landing-featured cards swap to a muted looping `<video>` on `mouseenter`. Phones have no mouseenter. Two valid replacements:

### Option A — Scroll-into-view autoplay (TikTok/Instagram pattern)

When a card is centered in the viewport, swap to the muted looping video and play it. As soon as it scrolls past, pause + revert to thumbnail. **Recommended** for phone landscape into vertical-scroll feed.

Implementation: `IntersectionObserver` with `threshold: 0.6`, swap thumbnail → video on cross-in, pause + remove on cross-out. Do this only when `(hover: none)` so desktop hover-preview keeps working.

### Option B — Tap-to-preview (3-tap interaction)

First tap = swap to video and play once. Second tap = open modal. Cumbersome; users learn it slowly.

| Surface | Current | Plan | Effort |
|---|---|---|---|
| `/highlights` cards | hover-autoplay preview | Add IntersectionObserver path under `(hover: none)` only. Disable on `prefers-reduced-motion`. | **P1 / M** |
| Landing featured cards (`landing.js`) | hover-autoplay preview | Same IO path. | **P1 / S** |
| Bandwidth concern | Each preview is a full-clip download | On metered connection (iOS reports `navigator.connection.saveData`) skip auto-play and only show on tap. | **P2 / S** |

---

## 4. Touch gestures we should add

| Gesture | Surface | Behavior | Effort | Priority |
|---|---|---|---|---|
| Swipe left/right in modal | Modal viewer | Navigate to next/prev card. Same `slideToCard()` engine. | **P0 / M** |
| Swipe down on modal | Modal | Close modal (matches iOS sheet) | **P1 / M** |
| Long-press card | Highlights gallery | Quick-action menu: ⭐ Favorite / 🚫 Not a fox / 🗃 Archive / Share. Uses iOS context menu API where available, custom menu otherwise. | **P2 / L** |
| Pull-to-refresh | `/highlights` header | Refetch the gallery. iOS users expect this. Use a simple JS implementation (not `overscroll-behavior` which iOS Safari ignores). | **P2 / M** |
| Pinch-to-zoom in modal video | Already via panzoom lib | Verify on iOS — `touch-action: none` may be needed on `.modal-video-wrap` so iOS doesn't intercept. | **P0 / S** |
| Double-tap to favorite | Card or modal | Instagram-style. Heart pulses on top. | **P2 / S** |

### Swipe implementation sketch (for modal navigation)

```js
let touchStartX = 0, touchStartY = 0;
modal.addEventListener("touchstart", (e) => {
  touchStartX = e.touches[0].clientX;
  touchStartY = e.touches[0].clientY;
}, { passive: true });
modal.addEventListener("touchend", (e) => {
  const dx = e.changedTouches[0].clientX - touchStartX;
  const dy = e.changedTouches[0].clientY - touchStartY;
  if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
    slideToCard(dx > 0 ? prevId : nextId, dx > 0 ? "prev" : "next");
  } else if (dy > 80 && Math.abs(dy) > Math.abs(dx)) {
    closeCardModal();
  }
}, { passive: true });
```

---

## 5. Native conventions worth leveraging

### 5.1 Web Share API (iOS Safari supports it)

`navigator.share({ url, title, text })` opens the iOS share sheet (iMessage, Mail, AirDrop, etc.). Currently the share button calls `navigator.clipboard.writeText` and shows a toast.

| Where | Current | Plan |
|---|---|---|
| Share button in modal | clipboard copy + "Link copied" toast | If `navigator.share`, call it (returns a promise that resolves on send / rejects on cancel). Fall back to clipboard on desktop. **P1 / S** |
| Featured card on landing | none | Add a small share affordance on long-press. **P2 / M** |

### 5.2 Web Push (iOS 16.4+ in installed PWAs only)

The fox cam already pushes via ntfy.sh which has its own iOS app. We could ALSO support web push for users who installed the PWA. Per-user preference (Notify me when foxes appear).

| Item | Effort | Priority |
|---|---|---|
| `Notification.permission` request flow on first PWA launch | M | **P2** |
| Service Worker `push` handler that displays the notification with the clip thumbnail | M | **P2** |
| `/api/notify-prefs` endpoint + per-user opt-in column | S | **P2** |

Defer until basics are solid.

### 5.3 Apple Pencil hover on iPad (iOS 16.4+)

Pencil hover IS picked up as `hover: hover` media query. So our existing hover patterns light up automatically. No fix needed.

### 5.4 Multitasking on iPad

Slide Over / Split View can shrink the viewport to ≤320px width. Current breakpoints:
- Landing: `<= 540px` → 1-column featured grid
- /live: `<= 720px` → vertical 4-row stack
- Filters: ✅ flex-wrap

Action: **test in Slide Over** and add a `<= 360px` breakpoint that drops some non-essential UI (e.g., who-am-i email).

---

## 6. Video playback specifics on iOS

### 6.1 `playsinline` on every `<video>` — ✅ already

iOS will fullscreen any `<video>` without `playsinline` on tap. We have it everywhere.

### 6.2 Autoplay restrictions

iOS allows autoplay only when:
- `muted` is set (we have this)
- `playsinline` is set (we have this)
- The page has been "interacted with" since the cold load (any tap is enough)

The /live grid streams are autoplay-muted from cold load. Should work but **iOS may reject the first cycle** until the user taps anywhere. We may need to show a "Tap to enable live" overlay if `video.play()` rejects.

| Item | Plan | Effort |
|---|---|---|
| /live cold start: detect `play()` rejection | If rejected, show a tap-to-enable scrim over the grid. One tap unblocks all four. | **P0 / M** |
| /highlights modal first open | Same — autoplay video on modal open may reject. | **P1 / S** |

### 6.3 HLS vs MP4

iOS Safari prefers **HLS (`.m3u8`)** for adaptive streaming. We're serving plain `.mp4` from disk; iOS plays it fine via the `<video>` element but doesn't get adaptive bitrate. Since clips are short (5-90s) and we recently bumped resolution to 4MP/4K, **a 30-second 4K clip is ~30MB** — that's a meaningful download on cellular.

| Plan | Effort | Priority |
|---|---|---|
| Per-clip HLS variant (1080p + 720p ladders) generated at clip-save time | **L** | **P2** |
| Cellular-aware: serve a smaller pre-encoded variant when `navigator.connection.saveData` is true | **M** | **P1** |

### 6.4 Custom controls vs iOS native

We use `controls` on the modal `<video>`. iOS shows a different control bar (no triple-dot menu; has "AirPlay" instead). The play/scrubber/fullscreen layout differs slightly. Generally fine; **the custom prev/next arrows we added overlap iOS's "AirPlay" button on the right**.

| Plan | Effort | Priority |
|---|---|---|
| On `(pointer: coarse)`, push prev/next arrows further from the right edge | **S** | **P0** |
| Or: hide our prev/next on touch entirely, rely on swipe gestures | **S** | **P0** |

---

## 7. Visual + typography on small screens

| Item | Issue | Plan |
|---|---|---|
| Card thumbs aspect 16:9 | Fine on phone | none |
| Card meta two rows | Top row (species + remix-count + camera pill) wraps awkwardly < 360px | Stack vertically when narrower than 360px |
| Tabs row scrolls | "All / My Faves / Group Faves / Remixes / No Foxes" overflows on portrait phone | `overflow-x: auto` with `scroll-snap-type` so the active tab stays in view. Already wrapped flex; need horizontal scroll mode below 480px. **P0 / S** |
| Filter row | 6 dropdowns wrap onto 3+ rows on phone | Collapse into a single "Filters" button that opens a sheet on phone. Desktop shows the row. **P1 / M** |
| Landing logotext | clamp(420px, 48vw, 720px) — too big on iPhone SE (375px) | Bump min to clamp(280px, 60vw, 720px). **P0 / S** |
| Hero parallax | Animation perf can stutter on older iPhones | Throttle / disable on iPhone < 13 (use UA hint or perf-budget). Already respects `prefers-reduced-motion`. **P2 / M** |
| Replay button + close × | 32px each — below iOS 44pt min | Bump to 44px on touch. **P0 / S** |
| Action-btn (heart, demote, etc.) | ~28px tall — below 44pt min | Bump min-height to 44px on touch. **P0 / S** |
| Zoom buttons | 34px — below 44pt min | Same. **P0 / S** |

### Typography on small screens

- Body uses Nunito 16px — fine
- Display uses Fredoka — renders well on iOS
- Headings inside modal `.modal-title` are 18px — could go to 17px on iPhone SE for better single-line fit

---

## 8. Animation + delight features on touch

| Feature | iOS behavior | Plan |
|---|---|---|
| Animal-deliverer (Squirrel/Fox-3/Bear) on action click | Works (CSS transforms + setTimeout) | none |
| Live cam peeks (Fox-2 every 30-90s) | Works (CSS animations) | Verify perf on iPhone SE |
| Parade on Promote (8 animals march) | Heavy: 8 simultaneous transforms | Reduce to 4 animals on `(pointer: coarse)` to save battery. **P2 / S** |
| Konami code + brand 5x-tap easter eggs | Konami works only with keyboard. 5x-tap on H1 works on touch. | none |
| Landing parallax | 60fps on M-series. iPhone older might stutter. Add scroll-rAF throttle. | **P2 / M** |
| Page-load entrance (logotext bounce, layer slide-up) | CSS-only, works on iOS | none |

---

## 9. Outstanding desktop issues that surface on iOS too

Re-listing because these were never validated mobile-side:

- **Slide-in card sometimes blinks** (we patched, but on iOS the GPU compositor may still snap)
- **Panzoom wheel** doesn't translate to touch — pinch should work via panzoom lib but **needs verification with two-finger pinch on a real iPhone**
- **Service worker stale-state** (had multiple iterations) — verify `chrome://serviceworker-internals` equivalent on iOS (Settings → Safari → Advanced → Web Inspector + macOS Safari)

---

## 10. Prioritized fix list (what I'd do when you green-light)

### Phase 1 — Make it work on iPhone (P0 only, ~half a day)

1. **Safe-area insets** on hero CTA, /live grid, header, modal bottom (§0.3) — **30 min**
2. **Tap-targets ≥44px** on touch (action-btn, zoom-btn, close ×, replay, archive) — **30 min**
3. **Hover→always-visible** on touch for archive icon, modal nav, zoom controls (§1) — **30 min**
4. **Swipe gestures in modal** (left/right = prev/next; down = close) — **1.5 hr**
5. **Tabs row horizontal scroll on phone** (§7) — **15 min**
6. **Hero logotext min-width** for iPhone SE (§7) — **5 min**
7. **Video autoplay rejection scrim** on /live cold load (§6.2) — **45 min**
8. **iOS prev/next arrow position** clear of AirPlay button (§6.4) — **15 min**

Total ≈ 4.5 hours. Result: site is fully usable on iPhone with native gestures.

### Phase 2 — Make it feel native (P1, ~1 day)

1. **Bottom-sheet modal on phones** with drag-down dismiss + slide-up animation (§2)
2. **Scroll-into-view autoplay** on /highlights cards in place of hover (§3)
3. **Web Share API** integration (§5.1)
4. **Filter row → "Filters" sheet button** on phone (§7)
5. **Cellular-aware preview gating** via `navigator.connection.saveData` (§6.3)
6. **Splash screens** for PWA cold start (§0.1)
7. **Verify offline fallback** for /highlights (§0.2)

### Phase 3 — Polish + advanced (P2, when time)

1. Long-press → quick-action menu (§4)
2. Pull-to-refresh on /highlights (§4)
3. Double-tap to favorite (§4)
4. HLS encoding pipeline for clips (§6.3)
5. Apple-style status-bar-style "black-translucent" + manifest tweaks (§0.1)
6. Animation throttling on lower-end iPhones (§8)
7. Web Push opt-in for installed PWA (§5.2)

---

## 11. Verification checklist (for after Phase 1 lands)

- [ ] iPhone Safari: load `/` cold, both portrait + landscape
- [ ] iPhone PWA (Add to Home Screen): cold launch, verify status bar + safe areas
- [ ] iPhone Safari: log in, /live shows all 4 cams within 5s
- [ ] iPhone Safari: tap a /highlights card → modal opens, swipe left/right works
- [ ] iPhone Safari: tap heart, verify ⭐ Mine bucket updates
- [ ] iPhone Safari: tap 🚫, verify the card moves to No Foxes
- [ ] iPhone Safari: pinch-zoom in modal video works
- [ ] iPhone Safari: long-press a card to share
- [ ] iPad Safari: landscape /live grid is 2×2 fitting the viewport
- [ ] iPad Safari: modal stays centered (not bottom sheet)
- [ ] iPad Slide Over (≤320px): site stays usable
- [ ] PWA: offline cold launch shows the gallery shell
- [ ] PWA: notification permission flow (when implemented)

---

## 12. Files this will touch

- `fox-cam-public/static/warm-theme.css` — most changes
- `fox-cam-public/static/landing.css` — safe-area + hero min-width
- `fox-cam-public/static/modal.js` — swipe, scroll-view-autoplay, tap-targets
- `fox-cam-public/static/live.js` — autoplay-rejection scrim
- `fox-cam-public/static/card.js` — IntersectionObserver autoplay path
- `fox-cam-public/static/highlights.js` — filter-as-sheet, tabs scroll
- `fox-cam-public/templates/*.html` — additional meta tags, splash screens
- `fox-cam-public/static/sw.js` — verify offline fallback shell
- `fox-cam-public/static/manifest.webmanifest` — display_override + orientation

No new assets needed except splash PNGs (Phase 2).

---

## TL;DR for a tired version of you

Half a day of work makes the site usable on iPhone. A full day of work makes it
feel native. The biggest wins:

1. Tap-targets ≥44px (we're sub-44 in 4 places)
2. Hover→always-visible on touch (archive icon is invisible right now)
3. Swipe gestures in modal (prev/next arrows are the wrong pattern)
4. Bottom-sheet modal on phones (centered dialog feels desktop-y)
5. Scroll-into-view autoplay (hover-preview never fires on iOS)
6. Safe-area insets (home indicator overlaps the CTA on a notched phone)

Call out which of those you want first when you're back; I have the
implementation sketches above so each is straightforward.
