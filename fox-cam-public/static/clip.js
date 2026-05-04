// Single-clip permalink page. Loads the highlight metadata via the
// API and reuses window.makeCard from highlights.js for consistency
// with the gallery — but auto-plays the video instead of showing the
// thumbnail and starts the share buttons / favorite state correctly.

(async function () {
  const card = document.getElementById("clip-card");
  const eventId = card.dataset.eventId;
  try {
    const r = await fetch(`/api/highlights/${eventId}`);
    if (r.status === 404) {
      card.querySelector(".meta").textContent = "Clip not found.";
      return;
    }
    if (!r.ok) {
      card.querySelector(".meta").textContent = `Error ${r.status} loading clip.`;
      return;
    }
    const h = await r.json();
    const fresh = window.makeCard(h);
    fresh.classList.add("clip-permalink-card");
    card.replaceWith(fresh);

    // Auto-play the video on this dedicated page.
    const img = fresh.querySelector("img");
    if (img) {
      const v = document.createElement("video");
      v.src = `/api/highlights/${h.event_id}/clip`;
      v.controls = true;
      v.autoplay = true;
      v.muted = true;
      v.playsInline = true;
      img.replaceWith(v);
      // Skip the pre-roll on first play; family can scrub back if
      // they want to re-examine the lead-in.
      if (window.applyPrerollSkip) window.applyPrerollSkip(v);
    }
  } catch (e) {
    console.error(e);
    card.querySelector(".meta").textContent = `Error: ${e.message}`;
  }
})();
