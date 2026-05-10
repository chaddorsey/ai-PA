// HLS source attachment helper.
//
// Why this exists:
//   iOS Safari + macOS Safari can play HLS natively via a
//   <source type="application/vnd.apple.mpegurl"> element — no JS
//   library needed. Chrome / Firefox / Edge cannot, but they DO
//   support MediaSource Extensions, which is what hls.js needs to
//   pump segments into the <video> element manually.
//
//   Until backfill is finished, some legacy clips don't have HLS
//   yet. The curator returns 404 on the manifest endpoint for those
//   (and kicks off a background render so they're ready next time).
//   The browser path here MUST fall through cleanly to the MP4
//   source whenever HLS is unavailable, on every supported browser.
//
// Strategy:
//   - Native-HLS path (Safari): set videoEl.src = hlsUrl. On error
//     (manifest 404), swap to mp4Url. Single source attribute, simple
//     reset semantics, panzoom integration unchanged.
//   - hls.js path (everyone else): lazy-load /static/hls.min.js the
//     first time we need it. probe the manifest (HEAD-like GET);
//     if 200, attach hls.js to the videoEl; if 404, set src=mp4Url.
//   - hls.js failure path: fall through to mp4Url.
//
// Memory:
//   Each Hls() instance allocates a MediaSource buffer. We attach
//   the instance to videoEl._foxHls so callers can detach() on
//   modal close to release segments immediately rather than waiting
//   for GC.

(function () {
  let _hlsJsPromise = null;

  function loadHlsJs() {
    if (_hlsJsPromise) return _hlsJsPromise;
    _hlsJsPromise = new Promise((resolve) => {
      // If something else already injected hls.js (e.g., via SW
      // pre-cache + a previous attach call), use the cached global.
      if (window.Hls) { resolve(window.Hls); return; }
      const s = document.createElement("script");
      s.src = "/static/hls.min.js";
      s.async = true;
      s.onload = () => resolve(window.Hls || null);
      s.onerror = () => resolve(null);
      document.head.appendChild(s);
    });
    return _hlsJsPromise;
  }

  // Detach any hls.js instance previously bound to this <video>.
  // Should be called when swapping to a new clip OR closing the
  // modal so MediaSource segments can be GC'd promptly.
  function detachHls(videoEl) {
    const inst = videoEl && videoEl._foxHls;
    if (inst) {
      try { inst.destroy(); } catch (_) {}
      videoEl._foxHls = null;
    }
  }
  window.detachHls = detachHls;

  // Attach the best available source to videoEl.
  //   hlsUrl  — manifest URL (server may 404 if not rendered yet)
  //   mp4Url  — fallback source URL
  //   options.startPlay — call .play() after attach (defaults true)
  //
  // Resolves to an object describing what attached:
  //   { kind: "native-hls" | "hlsjs" | "mp4" }
  // for callers that want to know which path is in use (e.g. for
  // analytics or behavior tweaks).
  async function attachHlsSource(videoEl, hlsUrl, mp4Url, options) {
    const opts = options || {};
    const startPlay = opts.startPlay !== false;
    detachHls(videoEl);

    // Native HLS path. Safari is the only browser that returns a
    // truthy string from canPlayType for hls; every other browser
    // returns "".
    if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
      videoEl.src = hlsUrl;
      // Single one-shot listener: if manifest 404s, swap to MP4.
      // The 'error' event fires asynchronously after src= for
      // unreachable URLs, and we want the swap to be invisible.
      const onErr = () => {
        videoEl.removeEventListener("error", onErr);
        videoEl.src = mp4Url;
        try { videoEl.load(); } catch (_) {}
        if (startPlay) videoEl.play().catch(() => {});
      };
      videoEl.addEventListener("error", onErr, { once: true });
      try { videoEl.load(); } catch (_) {}
      if (startPlay) videoEl.play().catch(() => {});
      return { kind: "native-hls" };
    }

    // hls.js path. Probe the manifest first so a 404 doesn't get
    // surfaced to the user as an empty buffering state.
    let manifestOk = false;
    try {
      const probe = await fetch(hlsUrl, {
        method: "GET",
        credentials: "same-origin",
        // Range trick: only ask for the first byte so the proxy
        // returns headers fast and the body cost is negligible. The
        // FastAPI FileResponse honors Range natively.
        headers: { "Range": "bytes=0-0" },
      });
      manifestOk = probe.ok;  // 200 or 206
    } catch (_) {
      manifestOk = false;
    }

    if (manifestOk) {
      const Hls = await loadHlsJs();
      if (Hls && Hls.isSupported()) {
        const hls = new Hls({
          // Conservative buffering — small enough to feel snappy
          // on a 4-sec-segment manifest, large enough to absorb
          // network jitter without re-buffering visibly.
          maxBufferLength: 30,
          maxMaxBufferLength: 60,
          // Defer loading the next segment until we're close to
          // the end of the buffer. Reduces cellular bandwidth on
          // a viewer who's about to close the modal.
          startFragPrefetch: false,
        });
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal) return;
          // Recovery patterns from the official hls.js docs.
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            try { hls.startLoad(); } catch (_) {}
          } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            try { hls.recoverMediaError(); } catch (_) {}
          } else {
            // Last resort: tear down + fall through to MP4.
            detachHls(videoEl);
            videoEl.src = mp4Url;
            try { videoEl.load(); } catch (_) {}
            if (startPlay) videoEl.play().catch(() => {});
          }
        });
        hls.loadSource(hlsUrl);
        hls.attachMedia(videoEl);
        videoEl._foxHls = hls;
        if (startPlay) videoEl.play().catch(() => {});
        return { kind: "hlsjs" };
      }
      // hls.js unavailable or unsupported — fall through.
    }

    // MP4 fallback. Either the manifest 404'd or hls.js can't run
    // here. The .mp4 source is always the same media surface, just
    // less efficient on the wire.
    videoEl.src = mp4Url;
    try { videoEl.load(); } catch (_) {}
    if (startPlay) videoEl.play().catch(() => {});
    return { kind: "mp4" };
  }

  window.attachHlsSource = attachHlsSource;
})();
