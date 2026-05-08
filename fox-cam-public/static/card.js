// Shared highlight-card rendering. Used by both highlights.js (gallery)
// and clip.js (single-clip permalink page). Exposes window.makeCard
// plus helpers; everything else is page-local.

(function () {
  // Captured at gallery page load so navigating around doesn't reset the
  // "NEW" badges underneath the cursor. Set by highlights.js after it
  // fetches /api/viewer/state. 0 = mark nothing as new.
  window.LAST_SEEN_AT_PAGELOAD = 0;

  // Map internal stream names to family-friendly display names. Used
  // everywhere a camera label is shown (card meta, modal title, live
  // tile h2). Keep stream IDs as-is in URLs so /api/highlights etc.
  // don't break.
  window.prettyCamera = function prettyCamera(streamId) {
    if (!streamId) return "";
    const m = String(streamId).match(/fox_den_(\d+)/);
    return m ? `Fox Cam ${m[1]}` : streamId;
  };

  // Populate the "who am I" indicator in every page header. Identity
  // comes from window.CURRENT_EMAIL / window.IS_ADMIN injected by the
  // server when rendering an authed page (see _identity_ctx in
  // app/main.py). Avoids a /api/whoami round-trip that's unreliable
  // because of Cloudflare Access bypass-path header stripping.
  // Email + sign-out moved into the profile-popover (Account Circle
  // button in the upper-right header); the inline who-am-i pill is
  // redundant and stays hidden. We still flip the body.is-admin
  // class so admin-only UI (Feature link, Delete) renders.
  if (window.CURRENT_EMAIL && window.IS_ADMIN) {
    document.body.classList.add("is-admin");
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  // How far into the clip default playback should start. Frigate's
  // current pre_capture is 30s for alerts; we want ~5s of context
  // lead-in before the detection moment, so skip 25s. Pre-roll
  // remains in the clip for scrubbing back ("re-examining"); the
  // family just doesn't have to wait through it on first play.
  // If the clip is shorter than this offset (older clips, or
  // detection events with short pre), we clamp to a small fraction
  // of the duration as a fallback.
  const SKIP_PREROLL_S = 25;
  function applyPrerollSkip(video) {
    const seek = () => {
      const dur = video.duration;
      if (!isFinite(dur) || dur <= 0) return;
      // Don't skip past 80% of the clip (avoid landing inside the
      // post-roll on very short clips from older Frigate configs).
      const target = Math.min(SKIP_PREROLL_S, dur * 0.8);
      if (target > 0.5) video.currentTime = target;
    };
    if (video.readyState >= 1 /* HAVE_METADATA */) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
  }
  // Expose so clip.js can use the same logic on the permalink page.
  window.applyPrerollSkip = applyPrerollSkip;

  // ---------------------------------------------------------------
  // Scroll-into-view autoplay (TikTok / Instagram pattern). Phones
  // only — desktop has hover-preview. The card most-visible in the
  // viewport swaps thumbnail → muted looping <video>; as it scrolls
  // out, the video tears down and the thumbnail returns. One card
  // plays at a time. Honors prefers-reduced-motion + saveData.
  // ---------------------------------------------------------------
  let scrollAutoplayObserver = null;
  let scrollAutoplayCurrent = null;

  function ensureScrollAutoplayObserver() {
    if (scrollAutoplayObserver !== null) return scrollAutoplayObserver;
    if (!window.IntersectionObserver) return null;
    if (!window.matchMedia || !window.matchMedia("(max-width: 720px)").matches) return null;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
    if (navigator.connection && navigator.connection.saveData) return null;

    // rootMargin "-40% 0 -40% 0" shrinks the observation root to the
    // center 20% band of the viewport. Cards only "intersect" the
    // root when their pixels are in this band — i.e., the card is
    // approximately centered on screen. This makes autoplay feel
    // intentional (your eye is on the card before it plays) instead
    // of pre-firing as it scrolls into view.
    scrollAutoplayObserver = new IntersectionObserver((entries) => {
      // Tear down any card that left the center band.
      for (const entry of entries) {
        if (!entry.isIntersecting) {
          const v = entry.target.querySelector("video.preview");
          if (v) { try { v.pause(); } catch (_) {} v.remove(); }
          const card = entry.target.closest(".highlight");
          if (card) card.classList.remove("is-active-preview");
          if (scrollAutoplayCurrent === entry.target) scrollAutoplayCurrent = null;
        }
      }
      // Pick the card with the highest intersection within the
      // center band as the winner.
      let bestEntry = null;
      let bestRatio = 0.4;
      for (const entry of entries) {
        if (entry.isIntersecting && entry.intersectionRatio > bestRatio) {
          bestRatio = entry.intersectionRatio;
          bestEntry = entry;
        }
      }
      if (bestEntry && scrollAutoplayCurrent !== bestEntry.target) {
        if (scrollAutoplayCurrent) {
          const oldV = scrollAutoplayCurrent.querySelector("video.preview");
          if (oldV) { try { oldV.pause(); } catch (_) {} oldV.remove(); }
          const oldCard = scrollAutoplayCurrent.closest(".highlight");
          if (oldCard) oldCard.classList.remove("is-active-preview");
        }
        scrollAutoplayCurrent = bestEntry.target;
        const wrap = bestEntry.target;
        const card = wrap.closest(".highlight");
        const eventId = wrap.dataset.previewEvent;
        if (!eventId || wrap.querySelector("video.preview")) return;
        const v = document.createElement("video");
        v.src = `/api/highlights/${eventId}/clip`;
        // poster= shows the thumbnail INSIDE the video element
        // until decoded frames are available. Native browser
        // behavior — eliminates the black-rectangle stall during
        // preload/buffer because the video element paints the
        // poster bitmap, not its default black background. The
        // poster vanishes the instant the first decoded frame
        // arrives (iOS handles the swap natively).
        v.poster = `/api/highlights/${eventId}/thumbnail`;
        v.muted = true;
        v.loop = true;
        v.playsInline = true;
        v.preload = "auto";
        v.className = "preview";
        wrap.appendChild(v);
        applyPrerollSkip(v);
        // The video element stays at opacity:0 (CSS) until the
        // `playing` event fires — that's the moment iOS reports
        // that decoded frames are ramping into the renderer.
        // Adding .is-ready transitions opacity 0 → 1 over 0.2s,
        // revealing the playing video. Until then the <img>
        // thumbnail underneath is what the user sees, so there's
        // no black-rectangle stall regardless of buffer time.
        // Halo flash held an extra 500ms so it lands with
        // unmistakable video motion, not the first decoded frame.
        v.addEventListener("playing", () => {
          if (scrollAutoplayCurrent !== wrap) return;
          v.classList.add("is-ready");
          if (!card) return;
          setTimeout(() => {
            if (!card || scrollAutoplayCurrent !== wrap) return;
            card.classList.remove("is-active-preview");
            void card.offsetWidth;
            card.classList.add("is-active-preview");
          }, 500);
        }, { once: true });
        v.play().catch(() => {});
      }
    }, {
      rootMargin: "-40% 0px -40% 0px",
      threshold: [0, 0.5, 0.85],
    });
    return scrollAutoplayObserver;
  }

  window.makeCard = function makeCard(h) {
    const el = document.createElement("div");
    el.className = "highlight";
    el.dataset.eventId = h.event_id;
    // Heart state shows the CURRENT viewer's vote, not the aggregate.
    // Aggregate count appears as a small badge next to it.
    if (h.my_favorited) el.classList.add("is-favorited");
    if (h.my_demoted) el.classList.add("is-demoted");
    if ((h.favorite_count || 0) >= 2) el.classList.add("is-shared");
    if (h.featured) el.classList.add("is-featured");
    if (h.my_archived) el.classList.add("is-archived");
    el.appendChild(archiveToggle(h));
    const isNew = h.start_time && h.start_time > window.LAST_SEEN_AT_PAGELOAD;
    if (isNew) el.classList.add("is-new");
    const thumbWrap = cardThumb(h);
    el.appendChild(thumbWrap);
    el.appendChild(cardMeta(h));
    el.appendChild(cardActions(h));

    // Hover-preview is gated on the card root so moving the cursor
    // onto sibling overlays (archive pill, featured pin) doesn't
    // count as leaving the preview area. iOS-skip is enforced inside
    // cardThumb already (no _showPreview on iOS).
    if (!document.documentElement.classList.contains("ios") && thumbWrap._showPreview) {
      el.addEventListener("mouseenter", thumbWrap._showPreview);
      el.addEventListener("mouseleave", thumbWrap._hidePreview);
    }

    // Squirrel delivers the ✨ NEW badge on cards that arrived since
    // the viewer's last seen. Fired once per card via IntersectionObserver
    // so the squirrel only runs when the card actually enters the
    // viewport, not for every card off-screen.
    if (isNew && window.deliverBadge) {
      _scheduleNewDelivery(el);
    }
    return el;
  };

  // Frigate-style preview: thumbnail by default, swap to a muted looping
  // <video> on hover (desktop). Click still triggers full inline play
  // with controls. On mobile (no hover), behavior is unchanged — tap
  // = full play.
  function cardThumb(h) {
    const wrap = document.createElement("div");
    wrap.className = "thumb-wrap";

    const img = document.createElement("img");
    img.src = `/api/highlights/${h.event_id}/thumbnail`;
    img.loading = "lazy";
    img.alt = "";
    wrap.appendChild(img);

    let preview = null;
    let pendingHide = null;

    function showPreview() {
      clearTimeout(pendingHide);
      if (preview) {
        preview.play().catch(() => {});
        // Re-reveal in case a prior hidePreview's transition out
        // dropped is-ready. Cheap class re-add.
        preview.classList.add("is-ready");
        return;
      }
      preview = document.createElement("video");
      preview.src = `/api/highlights/${h.event_id}/clip`;
      preview.muted = true;
      preview.loop = true;
      preview.playsInline = true;
      preview.preload = "metadata";
      preview.className = "preview";
      // CSS gates .preview at opacity:0 until .is-ready lands —
      // primarily for the phone scroll-autoplay path's
      // black-rectangle suppression, but desktop hover hits the
      // same selector. Add .is-ready when the first decoded frame
      // arrives so the fade-in matches the original 0.2s ease
      // reveal instead of the video staying invisible.
      preview.addEventListener("playing", () => {
        preview && preview.classList.add("is-ready");
      }, { once: true });
      wrap.appendChild(preview);
      applyPrerollSkip(preview);
      preview.play().catch(() => {});
    }

    function hidePreview() {
      pendingHide = setTimeout(() => {
        if (!preview) return;
        preview.pause();
        preview.remove();
        preview = null;
      }, 80);
    }

    // Skip hover-preview on iOS — mouseenter fires unpredictably from
    // taps and the autoplay download is wasted bandwidth on cellular.
    // Tap on a card opens the modal (highlights.js) or plays inline
    // (clip page) — both more useful than a hover preview that the
    // user has to discover.
    //
    // Hover is bound at the .highlight (card root) level by makeCard,
    // not on .thumb-wrap directly: the archive-toggle pill sits over
    // the thumb's top-right corner via position:absolute and would
    // otherwise trigger mouseleave on the wrap when the cursor moved
    // onto it (visibly snapping the preview back to the thumbnail).
    // Stash the show/hide handlers so makeCard can reach them.
    wrap._showPreview = showPreview;
    wrap._hidePreview = hidePreview;
    // playInline replaces the thumbnail with a <video controls>.
    // Skip it on /highlights — every card-tap opens the modal there,
    // and the brief inline-controls overlay before the modal mounts
    // is confusing. Clip permalink page (no #highlights element)
    // still uses inline play.
    //
    // CRITICAL: bail if a <video> already exists in the wrap. Clip /
    // remix permalinks have clip.js pre-install a video element with
    // remix trim + zoom set up; without this guard, every tap on the
    // iOS native controls (play button, scrubber, fullscreen, rewind-
    // 10) bubbles here and runs playInline, which DESTROYS the
    // pre-configured video and replaces it with a fresh one starting
    // at t=0 — looks like "tap restarts from mid clip" because the
    // user expected the remix start, got the parent-clip start.
    if (!document.getElementById("highlights")) {
      wrap.addEventListener("click", (e) => {
        if (wrap.querySelector("video")) return;
        playInline(wrap, h);
      });
    }
    // Phone-only scroll-into-view autoplay: the singleton observer
    // takes ownership of swapping the thumbnail in/out for a muted
    // looping preview as this card crosses the viewport center.
    // Stash event_id on the wrap so the observer doesn't need a
    // closure for each card.
    if (document.getElementById("highlights")) {
      const obs = ensureScrollAutoplayObserver();
      if (obs) {
        wrap.dataset.previewEvent = h.event_id;
        obs.observe(wrap);
      }
    }
    return wrap;
  }

  function cardMeta(h) {
    const div = document.createElement("div");
    div.className = "meta";
    const t = new Date(h.start_time * 1000).toLocaleString();
    // Species badge — only render if classifier ran. Different colors
    // for fox vs other wildlife vs none/person/vehicle so family can
    // scan the gallery and ignore the not-fox cards quickly.
    let speciesHTML = "";
    if (h.species) {
      const cls = "species-" + (
        h.species === "fox" ? "fox" :
        ["none","person","vehicle","error"].includes(h.species) ? "muted" :
        "other"
      );
      const conf = h.species_confidence || "";
      const explainBtn = h.classifier_raw
        ? `<button class="species-why" data-event-id="${h.event_id}" title="Why this classification?" aria-label="Why this classification?">?</button>`
        : "";
      speciesHTML = `<span class="species ${cls}" title="${conf} confidence">${h.species}</span>${explainBtn}`;
    }
    const newBadge = (h.start_time && h.start_time > window.LAST_SEEN_AT_PAGELOAD)
      ? `<span class="new-badge">NEW</span> ` : "";
    const remixCount = h.remix_count || 0;
    const remixHTML = remixCount > 0
      ? `<a class="remix-count-link" href="/clip/${h.event_id}#remixes" title="View remixes">` +
        `<span class="material-icons" aria-hidden="true">movie_edit</span>` +
        `<span class="remix-count-num">${remixCount}</span>` +
        `</a>`
      : "";
    const cam = window.prettyCamera ? window.prettyCamera(h.camera) : h.camera;
    div.innerHTML = `
      <div class="meta-row meta-row-top">
        <span class="meta-left">${newBadge}${speciesHTML}${remixHTML ? " " + remixHTML : ""}</span>
        <span class="meta-cam">${cam}</span>
      </div>
      <div class="meta-row meta-row-bottom">
        <a class="time" href="/clip/${h.event_id}">${t}</a>
        <span class="meta-sep"> – </span>
        <span class="meta-dur">${h.duration_s.toFixed(1)}s</span>
      </div>`;
    // Wire the "?" button to the popover. Done after innerHTML so the
    // node exists.
    const why = div.querySelector(".species-why");
    if (why) {
      why.addEventListener("click", (e) => {
        e.stopPropagation();
        showExplain(why, h);
      });
    }
    return div;
  }

  // Lightweight popover. Click ? on mobile or hover on desktop to see
  // the classifier's per-frame reasoning. Click anywhere else to dismiss.
  function showExplain(anchor, h) {
    document.querySelectorAll(".explain-popover").forEach((p) => p.remove());
    const pop = document.createElement("div");
    pop.className = "explain-popover";
    const lines = (h.classifier_raw || "").split(";").map(s => s.trim()).filter(Boolean);
    pop.innerHTML = `
      <div class="explain-header">
        <strong>${h.species}</strong>
        <span class="muted">${h.species_confidence || ""} confidence · ${h.classifier_model || ""}</span>
      </div>
      <ul>${lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>
    `;
    document.body.appendChild(pop);
    const rect = anchor.getBoundingClientRect();
    pop.style.top = `${window.scrollY + rect.bottom + 6}px`;
    pop.style.left = `${Math.min(window.innerWidth - 340, rect.left)}px`;
    setTimeout(() => {
      const onDocClick = (ev) => {
        if (!pop.contains(ev.target) && ev.target !== anchor) {
          pop.remove();
          document.removeEventListener("click", onDocClick);
        }
      };
      document.addEventListener("click", onDocClick);
    }, 0);
  }

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Material Icon ligature helper.
  function MI(name) {
    return `<span class="material-icons" aria-hidden="true">${name}</span>`;
  }

  // Link 2 inline SVG (Material Symbols' canonical 45° two-loop
  // chain). Used in place of the `link` ligature so the rendering
  // matches what the user explicitly requested.
  const LINK2_ICON_SVG = `
    <svg xmlns="http://www.w3.org/2000/svg" height="22" width="22" viewBox="0 -960 960 960" aria-hidden="true" focusable="false">
      <path fill="currentColor" d="M318-120q-82 0-140-58t-58-140q0-40 15-76t43-64l134-133 56 56-134 134q-17 17-25.5 38.5T200-318q0 49 34.5 83.5T318-200q23 0 45-8.5t39-25.5l133-134 57 57-134 133q-28 28-64 43t-76 15Zm79-220-57-57 223-223 57 57-223 223Zm251-28-56-57 134-133q17-17 25-38t8-44q0-50-34-85t-84-35q-23 0-44.5 8.5T558-726L425-592l-57-56 134-134q28-28 64-43t76-15q82 0 139.5 58T839-641q0 39-14.5 75T782-502L648-368Z"/>
    </svg>`;
  // "Not a fox" combo glyph: paw + block overlay. Block uses
  // Material Symbols (variable font) at wght=700, GRAD=200 so its
  // strokes stand out clean against the paw.
  const NOT_FOX_HTML = `
    <span class="not-fox-icon" aria-hidden="true">
      <span class="material-icons not-fox-base">pets</span>
      <span class="material-symbols-outlined not-fox-overlay">block</span>
    </span>`;

  function iconActionBtn(html, kind, active, label, onClick) {
    const b = document.createElement("button");
    b.className = `action-btn action-${kind} action-iconic` + (active ? " active" : "");
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.title = label;
    b.innerHTML = html;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      onClick();
    });
    return b;
  }

  function cardActions(h) {
    const bar = document.createElement("div");
    bar.className = "actions";

    // Favorite — Material Icon star (filled when active, outline
    // otherwise). Family count appears as a small inline badge.
    const favCount = h.favorite_count || 0;
    const starHtml = h.my_favorited ? MI("star") : MI("star_border");
    const countHtml = favCount > 1 ? `<span class="action-count">${favCount}</span>` : "";
    bar.appendChild(iconActionBtn(starHtml + countHtml, "favorite", h.my_favorited,
      h.my_favorited ? "Remove favorite" : "Favorite",
      () => {
        const wasFav = h.my_favorited;
        setAction(h.event_id, wasFav ? "clear" : "favorite");
        if (!wasFav && window.deliverBadge) {
          const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
          if (card) window.deliverBadge(card, "fox-3", "⭐ Mine", { badgeClass: "badge-mine" });
        }
      }));

    // Not-a-fox toggle (or global Restore in No Foxes view).
    const inNoFoxesView = (document.querySelector(".tab.active")?.dataset.bucket) === "demoted";
    if (inNoFoxesView) {
      bar.appendChild(iconActionBtn(MI("undo"), "demote", false, "Restore", async () => {
        if (!confirm("Restore this clip to the main highlights view for everyone? It's currently flagged as 'No Foxes' by someone in the family — restoring will move it back into circulation for all users.")) return;
        const r = await fetch(`/api/actions/${encodeURIComponent(h.event_id)}/unflag_no_foxes`,
          { method: "POST", credentials: "same-origin" });
        if (!r.ok) { alert("Couldn't restore."); return; }
        const data = await r.json();
        Object.assign(h, data.highlight || {});
        const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
        if (card) {
          card.style.transition = "opacity 0.3s, transform 0.3s";
          card.style.opacity = "0";
          card.style.transform = "scale(0.95)";
          setTimeout(() => card.remove(), 300);
        }
      }));
    } else {
      bar.appendChild(iconActionBtn(NOT_FOX_HTML, "demote", h.my_demoted,
        h.my_demoted ? "Restore (it IS a fox)" : "Not a fox",
        () => {
          const wasDemoted = h.my_demoted;
          setAction(h.event_id, wasDemoted ? "clear" : "demote");
          if (!wasDemoted && window.deliverBadge) {
            const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
            if (card) window.deliverBadge(card, "frog", "🚫 Not a fox", { badgeClass: "badge-nofox" });
          }
        }));
    }

    // Share — Material Icon link (chain) for the gallery card. Quick
    // copy-to-clipboard with toast (no sheet animation; cards are
    // for fast scanning).
    bar.appendChild(iconActionBtn(LINK2_ICON_SVG, "share", false, "Copy link",
      () => copyShareLink(h.event_id)));

    // Remix — Material Icon movie_edit (matches the bottom Remixes
    // tab). Only shown after the user has favorited.
    if (h.my_favorited) {
      bar.appendChild(iconActionBtn(MI("movie_edit"), "remix", false, "Remix", () => {
        if (window.openCardModalInRemixMode) {
          window.openCardModalInRemixMode(h.event_id);
        } else {
          location.href = `/highlights/${encodeURIComponent(h.event_id)}/remix`;
        }
      }));
    }

    // Admin Feature link — right-justified text link above the card
    // action row. Less prominent than a peer-pill button: the action
    // is editorial, not curatorial.
    if (window.IS_ADMIN) {
      const featured = !!h.featured;
      const featLink = document.createElement("a");
      featLink.className = "card-feature-link";
      featLink.href = "javascript:void(0)";
      featLink.textContent = featured ? "★ Featured" : "Feature";
      featLink.title = featured ? "Unfeature" : "Promote to landing page";
      featLink.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleFeature(h);
      });
      bar.parentElement || null;  // bar not yet attached
      // Insert as a sibling above the action row by stashing on the
      // bar; cardEl appends bar as the last child, so we can set a
      // marker and let CSS float it. Simpler: prepend to bar with
      // class so it self-aligns via CSS.
      bar.appendChild(featLink);
    }
    return bar;
  }

  // Promote/unpromote with optional admin caption. On promote, prompt
  // for an optional one-line caption (max 140 chars). On unpromote,
  // confirm before clearing. Posts to /api/admin/* — server re-checks
  // ADMIN_EMAILS, so the client-side IS_ADMIN flag is purely cosmetic.
  async function toggleFeature(h) {
    const featured = !!h.featured;
    let url, body;
    if (featured) {
      if (!confirm("Remove this clip from the public landing page?")) return;
      url = `/api/admin/highlights/${encodeURIComponent(h.event_id)}/unfeature`;
      body = "{}";
    } else {
      const caption = (prompt("Optional caption (≤140 chars):", h.featured_caption || "") || "").trim();
      if (caption.length > 140) {
        alert("Caption must be 140 characters or fewer.");
        return;
      }
      url = `/api/admin/highlights/${encodeURIComponent(h.event_id)}/feature`;
      body = JSON.stringify({ caption: caption || null });
    }
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        credentials: "same-origin",
      });
      if (r.status === 403) { alert("Admin only."); return; }
      if (!r.ok) { alert("Couldn't update featured status."); return; }
      const data = await r.json();
      // Update the in-memory highlight + re-render the card so the
      // toggle flips and (if newly promoted) we can fly the Deer in
      // with the badge.
      const el = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
      Object.assign(h, data.highlight || {});
      if (el && el.parentNode) {
        const rebuilt = window.makeCard(h);
        el.parentNode.replaceChild(rebuilt, el);
        if (!featured) {
          // Just-promoted: fire the parade across the top + the Deer
          // delivers the badge onto the card. Two layered moments —
          // small (per-card) + big (page-wide) — for a real "we made
          // a public choice" feel.
          if (window.fireParade) window.fireParade();
          if (window.deliverBadge) {
            setTimeout(() => window.deliverBadge(rebuilt, "deer", "★ Featured", { badgeClass: "badge-featured" }), 400);
          }
        }
      }
    } catch (err) {
      console.error("[card] toggleFeature failed", err);
      alert("Network error updating featured status.");
    }
  }

  function actionBtn(label, kind, active, onClick) {
    const b = document.createElement("button");
    b.className = `action-btn action-${kind}` + (active ? " active" : "");
    b.title = ({
      favorite: active ? "Remove from favorites" : "Add to favorites",
      demote: active ? "Restore (it IS a fox)" : "Mark as not a fox",
      share: "Copy share link",
    })[kind];
    b.textContent = label;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      onClick();
    });
    return b;
  }

  async function setAction(eventId, action) {
    // /api/actions/* is gated by the authed Access app exclusively so
    // the auth header reaches origin (the older /api/highlights/{id}/{action}
    // path also matched the public Bypass app and lost the header).
    const r = await fetch(`/api/actions/${encodeURIComponent(eventId)}/${action}`,
      { method: "POST", credentials: "same-origin" });
    if (!r.ok) {
      console.error(`${action} failed`, r.status);
      return;
    }
    const data = await r.json();
    const h = data.highlight;
    const card = document.querySelector(`.highlight[data-event-id="${eventId}"]`);
    if (!card) return;

    // Decide whether the card should still be visible based on the page +
    // active tab. Pages other than /highlights just re-render in place.
    const tab = document.querySelector(".tab.active");
    const currentBucket = tab ? tab.dataset.bucket : null;
    let shouldHide = false;
    // pending = "All" bucket. Hide a card here only when the CURRENT
    // user demotes — using h.demoted (server aggregate) caused a
    // newly-favorited clip to disappear from All if any OTHER family
    // member had previously demoted it. The user's own action should
    // be the only thing that hides their view.
    if (currentBucket === "pending" && h.my_demoted) shouldHide = true;
    if (currentBucket === "favorites" && !h.favorited) shouldHide = true;
    if (currentBucket === "mine" && !h.my_favorited) shouldHide = true;
    if (currentBucket === "shared" && (h.favorite_count || 0) < 2) shouldHide = true;
    // No Foxes is a SHARED bucket (anyone-flagged → all see it). The
    // card disappears only when the global demoted flag clears (which
    // happens after the unflag-no-foxes endpoint wipes all votes).
    if (currentBucket === "demoted" && !h.demoted) shouldHide = true;

    if (shouldHide) {
      card.style.transition = "opacity 0.3s";
      card.style.opacity = "0";
      setTimeout(() => card.remove(), 300);
    } else {
      const fresh = window.makeCard(h);
      card.replaceWith(fresh);
    }
  }

  async function copyShareLink(eventId) {
    const url = `${location.origin}/clip/${eventId}`;
    try {
      await navigator.clipboard.writeText(url);
      flashToast(`Link copied: ${url}`);
    } catch {
      prompt("Copy this URL:", url);
    }
  }

  function flashToast(msg) {
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.classList.add("show"), 10);
    setTimeout(() => {
      t.classList.remove("show");
      setTimeout(() => t.remove(), 300);
    }, 2200);
  }

  function playInline(wrap, h) {
    // wrap is the .thumb-wrap div now. Replace its contents with a
    // <video controls> for full inline playback.
    wrap.innerHTML = "";
    const v = document.createElement("video");
    v.src = `/api/highlights/${h.event_id}/clip`;
    v.controls = true;
    v.autoplay = true;
    v.playsInline = true;
    wrap.appendChild(v);
    applyPrerollSkip(v);
  }

  // Archive toggle — top-right corner of every card. Uses the
  // Material Symbols archive path (box + down-arrow, shared with
  // the modal action row). Built via createElementNS so the SVG
  // ends up in the SVG namespace; setting innerHTML on a button
  // works in spec but on some browsers (and through some HTML
  // sanitisation paths) the inner <svg>/<path> end up as
  // HTMLUnknownElement and don't render. The explicit-namespace
  // path is bulletproof.
  const ARCHIVE_PATH_DOWN = "m480-240 160-160-56-56-64 64v-168h-80v168l-64-64-56 56 160 160ZM200-640v440h560v-440H200Zm0 520q-33 0-56.5-23.5T120-200v-499q0-14 4.5-27t13.5-24l50-61q11-14 27.5-21.5T250-840h460q18 0 34.5 7.5T772-811l50 61q9 11 13.5 24t4.5 27v499q0 33-23.5 56.5T760-120H200Zm16-600h528l-34-40H250l-34 40Zm264 300Z";
  const ARCHIVE_PATH_UP   = "M480-560 320-400l56 56 64-64v168h80v-168l64 64 56-56-160-160ZM200-640v440h560v-440H200Zm0 520q-33 0-56.5-23.5T120-200v-499q0-14 4.5-27t13.5-24l50-61q11-14 27.5-21.5T250-840h460q18 0 34.5 7.5T772-811l50 61q9 11 13.5 24t4.5 27v499q0 33-23.5 56.5T760-120H200Zm16-600h528l-34-40H250l-34 40Zm264 300Z";
  function buildArchiveSvg(pathD) {
    const SVGNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", "0 -960 960 960");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    const p = document.createElementNS(SVGNS, "path");
    p.setAttribute("d", pathD);
    p.setAttribute("fill", "currentColor");
    svg.appendChild(p);
    return svg;
  }
  function archiveToggle(h) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "archive-toggle" + (h.my_archived ? " is-archived" : "");
    btn.title = h.my_archived ? "Unarchive (move back to Active)" : "Archive (hide from Active)";
    btn.setAttribute("aria-label", btn.title);
    btn.appendChild(buildArchiveSvg(h.my_archived ? ARCHIVE_PATH_UP : ARCHIVE_PATH_DOWN));
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      toggleArchive(h);
    });
    return btn;
  }
  async function toggleArchive(h) {
    const wasArchived = !!h.my_archived;
    const action = wasArchived ? "unarchive" : "archive";
    const r = await fetch(`/api/actions/${encodeURIComponent(h.event_id)}/${action}`,
      { method: "POST", credentials: "same-origin" });
    if (!r.ok) { console.error("archive toggle failed", r.status); return; }
    const data = await r.json();
    Object.assign(h, data.highlight || {});
    const card = document.querySelector(`.highlight[data-event-id="${CSS.escape(h.event_id)}"]`);
    if (!card) return;
    const status = document.getElementById("filter-status")?.value || "active";
    // Hide if the new state moves the card out of the current Status
    // filter (active → archived if archiving, archived → active if
    // unarchiving). 'any' keeps everything visible.
    const movedOut = (status === "active" && h.my_archived) ||
                     (status === "archived" && !h.my_archived);
    if (movedOut) {
      card.style.transition = "opacity 0.3s, transform 0.3s";
      card.style.opacity = "0";
      card.style.transform = "scale(0.95)";
      setTimeout(() => card.remove(), 300);
    } else {
      const fresh = window.makeCard(h);
      card.replaceWith(fresh);
    }
  }
  window.toggleArchive = toggleArchive;

  // Stagger NEW-badge deliveries so a freshly-loaded gallery doesn't
  // launch eight squirrels at once. Each card's animation is queued and
  // released ~600ms after the previous one. Only fires once per card.
  let _newQueue = Promise.resolve();
  function _scheduleNewDelivery(cardEl) {
    if (cardEl.dataset.newDelivered) return;
    cardEl.dataset.newDelivered = "1";
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        io.disconnect();
        _newQueue = _newQueue.then(() => new Promise((resolve) => {
          window.deliverBadge(cardEl, "squirrel", "✨ NEW", { badgeClass: "badge-new" });
          setTimeout(resolve, 600);
        }));
      }
    }, { threshold: 0.3 });
    io.observe(cardEl);
  }

  // Also expose infoCard for empty-state messages on the gallery page.
  window.infoCard = function infoCard(msg) {
    const el = document.createElement("div");
    el.className = "highlight info-card";
    el.innerHTML = `<div class="meta">${msg}</div>`;
    return el;
  };

  // ---------------------------------------------------------------
  // Double-tap-to-favorite (iOS only).
  //
  // Single-tap opens the modal (existing behavior, owned by modal.js's
  // document-level click delegation). Double-tap should fire favorite
  // INSTEAD of opening the modal — so we intercept clicks at the
  // capture phase on /highlights, defer the modal-open by ~280ms to
  // allow a second tap to arrive, and:
  //   - second tap arrives within window → cancel modal timer, fire
  //     favorite + heart-pulse animation.
  //   - timer expires with no second tap → fire modal-open.
  //   - card was already favorited → second tap re-pulses the heart
  //     (visual ack) but still cancels the modal so the gesture has
  //     consistent meaning. Use the visible ⭐ button to unfavorite.
  //
  // The 280ms window is the tradeoff: long enough to catch most
  // double-taps, short enough that single-tap latency stays
  // perceptibly snappy. CSS `touch-action: manipulation` on
  // .highlight removes the browser's own 300ms double-tap-zoom
  // detection delay.
  // ---------------------------------------------------------------
  if (document.documentElement.classList.contains("ios")) {
    const TAP_WINDOW = 280;
    let lastTap = { time: 0, eventId: null };
    let pendingOpenTimer = null;

    document.addEventListener("click", (e) => {
      if (!document.getElementById("highlights")) return;
      const card = e.target.closest(".highlight[data-event-id]");
      if (!card) return;
      // Action buttons + archive toggle handle their own clicks.
      if (e.target.closest("button, .action-btn, .archive-toggle, .species-why, a")) {
        return;
      }
      const eventId = card.dataset.eventId;
      const now = Date.now();

      // Always intercept the click — modal.js's bubble-phase
      // listener at document level would otherwise open the modal
      // immediately on every tap.
      e.preventDefault();
      e.stopImmediatePropagation();

      if (lastTap.eventId === eventId && (now - lastTap.time) < TAP_WINDOW) {
        // Double-tap detected.
        if (pendingOpenTimer) { clearTimeout(pendingOpenTimer); pendingOpenTimer = null; }
        lastTap = { time: 0, eventId: null };
        const alreadyFav = card.classList.contains("is-favorited");
        if (alreadyFav) {
          // Already favorited: re-pulse the heart for visual ack,
          // don't unfavorite (Instagram pattern is one-way).
          if (window.deliverBadge) {
            window.deliverBadge(card, "fox-3", "⭐ Mine",
              { badgeClass: "badge-mine" });
          }
        } else {
          setAction(eventId, "favorite");
          if (window.deliverBadge) {
            window.deliverBadge(card, "fox-3", "⭐ Mine",
              { badgeClass: "badge-mine" });
          }
        }
        return;
      }

      // Single tap — defer the modal-open so a second tap can
      // arrive and cancel it.
      lastTap = { time: now, eventId };
      pendingOpenTimer = setTimeout(() => {
        pendingOpenTimer = null;
        lastTap = { time: 0, eventId: null };
        if (window.openCardModal) window.openCardModal(eventId);
      }, TAP_WINDOW);
    }, true);  // capture phase — fires before modal.js's bubble listener
  }
})();
