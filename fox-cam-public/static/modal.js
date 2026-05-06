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

  // Fetch single-highlight metadata. Goes through /api/actions/* —
  // the AUTHED Cloudflare Access path — so my_favorited / my_demoted
  // reflect actual per-user state. (The /api/highlights/{id} alias is
  // in the public Bypass app and CF strips the auth header there,
  // returning my_favorited=false for everyone.)
  async function fetchHighlightAuthed(eventId) {
    const r = await fetch(
      `/api/actions/${encodeURIComponent(eventId)}/highlight`,
      { credentials: "same-origin" }
    );
    if (!r.ok) throw new Error(`fetch ${r.status}`);
    return r.json();
  }

  function openLoadingDialog() {
    if (dialog.open) return;
    body.innerHTML = '<p style="padding:32px;text-align:center;color:#6b4a3a;">Loading…</p>';
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    document.body.classList.add("modal-open");
  }

  function showModalLoadError() {
    body.innerHTML = `<p style="padding:32px;text-align:center;color:#6b4a3a;">
      Couldn't load this clip. <a href="javascript:window.closeCardModal()">Close</a></p>`;
  }

  // Open the modal directly into the remix editor. Used by gallery
  // cards' ✂️ Remix button so the user never leaves /highlights —
  // Save/Cancel return to the in-modal viewer.
  window.openCardModalInRemixMode = async function openCardModalInRemixMode(eventId) {
    openLoadingDialog();
    let h;
    try { h = await fetchHighlightAuthed(eventId); }
    catch (err) { showModalLoadError(); return; }
    current = h;
    currentRemix = null;
    renderRemixEditor(h);
  };

  window.openCardModal = async function openCardModal(eventId) {
    openLoadingDialog();
    let h;
    try { h = await fetchHighlightAuthed(eventId); }
    catch (err) { showModalLoadError(); return; }
    current = h;
    // Clear remix-mode pointer left over from a prior remix session.
    // Without this, swipe-nav inside a regular highlight modal walks
    // window.REMIX_NAV_LIST instead of the highlight siblings.
    currentRemix = null;
    renderViewer(h);
  };

  // Open a saved remix in the modal in playback mode. Used from the
  // /highlights Remixes tab where each list item is a remix card.
  window.openRemixModal = async function openRemixModal(remixId) {
    if (!dialog.open) {
      body.innerHTML = '<p style="padding:32px;text-align:center;color:#6b4a3a;">Loading…</p>';
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      document.body.classList.add("modal-open");
    }
    let remix;
    try {
      const r = await fetch(`/api/remixes/${encodeURIComponent(remixId)}`,
        { credentials: "same-origin" });
      const body_ = await r.json();
      remix = body_.remix || body_;
    } catch (err) {
      body.innerHTML = `<p style="padding:32px;text-align:center;color:#6b4a3a;">
        Couldn't load this remix. <a href="javascript:window.closeCardModal()">Close</a></p>`;
      return;
    }
    let parentH;
    try {
      const pr = await fetch(`/api/highlights/${encodeURIComponent(remix.event_id)}`,
        { credentials: "same-origin" });
      parentH = await pr.json();
    } catch (err) { /* no parent */ }
    current = parentH;
    currentRemix = remix;   // tracked separately so prev/next can navigate remixes
    renderRemixPlaybackWithNav(parentH, remix);
  };

  let currentRemix = null;

  // Wrapper around the existing remix-playback view that adds prev/next
  // buttons that walk window.REMIX_NAV_LIST set by highlights.js.
  function renderRemixPlaybackWithNav(parentH, remix) {
    renderRemixPlayback(parentH, remix);
    // Inject prev/next nav into the modal-video-wrap for remix mode
    const wrap = body.querySelector(".modal-video-wrap");
    const list = window.REMIX_NAV_LIST || [];
    const idx = list.indexOf(remix.remix_id);
    const prevId = idx > 0 ? list[idx - 1] : null;
    const nextId = (idx >= 0 && idx < list.length - 1) ? list[idx + 1] : null;
    if (wrap) {
      const prev = document.createElement("button");
      prev.className = "modal-nav prev";
      prev.type = "button";
      prev.tabIndex = -1;
      prev.setAttribute("aria-label", "Previous remix");
      prev.innerHTML = `<span class="material-icons">chevron_left</span>`;
      if (!prevId) prev.disabled = true;
      prev.addEventListener("click", (e) => {
        e.stopPropagation();
        if (prevId) slideToRemix(prevId, "prev");
      });
      const next = document.createElement("button");
      next.className = "modal-nav next";
      next.type = "button";
      next.tabIndex = -1;
      next.setAttribute("aria-label", "Next remix");
      next.innerHTML = `<span class="material-icons">chevron_right</span>`;
      if (!nextId) next.disabled = true;
      next.addEventListener("click", (e) => {
        e.stopPropagation();
        if (nextId) slideToRemix(nextId, "next");
      });
      wrap.appendChild(prev);
      wrap.appendChild(next);
    }
  }

  async function slideToRemix(remixId, direction) {
    if (sliding) return;
    sliding = true;
    const oldStage = body.querySelector(".modal-stage");
    const outClass = direction === "next" ? "sliding-out-left" : "sliding-out-right";
    const inClass  = direction === "next" ? "sliding-in-from-right" : "sliding-in-from-left";
    if (oldStage) oldStage.classList.add(outClass);
    let remix, parentH;
    try {
      const r = await fetch(`/api/remixes/${encodeURIComponent(remixId)}`,
        { credentials: "same-origin" });
      const j = await r.json();
      remix = j.remix || j;
      const pr = await fetch(`/api/highlights/${encodeURIComponent(remix.event_id)}`,
        { credentials: "same-origin" });
      parentH = await pr.json();
    } catch (err) { sliding = false; return; }
    await new Promise((res) => setTimeout(res, 280));
    current = parentH;
    currentRemix = remix;
    renderRemixPlaybackWithNav(parentH, remix);
    const newStage = body.querySelector(".modal-stage");
    if (newStage) {
      newStage.classList.add(inClass);
      newStage.getBoundingClientRect();
      requestAnimationFrame(() => newStage.classList.add("sliding-in-active"));
      setTimeout(() => newStage.classList.remove(inClass, "sliding-in-active"), 380);
    }
    closeBtn.focus({ preventScroll: true });
    sliding = false;
  }

  window.closeCardModal = function closeCardModal() {
    teardownVideo();
    body.innerHTML = "";
    current = null;
    // Reset remix-mode pointer too — without this, opening a regular
    // highlight modal next would still see currentRemix as truthy
    // and swipes would route through stale REMIX_NAV_LIST entries.
    currentRemix = null;
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
    try { newH = await fetchHighlightAuthed(eventId); }
    catch (err) { console.error("[modal] slide fetch failed", err); }
    if (!newH) { sliding = false; return; }

    // Wait for the slide-out to finish (~260ms) before swapping
    // body content. We started the timer when the class was added,
    // and the fetch usually finishes faster than that on local API.
    await new Promise((res) => setTimeout(res, 280));

    current = newH;
    currentRemix = null;          // exiting any remix-mode swipe
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
    // Steal focus from any prev/next button that briefly held it,
    // so Chrome's :focus ring (sometimes rendered as box-shadow even
    // after we set outline:none) doesn't linger on the prev arrow.
    closeBtn.focus({ preventScroll: true });
    sliding = false;
  }
  window.slideToCard = slideToCard;

  // Keyboard shortcuts: ←/→ navigate (with slide), ESC closes.
  document.addEventListener("keydown", (e) => {
    if (!dialog.open) return;
    if (e.target && /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const direction = e.key === "ArrowLeft" ? "prev" : "next";
      navigateModal(direction, e);
    }
  });

  // Unified navigation entry point — used by both keyboard and touch
  // swipe. Handles both highlight-card mode (slideToCard over
  // findSiblingIds()) and remix-playback mode (slideToRemix over
  // window.REMIX_NAV_LIST). Returns true if a slide fired so the
  // caller can suppress default browser behavior.
  function navigateModal(direction, ev) {
    if (currentRemix) {
      const list = window.REMIX_NAV_LIST || [];
      const i = list.indexOf(currentRemix.remix_id);
      if (i < 0) return false;
      const target = direction === "prev" ? list[i - 1] : list[i + 1];
      if (!target) return false;
      if (ev && ev.preventDefault) ev.preventDefault();
      slideToRemix(target, direction);
      return true;
    }
    if (!current) return false;
    const siblings = findSiblingIds();
    const i = siblings.indexOf(current.event_id);
    if (i < 0) return false;
    const target = direction === "prev" ? siblings[i - 1] : siblings[i + 1];
    if (!target) return false;
    if (ev && ev.preventDefault) ev.preventDefault();
    slideToCard(target, direction);
    return true;
  }

  // Touch swipe handler — bound on the dialog (not the video wrap, so
  // pinch on the video stays with panzoom). A horizontal swipe of >60px
  // and at least 1.5× more horizontal than vertical fires navigateModal.
  // Vertical scroll inside the body (touch-action: pan-y) is preserved.
  //
  // Guards (review-fix):
  // - Reject when touch starts on an interactive control: a horizontal
  //   drag that ends past 60px would otherwise fire BOTH the button's
  //   click AND a navigation, executing the action against the wrong
  //   clip after the slide.
  // - Reset touchStartT whenever a second finger lands (pinch-zoom):
  //   without this, lifting one of two pinch fingers fires touchend
  //   with changedTouches.length===1, producing a phantom navigation.
  const SWIPE_IGNORE_TARGETS =
    "button, a, input, select, textarea, .action-btn, " +
    ".card-modal-close, .card-modal-replay, .modal-nav, " +
    ".zoom-btn, .zoom-controls, .meta-download";
  let touchStartX = 0, touchStartY = 0, touchStartT = 0;
  dialog.addEventListener("touchstart", (e) => {
    // Multi-touch invalidates any prior single-finger anchor.
    if (e.touches.length !== 1) { touchStartT = 0; return; }
    const t = e.touches[0];
    if (e.target && e.target.closest && e.target.closest(SWIPE_IGNORE_TARGETS)) {
      touchStartT = 0;
      return;
    }
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchStartT = Date.now();
  }, { passive: true });
  dialog.addEventListener("touchend", (e) => {
    if (!touchStartT) return;
    // Only commit when the LAST finger lifted — this guards against
    // mid-pinch single-finger lifts that we'd otherwise read as a
    // swipe across the original anchor.
    if (e.touches.length !== 0) { touchStartT = 0; return; }
    const dt = Date.now() - touchStartT;
    touchStartT = 0;
    if (dt > 600) return;             // too slow → user was holding, not swiping
    if (e.changedTouches.length !== 1) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - touchStartX;
    const dy = t.clientY - touchStartY;

    // Vertical swipe-down on phones → dismiss the bottom sheet.
    // Threshold higher than horizontal nav (100px) so pull-to-scroll
    // intent doesn't fire close. Only on viewports where the modal
    // is rendered as a sheet.
    const isPhoneSheet = window.matchMedia("(max-width: 720px)").matches;
    if (isPhoneSheet && dy > 100 && Math.abs(dy) > Math.abs(dx) * 1.5) {
      window.closeCardModal();
      return;
    }

    if (Math.abs(dx) < 60) return;
    if (Math.abs(dx) < Math.abs(dy) * 1.5) return;
    navigateModal(dx > 0 ? "prev" : "next", null);
  }, { passive: true });

  closeBtn.addEventListener("click", () => window.closeCardModal());
  // Replay button — restart the current modal video from frame 0.
  const replayBtn = dialog.querySelector(".card-modal-replay");
  if (replayBtn) {
    replayBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!videoEl) return;
      try {
        videoEl.currentTime = 0;
        const p = videoEl.play();
        if (p && typeof p.catch === "function") p.catch(() => {});
      } catch {}
    });
  }
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
          <button class="modal-nav prev" type="button" aria-label="Previous clip" tabindex="-1" ${prevId ? "" : "disabled"}>
            <span class="material-icons">chevron_left</span>
          </button>
          <button class="modal-nav next" type="button" aria-label="Next clip" tabindex="-1" ${nextId ? "" : "disabled"}>
            <span class="material-icons">chevron_right</span>
          </button>
          <div class="zoom-controls" aria-hidden="true">
            <button class="zoom-btn zoom-in"  type="button" title="Zoom in"  aria-label="Zoom in"><span class="material-icons">add</span></button>
            <button class="zoom-btn zoom-out" type="button" title="Zoom out" aria-label="Zoom out"><span class="material-icons">remove</span></button>
            <button class="zoom-btn zoom-fit" type="button" title="Fit"      aria-label="Fit"><span class="material-icons">crop_free</span></button>
          </div>
        </div>
        <div class="modal-meta">
          <h2 class="modal-title" id="card-modal-title">${escapeHtml((window.prettyCamera||(s=>s))(h.camera))} · ${t}</h2>
          <div class="modal-badges">${speciesBadge}${sharedBadge}${featuredBadge}
            <span class="modal-meta-extra">
              ${(h.duration_s || 0).toFixed(1)}s
              <span class="meta-share-slot"></span>
            </span>
          </div>
        </div>
        <div class="modal-actions" id="modal-actions"></div>
      </div>
    `;
    // Meta-extra row gets two icon buttons:
    //   link  — copy URL (fast, single action, no sheet animation)
    //   share — universal share sheet (Messages / Mail / AirDrop / etc.)
    const shareSlot = body.querySelector(".meta-share-slot");
    if (shareSlot) {
      const pageUrl = `${location.origin}/clip/${h.event_id}`;
      shareSlot.appendChild(buildLinkButton({ pageUrl, label: "Copy link" }));
      shareSlot.appendChild(buildShareButton({ pageUrl, label: "Share" }));
    }

    // Attach the video stream. Always play from frame 0 in the modal —
    // applyPrerollSkip() jumps ~25s in to skip Frigate's pre-event
    // buffer, but for an opened/slid modal card the user expects to
    // see the entire clip from the beginning.
    videoEl = body.querySelector(".modal-video");
    videoEl.src = `/api/highlights/${encodeURIComponent(h.event_id)}/clip`;
    videoEl.currentTime = 0;

    // iOS: video starts WITHOUT the native control bar so a swipe
    // to the next clip doesn't flash an autoplay control overlay
    // over an already-playing video. Tap on the video calls up the
    // controls — iOS then handles its own auto-hide on idle. The
    // `ended` event strips controls again so a finished clip
    // doesn't pin the control bar visible (Replay button covers
    // restart). Non-iOS keeps the template `controls` attribute.
    if (document.documentElement.classList.contains("ios")) {
      videoEl.controls = false;
      videoEl.removeAttribute("controls");
      // Tap-to-reveal-controls. Bind on the WRAP in CAPTURE phase
      // — capture phase walks root → target, so the wrap (parent)
      // fires before the video-level pan-block guard runs. Whether
      // the guard later calls stopPropagation doesn't matter; our
      // tap-reveal already executed.
      const wrapEl = body.querySelector(".modal-video-wrap");
      let tapStart = null;
      if (wrapEl) {
        wrapEl.addEventListener("touchstart", (e) => {
          if (e.touches.length !== 1) { tapStart = null; return; }
          if (e.target.closest("button, .zoom-controls, .modal-nav")) {
            tapStart = null;
            return;
          }
          const t = e.touches[0];
          tapStart = { x: t.clientX, y: t.clientY, time: Date.now() };
        }, true /* capture */);
        wrapEl.addEventListener("touchend", (e) => {
          if (!tapStart) return;
          const start = tapStart;
          tapStart = null;
          if (e.changedTouches.length !== 1) return;
          if (Date.now() - start.time > 500) return;
          const t = e.changedTouches[0];
          const dx = t.clientX - start.x;
          const dy = t.clientY - start.y;
          if (dx * dx + dy * dy > 64) return;
          if (!videoEl.controls) {
            videoEl.controls = true;
            videoEl.setAttribute("controls", "");
          }
        }, true /* capture */);
      }
      videoEl.addEventListener("ended", () => {
        videoEl.controls = false;
        videoEl.removeAttribute("controls");
      });
    }

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
    const wrap = body.querySelector(".modal-video-wrap");
    panzoomInstance = bindPanzoom(videoEl, wrap);
    if (panzoomInstance) {
      wireZoomButtons(body, ".zoom-controls .zoom-in", ".zoom-controls .zoom-out",
                       ".zoom-controls .zoom-fit", panzoomInstance, wrap);
    }

    // Action row — Material Icons throughout for a flat, universal
    // affordance vocabulary (no platform-specific glyph forks).
    //   star          favorite
    //   pets+block    "not a fox"
    //   archive       archive / unarchive
    //   content_cut   remix (only when favorited)
    // Admin "Feature" sits as a separate text link above the row.
    const actionsBar = body.querySelector("#modal-actions");

    // Favorite — filled star when active, outline when not. Count
    // (when ≥2) renders inline as a small superscript-y span.
    const favLabel = h.my_favorited
      ? ICON("star") + (h.favorite_count > 1 ? `<span class="action-count">${h.favorite_count}</span>` : "")
      : ICON("star_border");
    actionsBar.appendChild(iconActionBtn(favLabel, "favorite", h.my_favorited,
      h.my_favorited ? "Remove favorite" : "Favorite",
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
      }));

    // Not-a-fox toggle. In the No Foxes view it becomes a single-tap
    // GLOBAL restore (with confirm); elsewhere it's a per-user vote.
    const inNoFoxesView = (document.querySelector(".tab.active")?.dataset.bucket) === "demoted";
    if (inNoFoxesView) {
      actionsBar.appendChild(iconActionBtn(ICON("undo"), "demote", false, "Restore", async () => {
        if (!confirm("Restore this clip to the main highlights view for everyone? It's currently flagged as 'No Foxes' by someone in the family — restoring will move it back into circulation for all users.")) return;
        const r = await fetch(`/api/actions/${encodeURIComponent(h.event_id)}/unflag_no_foxes`,
          { method: "POST", credentials: "same-origin" });
        if (!r.ok) { alert("Couldn't restore."); return; }
        const data = await r.json();
        Object.assign(h, data.highlight || {});
        window.closeCardModal();
      }));
    } else {
      actionsBar.appendChild(iconActionBtn(NOT_FOX_ICON_HTML, "demote", h.my_demoted,
        h.my_demoted ? "Restore (it IS a fox)" : "Not a fox",
        async () => {
          const wasDemoted = h.my_demoted;
          const updated = await postAction(h.event_id, wasDemoted ? "clear" : "demote");
          if (updated) {
            Object.assign(h, updated);
            renderViewer(h);
            const tab = document.querySelector(".tab.active");
            const currentBucket = tab ? tab.dataset.bucket : null;
            let shouldHide = false;
            // pending = "All". Hide only when CURRENT user demotes,
            // not when another family member already had — otherwise
            // a fresh favorite would vanish the card (see card.js).
            if (currentBucket === "pending" && h.my_demoted) shouldHide = true;
            if (currentBucket === "favorites" && !h.favorited) shouldHide = true;
            if (currentBucket === "mine" && !h.my_favorited) shouldHide = true;
            if (currentBucket === "shared" && (h.favorite_count || 0) < 2) shouldHide = true;
            if (currentBucket === "demoted" && !h.demoted) shouldHide = true;
            if (shouldHide) {
              const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
              if (card) {
                card.style.transition = "opacity 0.3s, transform 0.3s";
                card.style.opacity = "0";
                card.style.transform = "scale(0.95)";
                setTimeout(() => card.remove(), 300);
              }
            }
          }
        }));
    }

    if (h.my_favorited) {
      actionsBar.appendChild(iconActionBtn(ICON("movie_edit"), "remix", false, "Remix",
        () => renderRemixEditor(h)));
    }
    // Delete (admin-only, irreversible) — rendered as a small red
    // text link in the upper-right corner of the modal's text area
    // (set up by CSS .modal-meta-delete). Out of the main action row
    // because deleting is destructive and shouldn't be next to the
    // hearts and shares.
    if (window.IS_ADMIN) {
      const deleteLink = document.createElement("a");
      deleteLink.className = "modal-meta-delete";
      deleteLink.href = "javascript:void(0)";
      deleteLink.textContent = "Delete";
      deleteLink.title = "Permanently delete this clip (admin)";
      deleteLink.addEventListener("click", async (e) => {
        e.preventDefault();
        if (!confirm("Permanently delete this clip? Removes the video, thumbnail, all remixes, and all user actions. This cannot be undone.")) return;
        const r = await fetch(
          `/api/admin/highlights/${encodeURIComponent(h.event_id)}`,
          { method: "DELETE", credentials: "same-origin" }
        );
        if (!r.ok) { alert("Couldn't delete clip."); return; }
        const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
        if (card) {
          card.style.transition = "opacity 0.3s, transform 0.3s";
          card.style.opacity = "0";
          card.style.transform = "scale(0.95)";
          setTimeout(() => card.remove(), 300);
        }
        window.closeCardModal();
      });
      const metaArea = body.querySelector(".modal-meta");
      if (metaArea) metaArea.appendChild(deleteLink);
    }
    // Archive toggle (per-user) — explicit Material Symbols SVG so
    // the archive glyph matches the user's intended design (box +
    // arrow), not the flatter `archive` ligature in Material Icons.
    actionsBar.appendChild(iconActionBtn(
      h.my_archived ? UNARCHIVE_ICON_SVG : ARCHIVE_ICON_SVG,
      "archive", !!h.my_archived,
      h.my_archived ? "Unarchive" : "Archive",
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

    // Admin Feature link — right-justified text link above the
    // action row. Less prominent than a pill button (the action is
    // editorial/curatorial, not a peer to favorite/archive) but
    // still discoverable for admins.
    if (window.IS_ADMIN) {
      const featured = !!h.featured;
      const featLink = document.createElement("a");
      featLink.className = "modal-feature-link";
      featLink.href = "javascript:void(0)";
      featLink.textContent = featured ? "★ Featured" : "Feature";
      featLink.title = featured ? "Unfeature" : "Promote to landing page";
      featLink.addEventListener("click", (e) => {
        e.preventDefault();
        toggleFeature(h);
      });
      // Insert above the actions bar (inside the modal-stage).
      actionsBar.parentNode.insertBefore(featLink, actionsBar);
    }

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
            <button class="zoom-btn zoom-in"  type="button" title="Zoom in"><span class="material-icons">add</span></button>
            <button class="zoom-btn zoom-out" type="button" title="Zoom out"><span class="material-icons">remove</span></button>
            <button class="zoom-btn zoom-fit" type="button" title="Fit"><span class="material-icons">crop_free</span></button>
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
      wireZoomButtons(body, ".zoom-in", ".zoom-out", ".zoom-fit",
                       panzoomInstance, wrap);
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
        // Surgical local merge — only the remix list + count change
        // after a remix save. Avoiding a refetch keeps the user's
        // in-modal state authoritative (saving a remix used to wipe
        // an in-modal ⭐ Mine because the refresh fetch's view of
        // my_favorited could lag the just-issued favorite POST).
        h.remixes = Array.isArray(h.remixes) ? h.remixes.slice() : [];
        if (data && data.remix) h.remixes.unshift(data.remix);
        h.remix_count = (h.remix_count || 0) + 1;
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

    // Date+time of the parent highlight, shown in the remix meta line.
    const parentDate = (parentH && parentH.start_time)
      ? new Date(parentH.start_time * 1000).toLocaleString()
      : "";

    body.innerHTML = `
      <div class="modal-stage modal-stage-remix-play">
        <div class="modal-video-wrap">
          <video class="modal-video" controls autoplay muted playsinline></video>
        </div>
        <div class="modal-meta">
          <h2 class="modal-title">🎬 ${escapeHtml(title)}</h2>
          <div class="modal-badges">
            <span class="modal-badge fox">@${escapeHtml(username)}</span>
            <span class="modal-meta-extra">
              ${parentDate ? `${parentDate} · ` : ""}${dur}s
              <span class="meta-share-slot"></span>
            </span>
          </div>
          <button class="modal-back-pill" type="button" id="rp-back">← See original highlight</button>
        </div>
      </div>
    `;
    // Meta-extra row: link icon (copy URL) + share-sheet icon
    // (navigator.share). Same pattern as the regular highlight viewer
    // so the user has a single mental model. Replaces the legacy
    // download icon — share-sheet's "Save to Files" / right-click on
    // the page-level remix permalink covers download intent.
    const remixPageUrl = `${location.origin}/remix/${remix.remix_id}`;
    const shareSlot = body.querySelector(".meta-share-slot");
    if (shareSlot) {
      shareSlot.appendChild(buildLinkButton({ pageUrl: remixPageUrl, label: "Copy link" }));
      shareSlot.appendChild(buildShareButton({ pageUrl: remixPageUrl, label: "Share" }));
    }

    // Drop native controls — when we apply the saved zoom_scale via
    // panzoom (transform: scale on the video element), native HTML5
    // controls render at the transformed bottom edge and get clipped
    // by the wrap's overflow. Users requested trim+zoom playback as
    // intended over a scrubber. They can still tap to play/pause and
    // pinch/scroll to interactively zoom.
    videoEl = body.querySelector(".modal-video");
    videoEl.controls = false;
    videoEl.removeAttribute("controls");
    videoEl.src = `/api/highlights/${encodeURIComponent(parentH.event_id)}/clip`;
    const wrap = body.querySelector(".modal-video-wrap");

    // Seek + auto-pause within the trim window. Defensive against the
    // metadata-already-loaded race.
    const seekToStart = () => {
      const startS = Number(remix.start_offset_s) || 0;
      try { videoEl.currentTime = startS; } catch {}
    };
    if (videoEl.readyState >= 1) seekToStart();
    else {
      videoEl.addEventListener("loadedmetadata", seekToStart, { once: true });
      videoEl.addEventListener("loadeddata", seekToStart, { once: true });
    }
    videoEl.addEventListener("timeupdate", () => {
      const endS = Number(remix.end_offset_s) || 0;
      if (endS && videoEl.currentTime >= endS - 0.05) {
        videoEl.pause();
        videoEl.currentTime = Number(remix.start_offset_s) || 0;
      }
    });
    // Tap-to-play-pause replacement for the native controls.
    videoEl.addEventListener("click", (e) => {
      if (videoEl.paused) videoEl.play().catch(() => {});
      else videoEl.pause();
    });

    // Bind panzoom only long enough to apply the saved view, then
    // PAUSE it. Remix playback shows the creator's frozen frame —
    // viewers shouldn't be able to drag or pinch-zoom around. With
    // panzoom paused, its event listeners are removed, so taps on
    // the video bubble cleanly to the dialog swipe handler and the
    // entire sheet becomes a swipe-nav target.
    panzoomInstance = bindPanzoom(videoEl, wrap);
    const applySavedZoom = () => {
      if (!panzoomInstance) return;
      try {
        if (remix.zoom_scale && remix.zoom_scale > 1.01) {
          const r = wrap.getBoundingClientRect();
          const cx = (Number(remix.zoom_x) || 0.5) * r.width;
          const cy = (Number(remix.zoom_y) || 0.5) * r.height;
          panzoomInstance.zoomAbs(0, 0, remix.zoom_scale);
          panzoomInstance.moveTo(
            r.width / 2 - cx * remix.zoom_scale,
            r.height / 2 - cy * remix.zoom_scale
          );
        }
        // Freeze: pause unbinds panzoom's pointer listeners so
        // touches on the video pass through to dialog swipe nav.
        if (typeof panzoomInstance.pause === "function") {
          panzoomInstance.pause();
        }
      } catch (err) { /* ignore */ }
    };
    if (videoEl.readyState >= 1) applySavedZoom();
    else videoEl.addEventListener("loadedmetadata", applySavedZoom, { once: true });

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
  // Wire +/-/⛶ zoom buttons against a panzoom instance, with two
  // refinements over the original smoothZoom-on-click pattern:
  //
  // 1. Anchored zoom math: explicitly compute the post-zoom translate
  //    so the wrap-center pixel stays fixed across the scale step.
  //    smoothZoom(centerX, centerY, factor) was being defeated by
  //    panzoom's bounds clamp inside small wraps (same bug fix that
  //    was applied to live.js v60).
  // 2. Dual binding on click + pointerup with 400ms de-dupe so iOS
  //    taps fire even when the synthesized click is suppressed.
  function wireZoomButtons(scope, inSel, outSel, fitSel, inst, wrap) {
    const zin  = scope.querySelector(inSel);
    const zout = scope.querySelector(outSel);
    const zfit = scope.querySelector(fitSel);
    const zoomToScale = (targetScale) => {
      const r = wrap.getBoundingClientRect();
      const t = inst.getTransform();
      const s = t.scale || 1;
      const wrapCx = r.width / 2;
      const wrapCy = r.height / 2;
      const cxL = (wrapCx - t.x) / s;
      const cyL = (wrapCy - t.y) / s;
      const sNew = Math.max(1, Math.min(6, targetScale));
      const txNew = wrapCx - cxL * sNew;
      const tyNew = wrapCy - cyL * sNew;
      inst.zoomAbs(0, 0, sNew);
      inst.moveTo(txNew, tyNew);
    };
    const bind = (btn, action) => {
      if (!btn) return;
      let last = 0;
      const fire = (e) => {
        e.stopPropagation();
        const now = Date.now();
        if (now - last < 400) return;
        last = now;
        action();
      };
      btn.addEventListener("click", fire);
      btn.addEventListener("pointerup", (e) => {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        fire(e);
      });
    };
    bind(zin,  () => zoomToScale((inst.getTransform().scale || 1) * 1.5));
    bind(zout, () => zoomToScale((inst.getTransform().scale || 1) / 1.5));
    bind(zfit, () => { inst.zoomAbs(0, 0, 1); inst.moveTo(0, 0); });
  }

  function bindPanzoom(videoTarget, wrapEl) {
    if (typeof window.panzoom !== "function" || !videoTarget || !wrapEl) {
      console.warn("[modal] panzoom missing", { hasLib: typeof window.panzoom });
      return null;
    }
    try {
      videoTarget.style.transformOrigin = "0 0";
      const inst = window.panzoom(videoTarget, {
        maxZoom: 6, minZoom: 1, bounds: true,
        boundsPadding: 0.1, zoomDoubleClickSpeed: 1,
      });
      // Pin pan at scale 1: anvaka panzoom doesn't honor a hook for
      // touch (only mouse). Use capture-phase stopPropagation
      // listeners that fire BEFORE panzoom's bubble-phase touchstart
      // listener. Multi-touch (pinch) and zoomed states allow pan
      // through. In remix-playback mode the panzoom is paused right
      // after the saved view is applied — let touches bubble to the
      // dialog swipe handler so the full card is a swipe-nav target.
      const guard = (e) => {
        if (videoTarget.closest(".modal-stage-remix-play")) return;
        const s = inst ? (inst.getTransform().scale || 1) : 1;
        if (s > 1.01) return;
        if (e.touches && e.touches.length > 1) return;
        if (e.button !== undefined && e.button !== 0) return;
        e.stopPropagation();
      };
      videoTarget.addEventListener("mousedown", guard, true);
      videoTarget.addEventListener("touchstart", guard, true);
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

  // Icon-content variant of actionBtn — accepts arbitrary HTML for
  // the button label (Material Icon ligature, custom combo glyph,
  // count-suffix span, etc.) instead of plain text. Matching CSS
  // class .action-btn.action-iconic strips text padding and centers
  // the glyph at hit-area floor.
  function iconActionBtn(html, kind, active, ariaLabel, onClick) {
    const b = document.createElement("button");
    b.className = `action-btn action-${kind} action-iconic` + (active ? " active" : "");
    b.type = "button";
    b.setAttribute("aria-label", ariaLabel);
    b.title = ariaLabel;
    b.innerHTML = html;
    b.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
    return b;
  }

  async function postAction(eventId, action) {
    const r = await fetch(`/api/actions/${encodeURIComponent(eventId)}/${action}`,
      { method: "POST", credentials: "same-origin" });
    if (!r.ok) { console.error(`${action} failed`, r.status); return null; }
    const data = await r.json();
    // Mirror the action onto the gallery card behind the modal so
    // the heart / outline / archive state stays in sync after close.
    // Without this, favoriting in the modal looked correct in-modal
    // but the underlying card on /highlights still showed unfilled.
    if (data.highlight && window.makeCard) {
      const card = document.querySelector(
        `.highlight[data-event-id="${CSS.escape(eventId)}"]`
      );
      if (card && card.parentNode) {
        const fresh = window.makeCard(data.highlight);
        card.replaceWith(fresh);
      }
    }
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

  // Trigger a browser-side download of the parent clip's mp4. Used
  // by the meta-download icon in both viewer and remix-playback modes.
  // For remix mode, the source is still the parent clip (remixes are
  // virtual sub-windows); the suffix encodes the remix title so
  // multiple downloads off the same parent stay distinguishable.
  // Build a meaningful .mp4 filename for a highlight: cam-iso8601[-suffix].mp4
  function clipFilename(h, suffix) {
    if (!h || !h.event_id) return "fox.mp4";
    const stamp = h.start_time
      ? new Date(h.start_time * 1000).toISOString().replace(/[:.]/g, "-").slice(0, 19)
      : h.event_id;
    const cam = (window.prettyCamera ? window.prettyCamera(h.camera) : (h.camera || "fox"))
      .replace(/\s+/g, "-").toLowerCase();
    let name = `${cam}-${stamp}`;
    if (suffix) name += "-" + String(suffix).replace(/[^a-z0-9-]+/gi, "-").slice(0, 40);
    return name + ".mp4";
  }

  function triggerDownload(h, suffix) {
    const filename = clipFilename(h, suffix);
    const a = document.createElement("a");
    a.href = `/api/highlights/${encodeURIComponent(h.event_id)}/clip?download=1&filename=${encodeURIComponent(filename)}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // ---------------------------------------------------------------------
  // Share helpers
  // ---------------------------------------------------------------------
  // Material Icons — universal flat design. Loaded via the Google
  // Fonts <link> in every template <head>. We just emit the ligature
  // and the font renders the glyph at currentColor.
  const ICON = (name) => `<span class="material-icons" aria-hidden="true">${name}</span>`;

  // Link 2 (Material Symbols' explicit "Link 2" variant — the 45°
  // diagonal two-loop chain). The Material Icons font's `link`
  // ligature renders a slightly different geometry; this inline
  // SVG is the canonical Link 2 path the user requested.
  const LINK2_ICON_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" height="22" width="22" viewBox="0 -960 960 960" aria-hidden="true" focusable="false">
      <path fill="currentColor" d="M318-120q-82 0-140-58t-58-140q0-40 15-76t43-64l134-133 56 56-134 134q-17 17-25.5 38.5T200-318q0 49 34.5 83.5T318-200q23 0 45-8.5t39-25.5l133-134 57 57-134 133q-28 28-64 43t-76 15Zm79-220-57-57 223-223 57 57-223 223Zm251-28-56-57 134-133q17-17 25-38t8-44q0-50-34-85t-84-35q-23 0-44.5 8.5T558-726L425-592l-57-56 134-134q28-28 64-43t76-15q82 0 139.5 58T839-641q0 39-14.5 75T782-502L648-368Z"/>
    </svg>`;

  // Archive — the explicit Material Symbols glyph the user provided
  // (box with downward arrow + lid line). Replaces the Material
  // Icons font's `archive` ligature which renders a flatter version.
  const ARCHIVE_ICON_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" height="22" width="22" viewBox="0 -960 960 960" aria-hidden="true" focusable="false">
      <path fill="currentColor" d="m480-240 160-160-56-56-64 64v-168h-80v168l-64-64-56 56 160 160ZM200-640v440h560v-440H200Zm0 520q-33 0-56.5-23.5T120-200v-499q0-14 4.5-27t13.5-24l50-61q11-14 27.5-21.5T250-840h460q18 0 34.5 7.5T772-811l50 61q9 11 13.5 24t4.5 27v499q0 33-23.5 56.5T760-120H200Zm16-600h528l-34-40H250l-34 40Zm264 300Z"/>
    </svg>`;
  // Unarchive — same box, arrow flipped UP (out of box). Mirror the
  // archive path along its vertical center.
  const UNARCHIVE_ICON_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" height="22" width="22" viewBox="0 -960 960 960" aria-hidden="true" focusable="false">
      <path fill="currentColor" d="M480-560 320-400l56 56 64-64v168h80v-168l64 64 56-56-160-160ZM200-640v440h560v-440H200Zm0 520q-33 0-56.5-23.5T120-200v-499q0-14 4.5-27t13.5-24l50-61q11-14 27.5-21.5T250-840h460q18 0 34.5 7.5T772-811l50 61q9 11 13.5 24t4.5 27v499q0 33-23.5 56.5T760-120H200Zm16-600h528l-34-40H250l-34 40Zm264 300Z"/>
    </svg>`;

  // "Not a fox" custom combo: pets icon (paw) with a block icon
  // overlaid at the upper-left of the paw. The block uses Material
  // Symbols (variable font) at wght=700, GRAD=200 so its strokes
  // are bolder and its grade higher — needed because at wght=400
  // the block icon's strokes vanished into the paw's pads.
  const NOT_FOX_ICON_HTML = `
    <span class="not-fox-icon" aria-hidden="true">
      <span class="material-icons not-fox-base">pets</span>
      <span class="material-symbols-outlined not-fox-overlay">block</span>
    </span>`;

  // Build a "copy link" button — fast, deterministic. No sheet,
  // no fallback prompt. Shows a toast on success. Material Icon
  // "link" (chain).
  function buildLinkButton(opts) {
    // opts: { pageUrl, label }
    const b = document.createElement("button");
    b.className = "action-btn action-link action-icon-only";
    b.type = "button";
    b.setAttribute("aria-label", opts.label || "Copy link");
    b.title = opts.label || "Copy link";
    b.innerHTML = LINK2_ICON_SVG;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      copyLink(opts.pageUrl);
    });
    return b;
  }

  function copyLink(url) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(
        () => flashToast("Link copied"),
        () => flashToast("Copy failed")
      );
    } else {
      flashToast("Copy not supported on this browser");
    }
  }

  // Build a share button that does the right thing per-platform:
  //   iOS PWA / iOS Safari → navigator.share with a File of the clip
  //     (so the share-sheet "Save to Files" option works without
  //     leaving the PWA). URL-only fallback if file fetch fails.
  //   Other Web Share-capable browsers → navigator.share({url}).
  //   Desktop → clipboard copy with toast.
  function buildShareButton(opts) {
    // opts: { pageUrl, label }
    // Universal share-sheet button — Material Icon "ios_share"
    // (square + up-arrow) used flat on every platform. On non-Web-
    // Share browsers doShare falls through to clipboard.
    const b = document.createElement("button");
    b.className = "action-btn action-share action-icon-only";
    b.type = "button";
    b.setAttribute("aria-label", opts.label || "Share");
    b.title = opts.label || "Share";
    b.innerHTML = ICON("ios_share");
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      doShare(opts).catch(() => {});
    });
    return b;
  }

  async function doShare(opts) {
    const { pageUrl } = opts;
    // URL-only share. iOS share sheet exposes Copy / Messages / Mail
    // / AirDrop / etc. as sheet options. We previously fetched the
    // clip and shared as a File so the sheet offered "Save to Files"
    // — but the fetch is slow (full MP4 over the wire) and the user
    // preferred the snappier link-share experience. Save-to-Files
    // moves to the desktop Download path.
    if (navigator.share) {
      try {
        // Pass URL only (omit text). iOS's "Copy" share-sheet action
        // copies whichever of url/text is provided; with both, it
        // copies the text. We want the URL on clipboard.
        await navigator.share({
          url: pageUrl,
          title: "Our Foxes — clip",
        });
        return;
      } catch (err) {
        if (err && err.name === "AbortError") return;
        // Other errors: silent fall-through to clipboard.
      }
    }
    if (navigator.clipboard) {
      navigator.clipboard.writeText(pageUrl).then(
        () => flashToast("Link copied"),
        () => flashToast("Copy failed")
      );
      return;
    }
    flashToast("Sharing not supported on this browser");
  }

  // Download a server-rendered trimmed + (when zoomed) cropped MP4 of
  // a saved remix. First click pays the ffmpeg cost; later clicks hit
  // the curator's cache instantly.
  function triggerRemixDownload(remix, parentH) {
    if (!remix || !remix.remix_id) return;
    const stamp = parentH && parentH.start_time
      ? new Date(parentH.start_time * 1000).toISOString().replace(/[:.]/g, "-").slice(0, 19)
      : remix.remix_id;
    const cam = (window.prettyCamera ? window.prettyCamera(parentH?.camera) : (parentH?.camera || "fox"))
      .replace(/\s+/g, "-").toLowerCase();
    const titlePart = (remix.title || "remix").replace(/[^a-z0-9-]+/gi, "-").slice(0, 40);
    const filename = `${cam}-${stamp}-${titlePart}.mp4`;
    const a = document.createElement("a");
    a.href = `/api/remixes/${encodeURIComponent(remix.remix_id)}/download?filename=${encodeURIComponent(filename)}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
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
    // Use the HTML popover API to place the toast in its own top-
    // layer slot. <dialog>.showModal() also uses the top layer, but
    // a popover declared after the dialog stacks ABOVE it. Earlier
    // we tried appending the toast inside the dialog, which worked
    // but triggered a brief backdrop repaint (modal "blinks white")
    // when the toast was removed. The popover path keeps the toast
    // independent of the dialog's child list.
    document.body.appendChild(t);
    if (typeof t.showPopover === "function") {
      try {
        t.setAttribute("popover", "manual");
        t.showPopover();
      } catch (_) {
        // older browser quirks: ignore, toast still renders via z-index
      }
    }
    setTimeout(() => t.classList.remove("show"), 1700);
    setTimeout(() => {
      try { if (t.hidePopover) t.hidePopover(); } catch (_) {}
      t.remove();
    }, 2100);
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
