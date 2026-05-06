// Wires the Display Name input inside the profile popover, plus the
// first-login onboarding dialog. Backend operations live in
// profiles.js — this file is purely UI state.

(() => {
  "use strict";

  if (!window.Profiles) return;

  // ---- Popover input -------------------------------------------------
  const input = document.getElementById("profile-name-input");
  const saveBtn = document.getElementById("profile-name-save");
  const stateEl = document.getElementById("profile-name-state");
  const popover = document.getElementById("profile-popover");

  function setState(msg, klass) {
    if (!stateEl) return;
    stateEl.className = `profile-name-state ${klass || ""}`;
    stateEl.textContent = msg || "";
  }

  async function loadInputFromProfile() {
    if (!input) return;
    try {
      const p = await window.Profiles.getMine();
      input.value = (p && p.display_name) || "";
    } catch { /* ignore */ }
  }

  if (saveBtn && input) {
    saveBtn.addEventListener("click", async () => {
      const name = input.value.trim();
      if (!name) { setState("Name can't be empty.", "warn"); return; }
      saveBtn.disabled = true;
      setState("Saving…", "muted");
      try {
        await window.Profiles.setMine(name);
        setState("Saved.", "ok");
      } catch (err) {
        setState(`Couldn't save: ${err.message || err}`, "warn");
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  if (popover) {
    popover.addEventListener("toggle", (e) => {
      if (e.newState === "open") {
        loadInputFromProfile();
        setState("");
      }
    });
  }

  // ---- First-login dialog -------------------------------------------
  // Shown if curator has no profile row for this user. Modal — they
  // can't escape without entering a name (well, they can, but the
  // dialog re-opens on the next page load).
  const dialog = document.getElementById("profile-onboarding");
  const onbInput = document.getElementById("profile-onboarding-input");
  const onbSave = document.getElementById("profile-onboarding-save");
  const onbErr = document.getElementById("profile-onboarding-err");

  async function maybeShowOnboarding() {
    if (!dialog) return;
    const needs = await window.Profiles.needsOnboarding();
    if (!needs) return;
    try {
      dialog.showModal();
      // Pre-fill with the email prefix as a starting suggestion —
      // most people just want to capitalize their first name and go.
      const email = window.Profiles.myEmail();
      if (onbInput && email && email.includes("@")) {
        const stem = email.split("@")[0];
        onbInput.value = stem.charAt(0).toUpperCase() + stem.slice(1);
      }
      onbInput?.focus();
      onbInput?.select();
    } catch { /* dialog API not supported — silently skip */ }
  }

  if (onbSave && onbInput) {
    const submit = async () => {
      const name = onbInput.value.trim();
      if (!name) { onbErr.textContent = "Please enter a name."; return; }
      onbSave.disabled = true;
      onbErr.textContent = "";
      try {
        await window.Profiles.setMine(name);
        dialog.close();
        // Re-render anything that's already on screen by refreshing
        // the cache + reloading. Simplest path; runs in <1s.
        location.reload();
      } catch (err) {
        onbErr.textContent = err.message || String(err);
      } finally {
        onbSave.disabled = false;
      }
    };
    onbSave.addEventListener("click", submit);
    onbInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
    });
  }

  // Defer to next tick so Profiles' lazy fetch can settle.
  setTimeout(maybeShowOnboarding, 100);
})();
