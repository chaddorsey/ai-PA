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
    // showModal throws if the dialog is already open. Guard so callers
    // that don't know whether the modal is currently displayed (e.g.
    // direct card clicks while a modal is open) don't crash.
    if (!dialog.open) {
      body.innerHTML = '<p style="padding:32px;text-align:center;color:#6b4a3a;">Loading…</p>';
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      document.body.classList.add("modal-open");
    }

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

  // Walk the gallery in DOM order to find the list of currently-loaded
  // event_ids so the prev/next arrows can navigate inside the active
  // tab+filter without a refetch.
  function findSiblingIds() {
    return Array.from(document.querySelectorAll("#highlights .highlight[data-event-id]"))
      .map((el) => el.dataset.eventId);
  }

  // Slide-animated navigation between cards inside the modal.
  //
  // The whole point: the modal chrome stays in place. Only the
  // .modal-stage swaps. We bypass openCardModal because it (a) calls
  // dialog.showModal() again — which is a no-op or throws on an
  // already-open dialog, but in some browsers visibly flashes — and
  // (b) sets body.innerHTML to a "Loading…" placeholder while it
  // fetches, which the user sees as a brief blank flash.
  //
  // Instead: fetch the next highlight in parallel with the slide-out
  // animation, then render the new viewer directly into the body
  // and slide it in. Old and new stages coexist briefly (old at
  // -100%, new at +100% → 0) so there's no empty frame between.
  let sliding = false;
  async function slideToCard(eventId, direction) {
    if (sliding) return;
    sliding = true;

    const outClass = direction === "next" ? "sliding-out-left" : "sliding-out-right";
    const inClass  = direction === "next" ? "sliding-in-from-right" : "sliding-in-from-left";

    // Kick off slide-out + fetch concurrently.
    const oldStage = body.querySelector(".modal-stage");
    if (oldStage) oldStage.classList.add(outClass);
    let newH = null;
    try {
      const r = await fetch(`/api/highlights/${encodeURIComponent(eventId)}`,
        { credentials: "same-origin" });
      if (r.ok) newH = await r.json();
    } catch (err) {
      console.error("[modal] slide fetch failed", err);
    }
    if (!newH) { sliding = false; return; }

    // Wait for the slide-out to finish (~260ms) before swapping
    // body content. We started the timer when the class was added,
    // and the fetch usually finishes faster than that on local API.
    await new Promise((res) => setTimeout(res, 280));

    current = newH;
    // Render with the slide-in class already applied — the stage
    // appears off-screen on its first paint, never at center.
    renderViewer(newH, direction === "next" ? "right" : "left");

    const newStage = body.querySelector(".modal-stage");
    if (newStage) {
      newStage.getBoundingClientRect();   // force reflow before transition
      requestAnimationFrame(() => {
        newStage.classList.add("sliding-in-active");
      });
      // After the transition completes, drop the slide classes so the
      // stage returns to its natural (in-flow, transform-none) state.
      // Removing the classes is fine because both target the same
      // transform: translateX(0) endpoint — no visible change.
      setTimeout(() => {
        newStage.classList.remove(inClass, "sliding-in-active");
      }, 380);
    }
    sliding = false;
  }
  window.slideToCard = slideToCard;

  // Keyboard shortcuts: ←/→ navigate (with slide), ESC closes.
  document.addEventListener("keydown", (e) => {
    if (!dialog.open) return;
    if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const siblings = findSiblingIds();
      if (!current) return;
      const i = siblings.indexOf(current.event_id);
      if (i < 0) return;
      const direction = e.key === "ArrowLeft" ? "prev" : "next";
      const target = direction === "prev" ? siblings[i - 1] : siblings[i + 1];
      if (target) {
        e.preventDefault();
        slideToCard(target, direction);
      }
    }
  });

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

  function renderViewer(h, slideInFrom) {
    teardownVideo();

    const speciesBadge = renderSpeciesBadge(h);
    const sharedBadge = (h.favorite_count || 0) >= 2
      ? `<span class="modal-badge shared">⭐ ${h.favorite_count}</span>` : "";
    const featuredBadge = h.featured
      ? `<span class="modal-badge featured">★ Featured</span>` : "";

    const t = new Date(h.start_time * 1000).toLocaleString();

    const siblings = findSiblingIds();
    const idx = siblings.indexOf(h.event_id);
    const prevId = idx > 0 ? siblings[idx - 1] : null;
    const nextId = (idx >= 0 && idx < siblings.length - 1) ? siblings[idx + 1] : null;

    // If we're sliding in from a side, bake the slide-in class into
    // the initial HTML so the new stage is NEVER painted at the
    // default position 0 between insertion and the requestAnimationFrame
    // that triggers the slide-in transition.
    const slideClass = slideInFrom ? ` sliding-in-from-${slideInFrom}` : "";
    body.innerHTML = `
      <div class="modal-stage${slideClass}">
        <div class="modal-video-wrap">
          <video class="modal-video" controls autoplay muted playsinline></video>
          <button class="modal-nav prev" type="button" aria-label="Previous clip" ${prevId ? "" : "disabled"}>
            <span class="material-icons">chevron_left</span>
          </button>
          <button class="modal-nav next" type="button" aria-label="Next clip" ${nextId ? "" : "disabled"}>
            <span class="material-icons">chevron_right</span>
          </button>
        </div>
        <div class="modal-meta">
          <h2 class="modal-title" id="card-modal-title">${escapeHtml((window.prettyCamera||(s=>s))(h.camera))} · ${t}</h2>
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

    // Wire prev/next nav with a slide animation between cards. The
    // viewer only swaps content (no full-modal teardown), so the
    // overall feeling is a single carousel of clips.
    const prevBtn = body.querySelector(".modal-nav.prev");
    const nextBtn = body.querySelector(".modal-nav.next");
    if (prevBtn && prevId) prevBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      slideToCard(prevId, "prev");
    });
    if (nextBtn && nextId) nextBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      slideToCard(nextId, "next");
    });

    // Pinch / scroll / drag to zoom into the video. Bound after the
    // video element exists so panzoom can measure its size on first
    // load.
    bindPanzoom(videoEl, body.querySelector(".modal-video-wrap"));

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
    // No Foxes button. Shared/global semantics: in the No Foxes
    // view it reads "↩ Restore" and globally clears all demote
    // votes (with a warning) since the bucket is community-flagged.
    const inNoFoxesView = (document.querySelector(".tab.active")?.dataset.bucket) === "demoted";
    if (inNoFoxesView) {
      actionsBar.appendChild(actionBtn("↩ Restore", "demote", false, async () => {
        if (!confirm("Restore this clip to the main highlights view for everyone? It's currently flagged as 'No Foxes' by someone in the family — restoring will move it back into circulation for all users.")) return;
        const r = await fetch(`/api/actions/${encodeURIComponent(h.event_id)}/unflag_no_foxes`,
          { method: "POST", credentials: "same-origin" });
        if (!r.ok) { alert("Couldn't restore."); return; }
        const data = await r.json();
        Object.assign(h, data.highlight || {});
        // Card leaves the No Foxes bucket; close the modal so the
        // gallery refreshes naturally on the user's next action.
        window.closeCardModal();
      }));
    } else {
      actionsBar.appendChild(actionBtn("🚫", "demote", h.my_demoted, async () => {
        const wasDemoted = h.my_demoted;
        const updated = await postAction(h.event_id, wasDemoted ? "clear" : "demote");
        if (updated) { Object.assign(h, updated); renderViewer(h); }
      }));
    }
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
    // Delete (admin-only, irreversible)
    if (window.IS_ADMIN) {
      actionsBar.appendChild(actionBtn(
        "🗑 Delete", "delete", false,
        async () => {
          if (!confirm("Permanently delete this clip? Removes the video, thumbnail, all remixes, and all user actions. This cannot be undone.")) return;
          const r = await fetch(
            `/api/admin/highlights/${encodeURIComponent(h.event_id)}`,
            { method: "DELETE", credentials: "same-origin" }
          );
          if (!r.ok) {
            alert("Couldn't delete clip.");
            return;
          }
          // Remove the card from the gallery if it's still there.
          const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
          if (card) {
            card.style.transition = "opacity 0.3s, transform 0.3s";
            card.style.opacity = "0";
            card.style.transform = "scale(0.95)";
            setTimeout(() => card.remove(), 300);
          }
          window.closeCardModal();
        }
      ));
    }
    // Archive toggle (per-user)
    actionsBar.appendChild(actionBtn(
      h.my_archived ? "🗃 Unarchive" : "🗃 Archive",
      "archive", !!h.my_archived,
      async () => {
        const wasArchived = !!h.my_archived;
        const r = await fetch(
          `/api/actions/${encodeURIComponent(h.event_id)}/${wasArchived ? "unarchive" : "archive"}`,
          { method: "POST", credentials: "same-origin" }
        );
        if (!r.ok) return;
        const data = await r.json();
        Object.assign(h, data.highlight || {});
        renderViewer(h);
      }
    ));

    // Existing remixes for this clip — list them below the actions
    // so the user can jump to a specific cut without leaving the
    // modal. Each entry is a link to /remix/<remix_id> which is the
    // standalone remix-playback page (already gated by Access).
    if (Array.isArray(h.remixes) && h.remixes.length) {
      const panel = document.createElement("div");
      panel.className = "modal-remixes";
      panel.innerHTML = `<h3 class="modal-remixes-h">🎬 Remixes <span class="muted">(${h.remixes.length})</span></h3>`;
      const list = document.createElement("div");
      list.className = "modal-remixes-list";
      for (const r of h.remixes) {
        const dur = (r.end_offset_s - r.start_offset_s).toFixed(1);
        const username = r.created_by ? r.created_by.split("@")[0] : "anonymous";
        const titleText = r.title || "(untitled)";
        const zoom = (r.zoom_scale && r.zoom_scale > 1.01) ? ` · zoom ${r.zoom_scale.toFixed(1)}×` : "";
        const item = document.createElement("a");
        item.className = "modal-remix-item";
        item.href = "javascript:void(0)";   // stay in modal
        item.addEventListener("click", (e) => {
          e.preventDefault();
          renderRemixPlayback(h, r);
        });
        item.innerHTML = `
          <span class="rx-author">@${escapeHtml(username)}</span>
          <span class="rx-title">${escapeHtml(titleText)}</span>
          <span class="rx-meta muted">${dur}s${zoom}</span>`;
        list.appendChild(item);
      }
      panel.appendChild(list);
      body.querySelector(".modal-stage").appendChild(panel);
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
      const zoomChanged = panzoomInstance && Math.abs((panzoomInstance.getTransform?.()?.scale ?? 1) - 1) > 0.02;
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
        const wasPlaying = !videoEl.paused;
        videoEl.pause();
        playPause.textContent = "▶";
        const move = (ev) => {
          const rect = track.getBoundingClientRect();
          let pct = (ev.clientX - rect.left) / rect.width;
          pct = Math.max(0, Math.min(1, pct));
          const t = pct * (videoEl.duration || 0);
          if (key === "start") state.start = Math.min(t, state.end - 0.2);
          else                state.end   = Math.max(t, state.start + 0.2);
          state.dirty = true;
          // Seek the video to the dragged handle so the playhead
          // tracks the trim edge in real time. Without this the
          // scrubber stays stuck at its old position until the user
          // releases and presses play.
          videoEl.currentTime = (key === "start") ? state.start : state.end;
          updateTrimVisuals();
        };
        const up = () => {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
          if (wasPlaying) {
            videoEl.currentTime = state.start;
            videoEl.play();
            playPause.textContent = "❚❚";
          }
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
      });
    }
    dragHandle(startH, "start");
    dragHandle(endH, "end");

    // Click anywhere on the track (not on a handle) to seek.
    track.addEventListener("click", (e) => {
      if (e.target === startH || e.target === endH) return;
      const rect = track.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      const t = pct * (videoEl.duration || 0);
      videoEl.currentTime = Math.max(state.start, Math.min(state.end, t));
      updatePlayhead();
    });

    titleInp.addEventListener("input", () => {
      state.dirtyTitle = titleInp.value.trim().length > 0;
      updateTrimVisuals();
    });

    // Pan/zoom on the video. anvaka/panzoom API is "on('zoom', cb)" +
    // getTransform(), smoothZoom(cx, cy, factor), zoomAbs(x, y, scale).
    panzoomInstance = bindPanzoom(videoEl, wrap);
    if (panzoomInstance) {
      panzoomInstance.on("zoom", () => {
        const t = panzoomInstance.getTransform();
        zoomDisp.textContent = `zoom: ${t.scale.toFixed(2)}×`;
        updateTrimVisuals();
      });
      const zin = body.querySelector(".zoom-in");
      const zout = body.querySelector(".zoom-out");
      const zfit = body.querySelector(".zoom-fit");
      if (zin) zin.addEventListener("click", (e) => {
        e.stopPropagation();
        const r = wrap.getBoundingClientRect();
        panzoomInstance.smoothZoom(r.left + r.width/2, r.top + r.height/2, 1.5);
      });
      if (zout) zout.addEventListener("click", (e) => {
        e.stopPropagation();
        const cur = panzoomInstance.getTransform().scale;
        const next = cur / 1.5;
        if (next <= 1.05) {
          panzoomInstance.zoomAbs(0, 0, 1);
          panzoomInstance.moveTo(0, 0);
        } else {
          const r = wrap.getBoundingClientRect();
          panzoomInstance.smoothZoom(r.left + r.width/2, r.top + r.height/2, 1/1.5);
        }
      });
      if (zfit) zfit.addEventListener("click", (e) => {
        e.stopPropagation();
        panzoomInstance.zoomAbs(0, 0, 1);
        panzoomInstance.moveTo(0, 0);
      });
    }

    cancelBtn.addEventListener("click", () => renderViewer(h));

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
      const transform = panzoomInstance?.getTransform?.() ?? { scale: 1, x: 0, y: 0 };
      const payload = {
        title: titleInp.value.trim() || null,
        start_offset_s: state.start,
        end_offset_s:   state.end,
        zoom_scale:     transform.scale,
        zoom_x: 0.5,
        zoom_y: 0.5,
      };
      // Capture current pan center if zoomed (anvaka/panzoom returns
      // x/y as the translation in screen pixels of the [0,0] origin).
      if (transform.scale > 1.02) {
        const r = wrap.getBoundingClientRect();
        payload.zoom_x = (r.width / 2 - transform.x) / (r.width * transform.scale);
        payload.zoom_y = (r.height / 2 - transform.y) / (r.height * transform.scale);
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
  // Remix playback — read-only view of a saved remix inside the modal.
  // Plays the parent clip seeking from start_offset to end_offset and
  // applies the saved zoom region. Includes a "← See original highlight"
  // link that swaps back to the regular viewer for the parent.
  // ===========================================================================
  function renderRemixPlayback(parentH, remix) {
    teardownVideo();
    const username = remix.created_by ? remix.created_by.split("@")[0] : "anonymous";
    const dur = (remix.end_offset_s - remix.start_offset_s).toFixed(1);
    const title = remix.title || "(untitled)";

    body.innerHTML = `
      <div class="modal-stage modal-stage-remix-play">
        <div class="modal-back-row">
          <button class="modal-back" type="button" id="rp-back">← See original highlight</button>
        </div>
        <div class="modal-video-wrap">
          <video class="modal-video" controls autoplay muted playsinline></video>
        </div>
        <div class="modal-meta">
          <h2 class="modal-title">🎬 ${escapeHtml(title)}</h2>
          <div class="modal-badges">
            <span class="modal-badge fox">@${escapeHtml(username)}</span>
            <span class="modal-meta-extra">${dur}s</span>
          </div>
        </div>
      </div>
    `;

    videoEl = body.querySelector(".modal-video");
    videoEl.src = `/api/highlights/${encodeURIComponent(parentH.event_id)}/clip`;
    const wrap = body.querySelector(".modal-video-wrap");

    // Seek to start_offset, stop at end_offset.
    videoEl.addEventListener("loadedmetadata", () => {
      videoEl.currentTime = remix.start_offset_s || 0;
    }, { once: true });
    videoEl.addEventListener("timeupdate", () => {
      if (remix.end_offset_s && videoEl.currentTime >= remix.end_offset_s - 0.05) {
        videoEl.pause();
      }
    });

    // Apply saved zoom region (if any) via panzoom — for read-only
    // playback, we just zoom-and-pan in once on load, no interactive
    // controls. Bind panzoom anyway so the viewer can pinch/scroll
    // to adjust.
    panzoomInstance = bindPanzoom(videoEl, wrap);
    if (panzoomInstance && remix.zoom_scale && remix.zoom_scale > 1.01) {
      videoEl.addEventListener("loadedmetadata", () => {
        const r = wrap.getBoundingClientRect();
        const cx = (remix.zoom_x || 0.5) * r.width;
        const cy = (remix.zoom_y || 0.5) * r.height;
        try {
          panzoomInstance.zoomAbs(0, 0, remix.zoom_scale);
          panzoomInstance.moveTo(
            r.width / 2 - cx * remix.zoom_scale,
            r.height / 2 - cy * remix.zoom_scale
          );
        } catch (err) { /* ignore */ }
      }, { once: true });
    }

    body.querySelector("#rp-back").addEventListener("click", () => {
      renderViewer(parentH);
    });
  }

  // ===========================================================================
  // Panzoom binding — used by both the viewer and the remix editor.
  // Uses the lowercase anvaka/panzoom library (window.panzoom) which is
  // what clip.js / live.js already use. The capital-P @panzoom/panzoom
  // library has a different API and isn't loaded.
  // ===========================================================================
  function bindPanzoom(videoTarget, wrapEl) {
    if (typeof window.panzoom !== "function" || !videoTarget || !wrapEl) {
      console.warn("[modal] panzoom missing", { hasLib: typeof window.panzoom });
      return null;
    }
    try {
      videoTarget.style.transformOrigin = "0 0";
      const inst = window.panzoom(videoTarget, {
        maxZoom: 6, minZoom: 1, bounds: true,
        boundsPadding: 0.95, zoomDoubleClickSpeed: 1,
      });
      return inst;
    } catch (err) {
      console.warn("[modal] panzoom init failed", err);
      return null;
    }
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
