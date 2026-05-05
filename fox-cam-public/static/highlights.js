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
    // Filters apply within ANY filterable bucket — camera/time/date/
    // species narrow the visible set without changing which bucket
    // you're in. The Status pulldown is special: on the curated
    // buckets we always pass status=any so the curator returns both
    // active + archived; the frontend then splits them into an
    // "Archived" section below the active items.
    const filterable = bucket !== "demoted";
    const params = new URLSearchParams({
      bucket,
      time_of_day: filterable ? filterTime.value : "any",
      limit,
      offset,
    });
    if (filterable && filterCamera.value) params.append("camera", filterCamera.value);
    if (filterable && filterSpecies.value) params.append("species_filter", filterSpecies.value);
    if (bucket === "pending" && filterStatus && filterStatus.value) {
      params.append("status", filterStatus.value);
    } else {
      params.append("status", "any");
    }
    if (filterable) {
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

    // Curated buckets render archived items in a separate section so
    // a user can still see (and unarchive) clips they've put away
    // without losing them from the bucket entirely. On the All tab,
    // the Status pulldown (Active/All/Archived) drives this — no
    // section split.
    const splitArchived = bucket !== "pending" && bucket !== "demoted" && offset === 0;
    if (splitArchived) {
      const active = data.items.filter((h) => !h.my_archived);
      const archived = data.items.filter((h) => h.my_archived);
      for (const h of active) grid.appendChild(window.makeCard(h));
      if (archived.length) {
        const sep = document.createElement("div");
        sep.className = "section-divider";
        sep.innerHTML = `<h3>📦 Archived <span class="muted">(${archived.length})</span></h3>`;
        grid.appendChild(sep);
        for (const h of archived) grid.appendChild(window.makeCard(h));
      }
    } else {
      for (const h of data.items) grid.appendChild(window.makeCard(h));
    }
    offset += data.items.length;
    loadMore.style.display = data.items.length === limit ? "" : "none";
  }

  // onAll captured outside load() too so we don't recompute in the
  // archived split logic above. Stored at the bottom of load().

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

  // Filter row visibility + contextual label. Hidden on No Foxes
  // (everything there shares the same demoted state — filters add
  // nothing). Shown elsewhere with a "Filter <bucket name>" label so
  // the user knows the filters apply within the active bucket only.
  const BUCKET_LABEL = {
    pending: "All",
    mine:    "My Faves",
    shared:  "Group Faves",
    remixes: "Remixes",
    demoted: "No Foxes",
  };
  function syncFiltersVisibility() {
    document.body.classList.toggle("filters-hidden", bucket === "demoted");
    const lbl = document.getElementById("filters-label");
    if (lbl) lbl.textContent = "Filter " + (BUCKET_LABEL[bucket] || "");
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
