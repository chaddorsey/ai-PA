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
      // Bootstrap fast-path: page kicked off /api/bootstrap on load
      // which already includes profile_all. Consume it instead of
      // firing a duplicate /api/profile/all fetch.
      let j = null;
      if (window.BOOTSTRAP_DATA_PROMISE) {
        try {
          const boot = await window.BOOTSTRAP_DATA_PROMISE;
          if (boot && boot.profile_all) j = boot.profile_all;
        } catch {}
      }
      if (!j) {
        try {
          const r = await fetch("/api/profile/all",
                                 { credentials: "same-origin" });
          if (!r.ok) throw new Error(`profile/all ${r.status}`);
          j = await r.json();
        } catch (err) {
          console.warn("[profiles] couldn't load roster", err);
          _cache = {};
          _cachePromise = null;
          return _cache;
        }
      }
      const out = {};
      for (const p of (j.profiles || [])) {
        if (p && p.email) out[p.email.toLowerCase()] = p.display_name;
      }
      _cache = out;
      _cachePromise = null;
      return out;
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

  // Returns:
  //   { ok: true, profile: {...} | null }  on a successful fetch
  //   { ok: false }                         on network / 5xx / timeout
  //
  // Critically NOT collapsing "couldn't fetch" into "no profile":
  // the onboarding dialog uses this to decide whether to prompt for
  // a name. A transient curator timeout used to return null and fire
  // the dialog at users whose profile already existed — see
  // needsOnboarding() below for the discrimination.
  async function getMine() {
    if (!_myEmail) return { ok: true, profile: null };
    // Bootstrap fast-path. Same caveat as needsOnboarding(): we only
    // accept a positive result (got the bootstrap, has a profile).
    // A null profile in the bootstrap could mean "user has no profile
    // yet" OR "the curator sub-call failed and defaulted to null" —
    // since we can't distinguish, fall through to the explicit fetch
    // so the onboarding logic stays correct.
    if (window.BOOTSTRAP_DATA_PROMISE) {
      try {
        const boot = await window.BOOTSTRAP_DATA_PROMISE;
        if (boot && boot.profile && boot.profile.profile) {
          return { ok: true, profile: boot.profile.profile };
        }
      } catch {}
    }
    try {
      const r = await fetch("/api/profile",
                             { credentials: "same-origin" });
      if (!r.ok) return { ok: false };
      const j = await r.json();
      return { ok: true, profile: j.profile || null };
    } catch {
      return { ok: false };
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

  // True ONLY if we successfully fetched the profile and it has no
  // display_name set. Failures (timeouts, 5xx, network errors) →
  // false: don't prompt the user to set their name based on what
  // might just be a transient API blip.
  async function needsOnboarding() {
    if (!_myEmail) return false;
    const result = await getMine();
    if (!result.ok) return false;
    const p = result.profile;
    return !(p && p.display_name);
  }

  window.Profiles = {
    displayName, refresh, getMine, setMine, needsOnboarding,
    myEmail: () => _myEmail,
  };
})();
