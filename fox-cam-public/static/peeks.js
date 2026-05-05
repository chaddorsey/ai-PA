/* peeks.js — animals peek out from behind live-camera tiles
   ----------------------------------------------------------------------------
   Loaded only on /live (added in index.html). Picks a random tile + animal
   every 30-90 seconds, slides it out from behind the top-right corner of
   that tile, holds for 2 seconds, then ducks back. Strictly visual delight;
   no functional behavior tied to it.

   Respects prefers-reduced-motion (no peeks at all).
*/
(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduceMotion) return;

  const PEEKERS = [
    { svg: "/static/animals/Fox-2.svg",     hold: 2200 },
    { svg: "/static/animals/Squirrel.svg",  hold: 1500 },
    { svg: "/static/animals/Raccoon-1.svg", hold: 2400 },
    { svg: "/static/animals/Frog.svg",      hold: 1800 },
    { svg: "/static/animals/Rabbit.svg",    hold: 1900 },
  ];

  function pickRandom(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  function findTiles() {
    return Array.from(document.querySelectorAll(".cam"));
  }

  function ensurePeekSlot(tile) {
    let slot = tile.querySelector(".peek-slot");
    if (!slot) {
      slot = document.createElement("div");
      slot.className = "peek-slot";
      // Only force position:relative when the tile is currently
      // statically positioned. Spotlight mode sets the active cam to
      // position:absolute via CSS — overwriting that here knocks the
      // spotlight out of its container and collapses the layout
      // (manifests as "Cam 4 collapses when the squirrel peeks out").
      const pos = window.getComputedStyle(tile).position;
      if (pos === "static") tile.style.position = "relative";
      tile.appendChild(slot);
    }
    return slot;
  }

  function runPeek() {
    const tiles = findTiles();
    if (!tiles.length) return scheduleNext();
    const tile = pickRandom(tiles);
    const peeker = pickRandom(PEEKERS);
    const slot = ensurePeekSlot(tile);

    const img = document.createElement("img");
    img.src = peeker.svg;
    img.alt = "";
    img.style.position = "absolute";
    img.style.left = "0";
    img.style.bottom = "0";
    img.style.width = "100%";
    img.style.height = "auto";
    img.style.transform = "translateY(70%) scale(0.9) rotate(-6deg)";
    img.style.opacity = "0";
    img.style.transition = "transform 0.45s cubic-bezier(.34,1.4,.64,1), opacity 0.3s ease";
    slot.innerHTML = "";
    slot.appendChild(img);
    slot.classList.add("peek-active");

    requestAnimationFrame(() => {
      img.style.transform = "translateY(0) scale(1) rotate(0deg)";
      img.style.opacity = "1";
    });

    // Hold, then duck back.
    setTimeout(() => {
      img.style.transform = "translateY(75%) scale(0.85) rotate(4deg)";
      img.style.opacity = "0";
      setTimeout(() => {
        slot.classList.remove("peek-active");
        if (slot.firstChild) slot.removeChild(slot.firstChild);
        scheduleNext();
      }, 500);
    }, peeker.hold);
  }

  function scheduleNext() {
    // Random interval 30-90s, biased toward the lower end on first
    // load so the user notices the feature within their first minute.
    const min = 30_000, max = 90_000;
    const wait = min + Math.floor(Math.random() * (max - min));
    setTimeout(runPeek, wait);
  }

  // Start the first peek 12-25s after page load (later than the page
  // settling, but soon enough to feel responsive).
  function init() {
    const wait = 12_000 + Math.floor(Math.random() * 13_000);
    setTimeout(runPeek, wait);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
