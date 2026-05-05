/* modal.js — card-detail modal for /highlights
   ----------------------------------------------------------------------------
   Opening a card on /highlights expands it into a centered modal that
   plays the clip large and surfaces actions (favorite, demote, share,
   remix, feature) in place. The Remix button swaps the modal body to
   an inline trim editor without leaving the page; Cancel reverts to
   the viewer; Save Remix POSTs and reverts to the viewer.

   The X button, a backdrop click, or ESC closes the modal. The card.js
   click handlers do their own action work; we just open this when the
   card itself is clicked.

   Public API:
     window.openCardModal(eventId)
     window.closeCardModal()
*/
(function () {
  "use strict";

  const dialog = document.getElementById("card-modal");
  const body = document.getElementById("card-modal-body");
  const closeBtn = dialog && dialog.querySelector(".card-modal-close");
  if (!dialog || !body || !closeBtn) return;

  // Currently-open highlight + the active <video> + panzoom instance.
  let current = null;
  let videoEl = null;
  let panzoomInstance = null;

  // ===========================================================================
  // Open / close
  // ===========================================================================

  window.openCardModal = async function openCardModal(eventId) {
    body.innerHTML = '<p style="padding:32px;text-align:center;color:#6b4a3a;">Loading…</p>';
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    document.body.classList.add("modal-open");

    let h;
    try {
      const r = await fetch(`/api/highlights/${encodeURIComponent(eventId)}`,
        { credentials: "same-origin" });
      if (!r.ok) throw new Error(`fetch ${r.status}`);
      h = await r.json();
    } catch (err) {
      body.innerHTML = `<p style="padding:32px;text-align:center;color:#6b4a3a;">
        Couldn't load this clip. <a href="javascript:window.closeCardModal()">Close</a></p>`;
      return;
    }
    current = h;
    renderViewer(h);
  };

  window.closeCardModal = function closeCardModal() {
    teardownVideo();
    body.innerHTML = "";
    current = null;
    document.body.classList.remove("modal-open");
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  };

  function teardownVideo() {
    if (videoEl) {
      try { videoEl.pause(); } catch {}
      videoEl.removeAttribute("src");
      videoEl.load();
      videoEl = null;
    }
    if (panzoomInstance) {
      try { panzoomInstance.destroy(); } catch {}
      panzoomInstance = null;
    }
  }

  closeBtn.addEventListener("click", () => window.closeCardModal());
  dialog.addEventListener("click", (e) => {
    // Click on the backdrop (the dialog itself) closes; clicks bubbling
    // from inside the body don't.
    if (e.target === dialog) window.closeCardModal();
  });
  dialog.addEventListener("cancel", (e) => {
    // ESC on a <dialog> fires "cancel" before close. Wrap so our
    // teardown runs.
    e.preventDefault();
    window.closeCardModal();
  });

  // ===========================================================================
  // Default viewer layout
  // ===========================================================================

  function renderViewer(h) {
    teardownVideo();

    const speciesBadge = renderSpeciesBadge(h);
    const sharedBadge = (h.favorite_count || 0) >= 2
      ? `<span class="modal-badge shared">⭐ ${h.favorite_count}</span>` : "";
    const featuredBadge = h.featured
      ? `<span class="modal-badge featured">★ Featured</span>` : "";

    const t = new Date(h.start_time * 1000).toLocaleString();

    body.innerHTML = `
      <div class="modal-stage">
        <div class="modal-video-wrap">
          <video class="modal-video" controls autoplay muted playsinline></video>
        </div>
        <div class="modal-meta">
          <h2 class="modal-title" id="card-modal-title">${escapeHtml(h.camera)} · ${t}</h2>
          <div class="modal-badges">${speciesBadge}${sharedBadge}${featuredBadge}
            <span class="modal-meta-extra">${(h.duration_s || 0).toFixed(1)}s</span>
          </div>
        </div>
        <div class="modal-actions" id="modal-actions"></div>
      </div>
    `;

    // Attach the video stream + skip preroll.
    videoEl = body.querySelector(".modal-video");
    videoEl.src = `/api/highlights/${encodeURIComponent(h.event_id)}/clip`;
    if (window.applyPrerollSkip) window.applyPrerollSkip(videoEl);

    // Build action bar inline, mirroring card.js's row but routed back
    // through this modal so toggles update in place.
    const actionsBar = body.querySelector("#modal-actions");
    actionsBar.appendChild(actionBtn(
      h.my_favorited ? `⭐ ${h.favorite_count}` : "⭐",
      "favorite", h.my_favorited,
      async () => {
        const wasFav = h.my_favorited;
        const updated = await postAction(h.event_id, wasFav ? "clear" : "favorite");
        if (updated) {
          Object.assign(h, updated);
          renderViewer(h);
          if (!wasFav && window.deliverBadge) {
            window.deliverBadge(body.querySelector(".modal-stage"),
              "fox-3", "⭐ Mine", { badgeClass: "badge-mine" });
          }
        }
      }
    ));
    actionsBar.appendChild(actionBtn("🚫", "demote", h.my_demoted, async () => {
      const wasDemoted = h.my_demoted;
      const updated = await postAction(h.event_id, wasDemoted ? "clear" : "demote");
      if (updated) { Object.assign(h, updated); renderViewer(h); }
    }));
    actionsBar.appendChild(actionBtn("🔗 Share", "share", false, () => {
      const url = `${location.origin}/clip/${h.event_id}`;
      navigator.clipboard?.writeText(url).then(
        () => flashToast(`Link copied`),
        () => prompt("Copy this URL:", url)
      );
    }));
    if (h.my_favorited) {
      actionsBar.appendChild(actionBtn("✂️ Remix", "remix", false,
        () => renderRemixEditor(h)));
    }
    if (window.IS_ADMIN) {
      const featured = !!h.featured;
      actionsBar.appendChild(actionBtn(
        featured ? "★ Featured" : "Feature",
        "feature", featured,
        async () => toggleFeature(h)
      ));
    }
  }

  // ===========================================================================
  // Remix editor — swaps in-place inside the modal body
  // ===========================================================================

  function renderRemixEditor(h) {
    teardownVideo();

    body.innerHTML = `
      <div class="modal-stage modal-stage-remix">
        <div class="modal-video-wrap">
          <video class="modal-video" muted playsinline></video>
          <div class="zoom-controls" aria-hidden="true">
            <button class="zoom-btn zoom-in"  type="button" title="Zoom in">+</button>
            <button class="zoom-btn zoom-out" type="button" title="Zoom out">−</button>
            <button class="zoom-btn zoom-fit" type="button" title="Fit">⛶</button>
          </div>
        </div>
        <div class="remix-controls">
          <button class="remix-pp"  type="button" id="modal-remix-pp">▶</button>
          <span class="remix-time muted" id="modal-remix-time">0:00 / 0:00</span>
          <span class="remix-spacer"></span>
          <span class="muted small" id="modal-zoom-display">zoom: 1.0×</span>
        </div>
        <div class="trim-track" id="modal-trim-track">
          <div class="trim-region"></div>
          <div class="trim-handle trim-start" data-handle="start" tabindex="0"
            role="slider" aria-label="Trim start"></div>
          <div class="trim-handle trim-end"   data-handle="end"   tabindex="0"
            role="slider" aria-label="Trim end"></div>
          <div class="trim-playhead"></div>
        </div>
        <div class="remix-meta-row">
          <input id="modal-remix-title" type="text" maxlength="80"
            placeholder="Title (optional)">
          <span class="muted small" id="modal-trim-display"></span>
        </div>
        <div class="remix-actions-row">
          <button id="modal-remix-save"   class="primary" type="button" disabled>Save Remix</button>
          <button id="modal-remix-cancel" type="button">Cancel</button>
          <span class="muted small">
            Drag the orange handles to trim. Pinch / scroll the video to zoom.
          </span>
        </div>
      </div>
    `;

    // ---- Wire the editor: video, trim, zoom, save/cancel ------------------
    videoEl = body.querySelector(".modal-video");
    videoEl.src = `/api/highlights/${encodeURIComponent(h.event_id)}/clip`;

    const wrap = body.querySelector(".modal-video-wrap");
    const playPause = body.querySelector("#modal-remix-pp");
    const timeEl   = body.querySelector("#modal-remix-time");
    const zoomDisp = body.querySelector("#modal-zoom-display");
    const track    = body.querySelector("#modal-trim-track");
    const region   = track.querySelector(".trim-region");
    const startH   = track.querySelector(".trim-handle.trim-start");
    const endH     = track.querySelector(".trim-handle.trim-end");
    const playhead = track.querySelector(".trim-playhead");
    const titleInp = body.querySelector("#modal-remix-title");
    const trimDisp = body.querySelector("#modal-trim-display");
    const saveBtn  = body.querySelector("#modal-remix-save");
    const cancelBtn= body.querySelector("#modal-remix-cancel");

    // Trim state. Initial = full clip; "dirty" once user adjusts.
    const state = { start: 0, end: 0, dirty: false, dirtyTitle: false };
    let initialState = { start: 0, end: 0 };

    const fmt = (s) => {
      if (!isFinite(s)) return "0:00";
      const m = Math.floor(s / 60);
      const x = Math.floor(s % 60).toString().padStart(2, "0");
      return `${m}:${x}`;
    };

    function updateTrimVisuals() {
      const dur = videoEl.duration || 1;
      const sx = (state.start / dur) * 100;
      const ex = (state.end   / dur) * 100;
      startH.style.left = `${sx}%`;
      endH.style.left   = `${ex}%`;
      region.style.left = `${sx}%`;
      region.style.right = `${100 - ex}%`;
      trimDisp.textContent = `${fmt(state.start)} → ${fmt(state.end)} (${fmt(state.end - state.start)})`;
      const changed = Math.abs(state.start - initialState.start) > 0.05
        || Math.abs(state.end - initialState.end) > 0.05;
      const zoomChanged = panzoomInstance && Math.abs((panzoomInstance.getScale?.() ?? 1) - 1) > 0.02;
      saveBtn.disabled = !(changed || zoomChanged || state.dirtyTitle);
    }

    function updatePlayhead() {
      const dur = videoEl.duration || 1;
      playhead.style.left = `${(videoEl.currentTime / dur) * 100}%`;
      timeEl.textContent  = `${fmt(videoEl.currentTime)} / ${fmt(dur)}`;
      if (videoEl.currentTime >= state.end - 0.05) {
        videoEl.pause();
        playPause.textContent = "▶";
      }
    }

    videoEl.addEventListener("loadedmetadata", () => {
      state.start = 0;
      state.end = videoEl.duration || 0;
      initialState = { start: 0, end: state.end };
      updateTrimVisuals();
      updatePlayhead();
    });
    videoEl.addEventListener("timeupdate", updatePlayhead);

    playPause.addEventListener("click", () => {
      if (videoEl.paused) {
        if (videoEl.currentTime < state.start - 0.01 || videoEl.currentTime >= state.end - 0.05) {
          videoEl.currentTime = state.start;
        }
        videoEl.play();
        playPause.textContent = "❚❚";
      } else {
        videoEl.pause();
        playPause.textContent = "▶";
      }
    });

    function dragHandle(handle, key) {
      handle.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        handle.setPointerCapture(e.pointerId);
        const move = (ev) => {
          const rect = track.getBoundingClientRect();
          let pct = (ev.clientX - rect.left) / rect.width;
          pct = Math.max(0, Math.min(1, pct));
          const t = pct * (videoEl.duration || 0);
          if (key === "start") state.start = Math.min(t, state.end - 0.2);
          else                state.end   = Math.max(t, state.start + 0.2);
          state.dirty = true;
          updateTrimVisuals();
        };
        const up = () => {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
      });
    }
    dragHandle(startH, "start");
    dragHandle(endH, "end");

    titleInp.addEventListener("input", () => {
      state.dirtyTitle = titleInp.value.trim().length > 0;
      updateTrimVisuals();
    });

    // Pan/zoom on the video.
    if (window.Panzoom) {
      panzoomInstance = window.Panzoom(videoEl, {
        maxScale: 6, minScale: 1, contain: "outside",
        cursor: "zoom-in",
      });
      wrap.addEventListener("wheel", panzoomInstance.zoomWithWheel, { passive: false });
      videoEl.addEventListener("panzoomchange", () => {
        const s = panzoomInstance.getScale?.() ?? 1;
        zoomDisp.textContent = `zoom: ${s.toFixed(1)}×`;
        updateTrimVisuals();
      });
      body.querySelector(".zoom-in").addEventListener("click", () => panzoomInstance.zoomIn());
      body.querySelector(".zoom-out").addEventListener("click", () => panzoomInstance.zoomOut());
      body.querySelector(".zoom-fit").addEventListener("click", () => panzoomInstance.reset());
    }

    cancelBtn.addEventListener("click", () => renderViewer(h));

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
      const payload = {
        title: titleInp.value.trim() || null,
        start_offset_s: state.start,
        end_offset_s:   state.end,
        zoom_scale:     panzoomInstance?.getScale?.() ?? 1,
        zoom_x: 0.5,  // simple model: capture current pan as center
        zoom_y: 0.5,
      };
      // Capture current pan as center if zoomed.
      if (panzoomInstance && panzoomInstance.getScale?.() > 1.02) {
        const p = panzoomInstance.getPan?.() ?? { x: 0, y: 0 };
        const r = wrap.getBoundingClientRect();
        const s = panzoomInstance.getScale?.() ?? 1;
        payload.zoom_x = ((r.width / 2 - p.x) / s) / r.width;
        payload.zoom_y = ((r.height / 2 - p.y) / s) / r.height;
      }
      try {
        const r = await fetch(`/api/actions/${encodeURIComponent(h.event_id)}/remix`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          credentials: "same-origin",
        });
        if (!r.ok) {
          alert("Couldn't save remix.");
          saveBtn.disabled = false;
          saveBtn.textContent = "Save Remix";
          return;
        }
        const data = await r.json();
        // Refresh highlight (remix_count + remixes list updated).
        const refreshed = await fetch(`/api/highlights/${encodeURIComponent(h.event_id)}`,
          { credentials: "same-origin" });
        if (refreshed.ok) Object.assign(h, await refreshed.json());
        renderViewer(h);
        if (window.deliverBadge) {
          window.deliverBadge(body.querySelector(".modal-stage"),
            "raccoon-2", "🎬 Remixed", { badgeClass: "badge-remix" });
        }
      } catch (err) {
        alert("Network error saving remix.");
        saveBtn.disabled = false;
        saveBtn.textContent = "Save Remix";
      }
    });
  }

  // ===========================================================================
  // Helpers (action button factory, post helper, species badge, toast)
  // ===========================================================================

  function actionBtn(label, kind, active, onClick) {
    const b = document.createElement("button");
    b.className = `action-btn action-${kind}` + (active ? " active" : "");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
    return b;
  }

  async function postAction(eventId, action) {
    const r = await fetch(`/api/actions/${encodeURIComponent(eventId)}/${action}`,
      { method: "POST", credentials: "same-origin" });
    if (!r.ok) { console.error(`${action} failed`, r.status); return null; }
    const data = await r.json();
    return data.highlight;
  }

  async function toggleFeature(h) {
    const featured = !!h.featured;
    let url, payload;
    if (featured) {
      if (!confirm("Remove this clip from the public landing page?")) return;
      url = `/api/admin/highlights/${encodeURIComponent(h.event_id)}/unfeature`;
      payload = "{}";
    } else {
      const caption = (prompt("Optional caption (≤140 chars):", h.featured_caption || "") || "").trim();
      if (caption.length > 140) { alert("Caption max 140 chars."); return; }
      url = `/api/admin/highlights/${encodeURIComponent(h.event_id)}/feature`;
      payload = JSON.stringify({ caption: caption || null });
    }
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      credentials: "same-origin",
    });
    if (r.status === 403) { alert("Admin only."); return; }
    if (!r.ok) { alert("Couldn't update featured status."); return; }
    const data = await r.json();
    Object.assign(h, data.highlight || {});
    renderViewer(h);
    if (!featured) {
      if (window.fireParade) window.fireParade();
      if (window.deliverBadge) {
        setTimeout(() => window.deliverBadge(body.querySelector(".modal-stage"),
          "deer", "★ Featured", { badgeClass: "badge-featured" }), 400);
      }
    }
  }

  function renderSpeciesBadge(h) {
    if (!h.species) return "";
    if (["none", "person", "vehicle", "error"].includes(h.species)) {
      return `<span class="modal-badge muted">${escapeHtml(h.species)}</span>`;
    }
    const cls = h.species === "fox" ? "fox" : "wildlife";
    return `<span class="modal-badge ${cls}">${escapeHtml(h.species)}</span>`;
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function flashToast(msg) {
    const t = document.createElement("div");
    t.className = "toast show";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.classList.remove("show"), 1700);
    setTimeout(() => t.remove(), 2100);
  }

  // ===========================================================================
  // Hijack card clicks on /highlights so the card opens the modal instead
  // of navigating to /clip/{id}. Use event delegation since cards render
  // dynamically. Inner action buttons stop propagation in their handlers,
  // so this only fires when the user clicks the card body itself.
  // ===========================================================================

  document.addEventListener("click", (e) => {
    if (!document.getElementById("highlights")) return;  // not on /highlights
    const card = e.target.closest && e.target.closest(".highlight");
    if (!card || !card.dataset.eventId) return;
    // Action buttons (heart/demote/share/remix/feature) stopPropagation
    // in their own handlers, so we never reach this code for them. The
    // species "?" explain popover is a button too — let it work.
    if (e.target.closest(".action-btn, .species-why, button.species-why")) return;
    // Anchors inside the card (.time datetime, .remix-count-link) used
    // to navigate to /clip/{id}. Cancel that default and open the modal
    // for the same event instead.
    e.preventDefault();
    window.openCardModal(card.dataset.eventId);
  });
})();
