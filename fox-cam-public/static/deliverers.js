/* deliverers.js — animal-themed badge delivery animations
   ----------------------------------------------------------------------------
   When something noteworthy happens to a card (newly favorited, newly
   featured, etc.), an animal SVG flies in, drops a badge onto the card,
   and exits stage-bottom. This file owns the choreography.

   Public API:
     window.deliverBadge(cardEl, deliverer, badgeText, options)

   Deliverer presets define entry/exit curves + which SVG file to mount.
   Reduce-motion: replaced with a 200ms fade-in of the badge in place.
*/
(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const DELIVERERS = {
    squirrel:  { svg: "/static/animals/Squirrel.svg",  speed: 1.20, easing: "cubic-bezier(.4,0,.2,1)",   wiggle: true  },
    "fox-3":   { svg: "/static/animals/Fox-3.svg",     speed: 1.00, easing: "cubic-bezier(.34,1.4,.64,1)", wiggle: false },
    bear:      { svg: "/static/animals/Bear.svg",      speed: 0.55, easing: "cubic-bezier(.5,0,.25,1)",   wiggle: false },
    "raccoon-2": { svg: "/static/animals/Raccoon-2.svg", speed: 0.85, easing: "cubic-bezier(.4,0,.4,1)",   peek: true  },
    frog:      { svg: "/static/animals/Frog.svg",      speed: 0.70, easing: "steps(3,end)",               hop: true   },
    deer:      { svg: "/static/animals/Deer.svg",      speed: 0.75, easing: "cubic-bezier(.34,1.2,.64,1)", glide: true },
    rabbit:    { svg: "/static/animals/Rabbit.svg",    speed: 1.10, easing: "cubic-bezier(.5,0,.25,1)",   bounce: true },
  };

  /**
   * Drop a badge on a card via the named deliverer animal.
   *
   * @param {HTMLElement} cardEl       The .highlight DOM node receiving the badge.
   * @param {string}      delivererKey One of the keys in DELIVERERS.
   * @param {string}      badgeText    Text to display on the badge.
   * @param {object}      [opts]       { badgeClass: string, persist: bool }
   */
  window.deliverBadge = function deliverBadge(cardEl, delivererKey, badgeText, opts) {
    if (!cardEl || !cardEl.parentNode) return;
    opts = opts || {};
    const cfg = DELIVERERS[delivererKey] || DELIVERERS["fox-3"];

    // The badge that will be dropped. We mount it inside the card from
    // the start (so persistence is automatic), but invisible until the
    // animal "drops" it mid-flight.
    const badge = document.createElement("span");
    badge.className = "delivered-badge " + (opts.badgeClass || "badge-default");
    badge.textContent = badgeText;
    badge.style.opacity = "0";
    cardEl.appendChild(badge);

    if (reduceMotion) {
      badge.style.transition = "opacity 0.2s ease";
      requestAnimationFrame(() => { badge.style.opacity = "1"; });
      return;
    }

    // Mount the deliverer SVG as an absolutely-positioned overlay
    // anchored to the card's bounding box. We use the document body as
    // the parent so the SVG can fly in from outside the card without
    // being clipped by the card's overflow:hidden.
    const cardRect = cardEl.getBoundingClientRect();
    const overlay = document.createElement("img");
    overlay.src = cfg.svg;
    overlay.alt = "";
    overlay.className = "deliverer";
    overlay.style.position = "fixed";
    overlay.style.height = "60px";
    overlay.style.width = "auto";
    overlay.style.zIndex = "9999";
    overlay.style.pointerEvents = "none";
    overlay.style.willChange = "transform, opacity";
    overlay.style.transition = `transform ${(0.9 / cfg.speed).toFixed(2)}s ${cfg.easing}, opacity 0.3s ease`;

    // Start position: just below the card, slightly off to one side.
    // For peeking deliverers (raccoon), start behind the card and slide
    // out before flying.
    const startX = cardRect.left + cardRect.width * 0.5 - 30;
    const startY = cardRect.bottom + 80;
    const dropX = cardRect.left + cardRect.width - 70;
    const dropY = cardRect.top + 14;
    const exitX = startX;
    const exitY = window.innerHeight + 80;

    overlay.style.left = "0";
    overlay.style.top = "0";
    overlay.style.transform = `translate(${startX}px, ${startY}px) scale(0.9)`;
    overlay.style.opacity = "0";
    document.body.appendChild(overlay);

    // Three-phase animation: rise to drop point → drop badge → exit.
    requestAnimationFrame(() => {
      overlay.style.opacity = "1";
      const wiggle = cfg.wiggle ? "rotate(-8deg)" : cfg.bounce ? "translateY(-8px)" : "";
      overlay.style.transform = `translate(${dropX}px, ${dropY}px) scale(1) ${wiggle}`;
    });

    // Drop badge (becomes visible) midway, then exit.
    setTimeout(() => {
      badge.style.transition = "opacity 0.2s ease, transform 0.3s cubic-bezier(.34,1.6,.64,1)";
      badge.style.transform = "scale(1.05)";
      badge.style.opacity = "1";
      setTimeout(() => { badge.style.transform = "scale(1)"; }, 180);
    }, (0.9 / cfg.speed) * 1000 * 0.55);

    // Exit stage-bottom.
    setTimeout(() => {
      overlay.style.transform = `translate(${exitX}px, ${exitY}px) scale(0.9)`;
      overlay.style.opacity = "0";
    }, (0.9 / cfg.speed) * 1000 * 0.85);

    // Cleanup.
    setTimeout(() => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }, (0.9 / cfg.speed) * 1000 + 600);
  };

  // ---------------------------------------------------------------------------
  // Auto-trigger deliveries on card lifecycle.
  // ---------------------------------------------------------------------------
  // For now, manual triggers via card.js (after a Promote action). The
  // ambient peeks-from-behind-cameras and the parade-on-promote-celebration
  // come from a separate file (peeks.js) so this stays focused on the
  // badge-delivery primitive.

  // Map (event-name → deliverer + badge). card.js can call this directly:
  //   window.deliverBadge(card, "deer", "★ Featured")
  // or use the convenience map:
  window.DELIVERER_PRESETS = {
    new:       { animal: "squirrel", text: "✨ NEW",          klass: "badge-new" },
    mine:      { animal: "fox-3",    text: "⭐ Mine",         klass: "badge-mine" },
    shared:    { animal: "bear",     text: "🌟 Shared",       klass: "badge-shared" },
    remix:     { animal: "raccoon-2",text: "🎬 Remixed",      klass: "badge-remix" },
    "no-fox":  { animal: "frog",     text: "🚫 Not a fox",    klass: "badge-nofox" },
    featured:  { animal: "deer",     text: "★ Featured",      klass: "badge-featured" },
    loading:   { animal: "rabbit",   text: "Loading…",        klass: "badge-loading" },
  };
})();
