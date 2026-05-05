# Our Foxes — iOS PWA Implementation Tasks

**Branch:** `ios-pwa`
**Source audit:** `docs/plans/2026-05-05-fox-cam-mobile-pwa-audit.md`
**Created:** 2026-05-05 (post-review by coherence + feasibility + scope-guardian agents)

This is the buildable task list. Decisions resolving audit ambiguities, items
cut as YAGNI for a 5-family-member private site, and feasibility risks called
out by code-sampling against `fox-cam-public/static/*` are encoded directly
into the task descriptions.

---

## Decisions resolving audit ambiguities

| Question | Decision | Rationale |
|---|---|---|
| Gate iOS fixes by `body.ios`/`body.ios-pwa` (UA) or `@media (hover: none)` (capability)? | **`body.ios`/`body.ios-pwa`**, UA-based. Use `(hover: none)` only where the rule is genuinely capability-based (e.g. tap-target sizing). | User's framing requires this. Keeps desktop bundle untouched. |
| §4 swipe vs §6.4 reposition prev/next? | **Hide arrows on touch + add swipe.** Reposition is dead. | Easier to verify without iOS device; native pattern. |
| §1 hover-only inventory: which fix per element? | Always-visible on touch for: archive icon, modal nav, zoom controls (modal + live). Drop card hover-preview entirely on touch (no replacement; static thumb). | Scroll-into-view autoplay deferred (bandwidth + race risk). |
| `display_override` in manifest? | **Skip.** | iOS Safari ignores it; no behavior change. |
| Periodic Background Sync warm-up? | **Cut.** | Not implemented on iOS Safari. |
| HLS pipeline? | **Cut.** | Over-engineering for 5 family viewers on home Wi-Fi. |
| Web Push? | **Cut.** | ntfy.sh already covers this with a real iOS app. |
| Splash screens? | **Cut.** | Polish for a brief white flash; not worth per-device PNG generation. |
| Pull-to-refresh? | **Cut.** | Browser reload + tab tap already does it. |
| Long-press menu? | **Cut.** | L effort, four actions already reachable by tap. |
| Double-tap favorite? | **Cut.** | Conflicts with browser double-tap-zoom. |
| Filter row → sheet button? | **Defer.** | Wraps to 3 rows but still functional. Revisit if anyone complains. |
| Swipe-down to close modal? | **Defer.** | Backdrop tap + X work fine. Revisit with bottom-sheet modal. |
| Tabs scroll breakpoint precision | `max-width: 480px`, `scroll-snap-type: x mandatory`, active tab snapped to start. | Most predictable iOS scroll-snap behavior. |
| `touch-action` on `.modal-video-wrap` (pinch vs swipe collision) | `touch-action: pan-y` so vertical pinch + horizontal swipe coexist. Scope swipe handler to dialog body, not the video wrap. | Avoids swallowing pinch. |

---

## Foundation (must land first)

