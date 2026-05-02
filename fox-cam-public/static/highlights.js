// Highlights browser. Pages through curator's index, lazy-loads video
// when user clicks a thumbnail.

(function () {
  const grid = document.getElementById("highlights");
  const loadMore = document.getElementById("load-more");
  const filterCamera = document.getElementById("filter-camera");
  const filterScore = document.getElementById("filter-score");

  let offset = 0;
  const limit = 30;

  function reset() {
    offset = 0;
    grid.innerHTML = "";
    load();
  }

  async function load() {
    const params = new URLSearchParams({
      min_score: filterScore.value,
      limit,
      offset,
    });
    if (filterCamera.value) params.append("camera", filterCamera.value);

    const r = await fetch(`/api/highlights?${params}`);
    if (!r.ok) {
      grid.appendChild(errorCard(`server returned ${r.status}`));
      return;
    }
    const data = await r.json();
    if (data.items.length === 0 && offset === 0) {
      grid.appendChild(errorCard("No highlights yet."));
      loadMore.style.display = "none";
      return;
    }
    for (const h of data.items) grid.appendChild(card(h));
    offset += data.items.length;
    loadMore.style.display = data.items.length === limit ? "" : "none";
  }

  function card(h) {
    const el = document.createElement("div");
    el.className = "highlight";
    const t = new Date(h.start_time * 1000).toLocaleString();
    el.innerHTML = `
      <img src="/api/highlights/${h.event_id}/thumbnail" loading="lazy" alt="">
      <div class="meta">
        <div class="time">${t}</div>
        <div>${h.camera} · ${h.label} · ${h.duration_s.toFixed(1)}s
          · <span class="score">fox ${(h.fox_likelihood * 100).toFixed(0)}%</span></div>
      </div>`;
    el.addEventListener("click", () => playClip(el, h));
    return el;
  }

  function playClip(el, h) {
    const img = el.querySelector("img");
    if (!img) return;
    const v = document.createElement("video");
    v.src = `/api/highlights/${h.event_id}/clip`;
    v.controls = true;
    v.autoplay = true;
    v.playsInline = true;
    img.replaceWith(v);
  }

  function errorCard(msg) {
    const el = document.createElement("div");
    el.className = "highlight";
    el.innerHTML = `<div class="meta">${msg}</div>`;
    return el;
  }

  filterCamera.addEventListener("change", reset);
  filterScore.addEventListener("change", reset);
  loadMore.addEventListener("click", load);
  load();
})();
