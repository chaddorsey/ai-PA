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
    // After the entrance transitions complete (~1.5s for the last layer),
    // strip transition smoothing from hero-layer so scroll-driven
    // parallax responds without the 600ms easing tail.
    setTimeout(() => document.body.classList.add("parallax-active"), 1600);
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

  // Initial cards above the fold; the rest reveal in BATCH_SIZE chunks
  // when the user taps "Show more".
  const INITIAL_BATCH = 6;
  const BATCH_SIZE = 6;

  async function renderFeatured() {
    const grid = document.getElementById("featured-grid");
    const moreBtn = document.getElementById("featured-more");
    if (!grid) return;
    let data;
    try {
      // Pull the full featured set in one request — the curator caps at
      // 200 and 200 small JSON rows is well under any practical payload
      // budget. Pagination is then handled client-side, which keeps the
      // "Show more" button instant and avoids hitting the backend on
      // every reveal.
      const r = await fetch("/api/featured?limit=200", { credentials: "same-origin" });
      data = await r.json();
    } catch (err) {
      console.warn("[landing] /api/featured failed", err);
      grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;opacity:0.6;">
        Couldn't load today's highlights — try again in a moment.</p>`;
      return;
    }
    // Server returns a unified `items` array of {type:"highlight"|"remix",
    // ...} sorted by featured_at DESC. Fall back to the legacy
    // `highlights`-only shape for older curator builds. Each item carries
    // its own permalink shape + media URLs (see buildCard).
    const items = (data && data.items) ||
                  ((data && data.highlights) || []).map((h) =>
                    Object.assign({ type: "highlight" }, h));
    if (!items.length) {
      // Empty state: friendly woodland-quiet message.
      grid.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:48px 12px;">
          <img src="/static/animals/Stump.svg" style="height:120px;opacity:0.85;" alt="">
          <p style="font-family:var(--font-display);font-size:18px;color:var(--color-ink-soft);margin:18px 0 0;">
            Quiet woods today. Check back tonight.
          </p>
        </div>`;
      if (moreBtn) moreBtn.hidden = true;
      return;
    }
    grid.innerHTML = "";
    let shown = 0;
    function appendBatch(n) {
      const next = items.slice(shown, shown + n);
      for (const h of next) grid.appendChild(buildCard(h));
      shown += next.length;
      if (moreBtn) moreBtn.hidden = shown >= items.length;
    }
    appendBatch(INITIAL_BATCH);
    if (moreBtn) {
      moreBtn.addEventListener("click", () => appendBatch(BATCH_SIZE));
    }
  }

  function buildCard(item) {
    // Normalize: a "remix" item carries its own remix_id/title plus a
    // nested `highlight` with the parent clip's metadata. Pull whatever
    // the card needs out of either source so the rendering branch below
    // doesn't have to care which type it's looking at.
    const isRemix = item.type === "remix";
    const parent  = isRemix ? (item.highlight || {}) : item;
    const hrefId  = isRemix ? item.remix_id : item.event_id;
    const href    = isRemix ? `/remix/${encodeURIComponent(hrefId)}`
                            : `/clip/${encodeURIComponent(hrefId)}`;
    // Thumbnail comes from the parent highlight either way (parent clip
    // thumb is already public-bypassed; remix-specific frame extraction
    // would be a follow-up).
    const thumbUrl = `/api/highlights/${encodeURIComponent(parent.event_id)}/thumbnail`;
    // Hover preview: full clip for highlights, trimmed remix MP4 for
    // remixes — so the user previews exactly what they'll see when they
    // tap. Both endpoints support range requests.
    const videoUrl = isRemix
      ? `/api/remixes/${encodeURIComponent(hrefId)}/clip`
      : `/api/highlights/${encodeURIComponent(parent.event_id)}/clip`;

    const card = document.createElement("a");
    card.className = "featured-card" + (isRemix ? " featured-remix" : "");
    card.href = href;
    card.setAttribute(
      "aria-label",
      item.featured_caption ||
      (isRemix ? `Remix${item.title ? ': ' + item.title : ''}`
               : `Highlight from ${prettyTime(parent.start_time)}`)
    );

    const thumb = document.createElement("img");
    thumb.className = "thumb";
    thumb.src = thumbUrl;
    thumb.alt = "";
    thumb.loading = "lazy";
    card.appendChild(thumb);

    let videoEl = null;
    function ensureVideo() {
      if (videoEl) return videoEl;
      videoEl = document.createElement("video");
      videoEl.muted = true;
      videoEl.loop = true;
      videoEl.playsInline = true;
      videoEl.preload = "metadata";
      videoEl.src = videoUrl;
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

    // Badges — species (from parent), shared count (highlight-only),
    // and a "remix" tag so the type is obvious at a glance.
    const badges = document.createElement("div");
    badges.className = "badges";
    if (isRemix) {
      const b = document.createElement("span");
      b.className = "badge remix";
      b.textContent = "✂ Remix";
      badges.appendChild(b);
    }
    if (parent.species && parent.species !== "person" && parent.species !== "vehicle") {
      const b = document.createElement("span");
      b.className = "badge fox";
      b.textContent = prettyLabel(parent.species);
      badges.appendChild(b);
    }
    if (!isRemix && (parent.favorite_count || 0) >= 2) {
      const b = document.createElement("span");
      b.className = "badge shared";
      b.textContent = `★ ${parent.favorite_count}`;
      badges.appendChild(b);
    }
    if (badges.children.length) card.appendChild(badges);

    // Caption: prefer admin-written, then remix's own title, then a
    // sensible default (time-of-day for highlights, "Remix" for remixes
    // without a title).
    const cap = document.createElement("div");
    cap.className = "caption";
    cap.textContent = item.featured_caption ||
                      (isRemix
                        ? (item.title || "Remix")
                        : prettyTime(parent.start_time));
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
