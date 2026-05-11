// foxcam.stream public gallery.
//
// Fetches /api/foxcam/featured (anonymous-readable), renders cards
// in a CSS grid, and wires two interactions:
//
//   1. Play-on-hover: when the pointer enters a card and the device
//      reports fine-pointer capability (i.e. desktop), the static
//      thumbnail fades out and a muted, looped <video> plays the
//      clip's HLS feed. On pointer-leave, the video pauses and the
//      thumbnail returns. Mobile devices (no hover) skip this path
//      entirely — they only see the static thumbnail until tap.
//
//   2. Tap / click: opens a screen-overlay native <dialog> with a
//      full-controls <video> playing the same HLS source. Native
//      controls give the browser's own fullscreen button + scrub
//      bar; iOS Safari plays HLS natively, other browsers use the
//      bundled hls.min.js via attachHlsSource. Tapping outside the
//      video or the close button dismisses.
//
// No buttons, no per-clip metadata beyond the "Fox Cam N" + timestamp
// caption — this surface is intentionally austere and read-only.

(function () {
  "use strict";

  const gallery = document.getElementById("foxcam-gallery");
  const player = document.getElementById("foxcam-player");
  const playerVideo = player.querySelector(".foxcam-player-video");
  const playerClose = player.querySelector(".foxcam-player-close");

  // Hover-play only on devices with fine pointers (mouse / trackpad).
  // Touch devices match `coarse` and would mis-trigger on every
  // scroll-near. Recomputed once at load; the surface doesn't need to
  // react to docking a mouse mid-session.
  const SUPPORTS_HOVER_PLAY =
    window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  // ---------------------------------------------------------------------
  // Render — fetch the featured list once, build the DOM. No pagination
  // yet; list endpoint caps at 200 which is plenty for a curated set.
  // ---------------------------------------------------------------------
  async function render() {
    let items;
    try {
      const r = await fetch("/api/foxcam/featured", { credentials: "omit" });
      if (!r.ok) throw new Error(`status ${r.status}`);
      const data = await r.json();
      items = Array.isArray(data.items) ? data.items : [];
    } catch (err) {
      gallery.innerHTML =
        `<div class="foxcam-empty">Couldn't load clips. Try again in a moment.</div>`;
      return;
    }
    if (!items.length) {
      gallery.innerHTML =
        `<div class="foxcam-empty">No clips here yet.</div>`;
      return;
    }
    gallery.innerHTML = "";
    for (const it of items) {
      gallery.appendChild(buildCard(it));
    }
  }

  // ---------------------------------------------------------------------
  // Card construction. Keeps DOM lean: no listeners attached at build
  // time — both hover and click are dispatched from a single delegated
  // handler on the gallery root (added once below).
  // ---------------------------------------------------------------------
  function buildCard(item) {
    const card = document.createElement("article");
    card.className = "foxcam-card";
    const kind = item.kind || "highlight";
    const id = item.id || item.event_id || item.remix_id;
    card.dataset.kind = kind;
    card.dataset.id = id;

    // Camera + timestamp resolution. For remixes, use the parent
    // highlight's camera + start_time; the curator's
    // list_foxcam_featured_remixes enriches the row with parent_*.
    const camera = item.camera || item.parent_camera || "fox_den_1";
    const startTime = item.start_time || item.parent_start_time || 0;
    card.dataset.camera = camera;
    card.dataset.startTime = String(startTime);

    // Asset URLs. Highlights use /api/highlights/<event>/... routes;
    // remixes have their own /api/remixes/<remix>/clip and the same
    // HLS path doesn't exist for remixes, so they fall back to the
    // inline trimmed MP4 — slower but works.
    const thumbUrl = kind === "highlight"
      ? `/api/highlights/${encodeURIComponent(id)}/thumbnail`
      : `/api/highlights/${encodeURIComponent(item.event_id)}/thumbnail`;
    const hlsUrl = kind === "highlight"
      ? `/api/highlights/${encodeURIComponent(id)}/hls/index.m3u8`
      : null;
    const mp4Url = kind === "highlight"
      ? `/api/highlights/${encodeURIComponent(id)}/clip`
      : `/api/remixes/${encodeURIComponent(id)}/clip`;
    card.dataset.hls = hlsUrl || "";
    card.dataset.mp4 = mp4Url;

    card.innerHTML = `
      <div class="foxcam-card-media">
        <img class="foxcam-card-thumb" src="${thumbUrl}" alt="" loading="lazy">
        <video class="foxcam-card-video" muted loop playsinline preload="none"
               poster="${thumbUrl}" aria-hidden="true"></video>
      </div>
      <div class="foxcam-card-caption">
        <span class="foxcam-card-cam">${prettyCamera(camera)}</span>
        <span class="foxcam-card-time">${formatTime(startTime)}</span>
      </div>
    `;
    return card;
  }

  // Camera name → "Fox Cam N". The user's spec calls for "Fox Cam N
  // mention" specifically; the cam ids are fox_den_{1,2,3,4} so the
  // trailing digit drives the label.
  function prettyCamera(name) {
    const m = /(\d+)$/.exec(name || "");
    return m ? `Fox Cam ${m[1]}` : (name || "Fox Cam");
  }

  // Format unix-epoch seconds for the card timestamp. Locale-default
  // so the page reads naturally for the visitor regardless of where
  // the clip was originally captured.
  function formatTime(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000);
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  }

  // ---------------------------------------------------------------------
  // Hover-play. Attach HLS on first hover (lazy), play / pause as the
  // pointer enters and leaves. We detach the source on leave so the
  // browser doesn't keep buffering segments for cards the user moved
  // off of — important when 20+ cards are on screen.
  // ---------------------------------------------------------------------
  function onCardHover(card, entering) {
    if (!SUPPORTS_HOVER_PLAY) return;
    const video = card.querySelector(".foxcam-card-video");
    if (!video) return;
    if (entering) {
      const hls = card.dataset.hls;
      const mp4 = card.dataset.mp4;
      if (window.attachHlsSource && hls) {
        window.attachHlsSource(video, hls, mp4);
      } else {
        video.src = mp4;
      }
      card.classList.add("is-playing");
      const p = video.play();
      if (p && p.catch) p.catch(() => {});
    } else {
      card.classList.remove("is-playing");
      try { video.pause(); } catch (_) {}
      // Detach HLS instance + clear src so segment fetches stop.
      try {
        if (video._foxHls) { video._foxHls.destroy(); video._foxHls = null; }
      } catch (_) {}
      try { video.removeAttribute("src"); video.load(); } catch (_) {}
    }
  }

  // ---------------------------------------------------------------------
  // Screen-overlay player. Reused dialog element; we swap src on each
  // open. iOS Safari plays HLS natively when src is an .m3u8;
  // hls.js handles other browsers.
  // ---------------------------------------------------------------------
  function openPlayer(card) {
    const hls = card.dataset.hls;
    const mp4 = card.dataset.mp4;
    const thumb = card.querySelector(".foxcam-card-thumb");
    // Set the poster to the same thumbnail the card was showing so
    // the overlay paints something immediately instead of going to
    // a black rectangle while the manifest loads + first segment
    // arrives over CF tunnel.
    if (thumb && thumb.src) {
      playerVideo.poster = thumb.src;
    } else {
      playerVideo.removeAttribute("poster");
    }
    // Show the dialog FIRST. Setting a video source while the
    // element is still inside a display:none dialog causes iOS
    // Safari (and sometimes Chrome) to silently defer the load —
    // the dialog opens to a blank black box and play() never starts.
    // Once the dialog is open the <video> is in the layout tree
    // and the source attach behaves normally.
    if (typeof player.showModal === "function") {
      player.showModal();
    } else {
      player.setAttribute("open", "");
    }
    // Reset to beginning so re-opens always start at 0:00.
    try { playerVideo.currentTime = 0; } catch (_) {}
    // attachHlsSource calls play() internally; no need to also call
    // it here (a second play() before the first completes throws
    // AbortError on some browsers and can race with the source swap).
    if (window.attachHlsSource && hls) {
      window.attachHlsSource(playerVideo, hls, mp4);
    } else {
      playerVideo.src = mp4;
      try { playerVideo.load(); } catch (_) {}
      const p = playerVideo.play();
      if (p && p.catch) p.catch(() => {});
    }
  }

  function closePlayer() {
    try { playerVideo.pause(); } catch (_) {}
    try {
      if (playerVideo._foxHls) { playerVideo._foxHls.destroy(); playerVideo._foxHls = null; }
    } catch (_) {}
    try { playerVideo.removeAttribute("src"); playerVideo.load(); } catch (_) {}
    if (player.open) {
      try { player.close(); } catch (_) {}
    }
  }

  // ---------------------------------------------------------------------
  // Delegated event handlers. Single set of listeners on the gallery
  // root regardless of card count.
  // ---------------------------------------------------------------------
  gallery.addEventListener("pointerover", (e) => {
    const card = e.target.closest(".foxcam-card");
    if (!card || e.pointerType !== "mouse") return;
    // pointerover bubbles for every child enter; only act on the first
    // entry into the card itself.
    if (card._foxHovering) return;
    card._foxHovering = true;
    onCardHover(card, true);
  });
  gallery.addEventListener("pointerout", (e) => {
    const card = e.target.closest(".foxcam-card");
    if (!card || e.pointerType !== "mouse") return;
    // pointerout fires for every child leave too; we only want the
    // exit from the card. relatedTarget = where the pointer went;
    // if it's still inside this card, this isn't a real leave.
    if (card.contains(e.relatedTarget)) return;
    card._foxHovering = false;
    onCardHover(card, false);
  });

  gallery.addEventListener("click", (e) => {
    const card = e.target.closest(".foxcam-card");
    if (!card) return;
    // Stop the hover playback first so we don't have two videos
    // streaming the same HLS bundle simultaneously.
    onCardHover(card, false);
    openPlayer(card);
  });

  playerClose.addEventListener("click", closePlayer);
  // Backdrop click closes too. The dialog's click target is the dialog
  // element itself when the user clicks outside the video.
  player.addEventListener("click", (e) => {
    if (e.target === player) closePlayer();
  });
  // ESC closes (native <dialog> already does this, but make sure
  // our cleanup runs alongside).
  player.addEventListener("close", closePlayer);

  // Kick off the first render.
  render();
})();