### F1. iOS detection + body classes
- New file `fox-cam-public/static/ios-detect.js` (small, ~15 lines) that on load sets `document.documentElement.classList` (so it's available before body renders) AND `document.body.classList` (so existing `body.foo` selectors work) with:
  - `ios` if `/iPad|iPhone|iPod/.test(navigator.platform) || (navigator.userAgent.includes("Mac") && navigator.maxTouchPoints > 1)`
  - `ios-pwa` if iOS AND (`window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true`)
- Inline this script in `<head>` (NOT a separate `<script src>`) of all 4 templates so it executes before stylesheet evaluates `body.ios`-prefixed selectors. **Avoids FOUC.**
- Add data-attribute fallback: also set `document.documentElement.dataset.ua = "ios"` for any future need.
- Bump SW CACHE name in every commit that ships CSS/JS so iOS doesn't serve stale.

**Files:** `static/ios-detect.js` (new, but inlined in head), `templates/{landing,index,highlights,clip}.html`.
**Verify:** Open DevTools, simulate iPhone UA → `body.ios` present.

---

## Phase 1 — Make it work on iPhone (P0)

### P1.1 Safe-area insets (4 surfaces)
- Landing hero CTA: bump bottom margin to `max(28px, env(safe-area-inset-bottom))`. **landing.css**.
- `/live` grid container: switch `100vh` math to `100dvh` and inject safe-area on top/bottom (`calc(100dvh - env(safe-area-inset-top) - env(safe-area-inset-bottom))`). **style.css** lines around `.live-layout[data-mode="grid"]` and the spotlight rules. Verify spotlight doesn't break.
- All authed page headers (`<header>` in style.css): `padding-top: max(1rem, env(safe-area-inset-top))` (already partial; ensure consistency).
- Card modal (`.card-modal` in warm-theme.css): `padding-bottom: env(safe-area-inset-bottom)`.

**Gate:** universal — `env()` is harmless on desktop (resolves to 0).
**Effort:** S.

### P1.2 Tap-targets ≥ 44pt under `(hover: none)` AND `body.ios`
- `.action-btn`: `min-height: 44px; min-width: 44px; padding inline-block adjusted`.
- `.zoom-btn` (currently 32–34px): `width: 44px; height: 44px`.
- `.card-modal-close` (×): `width: 44px; height: 44px; font-size scaled`.
- `.card-modal-replay`: same.
- `.archive-toggle`: same. Keep visual size via `padding`/`background-size` so the look isn't disrupted; the hit-area is what changes.

**Gate:** wrap in `@media (hover: none) { ... }` so this also catches Android/touchpad-Mac users without harming desktop trackpad UX. The `body.ios` framing is reserved for iOS-only behavior; tap-target sizing is universally a touch concern.
**Effort:** S.

### P1.3 Hover-only affordances → always-visible on touch
Within `@media (hover: none)`:
- `.archive-toggle { opacity: 0.7 }` (currently `opacity: 0` until card hover).
- `.modal-nav { opacity: 0.55 }`.
- `.zoom-controls { opacity: 0.7; pointer-events: auto }` (modal + live cam tile).
- Drop card hover-preview entirely on touch — leave the static thumbnail. **Gate via `body.ios`** to keep Android touch unaffected by this specific decision (Android can still preview if user wants; only iOS gets the "no preview" experience because that's what we tested for).

**Files:** warm-theme.css mainly, card.js (skip mouseenter binding when `body.ios`).
**Effort:** S.

### P1.4 Hide modal prev/next arrows on iOS + add swipe gestures
- CSS: `body.ios .modal-nav { display: none }`. Desktop keeps arrows.
- Swipe handler in modal.js: bind on `dialog` element (NOT `.modal-video-wrap` — pinch lives there).
  - `touchstart` → record `touchStartX`, `touchStartY`, `touchStartTime`.
  - `touchend` → compute dx, dy, dt. If `|dx| > 60 && |dx| > |dy| * 1.5 && dt < 600`, fire navigation.
  - **Branch on mode:** if `currentRemix` set, use `slideToRemix` walking `window.REMIX_NAV_LIST`. Otherwise use `slideToCard` mirroring the keyboard handler's `findSiblingIds()` lookup (modal.js:264–274). Don't reference `prevId`/`nextId` directly — they're locals in `renderViewer`.
- Set `touch-action: pan-y` on `.card-modal-body` so vertical scroll + horizontal swipe coexist; pinch on `.modal-video-wrap` continues to work via panzoom (panzoom binds gestures itself).
- Skip swipe close-on-down for now (deferred per scope).

**Files:** modal.js, warm-theme.css.
**Effort:** M (~1.5h budgeted; the 33% of Phase 1).

### P1.5 Tabs row horizontal scroll on phone
- In `warm-theme.css`, target `@media (max-width: 480px) .tabs`:
  ```
  flex-wrap: nowrap;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;  /* legacy iOS smooth scroll */
  ```
- `.tab` gets `scroll-snap-align: start; flex-shrink: 0`.
- Hide scrollbar via `::-webkit-scrollbar { display: none }` for visual cleanliness.

**Effort:** S.

### P1.6 Hero logotext min-width for iPhone SE
- `landing.css`: locate `clamp(420px, 48vw, 720px)` on the logo, change to `clamp(280px, 60vw, 720px)`.

**Effort:** S (one line).

### P1.7 Autoplay-rejection scrim on `/live`
- Single instrumentation point: in `live.js`'s `start(video, stream, status)` (line ~454), wrap the eventual `video.play()` calls in `tryWebRTC` and `runMSE`. When `play()` rejects with `NotAllowedError`, dispatch a custom event `fox-live:needs-tap` on `document`.
- New scrim in `index.html`: hidden by default, listens for `fox-live:needs-tap`, shows a translucent overlay over the live grid with text "Tap to start live cameras". On tap, calls `video.play()` on all 4 grid-stream videos.
- After ANY successful play (any cam), dismiss the scrim — one tap unblocks all.
- Gate: only render scrim under `body.ios`. Other browsers either autoplay successfully or already handle it.

**Files:** live.js, index.html, style.css/warm-theme.css for scrim style.
**Effort:** M (~45 min).

### P1.8 Verify modal pinch-zoom on iOS via panzoom
- Add `touch-action: none` on `.modal-video-wrap > video` (the actual video element panzoom binds to). Panzoom needs to capture all gestures on the video itself.
- Keep `touch-action: pan-y` on `.card-modal-body` (parent).
- This delineates: vertical scroll on the modal body, all gestures on the video.

**Effort:** S.

### P1.9 Web Share API for the share button
- In modal.js's share button handler: if `navigator.share`, call `navigator.share({ url, title: "Our Foxes — clip", text: "Fox cam clip" })`. Fall back to current clipboard logic if rejected, missing, or fails.
- Don't gate on `body.ios` — Web Share works on iOS Safari, Chrome Android, and macOS Safari 14+; let it light up wherever supported.

**Effort:** S.

---

## Phase 1 commit plan

Group into ~5 commits to keep blast radius small and review-friendly:

1. **F1** foundation (detection script + template head edits + first SW bump).
2. **P1.1 + P1.6** safe-area + logotext (CSS-only).
3. **P1.2 + P1.3 + P1.5** tap-targets + always-visible-on-touch + tabs scroll (CSS + small card.js change).
4. **P1.4 + P1.8** modal swipe + touch-action (modal.js + CSS).
5. **P1.7 + P1.9** autoplay scrim + Web Share (live.js + modal.js).

Each commit: rebuild fox-cam-public, run `correctness-reviewer` + `maintainability-reviewer` + `project-standards-reviewer` in parallel against the diff, address blocking findings, commit. Final commit: bump SW CACHE.

---

## Phase 2 — Make it feel native (P1, after Phase 1 is verified on real iOS)

### P2.1 Bottom-sheet modal on phones (≤720px)
Per audit §2 sketch. Pure CSS for the layout + slide-up animation. Pair with the existing swipe handler from P1.4 (hook the down-swipe path back on, since now the gesture matches the visual metaphor).

### P2.2 Verify offline `/highlights` shell
- Audit claim: SW network-first caches HTML on first successful fetch. Verified by reading sw.js — but the **first cold-load offline** fails because there's nothing in cache yet.
- Fix: in `install` handler, precache `/highlights` (will fetch authed; CF Access cookie present at install time). If precache 401s (token expired), don't fail install — let runtime cache it instead.

### P2.3 Add iOS-specific manifest tweaks (drop ones that don't work)
- `apple-mobile-web-app-status-bar-style: black-translucent` in landing template only (so hero gradient runs under status bar). Other authed pages stay `default`.
- Skip `display_override` (iOS ignores).
- Skip `orientation: portrait-primary` for now — iPad use case wants free orientation.

---

## Phase 3 — Cut entirely

Per scope-guardian review:
- HLS encoding pipeline.
- Web Push.
- Periodic Background Sync.
- Splash screens (per-iPhone-resolution PNGs).
- Per-iPhone-model animation throttling.
- Pull-to-refresh JS.
- Long-press context menu.
- Double-tap favorite.
- Scroll-into-view autoplay.
- Cellular-aware preview gating (only matters once IO autoplay ships).
- Filter row → sheet button.
- Swipe-down to close modal (revisit with P2.1 bottom sheet).

If any of these become user complaints in practice, lift back into a future phase.

---

## Verification checklist (after Phase 1)

Owner: human, on real iPhone + iPad.

- [ ] iPhone Safari: `/` cold load, both orientations.
- [ ] iPhone PWA: cold launch, status bar visible, no content under home indicator.
- [ ] iPhone Safari: `/live` shows tap-to-enable scrim if autoplay blocked; one tap starts all 4 cams.
- [ ] iPhone Safari: `/highlights` tabs row scrolls horizontally with snap.
- [ ] iPhone Safari: tap a card → modal opens, swipe left/right navigates, no visible prev/next arrows.
- [ ] iPhone Safari: pinch-zoom in modal video works.
- [ ] iPhone Safari: share button opens iOS share sheet.
- [ ] iPhone Safari: archive icon visible (not invisible).
- [ ] iPhone Safari: every tap target ≥44pt (visual + accessibility inspector).
- [ ] iPad Safari: modal stays centered (NOT bottom sheet — Phase 1 only ships swipe + always-visible affordances).
- [ ] iPad Slide Over (≤320px): site stays usable.
- [ ] Desktop Chrome: nothing changed visually or behaviorally.
- [ ] Desktop Safari: nothing changed.

---

## Files this branch will touch

Per Phase 1:
- `fox-cam-public/templates/{landing,index,highlights,clip}.html` — inline detection script in `<head>`.
- `fox-cam-public/static/warm-theme.css` — most CSS.
- `fox-cam-public/static/landing.css` — hero CTA safe-area + logotext min-width.
- `fox-cam-public/static/style.css` — `/live` viewport math + tap-target media query.
- `fox-cam-public/static/modal.js` — swipe handler + Web Share.
- `fox-cam-public/static/live.js` — autoplay-rejection event.
- `fox-cam-public/static/card.js` — skip hover-preview on iOS.
- `fox-cam-public/static/sw.js` — CACHE bumps per commit.

Per Phase 2:
- All Phase 1 files +
- `fox-cam-public/static/sw.js` install-handler precache.
- `fox-cam-public/templates/landing.html` status-bar-style.

No new endpoints. No new dependencies.
