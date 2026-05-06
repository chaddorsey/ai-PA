// User profile / display name helper.
//
// Three responsibilities:
//   1. Lazy-load the full {email: name} roster on first call and cache
//      it client-side. Friends-and-family scale — a few dozen rows
//      max, so one fetch per page is fine.
//   2. Expose a synchronous-feeling getter that any UI can call:
//        Profiles.displayName("foo@bar.com") → "Foo Bar" (or "foo")
//   3. Manage the current user's profile: getMine(), setMine(name),
//      and a "needs onboarding" check the first-login prompt uses.

(() => {
  "use strict";

  let _cache = null;       // { email_lower: name }
  let _cachePromise = null;
  let _myEmail = (window.CURRENT_EMAIL || "").toLowerCase();

  async function loadAll() {
    if (_cache) return _cache;
    if (_cachePromise) return _cachePromise;
    _cachePromise = (async () => {
      try {
        const r = await fetch("/api/profile/all",
                               { credentials: "same-origin" });
        if (!r.ok) throw new Error(`profile/all ${r.status}`);
        const j = await r.json();
        const out = {};
        for (const p of (j.profiles || [])) {
          if (p && p.email) out[p.email.toLowerCase()] = p.display_name;
        }
        _cache = out;
        return out;
      } catch (err) {
        console.warn("[profiles] couldn't load roster", err);
        _cache = {};
        return _cache;
      } finally {
        _cachePromise = null;
      }
    })();
    return _cachePromise;
  }

  // Trigger a load on script init so the cache is warm by the time
  // any UI asks for a name. Don't await — fire-and-forget.
  loadAll();

  function fallback(email) {
    if (!email) return "someone";
    return email.includes("@") ? email.split("@")[0] : email;
  }

  // Synchronous-feeling lookup. Returns the cached name if loadAll()
  // has finished; otherwise the email-prefix fallback. Callers that
  // need the absolute freshest name can `await Profiles.refresh()`
  // first, but most UI sites are fine with eventually-consistent
  // names — the next render cycle picks up changes.
  function displayName(email) {
    if (!email) return "someone";
    const key = email.toLowerCase();
    if (_cache && _cache[key]) return _cache[key];
    return fallback(email);
  }

  async function refresh() {
    _cache = null;
    return loadAll();
  }

  async function getMine() {
    if (!_myEmail) return null;
    try {
      const r = await fetch("/api/profile",
                             { credentials: "same-origin" });
      if (!r.ok) return null;
      const j = await r.json();
      return j.profile || null;
    } catch {
      return null;
    }
  }

  async function setMine(displayNameStr) {
    const name = String(displayNameStr || "").trim();
    if (!name) throw new Error("display name cannot be empty");
    const r = await fetch("/api/profile", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: name }),
    });
    if (!r.ok) {
      let msg = `profile save failed: ${r.status}`;
      try { msg = (await r.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    // Patch the cache so the new name is visible everywhere
    // immediately, no full re-fetch needed.
    if (_cache && _myEmail) _cache[_myEmail] = name;
    return r.json();
  }

  // True if the current authed user has no profile yet — the
  // first-login prompt watches this to decide whether to surface.
  async function needsOnboarding() {
    if (!_myEmail) return false;
    const p = await getMine();
    return !(p && p.display_name);
  }

  window.Profiles = {
    displayName, refresh, getMine, setMine, needsOnboarding,
    myEmail: () => _myEmail,
  };
})();
