// Shared highlight-card rendering. Used by both highlights.js (gallery)
// and clip.js (single-clip permalink page). Exposes window.makeCard
// plus helpers; everything else is page-local.

(function () {
  window.makeCard = function makeCard(h) {
    const el = document.createElement("div");
    el.className = "highlight";
    el.dataset.eventId = h.event_id;
    if (h.favorited) el.classList.add("is-favorited");
    if (h.demoted) el.classList.add("is-demoted");
    el.appendChild(cardThumb(h));
    el.appendChild(cardMeta(h));
    el.appendChild(cardActions(h));
    return el;
  };

  function cardThumb(h) {
    const img = document.createElement("img");
    img.src = `/api/highlights/${h.event_id}/thumbnail`;
    img.loading = "lazy";
    img.alt = "";
    img.addEventListener("click", () => playInline(img.parentElement, h));
    return img;
  }

  function cardMeta(h) {
    const div = document.createElement("div");
    div.className = "meta";
    const t = new Date(h.start_time * 1000).toLocaleString();
    const fox = (h.fox_likelihood * 100).toFixed(0);
    div.innerHTML = `
      <a class="time" href="/clip/${h.event_id}">${t}</a>
      <div>${h.camera} · ${h.label} · ${h.duration_s.toFixed(1)}s
        · <span class="score">fox ${fox}%</span></div>`;
    return div;
  }

  function cardActions(h) {
    const bar = document.createElement("div");
    bar.className = "actions";
    bar.appendChild(actionBtn("⭐", "favorite", h.favorited, () =>
      setAction(h.event_id, h.favorited ? "clear" : "favorite")
    ));
    bar.appendChild(actionBtn("🚫", "demote", h.demoted, () =>
      setAction(h.event_id, h.demoted ? "clear" : "demote")
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

  function playInline(card, h) {
    const img = card.querySelector("img");
    if (!img) return;
    const v = document.createElement("video");
    v.src = `/api/highlights/${h.event_id}/clip`;
    v.controls = true;
    v.autoplay = true;
    v.playsInline = true;
    img.replaceWith(v);
  }

  // Also expose infoCard for empty-state messages on the gallery page.
  window.infoCard = function infoCard(msg) {
    const el = document.createElement("div");
    el.className = "highlight info-card";
    el.innerHTML = `<div class="meta">${msg}</div>`;
    return el;
  };
})();
