/* landing.js — Public landing page driver
   ----------------------------------------------------------------------------
   Responsibilities:
     1. Trigger the staggered page-load entrance (adds .ready to <body>)
     2. Drive the parallax layers on scroll using transform: translateY
     3. Fetch /api/featured and render the 3×2 highlights grid
     4. Hover-autoplay clip previews on each featured card

   No build step, no React. Vanilla. GSAP loaded via CDN if available; otherwise
   we fall back to a tiny rAF-based parallax loop. The fallback is fine for our
   scale (one page, six cards, three layers).
*/
(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------------------------
  // 1. Page-load entrance
  // ---------------------------------------------------------------------------
  // Wait one frame after DOMContentLoaded so the browser has applied initial
  // styles before we toggle the .ready class — otherwise the first transition
  // sometimes runs in zero frames (pop-in feels broken).

  function startEntrance() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.body.classList.add("ready");
      });
    });
  }

  // ---------------------------------------------------------------------------
  // 2. Parallax — translateY scaled by data-speed on each .hero-layer
  // ---------------------------------------------------------------------------
  // Speed semantics: 0 = static (no movement), 1 = full scroll speed.
  // Layers further from the camera have lower speeds (0.15 sky → 0.85 fore).

  function setupParallax() {
    if (reduceMotion) return;

    const layers = Array.from(document.querySelectorAll(".hero-layer"));
    if (!layers.length) return;

    let lastY = -1;
    let ticking = false;

    function update() {
      const y = window.scrollY;
      // Only update if scroll actually moved (avoids jitter from rAF cycles
      // triggered by other things).
      if (y === lastY) { ticking = false; return; }
      lastY = y;
      for (const el of layers) {
        const speed = parseFloat(el.dataset.speed) || 0;
        // Negative because we want layers to move UP as we scroll DOWN.
        const ty = -y * speed;
        el.style.transform = `translateY(${ty.toFixed(1)}px)`;
      }
      ticking = false;
    }

    function onScroll() {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    update();
  }

  // ---------------------------------------------------------------------------
  // 3. Featured grid render
  // ---------------------------------------------------------------------------

  async function renderFeatured() {
    const grid = document.getElementById("featured-grid");
    if (!grid) return;
    let data;
    try {
      const r = await fetch("/api/featured?limit=6", { credentials: "same-origin" });
      data = await r.json();
    } catch (err) {
      console.warn("[landing] /api/featured failed", err);
      grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;opacity:0.6;">
        Couldn't load today's highlights — try again in a moment.</p>`;
      return;
    }
    const items = (data && data.highlights) || [];
    if (!items.length) {
      // Empty state: friendly woodland-quiet message.
      grid.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:48px 12px;">
          <img src="/static/animals/Stump.svg" style="height:120px;opacity:0.85;" alt="">
          <p style="font-family:var(--font-display);font-size:18px;color:var(--color-ink-soft);margin:18px 0 0;">
            Quiet woods today. Check back tonight.
          </p>
        </div>`;
      return;
    }
    grid.innerHTML = "";
    for (const h of items) {
      grid.appendChild(buildCard(h));
    }
  }

  function buildCard(h) {
    const card = document.createElement("a");
    card.className = "featured-card";
    card.href = `/clip/${encodeURIComponent(h.event_id)}`;
    card.setAttribute("aria-label", h.featured_caption || `Highlight from ${prettyTime(h.start_time)}`);

    // Thumbnail (always loaded; video lazy-loaded on hover for bandwidth).
    const thumb = document.createElement("img");
    thumb.className = "thumb";
    thumb.src = `/api/highlights/${encodeURIComponent(h.event_id)}/thumbnail`;
    thumb.alt = "";
    thumb.loading = "lazy";
    card.appendChild(thumb);

    // Hover-autoplay video (created on first hover to avoid loading 6 clips
    // unnecessarily on page load; mobile gets only the thumbnail).
    let videoEl = null;
    function ensureVideo() {
      if (videoEl) return videoEl;
      videoEl = document.createElement("video");
      videoEl.muted = true;
      videoEl.loop = true;
      videoEl.playsInline = true;
      videoEl.preload = "metadata";
      videoEl.src = `/api/highlights/${encodeURIComponent(h.event_id)}/clip`;
      card.appendChild(videoEl);
      return videoEl;
    }

    if (!reduceMotion && !isLikelyTouchDevice()) {
      card.addEventListener("mouseenter", () => {
        const v = ensureVideo();
        v.currentTime = 0;
        v.play().catch(() => { /* autoplay block — fine, hover-only */ });
      });
      card.addEventListener("mouseleave", () => {
        if (videoEl) videoEl.pause();
      });
    }

    // Badges — species + shared (if multi-favorited)
    const badges = document.createElement("div");
    badges.className = "badges";
    if (h.species && h.species !== "person" && h.species !== "vehicle") {
      const b = document.createElement("span");
      b.className = "badge fox";
      b.textContent = prettyLabel(h.species);
      badges.appendChild(b);
    }
    if ((h.favorite_count || 0) >= 2) {
      const b = document.createElement("span");
      b.className = "badge shared";
      b.textContent = `★ ${h.favorite_count}`;
      badges.appendChild(b);
    }
    if (badges.children.length) card.appendChild(badges);

    // Caption (admin-written) or default to time of day
    const cap = document.createElement("div");
    cap.className = "caption";
    cap.textContent = h.featured_caption || prettyTime(h.start_time);
    card.appendChild(cap);

    return card;
  }

  function prettyLabel(species) {
    const s = String(species || "").toLowerCase();
    if (s === "fox") return "🦊 Fox";
    if (s === "raccoon") return "🦝 Raccoon";
    if (s === "deer") return "🦌 Deer";
    if (s === "rabbit") return "🐇 Rabbit";
    if (s === "squirrel") return "🐿️ Squirrel";
    if (s === "bear") return "🐻 Bear";
    if (s === "domestic dog" || s === "dog") return "🐕 Dog";
    if (s === "domestic cat" || s === "cat") return "🐈 Cat";
    return s;
  }

  function prettyTime(epochSeconds) {
    if (!epochSeconds) return "";
    const d = new Date(epochSeconds * 1000);
    const opts = { weekday: "long", hour: "numeric", minute: "2-digit" };
    return d.toLocaleString(undefined, opts);
  }

  function isLikelyTouchDevice() {
    return ("ontouchstart" in window) || navigator.maxTouchPoints > 0;
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  function init() {
    startEntrance();
    setupParallax();
    renderFeatured();
  }
})();
