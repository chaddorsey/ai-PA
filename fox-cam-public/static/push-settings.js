// Wires the Push notifications panel inside the profile popover.
// Driven by /static/push-client.js which owns the actual subscribe /
// unsubscribe / fetch logic — this file is purely UI state.

(() => {
  "use strict";

  const root = document.getElementById("push-settings");
  if (!root) return;

  const stateMsg = document.getElementById("push-state-msg");
  const enableBtn = document.getElementById("push-enable");
  const disableBtn = document.getElementById("push-disable");
  const testBtn = document.getElementById("push-test");
  const prefsList = document.getElementById("push-prefs");
  const pwaHint = document.getElementById("push-pwa-hint");
  const popover = document.getElementById("profile-popover");

  if (!window.PushClient) {
    stateMsg.textContent = "Push client unavailable.";
    return;
  }

  function setState(label, klass) {
    stateMsg.className = `push-state ${klass || ""}`;
    stateMsg.textContent = label;
  }

  async function renderState() {
    enableBtn.hidden = true;
    disableBtn.hidden = true;
    testBtn.hidden = true;
    prefsList.hidden = true;
    pwaHint.hidden = true;

    const cap = await window.PushClient.capabilityState();
    if (cap === "unsupported") {
      setState("This browser doesn't support push notifications.", "muted");
      return;
    }
    if (cap === "needs-pwa") {
      setState("Push notifications require Home Screen install.", "muted");
      pwaHint.hidden = false;
      return;
    }
    if (cap === "denied") {
      setState("Permission denied — enable Notifications in Settings.", "warn");
      return;
    }
    if (cap === "subscribed") {
      setState("Notifications are on for this device.", "ok");
      disableBtn.hidden = false;
      testBtn.hidden = false;
      // Self-heal: if server doesn't know about this device (ghost
      // local sub, deploy mishap, DB reset), re-POST it now so the
      // next push finds a target. Idempotent on endpoint.
      window.PushClient.ensureServerSync().catch(() => {});
      await renderPreferences();
      prefsList.hidden = false;
      return;
    }
    // "default" or "granted" but no subscription yet on this device.
    setState("Notifications are off.", "muted");
    enableBtn.hidden = false;
  }

  async function renderPreferences() {
    let prefs = {};
    try { prefs = await window.PushClient.getPreferences(); }
    catch { prefs = {}; }
    prefsList.innerHTML = "";
    for (const [kind, meta] of Object.entries(prefs)) {
      const li = document.createElement("li");
      li.className = "push-pref";
      const id = `push-pref-${kind}`;
      li.innerHTML = `
        <label for="${id}">
          <input type="checkbox" id="${id}" ${meta.enabled ? "checked" : ""}>
          <span class="push-pref-text">
            <span class="push-pref-label">${meta.label || kind}</span>
            <span class="push-pref-desc">${meta.desc || ""}</span>
          </span>
        </label>`;
      const cb = li.querySelector("input");
      cb.addEventListener("change", async () => {
        cb.disabled = true;
        try {
          await window.PushClient.setPreference(kind, cb.checked);
        } catch (err) {
          // Revert on failure so the UI stays truthful.
          cb.checked = !cb.checked;
          alert("Couldn't save that preference. Try again?");
        } finally {
          cb.disabled = false;
        }
      });
      prefsList.appendChild(li);
    }
  }

  // ---- Click handlers --------------------------------------------------
  // CRITICAL: subscribe() must run inside the synchronous click handler
  // so the Notification permission prompt gets a user-gesture context.
  // We can't await anything before calling PushClient.subscribe.
  enableBtn.addEventListener("click", async () => {
    enableBtn.disabled = true;
    setState("Asking for permission…", "muted");
    try {
      await window.PushClient.subscribe();
    } catch (err) {
      const msg = String(err && err.message || err);
      if (msg.includes("ios-needs-pwa")) {
        setState("Add to Home Screen first to enable push on iPhone.", "warn");
        pwaHint.hidden = false;
      } else if (msg.includes("permission denied")) {
        setState("Permission denied — enable Notifications in Settings.", "warn");
      } else {
        setState(`Couldn't enable: ${msg}`, "warn");
      }
      enableBtn.disabled = false;
      return;
    }
    enableBtn.disabled = false;
    await renderState();
  });

  disableBtn.addEventListener("click", async () => {
    disableBtn.disabled = true;
    setState("Disabling…", "muted");
    try { await window.PushClient.unsubscribe(); }
    catch { /* still fine to render fresh state */ }
    disableBtn.disabled = false;
    await renderState();
  });

  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    const original = testBtn.querySelector(".material-icons")?.nextSibling?.nodeValue || "";
    try {
      const result = await window.PushClient.sendTestPush();
      setState(
        `Test sent to ${result.sent}/${result.device_count} device${
          result.device_count === 1 ? "" : "s"
        }.`,
        "ok",
      );
    } catch (err) {
      setState(`Test failed: ${err.message || err}`, "warn");
    } finally {
      testBtn.disabled = false;
    }
  });

  // Re-render whenever the profile popover opens — covers permission
  // changes the user made in Settings outside our flow.
  if (popover) {
    popover.addEventListener("toggle", (e) => {
      if (e.newState === "open") renderState();
    });
  }

  // First paint.
  renderState();
})();
