// Push subscription client.
//
// Surfaces a single async API the settings panel calls:
//   - capabilityState() → "unsupported" | "needs-pwa" | "granted"
//                       | "denied" | "default" | "subscribed"
//   - subscribe()       → permission prompt → subscribe → POST to server
//   - unsubscribe()     → unsubscribe locally + DELETE on server
//   - getPreferences()  / setPreference(kind, enabled)
//   - sendTestPush()
//
// Web Push on iOS Safari is gated to installed PWAs (16.4+). We detect
// the non-PWA case so the UI can show "Add to Home Screen first"
// instead of a broken Enable button.
//
// pushManager.subscribe REQUIRES a synchronous user gesture for the
// permission prompt. Don't call subscribe() from a setTimeout, await
// chain that crosses an event-loop tick before the request, or any
// other indirection — call it directly inside the click handler.

(() => {
  "use strict";

  const SUPPORTED =
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window;

  // iOS PWA detection — Web Push only works in standalone mode on
  // iOS Safari. matchMedia('(display-mode: standalone)') is the
  // standards-compliant probe; navigator.standalone is the iOS quirk
  // we keep as fallback because Safari historically lagged.
  function isPwa() {
    return !!(
      window.matchMedia?.("(display-mode: standalone)").matches ||
      window.navigator.standalone
    );
  }

  // iOS detection — used to show "Add to Home Screen first" guidance
  // instead of the generic "denied" state.
  function isIos() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent || "") &&
            !window.MSStream;
  }

  function urlBase64ToUint8Array(base64) {
    // Web Push spec mandates base64url, but Notifications API expects
    // a standard Uint8Array. Pad + swap chars + atob.
    const padding = "=".repeat((4 - base64.length % 4) % 4);
    const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(b64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  async function getRegistration() {
    if (!SUPPORTED) return null;
    return navigator.serviceWorker.ready;
  }

  async function getSubscription() {
    const reg = await getRegistration();
    if (!reg) return null;
    return reg.pushManager.getSubscription();
  }

  async function capabilityState() {
    if (!SUPPORTED) return "unsupported";
    if (isIos() && !isPwa()) return "needs-pwa";
    if (Notification.permission === "denied") return "denied";
    const sub = await getSubscription();
    if (sub) return "subscribed";
    return Notification.permission === "granted" ? "granted" : "default";
  }

  let _vapidKey = null;
  async function fetchVapidKey() {
    if (_vapidKey) return _vapidKey;
    const r = await fetch("/api/push/vapid-public-key",
                           { credentials: "same-origin" });
    if (!r.ok) throw new Error(`vapid key fetch failed: ${r.status}`);
    const j = await r.json();
    _vapidKey = j.public_key;
    return _vapidKey;
  }

  async function subscribe() {
    if (!SUPPORTED) throw new Error("push not supported in this browser");
    if (isIos() && !isPwa()) {
      throw new Error("ios-needs-pwa");
    }
    // Permission must be requested from a user gesture. The caller is
    // a click handler; this Promise resolves before we hit subscribe.
    const perm = await Notification.requestPermission();
    if (perm !== "granted") throw new Error(`permission ${perm}`);
    const reg = await getRegistration();
    const key = await fetchVapidKey();
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,    // required by every browser
      applicationServerKey: urlBase64ToUint8Array(key),
    });
    // Ship the PushSubscription up to the server. The server-side
    // proxy injects the authed CF-Access email — the client never sets
    // it, so it can't subscribe a different user.
    const json = sub.toJSON();
    const r = await fetch("/api/push/subscriptions", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        endpoint: json.endpoint,
        keys: json.keys,
        user_agent: navigator.userAgent,
      }),
    });
    if (!r.ok) {
      // Server rejected — undo the subscribe so we don't end up with
      // a client-side push registration the server doesn't know about.
      try { await sub.unsubscribe(); } catch {}
      throw new Error(`server subscribe failed: ${r.status}`);
    }
    return sub;
  }

  async function unsubscribe() {
    const sub = await getSubscription();
    if (!sub) return false;
    const endpoint = sub.endpoint;
    let serverOk = true;
    try {
      const r = await fetch(
        `/api/push/subscriptions?endpoint=${encodeURIComponent(endpoint)}`,
        { method: "DELETE", credentials: "same-origin" });
      serverOk = r.ok;
    } catch { serverOk = false; }
    // Always tear down locally even if the server call failed (the
    // server-side row is harmless until garbage-collected by 410-Gone).
    try { await sub.unsubscribe(); } catch {}
    return serverOk;
  }

  async function getPreferences() {
    const r = await fetch("/api/push/preferences",
                           { credentials: "same-origin" });
    if (!r.ok) return {};
    const j = await r.json();
    return j.preferences || {};
  }

  async function setPreference(kind, enabled) {
    const r = await fetch("/api/push/preferences", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, enabled }),
    });
    if (!r.ok) throw new Error(`pref save failed: ${r.status}`);
    return r.json();
  }

  async function sendTestPush() {
    const r = await fetch("/api/push/test", {
      method: "POST",
      credentials: "same-origin",
    });
    if (!r.ok) throw new Error(`test push failed: ${r.status}`);
    return r.json();
  }

  window.PushClient = {
    SUPPORTED, isPwa, isIos,
    capabilityState, subscribe, unsubscribe,
    getPreferences, setPreference, sendTestPush,
  };
})();
