// Push notifications settings panel — drives the markup in
// _user_chrome.html via window.PushClient.
//
// Layout sections (top → bottom):
//   1. Master switch  → controls subscribe/unsubscribe; first ON
//      triggers Notification.requestPermission inside the gesture.
//   2. Pause notifications → 1h/2h/4h/8h links + active-state row.
//   3. Notification schedule → list of disable intervals + add button.
//   4. Per-kind toggles → Likes / New sightings (with sub-radios).
//   5. Send test push button.
//
// Sections 2-5 are hidden until the user is actually subscribed
// (master switch ON, permission granted, server has the row).

(() => {
  "use strict";

  const root = document.getElementById("push-settings");
  if (!root || !window.PushClient) return;

  const masterToggle = document.getElementById("push-master-toggle");
  const stateMsg     = document.getElementById("push-state-msg");
  const pwaHint      = document.getElementById("push-pwa-hint");
  const detail       = document.getElementById("push-detail");
  const pauseRow     = document.getElementById("push-pause-row");
  const pauseActive  = document.getElementById("push-pause-active");
  const pauseMsg     = document.getElementById("push-pause-msg");
  const pauseLinks   = root.querySelectorAll(".push-pause-link");
  const resumeLink   = document.getElementById("push-resume-link");
  const scheduleList = document.getElementById("push-schedule");
  const addIntervalBtn = document.getElementById("push-add-interval");
  const prefsList    = document.getElementById("push-prefs");
  const testBtn      = document.getElementById("push-test");
  const popover      = document.getElementById("profile-popover");

  function setState(label, klass) {
    stateMsg.className = `push-state ${klass || ""}`;
    stateMsg.textContent = label || "";
  }

  function showDetail(show) {
    detail.classList.toggle("locked", !show);
  }

  function pad2(n) { return String(n).padStart(2, "0"); }

  function fmtTime(min) {
    return `${pad2(Math.floor(min / 60))}:${pad2(min % 60)}`;
  }
  function parseTime(hhmm) {
    const m = /^(\d{2}):(\d{2})$/.exec(hhmm || "");
    if (!m) return null;
    const h = +m[1], mn = +m[2];
    if (h > 23 || mn > 59) return null;
    return h * 60 + mn;
  }
  function relTimeUntil(ts) {
    const d = ts - Math.floor(Date.now() / 1000);
    if (d <= 0) return "now";
    if (d < 60) return `${d}s`;
    if (d < 3600) return `${Math.round(d / 60)} min`;
    return `${Math.round(d / 3600 * 10) / 10} hr`;
  }
  function fmtClockUntil(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString(undefined,
      { hour: "numeric", minute: "2-digit" });
  }

  // ---- Master toggle ------------------------------------------------
  // The change handler must do its own subscribe() inside the original
  // user gesture for iOS to allow the permission prompt. We don't await
  // anything beforehand. If subscribe() succeeds, follow up with the
  // detail render asynchronously.
  masterToggle.addEventListener("change", async (e) => {
    const wantOn = masterToggle.checked;
    masterToggle.disabled = true;
    if (wantOn) {
      setState("Asking for permission…", "muted");
      try {
        await window.PushClient.subscribe();
        setState("Notifications on for this device.", "ok");
        await renderAll();
      } catch (err) {
        masterToggle.checked = false;
        const msg = String(err && err.message || err);
        if (msg.includes("ios-needs-pwa")) {
          setState("Add to Home Screen first to enable on iPhone.", "warn");
          pwaHint.hidden = false;
        } else if (msg.includes("permission")) {
          setState("Permission denied — enable in Settings.", "warn");
        } else {
          setState(`Couldn't enable: ${msg}`, "warn");
        }
        showDetail(false);
      }
    } else {
      setState("Disabling…", "muted");
      try { await window.PushClient.unsubscribe(); } catch {}
      setState("Notifications off.", "muted");
      showDetail(false);
    }
    masterToggle.disabled = false;
  });

  // ---- Pause links --------------------------------------------------
  for (const link of pauseLinks) {
    link.addEventListener("click", async (e) => {
      e.preventDefault();
      const hours = Number(link.dataset.hours);
      try {
        await window.PushClient.setPause(hours * 3600);
        await renderPause();
      } catch (err) {
        setState(`Pause failed: ${err.message || err}`, "warn");
      }
    });
  }
  resumeLink.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      await window.PushClient.setPause(null);
      await renderPause();
    } catch (err) {
      setState(`Resume failed: ${err.message || err}`, "warn");
    }
  });

  async function renderPause() {
    const p = await window.PushClient.getPause();
    if (p && p.active && p.paused_until) {
      pauseRow.hidden = true;
      pauseActive.hidden = false;
      pauseMsg.textContent =
        `Paused until ${fmtClockUntil(p.paused_until)} (${relTimeUntil(p.paused_until)} left).`;
    } else {
      pauseRow.hidden = false;
      pauseActive.hidden = true;
    }
  }

  // ---- Schedule -----------------------------------------------------
  function intervalRow(it) {
    const li = document.createElement("li");
    li.className = "push-schedule-row";
    li.dataset.id = it.id;
    li.innerHTML = `
      <input type="time" class="push-time push-time-start" value="${fmtTime(it.start_min)}">
      <span class="push-time-sep">to</span>
      <input type="time" class="push-time push-time-end" value="${fmtTime(it.end_min)}">
      <button type="button" class="push-int-del" aria-label="Remove">
        <span class="material-icons">close</span>
      </button>`;
    const startInp = li.querySelector(".push-time-start");
    const endInp   = li.querySelector(".push-time-end");
    const saveEdit = async () => {
      const s = parseTime(startInp.value);
      const e = parseTime(endInp.value);
      if (s == null || e == null) return;
      // Edit = delete + re-add. Cheaper than wiring a PATCH endpoint,
      // and the row count is tiny.
      try {
        await window.PushClient.removeScheduleInterval(it.id);
        await window.PushClient.addScheduleInterval(s, e);
        await renderSchedule();
      } catch (err) {
        setState(`Schedule save failed: ${err.message || err}`, "warn");
      }
    };
    startInp.addEventListener("change", saveEdit);
    endInp.addEventListener("change", saveEdit);
    li.querySelector(".push-int-del").addEventListener("click", async () => {
      try {
        await window.PushClient.removeScheduleInterval(it.id);
        await renderSchedule();
      } catch (err) {
        setState(`Delete failed: ${err.message || err}`, "warn");
      }
    });
    return li;
  }

  async function renderSchedule() {
    let intervals = [];
    try { intervals = (await window.PushClient.getSchedule()).intervals || []; }
    catch { intervals = []; }
    scheduleList.innerHTML = "";
    for (const it of intervals) scheduleList.appendChild(intervalRow(it));
  }

  addIntervalBtn.addEventListener("click", async () => {
    // Default to a sensible quiet-hours window — 22:00 → 07:00.
    try {
      await window.PushClient.addScheduleInterval(22 * 60, 7 * 60);
      await renderSchedule();
    } catch (err) {
      setState(`Couldn't add interval: ${err.message || err}`, "warn");
    }
  });

  // ---- Per-kind preferences ----------------------------------------
  function kindRow(kind, meta) {
    const li = document.createElement("li");
    li.className = "push-pref";
    const id = `push-pref-${kind}`;
    li.innerHTML = `
      <div class="push-pref-row">
        <div class="push-pref-text">
          <span class="push-pref-label">${meta.label || kind}</span>
          ${meta.desc ? `<span class="push-pref-desc">${meta.desc}</span>` : ""}
        </div>
        <label class="push-switch">
          <input type="checkbox" id="${id}" ${meta.enabled ? "checked" : ""}>
          <span class="push-switch-track"></span>
        </label>
      </div>`;
    const toggle = li.querySelector("input[type=checkbox]");
    toggle.addEventListener("change", async () => {
      toggle.disabled = true;
      try {
        await window.PushClient.setPreference(kind, { enabled: toggle.checked });
        // Re-render to flip option visibility on the same row.
        await renderPrefs();
      } catch {
        toggle.checked = !toggle.checked;
        setState("Couldn't save preference.", "warn");
      } finally {
        toggle.disabled = false;
      }
    });

    // Sub-options (radios) — only meaningful when this kind has options
    // AND the master toggle for this kind is ON.
    if (Array.isArray(meta.options) && meta.options.length) {
      const sub = document.createElement("div");
      sub.className = "push-pref-sub";
      if (!meta.enabled) sub.classList.add("locked");
      const groupName = `pushpref-opt-${kind}`;
      const inner = document.createElement("div");
      inner.className = "push-pref-options";
      for (const opt of meta.options) {
        const optId = `pushpref-opt-${kind}-${opt.value}`;
        const checked = (meta.value || meta.default_value) === opt.value;
        const r = document.createElement("label");
        r.className = "push-pref-option";
        // Two-line layout: bold label up top, muted sub-line beneath
        // explains the empirical trigger so users pick by intent,
        // not just by label name.
        const subLine = opt.desc
          ? `<span class="push-pref-option-desc">${opt.desc}</span>`
          : "";
        r.innerHTML = `
          <input type="radio" name="${groupName}" id="${optId}"
                 value="${opt.value}" ${checked ? "checked" : ""}>
          <span class="push-pref-option-text">
            <span class="push-pref-option-label">${opt.label}</span>
            ${subLine}
          </span>`;
        const radio = r.querySelector("input");
        radio.addEventListener("change", async () => {
          if (!radio.checked) return;
          try {
            await window.PushClient.setPreference(kind, { value: opt.value });
          } catch {
            setState("Couldn't save selection.", "warn");
          }
        });
        inner.appendChild(r);
      }
      sub.appendChild(inner);
      li.appendChild(sub);
    }
    return li;
  }

  async function renderPrefs() {
    let prefs = {};
    try { prefs = await window.PushClient.getPreferences(); }
    catch { prefs = {}; }
    prefsList.innerHTML = "";
    for (const [kind, meta] of Object.entries(prefs)) {
      prefsList.appendChild(kindRow(kind, meta));
    }
  }

  // ---- Test button --------------------------------------------------
  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    try {
      const r = await window.PushClient.sendTestPush();
      setState(`Test sent to ${r.sent}/${r.device_count} device${
        r.device_count === 1 ? "" : "s"}.`, "ok");
    } catch (err) {
      setState(`Test failed: ${err.message || err}`, "warn");
    } finally {
      testBtn.disabled = false;
    }
  });

  // ---- Render orchestration ----------------------------------------
  async function renderAll() {
    pwaHint.hidden = true;
    const cap = await window.PushClient.capabilityState();
    if (cap === "unsupported") {
      masterToggle.checked = false;
      masterToggle.disabled = true;
      setState("This browser doesn't support push notifications.", "muted");
      showDetail(false);
      return;
    }
    if (cap === "needs-pwa") {
      masterToggle.checked = false;
      masterToggle.disabled = true;
      setState("Add to Home Screen first to enable push on iPhone.", "warn");
      pwaHint.hidden = false;
      showDetail(false);
      return;
    }
    if (cap === "denied") {
      masterToggle.checked = false;
      masterToggle.disabled = true;
      setState("Permission denied — enable Notifications in Settings.", "warn");
      showDetail(false);
      return;
    }
    if (cap === "subscribed") {
      masterToggle.checked = true;
      masterToggle.disabled = false;
      setState("Notifications are on for this device.", "ok");
      showDetail(true);
      // Self-heal ghost subs (carries over from prior fix).
      window.PushClient.ensureServerSync().catch(() => {});
      await Promise.all([renderPause(), renderSchedule(), renderPrefs()]);
      return;
    }
    // "default" / "granted" but no live subscription on this device.
    masterToggle.checked = false;
    masterToggle.disabled = false;
    setState("Notifications are off.", "muted");
    showDetail(false);
  }

  if (popover) {
    popover.addEventListener("toggle", (e) => {
      if (e.newState === "open") renderAll();
    });
  }
  renderAll();
})();
