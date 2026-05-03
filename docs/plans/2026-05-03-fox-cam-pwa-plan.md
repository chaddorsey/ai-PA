---
title: Fox Cam — PWA install plan
date: 2026-05-03
status: planned (deferred — bigger lift than initial sketch)
related:
  - docs/followups/2026-05-02-fox-cam-improvements.md (F10)
  - fox-cam-public/static/
  - fox-cam-public/templates/
  - fox-cam-public/app/main.py
---

# Fox Cam — PWA install plan

## Why this got bumped to "bigger consideration"

The naive PWA sketch is "add manifest.json + service worker, done." That
works for static content. fox-cam-public has three properties that make
it more involved:

1. **Auth via Cloudflare Access JWT** — every request needs the
   cf-access-jwt-assertion header, which CF injects only on requests
   that traverse the tunnel. Service workers intercept fetches *before*
   they reach the network; we have to be careful not to break the auth
   flow by serving a cached (and unauthorized-by-CF) response.
2. **Live streaming** — WebRTC and MSE-over-WebSocket are not
   service-worker-cacheable in any useful way. The SW must pass these
   through untouched.
3. **iOS Safari quirks** — PWA support on iOS is functional but has
   edge cases around media playback, push notifications, and offline
   behavior that desktop Chromium doesn't share.

This isn't a 30-minute job. Probably 4–6 focused hours to do well, plus
testing on multiple devices.

## Goals

In rough priority:

1. **Add to Home Screen** support — when a family member visits
   foxes.cd-ai-pa.work in Safari and chooses "Add to Home Screen," they
   get an icon launching a chromeless window directly into the live view.
2. **Faster cold-load** — service worker caches static assets (JS, CSS,
   icons) so PWA launches are near-instant. Today every load through
   Cloudflare round-trips for assets.
3. **Native gestures** in the standalone PWA window (no browser chrome
   stealing pinch-zoom or swipe).
4. **iOS web push** — eventually replace ntfy with native iOS push
   notifications via the Web Push API. Not v1; documented as a follow-up.

## Non-goals (for v1)

- **Offline support for highlights playback.** Clips are sourced from a
  server-side curator; "watch a fox visit while on a plane" isn't worth
  the storage + sync complexity. Service worker stays online-only for
  user-data routes.
- **Background sync of new highlights.** Push notifications already
  cover "tell me when something new happens"; a background sync adds
  complexity without clear UX benefit.
- **Custom splash screens beyond the manifest defaults.** Apple takes
  the manifest's icon + theme color and produces a reasonable splash;
  we don't need bespoke artwork in v1.

## Architecture

### 1. Web App Manifest (`/static/manifest.webmanifest`)

```json
{
  "name": "Fox Cam",
  "short_name": "Fox Cam",
  "start_url": "/",
  "display": "standalone",
  "orientation": "any",
  "background_color": "#0e1014",
  "theme_color": "#0e1014",
  "icons": [
    { "src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/static/icon-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

Plus `<link rel="manifest" href="/static/manifest.webmanifest">` and
`<meta name="apple-mobile-web-app-capable" content="yes">` in both
`index.html` and `highlights.html`.

### 2. Icon assets

Need these in `fox-cam-public/static/`:

- `icon-192.png` — 192×192, used by Android home screen
- `icon-512.png` — 512×512, used by Android splash + maskable fallback
- `icon-maskable.png` — 512×512 with safe-zone padding (for adaptive
  icon shapes on Android)
- `apple-touch-icon.png` — 180×180, iOS home screen icon
- `apple-touch-icon-precomposed.png` — same, for older iOS

Source: a vector fox/cam glyph rendered at each size. Any half-decent
SVG of a fox icon → ImageMagick or `rsvg-convert` to bake out the PNGs.

### 3. Service worker (`/static/sw.js`)

Minimal, cache-first for static, network-only for everything else:

```js
const CACHE = "fox-cam-v1";
const STATIC_ASSETS = [
  "/", "/highlights",
  "/static/style.css", "/static/card.js",
  "/static/live.js", "/static/highlights.js", "/static/clip.js",
  "/static/icon-192.png", "/static/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC_ASSETS)));
});

