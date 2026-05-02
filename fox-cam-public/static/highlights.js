// Highlights browser. Tabs (All / Favorites / No Foxes), date + time-
// of-day filters, per-clip favorite/demote/share actions.

(function () {
  const grid = document.getElementById("highlights");
  const loadMore = document.getElementById("load-more");
  const filterCamera = document.getElementById("filter-camera");
  const filterTime = document.getElementById("filter-time");
  const filterDate = document.getElementById("filter-date");
  const tabs = document.querySelectorAll(".tab");

  let bucket = "pending";
  let offset = 0;
  const limit = 30;

  function reset() {
    offset = 0;
    grid.innerHTML = "";
    load();
  }

  function dateRange() {
    // Returns {since, until} in unix seconds, or {} for all dates.
    const v = filterDate.value;
    if (!v) return {};
    const now = Date.now();
    const day = 86400000;
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    if (v === "today") return { since: startOfToday.getTime() / 1000 };
    if (v === "yesterday") {
      const startOfY = startOfToday.getTime() - day;
      return { since: startOfY / 1000, until: startOfToday.getTime() / 1000 };
    }
    if (v === "7d") return { since: (now - 7 * day) / 1000 };
    if (v === "30d") return { since: (now - 30 * day) / 1000 };
    return {};
  }

  async function load() {
    const params = new URLSearchParams({
      bucket,
      time_of_day: filterTime.value,
      limit,
      offset,
    });
    if (filterCamera.value) params.append("camera", filterCamera.value);
    const range = dateRange();
    if (range.since !== undefined) params.append("since", range.since);
    if (range.until !== undefined) params.append("until", range.until);

    const r = await fetch(`/api/highlights?${params}`);
    if (!r.ok) {
      grid.appendChild(infoCard(`server returned ${r.status}`));
      return;
    }
    const data = await r.json();
    if (data.items.length === 0 && offset === 0) {
      grid.appendChild(infoCard(emptyMessage(bucket)));
      loadMore.style.display = "none";
      return;
    }
    for (const h of data.items) grid.appendChild(makeCard(h));
    offset += data.items.length;
    loadMore.style.display = data.items.length === limit ? "" : "none";
  }

  function emptyMessage(b) {
    if (b === "favorites") return "No favorites yet — click ⭐ on a clip to feature it here.";
    if (b === "demoted") return "Nothing here yet — clips marked “Not a fox” show up in this section.";
    return "No highlights yet for these filters.";
  }

  // Tabs
  tabs.forEach((t) => {
    t.addEventListener("click", () => {
      tabs.forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      bucket = t.dataset.bucket;
      reset();
    });
  });

  filterCamera.addEventListener("change", reset);
  filterTime.addEventListener("change", reset);
  filterDate.addEventListener("change", reset);
  loadMore.addEventListener("click", load);
  load();
})();

// ---------- shared card rendering (used by clip.js too) ----------

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
  // Re-render the card to reflect new state (or remove from view if it
  // moved out of the current bucket).
  const card = document.querySelector(`.highlight[data-event-id="${eventId}"]`);
  if (!card) return;
  const data = await r.json();
  const h = data.highlight;
  // If we're on "All" and the user demoted, hide the card.
  // If we're on Favorites and user un-favorited, hide.
  // If we're on Demoted and user cleared/favorited, hide.
  const url = new URL(location.href);
  const onAll = !url.searchParams.has("bucket") || url.searchParams.get("bucket") === "pending" || url.pathname === "/highlights";
  const tab = document.querySelector(".tab.active");
  const currentBucket = tab ? tab.dataset.bucket : "pending";
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
    // Fallback: prompt
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

function infoCard(msg) {
  const el = document.createElement("div");
  el.className = "highlight info-card";
  el.innerHTML = `<div class="meta">${msg}</div>`;
  return el;
}
