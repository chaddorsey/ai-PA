// Notifications popover — fetches /api/notifications, renders the
// list, and toggles the bell's unread dot. The popover element is
// created by _user_chrome.html and lives at #notifications-popover.
//
// Click on a notification:
//   - mark it read (server + DOM)
//   - if it's a remix_like, open the remix in the modal via the
//     existing window.openRemixModal hook — same surface as the
//     Remixes tab, so the user lands in remix-playback mode with the
//     heart already filled.
//
// Polling: we hit /api/notifications/unread_count on page load and
// after every popover close. No background polling — likes feel
// real-time enough on the next interaction.

(() => {
  "use strict";

  const popover = document.getElementById("notifications-popover");
  const list    = document.getElementById("notif-list");
  const markAll = document.getElementById("notif-mark-all");
  const bellWrap = document.getElementById("notif-bell-wrap");
  if (!popover || !list || !bellWrap) return;

  const RELATIVE = (ts) => {
    const dt = (Date.now() / 1000) - Number(ts || 0);
    if (dt < 60) return "just now";
    if (dt < 3600) return `${Math.floor(dt / 60)}m ago`;
    if (dt < 86400) return `${Math.floor(dt / 3600)}h ago`;
    if (dt < 86400 * 7) return `${Math.floor(dt / 86400)}d ago`;
    return new Date(ts * 1000).toLocaleDateString();
  };

  function escape(s) {
    return String(s || "").replace(/[&<>"']/g, (ch) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));
  }

  async function refreshUnreadDot() {
    // Bootstrap fast-path. Only consume the bootstrap value the FIRST
    // time refreshUnreadDot fires per page-load (subsequent calls —
    // e.g. after the user dismisses a notification — must hit the
    // network so the badge reflects the current state).
    if (window.BOOTSTRAP_DATA_PROMISE && !window._BOOTSTRAP_NOTIF_CONSUMED) {
      window._BOOTSTRAP_NOTIF_CONSUMED = true;
      try {
        const boot = await window.BOOTSTRAP_DATA_PROMISE;
        if (boot && boot.unread_count) {
          const n = Number(boot.unread_count.unread_count || 0);
          bellWrap.classList.toggle("has-unread", n > 0);
          return;
        }
      } catch {}
    }
    try {
      const r = await fetch("/api/notifications/unread_count",
                            { credentials: "same-origin" });
      const j = await r.json();
      const n = Number(j.unread_count || 0);
      bellWrap.classList.toggle("has-unread", n > 0);
    } catch { /* offline — no big deal */ }
  }

  function renderItem(n) {
    const li = document.createElement("li");
    li.className = "notif-item";
    if (!n.read_at) li.classList.add("unread");
    li.dataset.notifId = n.id;

    if (n.kind === "remix_like") {
      const likerEmail = n.payload?.liker_email || "";
      const liker = window.Profiles
        ? window.Profiles.displayName(likerEmail)
        : (likerEmail.split("@")[0] || "someone");
      const title = n.payload?.remix_title || "(untitled)";
      li.innerHTML = `
        <span class="material-icons" aria-hidden="true">favorite</span>
        <span class="notif-text">
          <span class="notif-liker">@${escape(liker)}</span> liked your remix
          <span class="notif-remix">"${escape(title)}"</span>
          <span class="notif-time">${RELATIVE(n.created_at)}</span>
        </span>`;
      li.addEventListener("click", async () => {
        // Mark read first (best-effort), then open the remix.
        try {
          await fetch(`/api/notifications/${n.id}/read`,
                       { method: "POST", credentials: "same-origin" });
        } catch {}
        li.classList.remove("unread");
        try { popover.hidePopover?.(); } catch {}
        const rid = n.payload?.remix_id;
        if (rid && window.openRemixModal) {
          window.openRemixModal(rid);
        } else if (rid) {
          location.href = `/remix/${encodeURIComponent(rid)}`;
        }
        refreshUnreadDot();
      });
    } else {
      // Generic fallback so unknown kinds still render readably.
      li.innerHTML = `
        <span class="material-icons" aria-hidden="true">info</span>
        <span class="notif-text">
          ${escape(n.kind)}
          <span class="notif-time">${RELATIVE(n.created_at)}</span>
        </span>`;
    }
    return li;
  }

  async function loadNotifications() {
    try {
      const r = await fetch("/api/notifications?limit=50",
                            { credentials: "same-origin" });
      const j = await r.json();
      const items = (j && j.items) || [];
      list.innerHTML = "";
      if (!items.length) {
        list.innerHTML = `
          <li class="notif-empty">
            <span class="material-icons" aria-hidden="true">notifications_off</span>
            <p>No notifications yet</p>
            <p class="muted">Likes on your remixes will land here.</p>
          </li>`;
        markAll.hidden = true;
        return;
      }
      for (const n of items) list.appendChild(renderItem(n));
      const anyUnread = items.some((n) => !n.read_at);
      markAll.hidden = !anyUnread;
    } catch {
      list.innerHTML = `<li class="notif-empty"><p>Couldn't load notifications.</p></li>`;
      markAll.hidden = true;
    }
  }

  markAll.addEventListener("click", async () => {
    try {
      await fetch("/api/notifications/mark_all_read",
                   { method: "POST", credentials: "same-origin" });
    } catch {}
    list.querySelectorAll(".notif-item.unread").forEach((el) => el.classList.remove("unread"));
    markAll.hidden = true;
    refreshUnreadDot();
  });

  // Reload on every show; refresh the dot on every hide.
  popover.addEventListener("toggle", (e) => {
    if (e.newState === "open") loadNotifications();
    else refreshUnreadDot();
  });

  // First paint.
  refreshUnreadDot();
})();