self.addEventListener("activate", (e) => {
  // Drop old caches on version bump.
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
  ));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // Bypass everything that needs CF Access auth or live streaming.
  // The SW must NOT cache or interpose these — let them pass through.
  if (url.pathname.startsWith("/api/")) return;            // auth-gated JSON
  if (url.pathname.startsWith("/api/webrtc/")) return;     // WebRTC signal
  if (url.pathname.startsWith("/api/mse/")) return;        // WebSocket MSE
  if (e.request.headers.get("upgrade") === "websocket") return;

  // Static asset → cache-first.
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(e.request).then((cached) =>
        cached || fetch(e.request).then((r) => {
          // Only cache successful 200s; CF auth failure (401) etc. should not poison cache.
          if (r.status === 200) {
            const copy = r.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
          }
          return r;
        })
      )
    );
    return;
  }

  // HTML pages → network-first with cache fallback. Network-first
  // because the asset versioning (?v=...) lives in HTML and we want
  // the latest version when online.
  if (url.pathname === "/" || url.pathname === "/highlights" ||
      url.pathname.startsWith("/clip/")) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // Default: pass through.
});
```

Registered in `index.html` / `highlights.html`:

```js
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("/static/sw.js").catch(console.error)
  );
}
```

### 4. CF Access compatibility

The big risk: a service worker can serve a cached HTML page that the
browser then tries to interpret with stale `cf-access-jwt-assertion`
state, and the JS inside makes API calls that 401. We avoid this by:

- Caching only `/` and `/highlights` HTML, not their derived state
- Ensuring all `/api/*` calls bypass the SW entirely (network-only)
- On 401 from any API, force a hard reload to re-trigger CF Access

Add to all fetch error handlers:
```js
if (response.status === 401) location.reload();
```

This makes a CF cookie-expiry feel like "the page reloaded once and now
works" rather than "everything is broken."

### 5. iOS standalone-mode fixes

Several behaviors differ in standalone vs. browser-tab on iOS:

- **`apple-mobile-web-app-status-bar-style`**: set to `black-translucent`
  in a `<meta>` so the system status bar matches the dark theme
- **Safe-area insets**: pad the header for the notch/home indicator:
  ```css
  header { padding-top: max(1rem, env(safe-area-inset-top)); }
  main   { padding-bottom: max(4rem, env(safe-area-inset-bottom)); }
  ```
- **`autoplay muted playsInline`** on all videos (already done in
  card.js) — required for autoplay in iOS standalone mode
- **Pinch-to-zoom passthrough**: `<meta name="viewport" content="...maximum-scale=1">`
  if we don't want the OS to pinch-zoom the page (we don't, since our
  pinch is on individual videos)

### 6. PWA-aware spotlight + zoom interaction

This is the bit that affects the **current** zoom work:

- Pinch-zoom on a video element works in PWA standalone mode without
  fighting Safari's UI (no two-finger page scroll to fight).
- `touch-action: pinch-zoom` on the wrapper lets the OS pinch-zoom
  (browser tab) BUT panzoom-level pinch lands on the video. Both
  coexist.
- For PWA standalone where there's no browser to pinch-zoom: pinch
  goes straight to the video. Same code path; behavior is just
  cleaner.

**No special PWA-only code needed for zoom**, as long as we don't
disable pinch globally with `touch-action: none` on the body.

### 7. Push notifications (deferred follow-up)

iOS 16.4+ supports Web Push for installed PWAs. To replace ntfy:

- Generate VAPID keypair on the server
- Endpoint to register a PushSubscription per user (keyed by CF email)
- Send pushes via `web-push` library when curator promotes a
  fox-classified highlight
- iOS shows the same banner UX as ntfy

**Not v1.** ntfy works today across all devices regardless of PWA install.
Migrate to Web Push later only if we want to consolidate notification
plumbing.

## Implementation order (when picked up)

1. **Manifest + icons + meta tags** in templates. Visit-from-Safari →
   "Add to Home Screen" works, app launches in standalone mode. Useful
   on its own; doesn't need SW.
2. **Service worker** — cache static assets only. Confirm CF Access
   doesn't break.
3. **iOS-specific polish** — status bar, safe-area, viewport.
4. **Test on actual devices** — at minimum: iOS Safari install, Chrome
   Android install, Chrome desktop install. Each has different quirks.
5. **(later)** Web Push to replace ntfy.

Each step lands as its own commit. Steps 1–3 are the v1 deliverable.
Step 4 is verification, not new code. Step 5 is its own follow-up.

## Pre-flight checks

- [ ] HTTPS confirmed (we have it via CF Tunnel)
- [ ] All assets reachable from inside CF Access (yes, gates work)
- [ ] No code currently uses `localStorage` in ways that would conflict
      with multi-window PWA usage (live.js does cache WebRTC results
      there — fine, scoped to origin)
- [ ] Service worker registration must be HTTPS or localhost — ✓ via CF

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| SW caches a 401 response, page becomes broken | Only cache 200 status; never cache /api/ or HTML responses with auth issues |
| iOS standalone PWA doesn't autoplay live streams | Already use `muted playsInline autoplay` on videos; aligns with iOS rules |
| CF Access cookie expires while in standalone PWA | Force-reload on 401 detection; CF re-auths the user transparently if they're still signed in to CF |
| Service worker version skew between users | Use cache version in CACHE constant; bump on every release; activate hook drops old caches |
| Pinch-zoom feels different in PWA vs. browser tab | Test both; design panzoom interactions to work in both contexts (touch-action: pinch-zoom rather than none) |

## Things to watch in current work that might affect PWA later

- **Don't add `touch-action: none` on the body** — needed for OS pinch
  in browser-tab mode. Scope it to specific zoomable wrappers only.
- **Don't bake the CF Access JWT into long-lived JS state** — read it
  fresh per request. Cookies/headers handle this naturally; just don't
  cache the email anywhere durable.
- **Don't introduce service-worker-incompatible APIs.** The streaming
  WebSocket and WebRTC paths are fine; they don't intersect with SW
  fetches. But if we ever introduce, e.g., a chunked SSE feed for new
  highlights, plan for SW interaction.
- **Asset versioning (`?v=...`) already protects us from PWA cache
  staleness** — new deploys produce a new version, SW fetches the new
  asset, old one drops out of cache.

## Out of scope (for now)

- **PWA-only features** like file system access, contact picker, etc.
- **Offline mode** for any user data
- **Server-rendered "shell" optimization** (HTML skeleton served
  static, JS hydrates)
- **App-store packaging** (Trusted Web Activities for Android Play
  Store, Apple's Trusted Web pathways)
