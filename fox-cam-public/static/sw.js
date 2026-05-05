// Service worker for Our Foxes PWA.
//
// Strategy:
//   - Static assets (CSS / JS / icons / SVG): cache-first. Cached on
//     install; refreshed when not in cache. Versioned via CACHE name —
//     bumping the suffix on a release drops the old cache.
//   - HTML pages (/, /highlights, /clip/*, /remix/*): network-first
//     with cache fallback. Browsers always get the freshest HTML when
//     online; offline opens load the last successful page.
//   - Everything else (API, WebSocket, WebRTC signaling, live MSE): pass
//     through completely. The SW must NOT intercept auth-gated /api/* —
//     a cached 401 response would persist and break the page.
//
// Cloudflare Access compatibility: every request still goes to the
// network when fresh, so CF cookies are honored. Cached HTML continues
// to work offline; on 401 from any /api fetch the page reloads to
// re-trigger the CF Access challenge.

const CACHE = "our-foxes-v41-tabs-borderless-toggle-tighter";

const STATIC_ASSETS = [
  "/static/style.css",
  "/static/card.js",
  "/static/live.js",
  "/static/highlights.js",
  "/static/clip.js",
  "/static/panzoom.min.js",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/favicon.png",
  "/static/icons/favicon.svg",
];

self.addEventListener("install", (event) => {
  // Pre-cache static assets so the first PWA launch has them ready,
  // including offline-first cold opens.
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Use individual put() calls so a single 401/redirect doesn't
      // abort the whole install. addAll() is all-or-nothing.
      Promise.all(STATIC_ASSETS.map((url) =>
        fetch(url, { credentials: "same-origin" })
          .then((r) => {
            if (r.ok) return cache.put(url, r);
          })
          .catch(() => {})
      ))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Drop old caches on version bump (CACHE constant changes).
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Only handle same-origin requests. Pass through everything else.
  if (url.origin !== self.location.origin) return;

  // NEVER intercept auth-gated, real-time, or live-streaming paths.
  // A cached 401 here would brick the page across the whole family.
  if (url.pathname.startsWith("/api/")) return;
  if (event.request.headers.get("upgrade") === "websocket") return;
  if (event.request.method !== "GET") return;

  // Static assets: cache-first.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: network-first with cache fallback.
  // /live is intentionally excluded — it's an authed-only page and
  // a stale cached copy could end up served to a freshly-deauthed
  // visitor (or worse, a different visitor on a shared device).
  if (url.pathname === "/" ||
      url.pathname === "/highlights" ||
      url.pathname.startsWith("/clip/") ||
      url.pathname.startsWith("/remix/")) {
    event.respondWith((async () => {
      try {
        const response = await fetch(event.request);
        if (response.status === 200) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      } catch (err) {
        // Network failed (offline). Try cache; if cache miss, surface
        // a real Response so the browser doesn't reject the FetchEvent
        // promise (which produces "Failed to convert value to
        // 'Response'" errors in the console + a hung navigation).
        const cached = await caches.match(event.request);
        if (cached) return cached;
        return new Response("Offline — please reconnect.", {
          status: 503,
          headers: { "Content-Type": "text/plain" }
        });
      }
    })());
    return;
  }

  // Default: don't intercept.
});
