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

  // Initial bucket comes from the server (parsed from ?bucket= query),
  // so a deep link or refresh restores the correct view. Falls back
  // to "pending" (= "All").
  let bucket = window.INITIAL_BUCKET || "pending";
  let offset = 0;
  const limit = 30;
  // Mark the matching top-tab active to mirror what the bottom tabs
  // already do (server-side via active_view). Both surfaces stay in
  // sync as the user clicks around.
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.bucket === bucket);
  });

  // window.IS_ADMIN is injected by the server in highlights.html.

  function reset() {
    offset = 0;
    grid.innerHTML = "";
    grid.classList.remove("remix-list-view");
    if (bucket === "remixes" && remixView === "list") {
      loadRemixesList();
    } else {
      load();
    }
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

  // Remixes tab uses a different rendering path — vertical list of
  // remix cards grouped by parent highlight, rather than the standard
  // .grid of highlight cards. Wire it before the regular load() so the
  // tab-change handler can dispatch.
  async function loadRemixesList() {
    grid.innerHTML = "";
    grid.classList.add("remix-list-view");
    let data;
    try {
      // "Liked by me" is a remix-tab-only status filter — pass it
      // through as liked_by_me=1 so the proxy threads it on to the
      // curator's liked_by_email filter.
      const likedByMe = filterStatus && filterStatus.value === "liked-by-me";
      const url = likedByMe
        ? "/api/remixes?limit=200&liked_by_me=1"
        : "/api/remixes?limit=200";
      const r = await fetch(url, { credentials: "same-origin" });
      data = await r.json();
    } catch (err) {
      grid.appendChild(window.infoCard("Couldn't load remixes."));
      return;
    }
    const items = (data && data.items) || [];
    if (!items.length) {
      grid.appendChild(buildEmptyState("remixes"));
      loadMore.style.display = "none";
      return;
    }
    // Group by parent event_id, preserving newest-first order from
    // the API. The parent of each group is the highlight itself.
    const groups = new Map();
    for (const r of items) {
      const eid = r.event_id;
      if (!groups.has(eid)) groups.set(eid, { event_id: eid, parent: r, remixes: [] });
      groups.get(eid).remixes.push(r);
    }
    // Cache the flat remix order so the modal can navigate prev/next
    // through every remix across all groups.
    window.REMIX_NAV_LIST = items.map((r) => r.remix_id);

    for (const g of groups.values()) {
      const block = document.createElement("div");
      block.className = "remix-group";

      const header = document.createElement("div");
      header.className = "remix-group-header";
      const cam = window.prettyCamera ? window.prettyCamera(g.parent.parent_camera) : (g.parent.parent_camera || "");
      const t = g.parent.parent_start_time
        ? new Date(g.parent.parent_start_time * 1000).toLocaleString()
        : "";
      const speciesPill = g.parent.parent_species
        ? `<span class="remix-group-species">${escapeHtml(g.parent.parent_species)}</span>`
        : "";
      const countPill = g.remixes.length > 1
        ? `<span class="remix-group-count">${g.remixes.length} remixes</span>` : "";
      header.innerHTML = `
        <a class="remix-group-link" href="/clip/${encodeURIComponent(g.event_id)}"
           data-event-id="${encodeURIComponent(g.event_id)}"
           title="View original highlight">
          <span class="remix-group-title">${cam} <span class="muted">·</span> ${t}</span>
          ${speciesPill}${countPill}
        </a>`;
      // In remix-list view, tapping the group header opens the
      // group's first (most recent) remix in remix-playback mode —
      // not the parent highlight. Keeps the user in remix-nav space
      // so swipes traverse REMIX_NAV_LIST instead of jumping to
      // sibling highlight clips.
      header.querySelector("a").addEventListener("click", (e) => {
        e.preventDefault();
        const firstRemix = g.remixes[0];
        if (firstRemix && window.openRemixModal) {
          window.openRemixModal(firstRemix.remix_id);
        } else if (window.openCardModal) {
          window.openCardModal(g.event_id);
        }
      });
      block.appendChild(header);

      // Indented child list — visual hierarchy via .remix-children
      // class. If only 1 remix, the indent + tree-glyph still apply
      // for a consistent look.
      const ul = document.createElement("ul");
      ul.className = "remix-children";
      for (const r of g.remixes) {
        const li = document.createElement("li");
        li.className = "remix-child" + (r.featured ? " is-featured" : "");
        li.dataset.remixId = r.remix_id;
        const dur = (r.end_offset_s - r.start_offset_s).toFixed(1);
        const username = r.created_by
          ? (window.Profiles ? window.Profiles.displayName(r.created_by) : r.created_by.split("@")[0])
          : "anonymous";
        const title = r.title || "(untitled)";
        const zoom = (r.zoom_scale && r.zoom_scale > 1.01) ? ` · zoom ${r.zoom_scale.toFixed(1)}×` : "";
        // Filled-heart + count badge when likes exist. Hidden at 0.
        const likeCount = Number(r.like_count || 0);
        const likesBadge = likeCount > 0
          ? `<span class="rx-likes" aria-label="${likeCount} like${likeCount === 1 ? "" : "s"}">
               <span class="material-icons">favorite</span>${likeCount}
             </span>`
          : "";
        // Featured-on-landing indicator — inline filled star before the
        // title. Tooltip explains; visible to everyone (read-only) so
        // non-admins also see at-a-glance which remixes are landing-
        // page material. Admin promote/unpromote still happens through
        // the modal's star action button.
        const featuredMark = r.featured
          ? `<span class="rx-featured" aria-label="Featured on landing"
                   title="Featured on landing"><span class="material-icons">star</span></span>`
          : "";
        // Each child shows the parent highlight's full-frame thumbnail
        // (remixes are sub-windows of that frame so it's the right
        // visual identifier). Tree glyph stays for hierarchy clarity.
        li.innerHTML = `
          <span class="rx-tree" aria-hidden="true">└─</span>
          <img class="rx-thumb" src="/api/highlights/${encodeURIComponent(g.event_id)}/thumbnail" alt="" loading="lazy">
          <div class="rx-text">
            <div class="rx-line1">${featuredMark}<span class="rx-title">${escapeHtml(title)}</span>${likesBadge}</div>
            <div class="rx-line2">
              <span class="rx-author">@${escapeHtml(username)}</span>
              <span class="rx-meta muted">${dur}s${zoom}</span>
            </div>
          </div>`;
        li.addEventListener("click", (e) => {
          e.preventDefault();
          if (window.openRemixModal) window.openRemixModal(r.remix_id);
        });
        ul.appendChild(li);
      }
      block.appendChild(ul);
      grid.appendChild(block);
    }
    loadMore.style.display = "none";
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  async function load() {
    // Filters apply within ANY filterable bucket — camera/time/date/
    // species narrow the visible set without changing which bucket
    // you're in. The Status pulldown is special: on the curated
    // buckets we always pass status=any so the curator returns both
    // active + archived; the frontend then splits them into an
    // "Archived" section below the active items.
    // Status="no-foxes" overrides bucket → demoted. The user picked
    // "show me what was rejected as not-a-fox"; that's a global
    // bucket query, not a refinement of Clips/Faves/Group/Remixes.
    // The bottom-tab pill stays on whatever was previously active
    // (no need to flip its visual state — Status drives the view).
    const noFoxes = filterStatus && filterStatus.value === "no-foxes";
    const effectiveBucket = noFoxes ? "demoted" : bucket;
    const filterable = effectiveBucket !== "demoted";
    const params = new URLSearchParams({
      bucket: effectiveBucket,
      time_of_day: filterable ? filterTime.value : "any",
      limit,
      offset,
    });
    if (filterable && filterCamera.value) params.append("camera", filterCamera.value);
    if (filterable && filterSpecies.value) params.append("species_filter", filterSpecies.value);
    if (filterable && filterStatus && filterStatus.value && !noFoxes
        && filterStatus.value !== "liked-by-me") {
      // Within a normal bucket, the Status pulldown narrows the
      // archived/active overlay. (no-foxes is handled by the bucket
      // override above, so we skip the extra status param. liked-by-me
      // is remix-tab-only — treated as "any" everywhere else.)
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
    // Show the list/cards toggle only on the Remixes tab.
    const vt = document.getElementById("view-toggle");
    if (vt) vt.hidden = bucket !== "remixes";
    // "Liked by Me" is a remix-tab-only Status filter. Hide elsewhere
    // and clear the selection if the user leaves the remix tab while
    // it's chosen so the next tab doesn't show an empty grid.
    if (filterStatus) {
      const opt = filterStatus.querySelector('option[value="liked-by-me"]');
      if (opt) opt.hidden = bucket !== "remixes";
      if (bucket !== "remixes" && filterStatus.value === "liked-by-me") {
        filterStatus.value = "active";
      }
    }
  }
  syncFiltersVisibility();

  // Remixes tab view mode: "list" (vertical grouped list, default) or
  // "grid" (standard highlight cards, one per parent clip — same as
  // the old behavior).
  let remixView = "list";
  const viewToggle = document.getElementById("view-toggle");
  if (viewToggle) {
    viewToggle.querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", () => {
        remixView = b.dataset.view;
        viewToggle.querySelectorAll("button").forEach((x) =>
          x.classList.toggle("active", x === b));
        if (bucket === "remixes") reset();
      });
    });
  }

  // Switch the in-page bucket without a full navigation. Used by the
  // top desktop tabs AND the bottom-tab nav on phones. Updates URL
  // via pushState so back/forward + share/refresh all work.
  function switchBucket(nextBucket) {
    bucket = nextBucket;
    document.querySelectorAll(".tab").forEach((x) =>
      x.classList.toggle("active", x.dataset.bucket === nextBucket));
    document.querySelectorAll(".bottom-tab[data-bucket]").forEach((x) =>
      x.classList.toggle("active", x.dataset.bucket === nextBucket));
    // Keep the URL honest so refresh / share preserves the view.
    const newUrl = nextBucket === "pending"
      ? "/highlights"
      : `/highlights?bucket=${encodeURIComponent(nextBucket)}`;
    if (location.pathname + location.search !== newUrl) {
      history.pushState({ bucket: nextBucket }, "", newUrl);
    }
    syncFiltersVisibility();
    reset();
  }

  tabs.forEach((t) => {
    t.addEventListener("click", () => switchBucket(t.dataset.bucket));
  });

  // Admin "Recover clip" button — opens a small inline form that POSTs
  // /api/admin/highlights/manual to recover a clip from raw recordings
  // for an arbitrary time window. Foundational primitive that the
  // future deeper-dive review surface will build on; for now driven by
  // this button. Server enforces ADMIN_EMAILS and validates the camera
  // + max window, so the client UX is minimal-prompt.
  const recoverBtn = document.getElementById("admin-recover-btn");
  if (recoverBtn) {
    const cameras = (window.CAMERAS && Array.isArray(window.CAMERAS))
      ? window.CAMERAS : ["fox_den_1", "fox_den_2", "fox_den_3", "fox_den_4"];
    recoverBtn.addEventListener("click", async () => {
      // Two-step prompt to keep the surface tiny. We could promote this
      // to a real modal with date/time pickers later — the same backend
      // endpoint won't change.
      const cam = (prompt(
        `Camera (one of: ${cameras.join(", ")})`,
        cameras[1] || cameras[0]) || "").trim();
      if (!cam) return;
      const startStr = (prompt(
        "Start time (local, e.g. 2026-05-08 00:25:00 or 12:25 AM today):",
        ""
      ) || "").trim();
      if (!startStr) return;
      const endStr = (prompt(
        "End time (same format) — max 10 minutes after start:",
        ""
      ) || "").trim();
      if (!endStr) return;
      const start = parseLocalTimeInput(startStr);
      const end = parseLocalTimeInput(endStr);
      if (!start || !end) {
        alert("Couldn't parse one of the times. Try '2026-05-08 00:25:00' or '12:25 AM today'.");
        return;
      }
      if (end - start > 600) {
        alert("Window too long — max 10 minutes.");
        return;
      }
      const caption = (prompt("Optional caption (≤140 chars):", "") || "").trim() || null;
      recoverBtn.disabled = true;
      recoverBtn.textContent = "Recovering…";
      try {
        const r = await fetch("/api/admin/highlights/manual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            camera: cam,
            start_time: start,
            end_time: end,
            label: "manual",
            caption,
          }),
        });
        if (r.status === 403) { alert("Admin only."); return; }
        const data = await r.json();
        if (!r.ok) {
          alert(`Recover failed: ${data.detail || r.status}`);
          return;
        }
        const h = data.highlight;
        const dur = (h && h.duration_s) ? h.duration_s.toFixed(1) : "?";
        alert(`Recovered ${dur}s clip from ${data.segment_count} segment(s). Refreshing gallery.`);
        reset();
      } catch (err) {
        alert(`Recover failed: ${err.message || err}`);
      } finally {
        recoverBtn.disabled = false;
        recoverBtn.innerHTML =
          '<span class="material-icons" aria-hidden="true">video_call</span>' +
          '<span class="admin-recover-label">Recover clip</span>';
      }
    });
  }

  // Lightweight local-time parser. Accepts:
  //   "YYYY-MM-DD HH:MM[:SS]" (24-hour, local)
  //   "HH:MM[:SS] AM/PM today" / "HH:MM[:SS] AM/PM yesterday"
  //   "HH:MM[:SS]" (assumed today)
  // Returns epoch seconds, or null if unparseable.
  function parseLocalTimeInput(s) {
    if (!s) return null;
    s = s.trim();
    // ISO-ish absolute: YYYY-MM-DD HH:MM[:SS]
    const isoMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (isoMatch) {
      const [, y, mo, d, h, m, sec] = isoMatch;
      const dt = new Date(+y, +mo - 1, +d, +h, +m, +(sec || 0));
      return Math.floor(dt.getTime() / 1000);
    }
    // HH:MM[:SS] [AM|PM] [today|yesterday]
    const tMatch = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?(?:\s+(today|yesterday))?$/i);
    if (tMatch) {
      let [, hh, mm, ss, ampm, day] = tMatch;
      hh = +hh; mm = +mm; ss = +(ss || 0);
      if (ampm) {
        ampm = ampm.toLowerCase();
        if (ampm === "pm" && hh < 12) hh += 12;
        if (ampm === "am" && hh === 12) hh = 0;
      }
      const base = new Date();
      if ((day || "").toLowerCase() === "yesterday") base.setDate(base.getDate() - 1);
      base.setHours(hh, mm, ss, 0);
      return Math.floor(base.getTime() / 1000);
    }
    // Fall back to Date constructor (handles a lot of edge cases).
    const t = Date.parse(s);
    if (!isNaN(t)) return Math.floor(t / 1000);
    return null;
  }

  // Bottom-tab nav: intercept the four /highlights tabs (Clips, My
  // Faves, Group Faves, Remixes) so they switch in place instead of
  // navigating. Live and non-bucket tabs do a real nav.
  document.querySelectorAll(".bottom-tab[data-bucket]").forEach((tab) => {
    tab.addEventListener("click", (e) => {
      // Already on /highlights → in-place switch.
      if (location.pathname === "/highlights") {
        e.preventDefault();
        switchBucket(tab.dataset.bucket);
      }
      // else: let the browser navigate to /highlights?bucket=...
    });
  });

  // Browser back/forward — re-render the gallery for the new bucket.
  window.addEventListener("popstate", () => {
    const params = new URLSearchParams(location.search);
    const next = params.get("bucket") || "pending";
    if (next !== bucket) switchBucket(next);
  });

  filterCamera.addEventListener("change", reset);
  filterTime.addEventListener("change", reset);
  filterDate.addEventListener("change", reset);
  filterSpecies.addEventListener("change", reset);
  if (filterStatus) filterStatus.addEventListener("change", reset);
  loadMore.addEventListener("click", load);

  // ---------------------------------------------------------------
  // Pull-to-refresh — phones only (≤720px). The native iOS Safari
  // bouncy overscroll at scroll-top doesn't give us a refresh
  // affordance, so we add one: when the user pulls down past
  // ~70px while at scrollY=0, fire reset() to refetch the gallery
  // (without a full page reload). Capture LAST_SEEN_AT_PAGELOAD
  // beforehand so newly-arrived clips get the ✨ NEW badge.
  // ---------------------------------------------------------------
  if (window.matchMedia && window.matchMedia("(max-width: 720px)").matches) {
    const ptr = document.createElement("div");
    ptr.className = "ptr-indicator";
    ptr.innerHTML = '<span class="material-icons" aria-hidden="true">refresh</span>';
    document.body.appendChild(ptr);

    const THRESHOLD = 70;
    const MAX_PULL = 100;
    let startY = 0;
    let pulling = false;
    let pullDist = 0;

    const setHeight = (h) => {
      ptr.style.height = `${h}px`;
      ptr.style.transition = "none";   // raw drag → no easing
    };
    const collapse = () => {
      ptr.style.transition = "height 0.18s ease";
      ptr.style.height = "0";
      ptr.classList.remove("spinning");
    };

    document.addEventListener("touchstart", (e) => {
      if (window.scrollY > 2) { pulling = false; return; }
      if (e.touches.length !== 1) { pulling = false; return; }
      if (document.querySelector(".card-modal[open]")) { pulling = false; return; }
      if (e.target.closest(".bottom-tabs, .chrome-popover, .chrome-btn, button")) {
        pulling = false; return;
      }
      startY = e.touches[0].clientY;
      pulling = true;
      pullDist = 0;
    }, { passive: true });

    document.addEventListener("touchmove", (e) => {
      if (!pulling) return;
      if (e.touches.length !== 1) { pulling = false; collapse(); return; }
      const t = e.touches[0];
      pullDist = Math.max(0, t.clientY - startY);
      // Strip height grows with the pull (rubber-banded by Math.min).
      // Up to MAX_PULL pixels of band before plateau.
      setHeight(Math.min(pullDist, MAX_PULL));
    }, { passive: true });

    document.addEventListener("touchend", () => {
      if (!pulling) return;
      pulling = false;
      if (pullDist > THRESHOLD) {
        // Lock at threshold height + spin.
        ptr.style.transition = "height 0.18s ease";
        ptr.style.height = `${THRESHOLD}px`;
        ptr.classList.add("spinning");
        window.LAST_SEEN_AT_PAGELOAD = Math.floor(Date.now() / 1000);
        reset();
        setTimeout(() => {
          collapse();
          fetch("/api/viewer/seen", { method: "POST", credentials: "same-origin" })
            .catch(() => {});
        }, 700);
      } else {
        collapse();
      }
      pullDist = 0;
    });
  }

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
      // reset() (not load()) so the initial render dispatches based on
      // the current bucket — including bucket="remixes" which routes
      // to loadRemixesList(). Calling load() directly here was the
      // reason a fresh navigation to /highlights?bucket=remixes (e.g.
      // tapping the bottom-nav Remixes tab from /clip or /live) showed
      // the clips view on first paint, then switched to the list only
      // when the tab was clicked again (same-page switchBucket→reset).
      reset();
      fetch("/api/viewer/seen", { method: "POST", credentials: "same-origin" }).catch(() => {});
    });
})();
