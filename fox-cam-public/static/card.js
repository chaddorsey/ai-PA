// Shared highlight-card rendering. Used by both highlights.js (gallery)
// and clip.js (single-clip permalink page). Exposes window.makeCard
// plus helpers; everything else is page-local.

(function () {
  // Captured at gallery page load so navigating around doesn't reset the
  // "NEW" badges underneath the cursor. Set by highlights.js after it
  // fetches /api/viewer/state. 0 = mark nothing as new.
  window.LAST_SEEN_AT_PAGELOAD = 0;

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

  window.makeCard = function makeCard(h) {
    const el = document.createElement("div");
    el.className = "highlight";
    el.dataset.eventId = h.event_id;
    // Heart state shows the CURRENT viewer's vote, not the aggregate.
    // Aggregate count appears as a small badge next to it.
    if (h.my_favorited) el.classList.add("is-favorited");
    if (h.my_demoted) el.classList.add("is-demoted");
    if ((h.favorite_count || 0) >= 2) el.classList.add("is-shared");
    if (h.start_time && h.start_time > window.LAST_SEEN_AT_PAGELOAD) {
      el.classList.add("is-new");
    }
    el.appendChild(cardThumb(h));
    el.appendChild(cardMeta(h));
    el.appendChild(cardActions(h));
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
      if (preview) { preview.play().catch(() => {}); return; }
      preview = document.createElement("video");
      preview.src = `/api/highlights/${h.event_id}/clip`;
      preview.muted = true;
      preview.loop = true;
      preview.playsInline = true;
      preview.preload = "metadata";
      preview.className = "preview";
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

    wrap.addEventListener("mouseenter", showPreview);
    wrap.addEventListener("mouseleave", hidePreview);
    wrap.addEventListener("click", () => playInline(wrap, h));
    return wrap;
  }

  function cardMeta(h) {
    const div = document.createElement("div");
    div.className = "meta";
    const t = new Date(h.start_time * 1000).toLocaleString();
    const fox = (h.fox_likelihood * 100).toFixed(0);
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
      speciesHTML = `<span class="species ${cls}" title="${conf} confidence">${h.species}</span>${explainBtn} · `;
    }
    const newBadge = (h.start_time && h.start_time > window.LAST_SEEN_AT_PAGELOAD)
      ? `<span class="new-badge">NEW</span> ` : "";
    div.innerHTML = `
      <a class="time" href="/clip/${h.event_id}">${t}</a>
      <div>${newBadge}${speciesHTML}${h.camera} · ${h.label} · ${h.duration_s.toFixed(1)}s
        · <span class="score">fox ${fox}%</span></div>`;
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

  function cardActions(h) {
    const bar = document.createElement("div");
    bar.className = "actions";
    // Heart shows YOUR state; small "★ N" suffix when family has favorited too.
    const favCount = h.favorite_count || 0;
    const favLabel = favCount > 1 ? `⭐ ${favCount}` : "⭐";
    bar.appendChild(actionBtn(favLabel, "favorite", h.my_favorited, () =>
      setAction(h.event_id, h.my_favorited ? "clear" : "favorite")
    ));
    bar.appendChild(actionBtn("🚫", "demote", h.my_demoted, () =>
      setAction(h.event_id, h.my_demoted ? "clear" : "demote")
    ));
    bar.appendChild(actionBtn("🔗", "share", false, () => copyShareLink(h.event_id)));
    return bar;
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
    const r = await fetch(`/api/highlights/${eventId}/${action}`, { method: "POST" });
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
    if (currentBucket === "pending" && h.demoted) shouldHide = true;
    if (currentBucket === "favorites" && !h.favorited) shouldHide = true;
    if (currentBucket === "mine" && !h.my_favorited) shouldHide = true;
    if (currentBucket === "shared" && (h.favorite_count || 0) < 2) shouldHide = true;
    if (currentBucket === "demoted" && !h.my_demoted) shouldHide = true;

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

  // Also expose infoCard for empty-state messages on the gallery page.
  window.infoCard = function infoCard(msg) {
    const el = document.createElement("div");
    el.className = "highlight info-card";
    el.innerHTML = `<div class="meta">${msg}</div>`;
    return el;
  };
})();
