// Gallery page logic. Card rendering + actions live in card.js
// (loaded before this file). This file owns tabs, filters, paging.

(function () {
  const grid = document.getElementById("highlights");
  const loadMore = document.getElementById("load-more");
  const filterCamera = document.getElementById("filter-camera");
  const filterTime = document.getElementById("filter-time");
  const filterDate = document.getElementById("filter-date");
  const filterSpecies = document.getElementById("filter-species");
  const filterStatus = document.getElementById("filter-status");
  const tabs = document.querySelectorAll(".tab");

  // Defensive — if any required element is missing, this isn't the
  // gallery page (e.g., card.js was loaded somewhere else); bail out.
  if (!grid || !loadMore) return;

  let bucket = "pending";
  let offset = 0;
  const limit = 30;

  // window.IS_ADMIN is injected by the server in highlights.html.

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
    // Filter row applies only to the "All" tab; every other bucket is
    // itself a curated subset (My Faves, Group Faves, Remixes, No
    // Foxes) where applying camera/time/date/species filters would
    // both confuse the user and hide otherwise-relevant clips.
    const onAll = bucket === "pending";
    const params = new URLSearchParams({
      bucket,
      time_of_day: onAll ? filterTime.value : "any",
      limit,
      offset,
    });
    if (onAll && filterCamera.value) params.append("camera", filterCamera.value);
    if (onAll && filterSpecies.value) params.append("species_filter", filterSpecies.value);
    // Status (Active/All/Archived) IS meaningful across buckets — a
    // user might archive a favorite — so keep it always.
    if (filterStatus && filterStatus.value) params.append("status", filterStatus.value);
    if (onAll) {
      const range = dateRange();
      if (range.since !== undefined) params.append("since", range.since);
      if (range.until !== undefined) params.append("until", range.until);
    }

    let r;
    try {
      r = await fetch(`/api/highlights?${params}`, { credentials: "same-origin" });
    } catch (err) {
      // "Failed to fetch" usually means the request hit a CORS-blocked
      // CF Access redirect — your team session expired or no longer
      // covers this path. Offer a reload that triggers re-auth.
      console.error("[highlights] /api/highlights network error:", err);
      const card = document.createElement("div");
      card.className = "empty-state";
      card.innerHTML = `
        <img src="/static/animals/Raccoon-1.svg" alt="" aria-hidden="true">
        <p>Your session timed out.</p>
        <p style="margin-top:8px;">
          <a href="/highlights" style="color:#f05a28;font-weight:600;text-decoration:none;border:1.5px solid #f05a28;padding:8px 18px;border-radius:999px;">Sign in again →</a>
        </p>`;
      grid.appendChild(card);
      return;
    }
    if (!r.ok) {
      const ct = r.headers.get("content-type") || "";
      let detail = `${r.status}`;
      try { detail += " — " + (ct.includes("json") ? JSON.stringify(await r.json()) : (await r.text()).slice(0, 200)); } catch {}
      console.error("[highlights] /api/highlights non-ok:", r.status, r.url);
      grid.appendChild(window.infoCard(`Server returned ${detail}. (URL: ${r.url})`));
      return;
    }
    let data;
    try { data = await r.json(); }
    catch (err) {
      console.error("[highlights] /api/highlights parse error:", err);
      grid.appendChild(window.infoCard(`Couldn't parse highlights response.`));
      return;
    }
    if (data.items.length === 0 && offset === 0) {
      grid.appendChild(buildEmptyState(bucket));
      loadMore.style.display = "none";
      return;
    }
    for (const h of data.items) grid.appendChild(window.makeCard(h));
    offset += data.items.length;
    loadMore.style.display = data.items.length === limit ? "" : "none";
  }

  function buildEmptyState(b) {
    const empties = {
      pending: { svg: "/static/animals/Stump.svg",    text: "Quiet woods today. Check back tonight." },
      mine:    { svg: "/static/animals/Bear.svg",     text: "Star a clip to save it as a favorite here." },
      shared:  { svg: "/static/animals/Tree-Trio.svg", text: "Once two of you star the same clip, it shows up here." },
      remixes: { svg: "/static/animals/Raccoon-2.svg", text: "Open a favorited clip and ✂️ Remix to capture a moment." },
      demoted: { svg: "/static/animals/Frog.svg",     text: "Nothing here yet — clips marked “Not a fox” live here." },
    };
    const cfg = empties[b] || empties.pending;
    const wrap = document.createElement("div");
    wrap.className = "empty-state";
    wrap.innerHTML = `
      <img src="${cfg.svg}" alt="" aria-hidden="true">
      <p>${cfg.text}</p>
    `;
    return wrap;
  }

  // The filter row (camera/time/date/status/species) is meaningful only
  // on the "All" tab — every other tab is itself a curated subset.
  // Toggle a body class so CSS hides the filters bar when not on All.
  function syncFiltersVisibility() {
    document.body.classList.toggle("filters-hidden", bucket !== "pending");
  }
  syncFiltersVisibility();

  tabs.forEach((t) => {
    t.addEventListener("click", () => {
      tabs.forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      bucket = t.dataset.bucket;
      syncFiltersVisibility();
      reset();
    });
  });

  filterCamera.addEventListener("change", reset);
  filterTime.addEventListener("change", reset);
  filterDate.addEventListener("change", reset);
  filterSpecies.addEventListener("change", reset);
  if (filterStatus) filterStatus.addEventListener("change", reset);
  loadMore.addEventListener("click", load);

  // Capture last-seen-at BEFORE marking as seen, so cards rendered on
  // this visit get the NEW badge. After load, post /api/viewer/seen so
  // the next visit's count starts fresh. ALL paths still call load(),
  // even when /api/viewer/state errors — without that, a single 401 on
  // viewer/state would leave the gallery empty forever.
  fetch("/api/viewer/state", { credentials: "same-origin" })
    .then((r) => r.ok ? r.json() : null)
    .then((s) => {
      window.LAST_SEEN_AT_PAGELOAD = (s && s.last_seen_at) || 0;
    })
    .catch((err) => {
      console.error("[highlights] /api/viewer/state failed:", err);
    })
    .finally(() => {
      load();
      fetch("/api/viewer/seen", { method: "POST", credentials: "same-origin" }).catch(() => {});
    });
})();
