// Live-stream client. Tries WebRTC first (lowest latency, ~200ms);
// falls back to MSE-over-WebSocket if WebRTC fails. WebRTC needs
// browser-to-go2rtc media path (LAN or TURN). MSE works through
// Cloudflare Tunnel as plain HTTP/WS, no NAT traversal needed.

(function () {
  console.log("[live.js] loaded, version=7");

  // iOS Safari (browser tab) doesn't expose MediaSource at all. iOS
  // 17.1+ adds ManagedMediaSource, but its API + segment expectations
  // differ enough that runMSE (which uses `new MediaSource()`) can't
  // just swap the constructor. Only flag HAS_MSE when the legacy
  // MediaSource is actually present — ManagedMediaSource counts as
  // "no MSE for our pipeline".
  const HAS_MSE = typeof window.MediaSource !== "undefined";
  const IS_IOS_LIKE = document.documentElement.classList.contains("ios");

  // Autoplay rejection: iOS Safari often refuses to start a muted
  // video without a prior user gesture, even with autoplay+muted+
  // playsinline set. The browser doesn't fire any error in that case
  // — video.play() returns a promise that rejects with NotAllowedError
  // and the video silently stays paused. We hook the promise from the
  // explicit play() calls in tryWebRTC + runMSE.
  //
  // Gated on body.ios so non-iOS browsers (Chrome on Linux can also
  // reject autoplay in backgrounded tabs / low-MEI origins) don't see
  // the scrim. Desktop bundle stays untouched.
  function notePlayRejection(promise) {
    if (!promise || typeof promise.then !== "function") return;
    promise.catch((err) => {
      if (err && err.name !== "NotAllowedError") return;
      if (!document.documentElement.classList.contains("ios")) return;
      revealAutoplayScrim();
    });
  }

  // Passive probe: 1.5s after a stream is marked "live (...)", check
  // whether the video is actually playing. If paused, the browser's
  // autoplay was likely rejected — call play() once explicitly so the
  // returned promise rejects with NotAllowedError and notePlayRejection
  // surfaces the scrim. If the video is already playing, do nothing
  // (avoids the race where an explicit play() interrupts an in-flight
  // autoplay attempt).
  function schedulePlayProbe(video) {
    setTimeout(() => {
      if (!video.paused || video.ended) return;
      // readyState 0 = HAVE_NOTHING — still buffering; not autoplay
      // rejection. Re-probe once shortly.
      if (video.readyState < 1) {
        setTimeout(() => {
          if (!video.paused || video.ended) return;
          notePlayRejection(video.play());
        }, 1500);
        return;
      }
      notePlayRejection(video.play());
    }, 1500);
  }

  // Scrim shown over the live grid when iOS refuses autoplay. One tap
  // anywhere on the scrim calls play() on every grid <video>. Once any
  // play() resolves the user-activation lock lifts globally; the scrim
  // dismisses on first observed `playing` event from any grid stream.
  let scrimEl = null;
  function revealAutoplayScrim() {
    if (!scrimEl) {
      scrimEl = document.getElementById("autoplay-scrim");
      if (!scrimEl) return;
      const enable = () => {
        const vids = document.querySelectorAll("video.grid-stream");
        vids.forEach((v) => {
          const p = v.play();
          if (p && typeof p.catch === "function") p.catch(() => {});
        });
        // Don't dismiss here — wait for a real `playing` event below
        // so we don't hide on a still-rejected attempt.
      };
      scrimEl.addEventListener("click", enable);
      scrimEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); enable(); }
      });
      // Any cam reaching `playing` (initial success or recovery after
      // retry) hides the scrim — covers the race where one cam starts
      // before the user even taps.
      document.querySelectorAll("video.grid-stream").forEach((v) => {
        v.addEventListener("playing", () => {
          if (scrimEl) scrimEl.hidden = true;
        });
      });
    }
    scrimEl.hidden = false;
  }

  // Chromium browsers (Chrome, Edge, Arc, Brave, Opera, etc.) replace
  // local IPs in WebRTC ICE candidates with `<uuid>.local` mDNS names
  // since Chrome 76 (2019) for privacy. go2rtc, running inside the
  // Docker VM, has no Bonjour resolver so it can't translate those
  // names to IPs — WebRTC always fails on these browsers without a
  // TURN server. Safari and Firefox still send raw IPs (with user
  // permission), so they can negotiate with go2rtc directly on LAN.
  //
  // We treat Chromium as "no WebRTC" up front to skip the long ICE
  // gathering + signaling round-trip that would inevitably fail.
  // `window.chrome` is present on every Chromium-based browser (and
  // nothing else). The localStorage cache below catches edge cases:
  // if a Chromium user has actually disabled the mDNS flag or has
  // a TURN server reachable, the first attempt still records "ok"
  // and we'll keep using WebRTC for them.
  const isChromium = !!window.chrome;

  const WEBRTC_CACHE_KEY = "fox-cam-webrtc-status";
  const WEBRTC_CACHE_TTL_MS = 12 * 60 * 60 * 1000;

  function getCachedWebRTCResult() {
    try {
      const raw = localStorage.getItem(WEBRTC_CACHE_KEY);
      if (!raw) return null;
      const entry = JSON.parse(raw);
      if (Date.now() - entry.ts > WEBRTC_CACHE_TTL_MS) return null;
      return entry.result; // "ok" | "fail"
    } catch {
      return null;
    }
  }

  function setCachedWebRTCResult(result) {
    try {
      localStorage.setItem(
        WEBRTC_CACHE_KEY,
        JSON.stringify({ result, ts: Date.now() })
      );
    } catch {}
  }

  // Start grid streams. The 600ms stagger exists to avoid VideoToolbox
  // decoder contention on macOS Chromium when 4 MediaSources spin up
  // at once. On iOS there's no MSE — only WebRTC — and the stagger
  // disadvantages the first cam, which has to negotiate ICE while the
  // OS network stack is cold. Cam 1 then hits the ICE timeout (even
  // at 6s) more often than cams 2–4 that benefit from a warmed-up
  // stack. Race all four in parallel on iOS.
  const gridVideos = document.querySelectorAll("video.grid-stream[data-stream]");
  const STAGGER_MS = IS_IOS_LIKE ? 0 : 600;
  (async () => {
    for (const video of gridVideos) {
      const stream = video.dataset.stream;
      const cam = video.closest(".cam");
      const status = cam ? cam.querySelector(".status") : null;
      start(video, stream, status).catch((err) => {
        console.error(`[${stream}] start error:`, err);
        if (status) status.textContent = `error: ${err.message}`;
      });
      // Bind panzoom as soon as the video has dimensions. If
      // loadedmetadata already fired before this listener attaches
      // (fast WebRTC cam beating our event registration), bind
      // synchronously instead — otherwise the cam ends up with no
      // panzoom and pinch silently fails.
      const bindWhenReady = () => bindGridPanzoom(cam, video);
      if (video.readyState >= 1) bindWhenReady();
      else video.addEventListener("loadedmetadata", bindWhenReady, { once: true });
      if (STAGGER_MS) await new Promise((r) => setTimeout(r, STAGGER_MS));
    }
  })();

  // Persistent grid-mode panzoom instances keyed by cam element so
  // we can dispose them cleanly on spotlight enter without leaving
  // stray listeners on the grid-stream <video>.
  const gridPanzooms = new Map();
  function bindGridPanzoom(cam, video) {
    if (!cam || !video || typeof window.panzoom !== "function") return;
    if (gridPanzooms.has(cam)) return;
    video.style.transformOrigin = "0 0";
    let inst;
    try {
      inst = window.panzoom(video, {
        maxZoom: 6, minZoom: 1, bounds: true,
        boundsPadding: 0.95, zoomDoubleClickSpeed: 1,
      });
    } catch (e) { return; }
    gridPanzooms.set(cam, inst);
    const wrap = video.parentElement;   // .video-wrap
    const zin  = wrap.querySelector(".zoom-controls .zoom-in");
    const zout = wrap.querySelector(".zoom-controls .zoom-out");
    const zfit = wrap.querySelector(".zoom-controls .zoom-fit");
    if (zin) zin.addEventListener("click", (e) => {
      e.stopPropagation();
      const r = wrap.getBoundingClientRect();
      inst.smoothZoom(r.left + r.width/2, r.top + r.height/2, 1.5);
    });
    if (zout) zout.addEventListener("click", (e) => {
      e.stopPropagation();
      const cur = inst.getTransform().scale;
      const next = cur / 1.5;
      if (next <= 1.05) {
        inst.zoomAbs(0, 0, 1);
        inst.moveTo(0, 0);
      } else {
        const r = wrap.getBoundingClientRect();
        inst.smoothZoom(r.left + r.width/2, r.top + r.height/2, 1/1.5);
      }
    });
    if (zfit) zfit.addEventListener("click", (e) => {
      e.stopPropagation();
      inst.zoomAbs(0, 0, 1);
      inst.moveTo(0, 0);
    });
  }

  // ---------- Spotlight (click-to-zoom) ----------
  // Click any tile to make it the spotlight; the others shrink into a
  // thumbnail rail. Click the spotlight to return to the grid. Streams
  // stay live across mode switches — moving a video element between
  // containers via the DOM doesn't tear down WebRTC/MSE connections,
  // because the underlying MediaSource / MediaStream is bound to the
  // element, not its position in the tree.
  const main = document.getElementById("live-main");
  const cams = document.querySelectorAll(".cam[data-stream]");

  // Track the active panzoom instance so we can tear it down on mode
  // change. Only one camera is spotlighted at a time, so one instance.
  let activeZoom = null;

  // Bring the spotlight (high-res) pipeline online for a given cam.
  // Uses the cam's .spotlight-stream <video> element which is dormant
  // until needed. The .grid-stream substream stays playing the whole
  // time; CSS hides it once .spotlight-ready flips on.
  function attachSpotlightStream(cam) {
    const sv = cam.querySelector("video.spotlight-stream");
    if (!sv) return;
    const baseName = sv.dataset.base;
    sv.dataset.stream = baseName;          // main stream
    const status = cam.querySelector(".status");
    // No MSE on this browser (iOS Safari): the substream the cam is
    // already playing via its grid-stream <video> has to be the
    // spotlight view too. Skip the hi-res attach entirely so we don't
    // crash on `new MediaSource()`.
    if (!HAS_MSE) {
      if (status) status.textContent = "live (sub)";
      return;
    }
    if (status) status.textContent = "loading hi-res…";
    runMSE(sv, baseName, status).catch((err) => {
      console.error(`[${baseName}] spotlight start error:`, err);
      if (status) status.textContent = `hi-res error: ${err.message}`;
    });
    // When the main stream is decoding frames, flip .spotlight-ready
    // so CSS hides the substream and shows main. Attached as a
    // PERSISTENT listener so post-error recoveries (runMSE auto-retry)
    // restore the high-res view automatically. Panzoom binding stays
    // a one-shot — repeated panzoom() on the same element disposes
    // and re-binds, which is wasteful but harmless.
    const onPlaying = () => {
      if (!cam.classList.contains("is-spotlight")) return;  // stale
      cam.classList.add("spotlight-ready");
      if (status) status.textContent = "live (hi-res)";
    };
    let panzoomBound = false;
    const onLoadedData = () => {
      if (!cam.classList.contains("is-spotlight")) return;
      cam.classList.add("spotlight-ready");
      if (!panzoomBound) {
        panzoomBound = true;
        attachPanzoom(cam, sv);
      }
    };
    sv.addEventListener("playing", onPlaying);
    sv.addEventListener("loadeddata", onLoadedData);

    // Spotlight-stream errors (Cam 4's 4K main stream occasionally
    // throws on certain SPS configs) used to leave .spotlight-ready
    // on while runMSE retried, hiding the substream and collapsing
    // the wrap. Drop the class so the substream is visible while the
    // high-res pipeline reconnects; the `playing` listener above
    // re-sets it on the next successful frame.
    const onSpotlightError = () => {
      if (!cam.classList.contains("is-spotlight")) return;  // stale
      cam.classList.remove("spotlight-ready");
      if (status) status.textContent = "hi-res hiccup — retrying…";
    };
    sv.addEventListener("error", onSpotlightError);

    // Stash refs so detachSpotlightStream can remove them cleanly.
    sv._listeners = { onPlaying, onLoadedData, onSpotlightError };
  }

  // (Re)initialize panzoom on a specific video element. Called twice
  // per spotlight enter: once on the grid-stream (immediate, so zoom
  // works on the visible substream while main is still loading) and
  // once on the spotlight-stream when it's ready (real high-res zoom).
  function attachPanzoom(cam, video) {
    if (typeof window.panzoom !== "function") return;
    if (activeZoom) {
      try { activeZoom.dispose(); } catch (_) {}
      activeZoom = null;
    }
    // Clear residual transform on the previous video so it returns
    // to identity if we ever swap back to it.
    cam.querySelectorAll("video").forEach((v) => {
      if (v !== video) {
        v.style.transform = "";
        v.style.transformOrigin = "";
      }
    });
    cam.classList.remove("is-zoomed");
    const computeMax = () => {
      const w = video.videoWidth || 0;
      const dw = video.clientWidth || 1;
      return w > 0 ? Math.max(1.5, w / dw) : 4;
    };
    activeZoom = window.panzoom(video, {
      maxZoom: computeMax(),
      minZoom: 1,
      bounds: true,
      boundsPadding: 0.95,
      smoothScroll: false,
      zoomDoubleClickSpeed: 1,
    });
    const onMeta = () => { if (activeZoom) activeZoom.setMaxZoom(computeMax()); };
    if (video.videoWidth > 0) onMeta();
    else video.addEventListener("loadedmetadata", onMeta, { once: true });
    wireZoomControls(cam, activeZoom, video);
  }

  // Tear down the spotlight (high-res) pipeline for a cam. Removes
  // .spotlight-ready so CSS reveals the substream again, then cleans
  // up the spotlight-stream's WS / MSE state. The grid-stream is
  // never touched.
  function detachSpotlightStream(cam) {
    cam.classList.remove("spotlight-ready");
    const sv = cam.querySelector("video.spotlight-stream");
    if (sv) {
      // Pull listeners we attached in attachSpotlightStream so the
      // next spotlight-enter starts with a clean event surface.
      const L = sv._listeners;
      if (L) {
        try { sv.removeEventListener("playing", L.onPlaying); } catch (_) {}
        try { sv.removeEventListener("loadeddata", L.onLoadedData); } catch (_) {}
        try { sv.removeEventListener("error", L.onSpotlightError); } catch (_) {}
        sv._listeners = null;
      }
      teardownVideo(sv);
      sv.style.transform = "";
      sv.style.transformOrigin = "";
    }
  }

  // Fully tear down the previous MSE pipeline on a video. Removes the
  // error listener, cancels any pending auto-retry, closes the WS, and
  // detaches the source. Called by switchStream and at the start of
  // runMSE so successive runs on the same video don't accumulate
  // listeners or compete with each other.
  function teardownVideo(video) {
    try { if (video._retryTimer) clearTimeout(video._retryTimer); } catch (_) {}
    video._retryTimer = null;
    try { if (video._onVideoError) video.removeEventListener("error", video._onVideoError); } catch (_) {}
    video._onVideoError = null;
    try { if (video._ws) video._ws.close(); } catch (_) {}
    video._ws = null;
    try {
      video.pause();
      video.srcObject = null;
      video.removeAttribute("src");
      video.load();
    } catch (_) {}
  }

  function setMode(mode, spotlight) {
    main.dataset.mode = mode;
    document.body.classList.toggle("spotlight-mode", mode === "spotlight");
    // Tear down any prior panzoom whenever the mode changes — different
    // spotlight = different video element = need a fresh instance.
    // panzoom.dispose() removes listeners but leaves the transform on
    // the element, so we explicitly clear it. Otherwise a zoomed video
    // returns to grid mode with the transform baked in (visible as
    // "lands offset in the upper-right of the grid tile").
    if (activeZoom) {
      try { activeZoom.dispose(); } catch (_) {}
      activeZoom = null;
    }
    document.querySelectorAll(".cam video").forEach((v) => {
      v.style.transform = "";
      v.style.transformOrigin = "";
    });
    cams.forEach((c) => c.classList.remove("is-zoomed"));

    if (spotlight) {
      main.dataset.spotlight = spotlight;
      // Cams always stay direct children of #live-main and the
      // grid-stream substream keeps playing on each. For the new
      // spotlight cam, fire up the parallel main-stream pipeline on
      // its .spotlight-stream video element. Any prior spotlight
      // (when swapping cams) gets its main pipeline torn down.
      cams.forEach((c) => {
        const isSpot = c.dataset.stream === spotlight;
        const wasSpot = c.classList.contains("is-spotlight");
        c.classList.toggle("is-spotlight", isSpot);
        if (isSpot && !wasSpot) attachSpotlightStream(c);
        if (!isSpot && wasSpot) detachSpotlightStream(c);
      });
      // Attach panzoom to the new spotlight video. Defer one frame so
      // CSS-driven resize completes before panzoom measures bounds.
      requestAnimationFrame(() => {
        const cam = document.querySelector(`.cam[data-stream="${spotlight}"]`);
        if (!cam) return;
        // Attach panzoom to the high-res spotlight-stream so zoom
        // works on real pixels. Falls back to grid-stream if the
        // spotlight pipeline isn't up yet (rare race).
        const video = cam.querySelector("video.spotlight-stream") ||
                      cam.querySelector("video.grid-stream");
        if (!video || typeof window.panzoom !== "function") return;
        // maxZoom = pixel-1:1. videoWidth is the source pixel count;
        // clientWidth is the rendered width. Their ratio is the zoom
        // level at which one source pixel = one display pixel; zooming
        // beyond that just enlarges already-stretched pixels (visible
        // mush, no actual detail gain).
        // videoWidth may be 0 until metadata loads; fall back to a
        // sensible cap and update on loadedmetadata.
        const computeMax = () => {
          const w = video.videoWidth || 0;
          const dw = video.clientWidth || 1;
          return w > 0 ? Math.max(1.5, w / dw) : 4;
        };
        activeZoom = window.panzoom(video, {
          maxZoom: computeMax(),
          minZoom: 1,
          bounds: true,
          boundsPadding: 0.95,
          smoothScroll: false,
          zoomDoubleClickSpeed: 1,
        });
        // Patch maxZoom in once the video reports its real resolution.
        const onMeta = () => {
          if (activeZoom) activeZoom.setMaxZoom(computeMax());
        };
        if (video.videoWidth > 0) onMeta();
        else video.addEventListener("loadedmetadata", onMeta, { once: true });
        wireZoomControls(cam, activeZoom, video);
      });
    } else {
      delete main.dataset.spotlight;
      cams.forEach((c) => {
        if (c.classList.contains("is-spotlight")) detachSpotlightStream(c);
        c.classList.remove("is-spotlight");
      });
    }
  }

  // Hook up the corner +/-/⛶ buttons + double-click + keyboard reset.
  function wireZoomControls(cam, pz, video) {
    const btnIn  = cam.querySelector(".zoom-in");
    const btnOut = cam.querySelector(".zoom-out");
    const btnFit = cam.querySelector(".zoom-fit");
    // Anchor zoom to the WRAPPER's visible center, not the video's
    // bounding box. The video element moves under pan; the wrapper
    // doesn't. Using the wrapper guarantees button-zoom always pivots
    // around the pixel currently at the center of the visible tile.
    const wrap = cam.querySelector(".video-wrap");

    const zoomAt = (factor, x, y) => {
      if (x === undefined || y === undefined) {
        const r = wrap.getBoundingClientRect();
        x = r.left + r.width / 2;
        y = r.top + r.height / 2;
      }
      pz.smoothZoom(x, y, factor);
    };

    const reset = () => {
      // Reset transform: scale 1, translate 0,0. video element's
      // transform-origin is 0,0 so this re-aligns it to the wrap.
      pz.zoomAbs(0, 0, 1);
      pz.moveTo(0, 0);
    };

    btnIn  && btnIn.addEventListener("click", (e) => { e.stopPropagation(); zoomAt(1.5); });
    btnOut && btnOut.addEventListener("click", (e) => {
      e.stopPropagation();
      // If zooming out would put us at or below 1×, snap to identity
      // transform rather than animate to a partial state. The bounds
      // constraint at minZoom=1 otherwise leaves the video pinned to
      // an edge when the prior pan offset can't shrink with scale —
      // hence the "Cam 4 zoom-out lands left of center" weirdness.
      const cur = pz.getTransform().scale;
      if (cur / 1.5 <= 1.05) reset();
      else zoomAt(1 / 1.5);
    });
    btnFit && btnFit.addEventListener("click", (e) => { e.stopPropagation(); reset(); });

    // Double-click anywhere on the video = zoom 2× at cursor.
    const onDbl = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      zoomAt(2, ev.clientX, ev.clientY);
    };
    video.addEventListener("dblclick", onDbl);

    // Track zoom state so cursor reflects pan-vs-zoom-in.
    pz.on("zoom", () => {
      const t = pz.getTransform();
      cam.classList.toggle("is-zoomed", t.scale > 1.01);
    });

    // Esc / 0 key resets while spotlight is active.
    const onKey = (ev) => {
      if (!cam.classList.contains("is-spotlight")) return;
      if (ev.key === "Escape" || ev.key === "0") {
        pz.moveTo(0, 0);
        pz.zoomAbs(0, 0, 1);
      }
    };
    document.addEventListener("keydown", onKey);

    // Stash cleanup for dispose() so we don't leak listeners.
    const origDispose = pz.dispose.bind(pz);
    pz.dispose = () => {
      try {
        video.removeEventListener("dblclick", onDbl);
        document.removeEventListener("keydown", onKey);
      } catch (_) {}
      origDispose();
    };
  }

  // Track pointer-down position per cam so we can distinguish a real
  // click from the tail of a drag. A drag that ends outside the
  // .video-wrap (e.g., past the bottom edge while panning a zoomed
  // view) would otherwise fire a click on the .cam element and
  // collapse spotlight — surprising and we leak the zoom transform
  // back into the grid view.
  const DRAG_THRESHOLD_PX = 6;
  const downPos = new WeakMap();

  // The "Live" nav link points to "/" — clicking it while already on
  // "/" would trigger a full page reload, tearing down all 4 streams
  // and forcing the 5-10s cold-start dance again. Intercept that click
  // and just collapse to grid mode in-place if we're already on /.
  const liveLink = document.querySelector('nav a[href="/"]');
  if (liveLink) {
    liveLink.addEventListener("click", (e) => {
      if (location.pathname === "/" || location.pathname === "") {
        e.preventDefault();
        if (main.dataset.mode !== "grid") setMode("grid");
      }
    });
  }

  cams.forEach((cam) => {
    cam.addEventListener("pointerdown", (e) => {
      downPos.set(cam, { x: e.clientX, y: e.clientY });
    });

    // Spotlight toggle. Shared body so both click (desktop) and a
    // touchend-derived tap (iOS — panzoom on the video swallows the
    // synthesized click in some cases) hit the same logic.
    const spotlightToggle = (target) => {
      if (target.tagName === "VIDEO" && target.controls) return;
      if (target.closest(".zoom-controls")) return;
      const stream = cam.dataset.stream;
      const inSpotlight = cam.classList.contains("is-spotlight");
      if (inSpotlight && target.closest(".video-wrap")) return;
      if (main.dataset.mode === "grid") {
        setMode("spotlight", stream);
      } else if (main.dataset.spotlight === stream) {
        setMode("grid");
      } else {
        setMode("spotlight", stream);
      }
    };

    cam.addEventListener("click", (e) => {
      // Was this a click, or the release of a drag? If pointer moved
      // more than threshold between down and up, treat as drag.
      const start = downPos.get(cam);
      if (start) {
        const dx = e.clientX - start.x;
        const dy = e.clientY - start.y;
        if (dx * dx + dy * dy > DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) {
          downPos.delete(cam);
          return;
        }
      }
      downPos.delete(cam);
      spotlightToggle(e.target);
    });

    // iOS tap fallback: panzoom on the <video> calls preventDefault on
    // pointerup which can suppress the synthesized click. Use touchend
    // as a parallel path — single-finger, short hold, no significant
    // movement = a tap. Mirrors the drag-threshold guard so a pan-end
    // doesn't toggle spotlight.
    let touchStartXY = null;
    let touchStartT = 0;
    cam.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) { touchStartXY = null; return; }
      const t = e.touches[0];
      touchStartXY = { x: t.clientX, y: t.clientY };
      touchStartT = Date.now();
    }, { passive: true });
    cam.addEventListener("touchend", (e) => {
      if (!touchStartXY) return;
      const start = touchStartXY;
      touchStartXY = null;
      if (e.touches.length !== 0) return;            // multi-touch end
      if (Date.now() - touchStartT > 500) return;   // long-press → not a tap
      if (e.changedTouches.length !== 1) return;
      const t = e.changedTouches[0];
      const dx = t.clientX - start.x;
      const dy = t.clientY - start.y;
      if (dx * dx + dy * dy > DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) return;
      // CRITICAL: only set recentTap (which suppresses click bubbling
      // via the capture-phase filter below) when this tap is actually
      // for spotlight toggling. A tap on a zoom button reaches here
      // too — without this guard, recentTap fires and the capture
      // filter kills the synthesized button click.
      const target = e.target;
      if (target.closest(".zoom-controls")) return;
      if (target.tagName === "VIDEO" && target.controls) return;
      const inSpotlight = cam.classList.contains("is-spotlight");
      if (inSpotlight && target.closest(".video-wrap")) return;
      cam.dataset.recentTap = String(Date.now());
      spotlightToggle(target);
    }, { passive: true });
    // Click suppression for touch-derived spotlight toggles.
    const origClickFilter = cam._origClickFilter;
    if (!origClickFilter) {
      cam.addEventListener("click", (e) => {
        const ts = parseInt(cam.dataset.recentTap || "0", 10);
        if (ts && Date.now() - ts < 350) {
          e.stopImmediatePropagation();
          cam.dataset.recentTap = "";
        }
      }, true);  // capture phase, runs before the toggle handler
      cam._origClickFilter = true;
    }
  });

  async function start(video, stream, status) {
    console.log(`[${stream}] start()`);
    const cached = getCachedWebRTCResult();
    // On iOS, NEVER skip WebRTC based on a cached failure — MSE isn't
    // available as a fallback, so a single bad WebRTC attempt would
    // permanently lock the cam off. Always retry WebRTC.
    const skipWebRTC = !IS_IOS_LIKE && (
      cached === "fail" || (isChromium && cached !== "ok")
    );
    if (skipWebRTC) {
      console.log(
        `[${stream}] skipping WebRTC (` +
          (cached === "fail"
            ? "cached failure"
            : "Chromium without proven WebRTC support") +
          ")"
      );
      if (!HAS_MSE) {
        status.textContent = "no compatible stream path";
        console.error(`[${stream}] cached WebRTC fail + no MSE; can't play`);
        return;
      }
      status.textContent = "connecting (MSE)…";
      await runMSE(video, stream, status);
      return;
    }

    status.textContent = "trying WebRTC…";
    try {
      await tryWebRTC(video, stream, status);
      console.log(`[${stream}] WebRTC succeeded`);
      setCachedWebRTCResult("ok");
      return;
    } catch (err) {
      console.warn(`[${stream}] WebRTC failed:`, err.message);
      setCachedWebRTCResult("fail");
    }
    if (!HAS_MSE) {
      // iOS path: WebRTC just failed and there's no MSE to fall back
      // to. Surface a friendly message; user can retry by reloading.
      status.textContent = "WebRTC unavailable — pull to refresh";
      console.error(`[${stream}] WebRTC failed and MediaSource is not available`);
      return;
    }
    status.textContent = "falling back to MSE…";
    await runMSE(video, stream, status);
  }

  // ---------- WebRTC ----------

  async function tryWebRTC(video, stream, status) {
    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.cloudflare.com:3478" }],
      bundlePolicy: "max-bundle",
    });
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    let resolveConn, rejectConn;
    const connected = new Promise((resolve, reject) => {
      resolveConn = resolve;
      rejectConn = reject;
    });
    connected.catch(() => {}); // pre-attach: silence unhandled-rejection warning

    // 3s is enough for LAN ICE on a desktop browser; iOS Safari often
    // takes longer to gather candidates over cellular or contended
    // wifi, so allow more headroom there. iOS has no MSE fallback —
    // a premature timeout = blank cam.
    const ICE_TIMEOUT_MS = IS_IOS_LIKE ? 6000 : 3000;
    const timer = setTimeout(() => rejectConn(new Error("ICE timeout")), ICE_TIMEOUT_MS);

    pc.ontrack = (e) => {
      if (video.srcObject !== e.streams[0]) video.srcObject = e.streams[0];
    };
    pc.onconnectionstatechange = () => {
      console.log(`[${stream}] pc state:`, pc.connectionState);
      if (pc.connectionState === "connected") {
        clearTimeout(timer);
        status.textContent = "live (WebRTC)";
        // Passive autoplay-rejection probe: don't call play() here
        // (it races with the browser's own autoplay attempt and can
        // throw AbortError, breaking the pipeline). Wait, then check
        // if the video is still paused — if so, autoplay was rejected
        // and we explicitly try again so notePlayRejection can detect
        // it and reveal the scrim.
        schedulePlayProbe(video);
        resolveConn();
      } else if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
        clearTimeout(timer);
        rejectConn(new Error(pc.connectionState));
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await new Promise((resolve) => {
      if (pc.iceGatheringState === "complete") return resolve();
      pc.addEventListener("icegatheringstatechange", () => {
        if (pc.iceGatheringState === "complete") resolve();
      });
    });

    const r = await fetch(`/api/webrtc/${encodeURIComponent(stream)}`, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: pc.localDescription.sdp,
    });
    if (!r.ok) {
      pc.close();
      throw new Error(`signaling ${r.status}`);
    }
    const answerSdp = await r.text();
    await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

    try {
      await connected;
      video._pc = pc;
    } catch (e) {
      pc.close();
      throw e;
    }
  }

  // ---------- MSE fallback ----------

  async function runMSE(video, stream, status) {
    console.log(`[${stream}] runMSE() start`);
    // Always start clean — successive runs on the same element (auto-
    // retry, switchStream) must not accumulate WS connections or
    // error listeners.
    teardownVideo(video);
    video.dataset.stream = stream;  // ensure correct after teardown

    // Probe codecs the browser can decode. Order matters — we want
    // higher-level options listed FIRST so go2rtc picks them when the
    // stream actually contains 4K/4MP frames. Without these, go2rtc
    // may default to Main@4.1 (avc1.4D0029) which legally tops out at
    // 1920x1080 — frames at 4K cause the decoder to throw MediaError
    // on every fragment after init. Cams now: 4MP / 4MP / 6MP / 4K.
    const candidates = [
      "avc1.640033",  // H.264 High@5.1   (≤4K)
      "avc1.4D0033",  // H.264 Main@5.1   (≤4K)
      "avc1.640032",  // H.264 High@5.0   (≤4K30)
      "avc1.4D0032",  // H.264 Main@5.0
      "avc1.640029",  // H.264 High@4.1   (≤1080p)
      "avc1.4D001F",  // H.264 Main@3.1
      "avc1.4D401F",
      "avc1.42E01E",
      "hvc1.1.6.L93.B0",
    ];
    const supported = candidates.filter((c) =>
      MediaSource.isTypeSupported(`video/mp4; codecs="${c}"`)
    );
    console.log(`[${stream}] codecs supported:`, supported);
    if (supported.length === 0) {
      throw new Error("no supported codec");
    }

    // Important: clear any existing srcObject first. WebRTC may have
    // left an MediaStream on srcObject, which takes precedence over
    // src and prevents MediaSource from attaching.
    video.srcObject = null;
    const ms = new MediaSource();
    video.src = URL.createObjectURL(ms);
    video.load();
    console.log(`[${stream}] MS attached, ms.readyState=${ms.readyState}, video.readyState=${video.readyState}`);

    // Pending state: data may arrive on the WS before MS opens. We buffer
    // metadata + frames until MS is open, then create the SourceBuffer
    // and drain.
    let sourceBuffer = null;
    let pendingMime = null;
    const queue = [];

    function flush() {
      if (!sourceBuffer || sourceBuffer.updating || queue.length === 0) return;
      try {
        sourceBuffer.appendBuffer(queue.shift());
      } catch (e) {
        console.error(`[${stream}] appendBuffer error:`, e);
      }
    }

    function tryCreateSourceBuffer() {
      if (sourceBuffer || !pendingMime || ms.readyState !== "open") return;
      console.log(`[${stream}] addSourceBuffer:`, pendingMime);
      try {
        sourceBuffer = ms.addSourceBuffer(pendingMime);
        sourceBuffer.mode = "segments";
        sourceBuffer.addEventListener("updateend", flush);
        sourceBuffer.addEventListener("error", (e) =>
          console.error(`[${stream}] sourceBuffer error:`, e)
        );
        status.textContent = "live (MSE)";
        // Passive autoplay-rejection probe — see comment in tryWebRTC.
        schedulePlayProbe(video);
        flush();
      } catch (e) {
        console.error(`[${stream}] addSourceBuffer failed:`, e);
      }
    }

    ms.addEventListener("sourceopen", () => {
      console.log(`[${stream}] MS sourceopen, video.readyState=${video.readyState}`);
      if (video.src && video.src.startsWith("blob:")) {
        URL.revokeObjectURL(video.src);
      }
      tryCreateSourceBuffer();
    });

    const wsScheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(
      `${wsScheme}://${location.host}/api/mse/${encodeURIComponent(stream)}`
    );
    ws.binaryType = "arraybuffer";

    let frameCount = 0;
    ws.addEventListener("open", () => {
      console.log(`[${stream}] WS open; sending init`);
      const payload = JSON.stringify({ type: "mse", value: supported.join(",") });
      console.log(`[${stream}] MSE init →`, payload);
      ws.send(payload);
    });

    ws.addEventListener("message", (ev) => {
      if (typeof ev.data === "string") {
        console.log(`[${stream}] MSE meta ←`, ev.data);
        try {
          const meta = JSON.parse(ev.data);
          if (meta.type === "mse" && meta.value && !pendingMime) {
            pendingMime = meta.value.startsWith("video/")
              ? meta.value
              : `video/mp4; codecs="${meta.value}"`;
            console.log(`[${stream}] codec from server:`, pendingMime, `ms.readyState=${ms.readyState}`);
            tryCreateSourceBuffer();
          }
        } catch (e) {
          console.error(`[${stream}] meta parse:`, ev.data, e);
        }
        return;
      }
      frameCount++;
      if (frameCount === 1 || frameCount % 100 === 0) {
        console.log(`[${stream}] frame ${frameCount}, ${ev.data.byteLength} bytes, queue=${queue.length}`);
      }
      queue.push(new Uint8Array(ev.data));
      flush();
    });

    ws.addEventListener("error", (e) => {
      console.error(`[${stream}] WS error:`, e);
    });
    ws.addEventListener("close", (ev) => {
      console.log(`[${stream}] WS close: code=${ev.code} reason=${ev.reason}`);
      if (status.textContent !== "live (MSE)") status.textContent = "disconnected";
    });

    // Add an event listener for video so we can see if it ever loads.
    video.addEventListener("loadedmetadata", () =>
      console.log(`[${stream}] video loadedmetadata, readyState=${video.readyState}`)
    );

    // One-shot auto-recovery scoped to THIS runMSE call. The handler
    // checks that video.dataset.stream still matches the stream we
    // were started for — if a switchStream() has fired in the meantime
    // (entering/leaving spotlight), this stale handler should no-op
    // rather than retry the old stream on top of the new pipeline.
    let retried = false;
    const onVideoError = (e) => {
      console.error(`[${stream}] video error:`, e, video.error);
      if (video.dataset.stream !== stream) return;  // stale; we've moved on
      if (retried) return;
      retried = true;
      try { ws.close(); } catch (_) {}
      try { video.src = ""; video.load(); } catch (_) {}
      console.log(`[${stream}] auto-retry in 1.5s…`);
      if (status) status.textContent = "retrying…";
      video._retryTimer = setTimeout(() => {
        if (video.dataset.stream !== stream) return;
        runMSE(video, stream, status).catch(() => {});
      }, 1500);
    };
    video._onVideoError = onVideoError;
    video.addEventListener("error", onVideoError);

    video._ws = ws;
  }
})();
