// Gallery page logic. Card rendering + actions live in card.js
// (loaded before this file). This file owns tabs, filters, paging.

(function () {
  const grid = document.getElementById("highlights");
  const loadMore = document.getElementById("load-more");
  const filterCamera = document.getElementById("filter-camera");
  const filterTime = document.getElementById("filter-time");
  const filterDate = document.getElementById("filter-date");
  const filterSpecies = document.getElementById("filter-species");
  const tabs = document.querySelectorAll(".tab");

  // Defensive — if any required element is missing, this isn't the
  // gallery page (e.g., card.js was loaded somewhere else); bail out.
  if (!grid || !loadMore) return;

  let bucket = "pending";
  let offset = 0;
  const limit = 30;

  function reset() {
    offset = 0;
    grid.innerHTML = "";
    load();
  }

  function dateRange() {
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
    if (filterSpecies.value) params.append("species_filter", filterSpecies.value);
    const range = dateRange();
    if (range.since !== undefined) params.append("since", range.since);
    if (range.until !== undefined) params.append("until", range.until);

    const r = await fetch(`/api/highlights?${params}`);
    if (!r.ok) {
      grid.appendChild(window.infoCard(`server returned ${r.status}`));
      return;
    }
    const data = await r.json();
    if (data.items.length === 0 && offset === 0) {
      grid.appendChild(window.infoCard(emptyMessage(bucket)));
      loadMore.style.display = "none";
      return;
    }
    for (const h of data.items) grid.appendChild(window.makeCard(h));
    offset += data.items.length;
    loadMore.style.display = data.items.length === limit ? "" : "none";
  }

  function emptyMessage(b) {
    if (b === "favorites") return "No favorites yet — click ⭐ on a clip to feature it here.";
    if (b === "demoted") return "Nothing here yet — clips marked “Not a fox” show up in this section.";
    return "No highlights yet for these filters.";
  }

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
  filterSpecies.addEventListener("change", reset);
  loadMore.addEventListener("click", load);
  load();
})();
