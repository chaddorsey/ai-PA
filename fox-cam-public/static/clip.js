// Single-clip permalink page. Loads the highlight metadata via the
// API and reuses window.makeCard for consistency with the gallery —
// but auto-plays the video instead of showing the thumbnail. Now also
// hosts the remix create/list UI: each highlight can have any number
// of family-saved sub-clips with optional zoom regions.
//
// If the URL is /remix/<id>, this page enters "remix playback" mode:
// fetches the remix, finds its parent highlight, and plays the trimmed
// + zoomed view automatically.

(async function () {
  const main = document.querySelector("main.clip-page");
  const eventId = main.dataset.eventId;
  const remixId = main.dataset.remixId;
  const card = document.getElementById("clip-card");

  let highlight = null;
  let remix = null;          // present when on /remix/<id>
  let videoEl = null;
  let pzInstance = null;     // panzoom on the video for capture
  let capturedZoom = null;   // {x, y, scale} captured for save

  try {
    if (remixId) {
      const rr = await fetch(`/api/remixes/${encodeURIComponent(remixId)}`);
      if (!rr.ok) throw new Error(`remix ${rr.status}`);
      const body = await rr.json();
      remix = body.remix;
      highlight = body.highlight;
    } else if (eventId) {
      const r = await fetch(`/api/highlights/${encodeURIComponent(eventId)}`);
      if (r.status === 404) {
        card.querySelector(".meta").textContent = "Clip not found.";
        return;
      }
      if (!r.ok) throw new Error(`highlight ${r.status}`);
      highlight = await r.json();
    } else {
      card.querySelector(".meta").textContent = "No clip specified.";
      return;
    }

    // Render the existing card (using highlight metadata) so the user
    // gets the species badge, action buttons, etc. Then swap thumbnail
    // for an autoplaying video element.
    const fresh = window.makeCard(highlight);
    fresh.classList.add("clip-permalink-card");
    card.replaceWith(fresh);

    const wrap = fresh.querySelector(".thumb-wrap") || fresh.querySelector("img")?.parentElement;
    const img = fresh.querySelector("img");
    if (img) {
      videoEl = document.createElement("video");
      videoEl.src = `/api/highlights/${highlight.event_id}/clip`;
      videoEl.controls = true;
      videoEl.autoplay = true;
      videoEl.muted = true;
      videoEl.playsInline = true;
      img.replaceWith(videoEl);

      if (remix) {
        // Remix playback: jump to start, stop at end, apply zoom.
        applyRemixPlayback(videoEl, wrap, remix);
      } else if (window.applyPrerollSkip) {
        window.applyPrerollSkip(videoEl);
      }

      // Wire up panzoom on the video itself so the user can pinch /
      // scroll in. We keep the instance for capture-zoom in the editor.
      if (typeof window.panzoom === "function" && wrap) {
        try {
          videoEl.style.transformOrigin = "0 0";
          pzInstance = window.panzoom(videoEl, {
            maxZoom: 6, minZoom: 1, bounds: true,
            boundsPadding: 0.95,
            zoomDoubleClickSpeed: 1,
          });
        } catch (e) { console.warn("panzoom init:", e); }
      }
    }

    // Show the remix panel + populate its list with existing remixes
    // (from the highlight payload) when on a clip permalink — not
    // when viewing a remix permalink (which is read-only).
    if (!remix) {
      const panel = document.getElementById("remix-panel");
      if (panel) {
        panel.hidden = false;
        renderRemixList(highlight.remixes || []);
        wireRemixEditor();
      }
    }
  } catch (e) {
    console.error(e);
    if (card) card.querySelector(".meta").textContent = `Error: ${e.message}`;
  }

  function applyRemixPlayback(video, wrap, remix) {
    const start = remix.start_offset_s || 0;
    const end = remix.end_offset_s;
    const seek = () => {
      try { video.currentTime = start; } catch (_) {}
    };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });
    // Stop at end-offset by clamping in timeupdate handler.
    video.addEventListener("timeupdate", () => {
      if (typeof end === "number" && video.currentTime >= end) {
        video.pause();
      }
    });
    // Apply saved zoom region: panzoom's transform model uses scale +
    // translate; we have center-of-view (zoom_x, zoom_y) + scale. We
    // wait for the video to know its rendered dimensions so the
    // wrap-to-video transform can be calibrated.
    if (remix.zoom_scale && remix.zoom_scale > 1.01 && wrap) {
      const applyZoom = () => {
        const r = wrap.getBoundingClientRect();
        const cx = remix.zoom_x ?? 0.5;
        const cy = remix.zoom_y ?? 0.5;
        const s = remix.zoom_scale;
        // Translate so that the wrap-relative point (cx*W, cy*H) ends
        // up at the wrap center after scaling.
        const tx = (r.width / 2) - (cx * r.width * s);
        const ty = (r.height / 2) - (cy * r.height * s);
        video.style.transformOrigin = "0 0";
        video.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
      };
      if (video.readyState >= 1) applyZoom();
      else video.addEventListener("loadedmetadata", applyZoom, { once: true });
    }
  }

  function renderRemixList(remixes) {
    const list = document.getElementById("remix-list");
    const count = document.getElementById("remix-count");
    list.innerHTML = "";
    count.textContent = remixes.length ? `(${remixes.length})` : "";
    if (!remixes.length) {
      list.innerHTML = '<p class="muted">No remixes yet — click "+ New remix" to capture one.</p>';
      return;
    }
    for (const r of remixes) {
      const dur = (r.end_offset_s - r.start_offset_s).toFixed(1);
      const a = document.createElement("a");
      a.href = `/remix/${r.remix_id}`;
      a.className = "remix-item";
      const zoom = (r.zoom_scale && r.zoom_scale > 1.01) ? `· zoom ${r.zoom_scale.toFixed(1)}×` : "";
      a.innerHTML = `
        <div class="remix-title">${escapeHtml(r.title || "(untitled)")}</div>
        <div class="remix-meta">${dur}s ${zoom}
          ${r.created_by ? "· by " + escapeHtml(r.created_by.split('@')[0]) : ""}</div>`;
      list.appendChild(a);
    }
  }

  function wireRemixEditor() {
    const editor = document.getElementById("remix-editor");
    const newBtn = document.getElementById("remix-new");
    const cancelBtn = document.getElementById("remix-cancel");
    const saveBtn = document.getElementById("remix-save");
    const startInput = document.getElementById("remix-start");
    const endInput = document.getElementById("remix-end");
    const titleInput = document.getElementById("remix-title");
    const markStartBtn = document.getElementById("remix-mark-start");
    const markEndBtn = document.getElementById("remix-mark-end");
    const captureZoomBtn = document.getElementById("remix-capture-zoom");
    const zoomLabel = document.getElementById("remix-zoom-label");

    newBtn?.addEventListener("click", () => {
      editor.hidden = false;
      newBtn.parentElement.hidden = true;
      if (videoEl && isFinite(videoEl.duration)) {
        startInput.value = "0";
        endInput.value = videoEl.duration.toFixed(1);
      }
    });
    cancelBtn?.addEventListener("click", () => {
      editor.hidden = true;
      newBtn.parentElement.hidden = false;
      capturedZoom = null;
      zoomLabel.textContent = "Zoom: fit";
    });
    markStartBtn?.addEventListener("click", () => {
      if (videoEl) startInput.value = videoEl.currentTime.toFixed(1);
    });
    markEndBtn?.addEventListener("click", () => {
      if (videoEl) endInput.value = videoEl.currentTime.toFixed(1);
    });
    captureZoomBtn?.addEventListener("click", () => {
      if (!pzInstance || !videoEl) return;
      const t = pzInstance.getTransform();
      if (t.scale <= 1.01) {
        capturedZoom = null;
        zoomLabel.textContent = "Zoom: fit (no zoom captured)";
        return;
      }
      const wrap = videoEl.parentElement;
      const r = wrap.getBoundingClientRect();
      // panzoom scale + translate → derive normalized center
      // The visible center in WRAP coords corresponds to the point in
      // VIDEO coords: (-tx + r.w/2) / scale, normalized by r.w.
      const cx = (-t.x + r.width / 2) / (t.scale * r.width);
      const cy = (-t.y + r.height / 2) / (t.scale * r.height);
      capturedZoom = {
        x: Math.max(0, Math.min(1, cx)),
        y: Math.max(0, Math.min(1, cy)),
        scale: t.scale,
      };
      zoomLabel.textContent =
        `Zoom: ${t.scale.toFixed(1)}× at (${(capturedZoom.x*100).toFixed(0)}%, ${(capturedZoom.y*100).toFixed(0)}%)`;
    });
    saveBtn?.addEventListener("click", async () => {
      const start = parseFloat(startInput.value);
      const end = parseFloat(endInput.value);
      if (!isFinite(start) || !isFinite(end) || end <= start) {
        alert("End must be after start.");
        return;
      }
      saveBtn.disabled = true;
      try {
        const body = {
          title: titleInput.value.trim() || null,
          start_offset_s: start,
          end_offset_s: end,
          zoom_x: capturedZoom?.x,
          zoom_y: capturedZoom?.y,
          zoom_scale: capturedZoom?.scale ?? 1.0,
        };
        const r = await fetch(`/api/highlights/${highlight.event_id}/remix`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!r.ok) throw new Error(`save ${r.status}`);
        const out = await r.json();
        // Refresh list, hide editor, copy permalink.
        const listResp = await fetch(`/api/remixes?event_id=${highlight.event_id}`);
        const listBody = await listResp.json();
        renderRemixList(listBody.items || []);
        editor.hidden = true;
        newBtn.parentElement.hidden = false;
        // Reset
        titleInput.value = "";
        capturedZoom = null;
        zoomLabel.textContent = "Zoom: fit";
        const url = `${location.origin}/remix/${out.remix_id}`;
        try { await navigator.clipboard.writeText(url); } catch {}
        alert(`Remix saved.\nPermalink copied:\n${url}`);
      } catch (e) {
        console.error(e);
        alert(`Save failed: ${e.message}`);
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
