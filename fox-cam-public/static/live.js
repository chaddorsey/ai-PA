// Live-stream client. Tries WebRTC first (lowest latency, ~200ms);
// falls back to MSE-over-WebSocket if WebRTC fails. WebRTC needs
// browser-to-go2rtc media path (LAN or TURN). MSE works through
// Cloudflare Tunnel as plain HTTP/WS, no NAT traversal needed.

(function () {
  console.log("[live.js] loaded, version=7");

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

  const videos = document.querySelectorAll("video[data-stream]");
  for (const video of videos) {
    const stream = video.dataset.stream;
    const status = document.getElementById(`s-${stream}`);
    start(video, stream, status).catch((err) => {
      console.error(`[${stream}] start error:`, err);
      status.textContent = `error: ${err.message}`;
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

  function setMode(mode, spotlight) {
    main.dataset.mode = mode;
    // Tear down any prior panzoom whenever the mode changes — different
    // spotlight = different video element = need a fresh instance.
    if (activeZoom) {
      try { activeZoom.dispose(); } catch (_) {}
      activeZoom = null;
    }
    cams.forEach((c) => c.classList.remove("is-zoomed"));

    if (spotlight) {
      main.dataset.spotlight = spotlight;
      cams.forEach((c) => {
        c.classList.toggle("is-spotlight", c.dataset.stream === spotlight);
      });
      // Attach panzoom to the new spotlight video. Defer one frame so
      // CSS-driven resize completes before panzoom measures bounds.
      requestAnimationFrame(() => {
        const cam = document.querySelector(`.cam[data-stream="${spotlight}"]`);
        if (!cam) return;
        const video = cam.querySelector("video");
        if (!video || typeof window.panzoom !== "function") return;
        activeZoom = window.panzoom(video, {
          maxZoom: 8,
          minZoom: 1,
          bounds: true,
          boundsPadding: 0.95,
          smoothScroll: false,
          // Disable panzoom's own double-click handling — we have our own.
          zoomDoubleClickSpeed: 1,
        });
        wireZoomControls(cam, activeZoom, video);
      });
    } else {
      delete main.dataset.spotlight;
      cams.forEach((c) => c.classList.remove("is-spotlight"));
    }
  }

  // Hook up the corner +/-/⛶ buttons + double-click + keyboard reset.
  function wireZoomControls(cam, pz, video) {
    const btnIn  = cam.querySelector(".zoom-in");
    const btnOut = cam.querySelector(".zoom-out");
    const btnFit = cam.querySelector(".zoom-fit");

    const zoomAt = (factor, x, y) => {
      const r = video.getBoundingClientRect();
      pz.smoothZoom(x ?? (r.left + r.width / 2),
                    y ?? (r.top + r.height / 2), factor);
    };

    btnIn  && btnIn.addEventListener("click", (e) => { e.stopPropagation(); zoomAt(1.5); });
    btnOut && btnOut.addEventListener("click", (e) => { e.stopPropagation(); zoomAt(1 / 1.5); });
    btnFit && btnFit.addEventListener("click", (e) => {
      e.stopPropagation();
      pz.moveTo(0, 0);
      pz.zoomAbs(0, 0, 1);
    });

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

  cams.forEach((cam) => {
    cam.addEventListener("click", (e) => {
      // Ignore the native video controls, zoom buttons, or any
      // interaction inside the video while in spotlight (so panning
      // doesn't bubble up and exit spotlight).
      if (e.target.tagName === "VIDEO" && e.target.controls) return;
      if (e.target.closest(".zoom-controls")) return;
      const stream = cam.dataset.stream;
      const inSpotlight = cam.classList.contains("is-spotlight");
      // Inside the spotlighted video, suppress click-to-collapse so
      // pan/zoom interactions don't accidentally go back to grid.
      // Header (h2) and status row outside the video still collapse.
      if (inSpotlight && e.target.closest(".video-wrap")) return;

      if (main.dataset.mode === "grid") {
        setMode("spotlight", stream);
      } else if (main.dataset.spotlight === stream) {
        setMode("grid");
      } else {
        setMode("spotlight", stream);
      }
    });
  });

  async function start(video, stream, status) {
    console.log(`[${stream}] start()`);
    const cached = getCachedWebRTCResult();
    // Skip WebRTC if either (a) we've cached a failure for this browser
    // or (b) we're on Chromium and haven't proven WebRTC works here.
    // Chromium's mDNS obfuscation means the attempt would just time out.
    const skipWebRTC = cached === "fail" || (isChromium && cached !== "ok");
    if (skipWebRTC) {
      console.log(
        `[${stream}] skipping WebRTC (` +
          (cached === "fail"
            ? "cached failure"
            : "Chromium without proven WebRTC support") +
          ")"
      );
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

    // 3s is enough for LAN ICE; longer just wastes user-visible time
    // before the MSE fallback. The localStorage cache means most users
    // only hit this once.
    const timer = setTimeout(() => rejectConn(new Error("ICE timeout")), 3000);

    pc.ontrack = (e) => {
      if (video.srcObject !== e.streams[0]) video.srcObject = e.streams[0];
    };
    pc.onconnectionstatechange = () => {
      console.log(`[${stream}] pc state:`, pc.connectionState);
      if (pc.connectionState === "connected") {
        clearTimeout(timer);
        status.textContent = "live (WebRTC)";
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

    // Probe codecs the browser can decode.
    const candidates = [
      "avc1.640029",  // H.264 High@4.1
      "avc1.4D001F",  // H.264 Main@3.1 (Dahuas — confirmed via go2rtc probe)
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
    video.addEventListener("error", (e) =>
      console.error(`[${stream}] video error:`, e, video.error)
    );

    video._ws = ws;
  }
})();
