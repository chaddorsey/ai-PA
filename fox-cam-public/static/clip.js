// Single-clip permalink page. Two modes share this template:
//
//   /clip/<event_id>          - default view; existing remixes listed
//                                below. Favorited cards add a "Remix"
//                                link that re-routes here with ?remix=1
//                                to enter remix mode.
//
//   /clip/<event_id>?remix=1  - remix-mode editor: focused player with
//                                a custom trim timeline + drag handles,
//                                pinch/scroll zoom (panzoom), title input,
//                                Save Remix button (enabled only once the
//                                user has actually edited something).
//
//   /remix/<remix_id>         - read-only playback of a saved remix:
//                                jumps to start_offset, stops at end_offset,
//                                applies the saved zoom region.
//
// The editor never tries to remix a non-favorited clip via UI; the
// Remix link in card.js only renders when h.my_favorited is true.
// Direct ?remix=1 URLs work regardless (CF Access already gates the page).

(async function () {
  const main = document.querySelector("main.clip-page");
  const eventId = main.dataset.eventId;
  const remixId = main.dataset.remixId;
  const card = document.getElementById("clip-card");
  const params = new URLSearchParams(location.search);
  const wantRemixMode = params.get("remix") === "1";

  let highlight = null;
  let remix = null;            // present on /remix/<id>
  let videoEl = null;          // active <video> on the page
  let pzInstance = null;       // panzoom instance bound to the active video

  // Probe identity so anonymous viewers (those who reached this page
  // via a shared featured-clip link) get a clean read-only view: no
  // favorite/demote/remix actions, no "Remixes" panel below.
  let whoami = { authed: false, admin: false };
  try {
    const wr = await fetch("/api/whoami", { credentials: "same-origin" });
    if (wr.ok) whoami = await wr.json();
  } catch { /* default to anonymous */ }
  window.IS_ADMIN = !!whoami.admin;
  if (!whoami.authed) {
    document.body.classList.add("is-anonymous");
    // Inject an explicit back-to-landing link for anonymous viewers,
    // since the default .meta-note (which links to /highlights) is
    // hidden by CSS for them.
    const back = document.createElement("a");
    back.className = "anon-back-link";
    back.href = "/";
    back.textContent = "← Back to Our Foxes";
    main.appendChild(back);
  }

  try {
    if (remixId) {
      const rr = await fetch(`/api/remixes/${encodeURIComponent(remixId)}`);
      if (!rr.ok) throw new Error(`remix ${rr.status}`);
      const body = await rr.json();
      remix = body.remix;
      highlight = body.highlight;
    } else if (eventId) {
      const r = await fetch(`/api/highlights/${encodeURIComponent(eventId)}`);
      if (r.status === 404) { card.querySelector(".meta").textContent = "Clip not found."; return; }
      if (!r.ok) throw new Error(`highlight ${r.status}`);
      highlight = await r.json();
    } else {
      card.querySelector(".meta").textContent = "No clip specified.";
      return;
    }

    if (wantRemixMode && highlight) {
      enterRemixMode(highlight);
      return;
    }

    // Default render: card with autoplaying video, list of remixes below.
    const fresh = window.makeCard(highlight);
    fresh.classList.add("clip-permalink-card");
    card.replaceWith(fresh);
    const wrap = fresh.querySelector(".thumb-wrap") || fresh.querySelector("img")?.parentElement;
    const img = fresh.querySelector("img");
    if (img) {
      videoEl = document.createElement("video");
      videoEl.src = `/api/highlights/${highlight.event_id}/clip`;
      videoEl.controls = true;
      videoEl.autoplay = true;
      videoEl.muted = true;
      videoEl.playsInline = true;
      img.replaceWith(videoEl);

      if (remix) applyRemixPlayback(videoEl, wrap, remix);
      else if (window.applyPrerollSkip) window.applyPrerollSkip(videoEl);
    }

    // Show existing remixes below the clip (read-only view).
    if (!remix) {
      const panel = document.getElementById("remix-panel");
      panel.id = "remixes";       // anchor target for #remixes deep-link
      panel.hidden = false;
      renderRemixList(highlight.remixes || []);
      // If we landed with #remixes in the URL (from card link), scroll
      // to the panel after render so the user lands on the list.
      if (location.hash === "#remixes") {
        requestAnimationFrame(() => {
          panel.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    }
  } catch (e) {
    console.error(e);
    if (card) card.querySelector(".meta").textContent = `Error: ${e.message}`;
  }

  // ---------------------------------------------------------------
  // Remix playback (read-only) — used on /remix/<id>
  // ---------------------------------------------------------------
  function applyRemixPlayback(video, wrap, remix) {
    const start = remix.start_offset_s || 0;
    const end = remix.end_offset_s;
    const seek = () => { try { video.currentTime = start; } catch (_) {} };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
    video.addEventListener("timeupdate", () => {
      if (typeof end === "number" && video.currentTime >= end) video.pause();
    });
    if (remix.zoom_scale && remix.zoom_scale > 1.01 && wrap) {
      const applyZoom = () => {
        const r = wrap.getBoundingClientRect();
        const cx = remix.zoom_x ?? 0.5;
        const cy = remix.zoom_y ?? 0.5;
        const s = remix.zoom_scale;
        const tx = (r.width / 2) - (cx * r.width * s);
        const ty = (r.height / 2) - (cy * r.height * s);
        video.style.transformOrigin = "0 0";
        video.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
      };
      if (video.readyState >= 1) applyZoom();
      else video.addEventListener("loadedmetadata", applyZoom, { once: true });
    }
  }

  // ---------------------------------------------------------------
  // Render existing remix list below the clip
  // ---------------------------------------------------------------
  function renderRemixList(remixes) {
    const list = document.getElementById("remix-list");
    const count = document.getElementById("remix-count");
    list.innerHTML = "";
    count.textContent = remixes.length ? `(${remixes.length})` : "";
    if (!remixes.length) {
      list.innerHTML = '<p class="muted">No remixes yet — favorite this clip and click ✂️ Remix to capture one.</p>';
      return;
    }
    for (const r of remixes) {
      const dur = (r.end_offset_s - r.start_offset_s).toFixed(1);
      const a = document.createElement("a");
      a.href = `/remix/${r.remix_id}`;
      a.className = "remix-item";
      const zoom = (r.zoom_scale && r.zoom_scale > 1.01) ? ` · zoom ${r.zoom_scale.toFixed(1)}×` : "";
      const username = r.created_by ? r.created_by.split('@')[0] : "anonymous";
      const title = r.title ? escapeHtml(r.title) : '<em class="muted">(untitled)</em>';
      a.innerHTML = `
        <div class="remix-title">
          <span class="remix-author">@${escapeHtml(username)}</span>
          <span class="remix-sep">·</span>
          ${title}
        </div>
        <div class="remix-meta">${dur}s${zoom}</div>`;
      list.appendChild(a);
    }
  }

  // ---------------------------------------------------------------
  // Remix mode (the editor)
  // ---------------------------------------------------------------
  function enterRemixMode(h) {
    // Hide the original card + remixes panel; show the editor stage.
    card.hidden = true;
    document.getElementById("remix-panel").hidden = true;
    const stage = document.getElementById("remix-mode");
    stage.hidden = false;

    const video = document.getElementById("remix-video");
    video.src = `/api/highlights/${h.event_id}/clip`;
    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    videoEl = video;

    const titleInput = document.getElementById("remix-title");
    const saveBtn = document.getElementById("remix-save");
    const cancelBtn = document.getElementById("remix-cancel");
    const ppBtn = document.getElementById("remix-playpause");
    const timeLbl = document.getElementById("remix-time");
    const trimDisplay = document.getElementById("remix-trim-display");
    const zoomDisplay = document.getElementById("remix-zoom-display");

    // Editor state — comparing against these on every input event
    // determines whether the Save button enables.
    const initialState = { start: 0, end: 0, zoom: 1, title: "" };
    const state = { start: 0, end: 0, zoom: 1, title: "" };

    const recomputeDirty = () => {
      const dirty =
        Math.abs(state.start - initialState.start) > 0.05 ||
        Math.abs(state.end - initialState.end) > 0.05 ||
        Math.abs(state.zoom - initialState.zoom) > 0.05 ||
        state.title.trim() !== initialState.title.trim();
      saveBtn.disabled = !dirty;
    };

    // Skip the pre-roll on initial play, like normal viewing.
    video.addEventListener("loadedmetadata", () => {
      const dur = video.duration;
      if (!isFinite(dur) || dur <= 0) return;
      // Pre-roll skip: jump 25s in if the clip is long enough; family
      // can drag the start handle back if they want pre-roll context.
      const target = Math.min(25, dur * 0.4);
      try { video.currentTime = target; } catch (_) {}
      // Initialize trim window to FULL clip — initialState matches.
      initialState.start = 0; initialState.end = dur;
      state.start = 0; state.end = dur;
      updateTimeline();
      updateTimeLabels();
      // Try to play; mobile may require interaction.
      video.play().catch(() => {});
    }, { once: true });

    video.addEventListener("timeupdate", () => {
      updatePlayhead();
      updateTimeLabels();
      // Pause at end-of-trim during preview playback.
      if (video.currentTime >= state.end - 0.05) {
        video.pause();
      }
    });

    // Play/pause toggle.
    ppBtn.addEventListener("click", () => {
      if (video.paused) video.play().catch(() => {});
      else video.pause();
    });
    video.addEventListener("play", () => { ppBtn.textContent = "⏸"; });
    video.addEventListener("pause", () => { ppBtn.textContent = "▶"; });

    // Panzoom on the video so user can pinch/scroll/drag.
    if (typeof window.panzoom === "function") {
      video.style.transformOrigin = "0 0";
      pzInstance = window.panzoom(video, {
        maxZoom: 6, minZoom: 1, bounds: true,
        boundsPadding: 0.95, zoomDoubleClickSpeed: 1,
      });
      pzInstance.on("zoom", () => {
        const t = pzInstance.getTransform();
        state.zoom = t.scale;
        zoomDisplay.textContent = `zoom: ${t.scale.toFixed(2)}×`;
        recomputeDirty();
      });
    }

    // Wire the corner zoom buttons to panzoom.
    const wrap = video.parentElement;
    wrap.querySelector(".zoom-in")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!pzInstance) return;
      const r = wrap.getBoundingClientRect();
      pzInstance.smoothZoom(r.left + r.width / 2, r.top + r.height / 2, 1.5);
    });
    wrap.querySelector(".zoom-out")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!pzInstance) return;
      const cur = pzInstance.getTransform().scale;
      if (cur / 1.5 <= 1.05) {
        pzInstance.zoomAbs(0, 0, 1);
        pzInstance.moveTo(0, 0);
      } else {
        const r = wrap.getBoundingClientRect();
        pzInstance.smoothZoom(r.left + r.width / 2, r.top + r.height / 2, 1 / 1.5);
      }
    });
    wrap.querySelector(".zoom-fit")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!pzInstance) return;
      pzInstance.zoomAbs(0, 0, 1);
      pzInstance.moveTo(0, 0);
    });

    // Trim timeline handles + click-to-seek.
    const track = document.getElementById("trim-track");
    const region = track.querySelector(".trim-region");
    const startH = track.querySelector(".trim-start");
    const endH = track.querySelector(".trim-end");
    const playH = track.querySelector(".trim-playhead");

    function trackPctFromX(clientX) {
      const r = track.getBoundingClientRect();
      return Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    }
    function updateTimeline() {
      const dur = video.duration;
      if (!isFinite(dur) || dur <= 0) return;
      const sp = state.start / dur, ep = state.end / dur;
      region.style.left = `${sp * 100}%`;
      region.style.width = `${(ep - sp) * 100}%`;
      startH.style.left = `${sp * 100}%`;
      endH.style.left = `${ep * 100}%`;
      const trimSecs = state.end - state.start;
      trimDisplay.textContent =
        `Trim: ${state.start.toFixed(1)}s → ${state.end.toFixed(1)}s (${trimSecs.toFixed(1)}s)`;
    }
    function updatePlayhead() {
      const dur = video.duration;
      if (!isFinite(dur) || dur <= 0) return;
      playH.style.left = `${(video.currentTime / dur) * 100}%`;
    }
    function updateTimeLabels() {
      const dur = isFinite(video.duration) ? video.duration : 0;
      timeLbl.textContent = `${fmtTime(video.currentTime)} / ${fmtTime(dur)}`;
    }

    // Drag handlers for handles. PointerEvent works for mouse + touch.
    let dragging = null;  // 'start' | 'end' | null
    function onHandleDown(ev) {
      const which = ev.currentTarget.dataset.handle;
      dragging = which;
      ev.currentTarget.setPointerCapture?.(ev.pointerId);
      ev.preventDefault();
      ev.stopPropagation();
    }
    function onPointerMove(ev) {
      if (!dragging) return;
      const dur = video.duration;
      if (!isFinite(dur) || dur <= 0) return;
      const t = trackPctFromX(ev.clientX) * dur;
      if (dragging === "start") {
        state.start = Math.max(0, Math.min(t, state.end - 0.5));
        try { video.currentTime = state.start; } catch (_) {}
      } else {
        state.end = Math.min(dur, Math.max(t, state.start + 0.5));
      }
      updateTimeline();
      recomputeDirty();
    }
    function onPointerUp(ev) {
      dragging = null;
    }
    startH.addEventListener("pointerdown", onHandleDown);
    endH.addEventListener("pointerdown", onHandleDown);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    // Click on the track (away from handles) seeks the playhead.
    track.addEventListener("click", (ev) => {
      if (ev.target === startH || ev.target === endH) return;
      const dur = video.duration;
      if (!isFinite(dur)) return;
      try { video.currentTime = trackPctFromX(ev.clientX) * dur; } catch (_) {}
    });

    titleInput.addEventListener("input", () => {
      state.title = titleInput.value;
      recomputeDirty();
    });

    // Save: capture current panzoom transform → normalized zoom_xy.
    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      try {
        let zoomCenter = null;
        if (pzInstance && state.zoom > 1.05) {
          const t = pzInstance.getTransform();
          const r = wrap.getBoundingClientRect();
          const cx = (-t.x + r.width / 2) / (t.scale * r.width);
          const cy = (-t.y + r.height / 2) / (t.scale * r.height);
          zoomCenter = {
            x: Math.max(0, Math.min(1, cx)),
            y: Math.max(0, Math.min(1, cy)),
          };
        }
        const body = {
          title: state.title.trim() || null,
          start_offset_s: state.start,
          end_offset_s: state.end,
          zoom_x: zoomCenter?.x,
          zoom_y: zoomCenter?.y,
          zoom_scale: state.zoom,
        };
        const r = await fetch(`/api/highlights/${h.event_id}/remix`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!r.ok) throw new Error(`save ${r.status}`);
        const out = await r.json();
        const url = `${location.origin}/remix/${out.remix_id}`;
        try { await navigator.clipboard.writeText(url); } catch {}
        alert(`Remix saved.\nPermalink copied to clipboard:\n${url}`);
        // Navigate back to the clip page (without ?remix=1) so they
        // see the new remix in the list.
        location.href = `/clip/${h.event_id}`;
      } catch (e) {
        console.error(e);
        alert(`Save failed: ${e.message}`);
        saveBtn.disabled = false;
      }
    });

    cancelBtn.addEventListener("click", () => {
      // Just go back to the regular clip view (drops query param).
      location.href = `/clip/${h.event_id}`;
    });
  }

  // Helpers
  function fmtTime(s) {
    if (!isFinite(s) || s < 0) s = 0;
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
