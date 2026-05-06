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

const CACHE = "our-foxes-v113-wordmark-tighter";

const STATIC_ASSETS = [
  "/static/style.css",
  "/static/warm-theme.css",
  "/static/landing.css",
  "/static/card.js",
  "/static/live.js",
  "/static/highlights.js",
  "/static/clip.js",
  "/static/modal.js",
  "/static/landing.js",
  "/static/deliverers.js",
  "/static/notifications.js",
  "/static/push-client.js",
  "/static/push-settings.js",
  "/static/peeks.js",
  "/static/easter-eggs.js",
  "/static/panzoom.min.js",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/favicon.png",
  "/static/icons/favicon.svg",
];

// HTML shells precached at install time so a cold OFFLINE launch
// (PWA opened from Home Screen with no network) shows the gallery
// or landing rather than the browser's offline error. The fetch
// handler is network-first for these — when online, the user
// always gets the freshest HTML; the cached copy is the offline
// fallback. Without this list, the very first offline launch would
// 404 since runtime cache is still empty.
const HTML_SHELLS_TO_PRECACHE = [
  "/",            // public landing
  "/highlights",  // primary authed surface (most-likely PWA entry)
  "/live",        // live grid HTML (streams won't work offline but
                  // the chrome + bottom-tabs render so the user
                  // can navigate to a cached /highlights)
];

self.addEventListener("install", (event) => {
  // Pre-cache static assets + HTML shells so the first PWA launch
  // (online OR offline) has them ready. We use individual put()
  // calls instead of cache.addAll so a single 401 / redirect / 503
  // doesn't abort the whole install — important because HTML
  // shells require Cloudflare Access auth and the install context
  // may or may not have a fresh CF cookie.
  event.waitUntil(
    caches.open(CACHE).then((cache) => {
      const all = STATIC_ASSETS.concat(HTML_SHELLS_TO_PRECACHE);
      return Promise.all(all.map((url) =>
        fetch(url, { credentials: "same-origin" })
          .then((r) => {
            // Only cache successful HTML/asset responses. A 401
            // (CF Access redirect) or 5xx is intentionally
            // skipped so a stale auth-error doesn't poison the
            // cache. The runtime fetch handler will populate
            // these later on the user's next online visit.
            if (r.ok) return cache.put(url, r);
          })
          .catch(() => { /* network unreachable at install — fine */ })
      ));
    })
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


// ---------------------------------------------------------------------
// Web Push handlers — show the notification + route the click. Curator
// fires these for remix_like and new_highlight events; payload shape:
//   {title, body, url, tag?, kind?}
//
// iOS Safari (16.4+) supports Web Push only for installed PWAs. The
// PushSubscription itself fails with NotAllowedError in non-PWA Safari
// — we never get to this code path on iOS unless the app is on the
// Home Screen, which is what we want.
// ---------------------------------------------------------------------

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; }
  catch { data = { title: "Our Foxes", body: event.data?.text?.() || "" }; }

  const title = data.title || "Our Foxes";
  const options = {
    body:  data.body  || "",
    icon:  "/static/icons/icon-192.png",
    // 'badge' renders as a monochrome glyph in the Android status bar
    // (and is silently ignored on iOS, where we don't have a separate
    // badge asset to ship). Reusing the regular favicon is the right
    // fallback until the user provides splash + badge artwork later
    // in the Phase 2 second wave.
    badge: "/static/icons/favicon.png",
    // 'tag' coalesces repeats: a second push with the same tag
    // replaces the first instead of stacking. For remix_like we tag
    // by remix_id so a flurry of likes on one remix collapses into
    // a single banner.
    tag:   data.tag || data.kind || "fox-cam",
    // Click target — picked up by the notificationclick handler below.
    data:  { url: data.url || "/highlights", kind: data.kind || "" },
    renotify: true,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/highlights";
  // Focus an existing visible client at this origin if one is open;
  // otherwise spawn a new window. clientList includes uncontrolled
  // pages too thanks to includeUncontrolled.
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({
      type: "window",
      includeUncontrolled: true,
    });
    for (const c of all) {
      try {
        // Bring the existing PWA tab forward and ask it to navigate.
        await c.focus();
        if ("navigate" in c && c.url !== url) {
          await c.navigate(url).catch(() => {});
        }
        return;
      } catch { /* try next */ }
    }
    if (self.clients.openWindow) {
      await self.clients.openWindow(url);
    }
  })());
});
