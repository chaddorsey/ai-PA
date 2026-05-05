/* easter-eggs.js — surprise+delight moments
   ----------------------------------------------------------------------------
   - 8-animal parade across the top of the screen, fired:
       * after a successful Promote action (window.fireParade())
       * via Konami code (↑ ↑ ↓ ↓ ← → ← → B A)
       * after 5 quick clicks on the brand H1 in the header
   - All respect prefers-reduced-motion (parade replaced with a brief
     confetti-style fade of the badges).
*/
(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const PARADERS = [
    "/static/animals/Squirrel.svg",
    "/static/animals/Fox-3.svg",
    "/static/animals/Bear.svg",
    "/static/animals/Raccoon-2.svg",
    "/static/animals/Frog.svg",
    "/static/animals/Deer.svg",
    "/static/animals/Rabbit.svg",
    "/static/animals/Fox-1.svg",
  ];

  let paradeRunning = false;
  function fireParade() {
    if (paradeRunning) return;
    paradeRunning = true;

    const stage = document.createElement("div");
    stage.className = "parade-stage";
    stage.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100%; height: 120px;
      pointer-events: none; z-index: 9998; overflow: hidden;
    `;
    document.body.appendChild(stage);

    if (reduceMotion) {
      stage.innerHTML = '<div style="text-align:center;font-family:Fredoka,sans-serif;font-size:24px;color:#f05a28;padding:32px;">🎉 Featured!</div>';
      setTimeout(() => { stage.remove(); paradeRunning = false; }, 1800);
      return;
    }

    PARADERS.forEach((src, i) => {
      const animal = document.createElement("img");
      animal.src = src;
      animal.alt = "";
      animal.style.cssText = `
        position: absolute;
        height: 80px;
        bottom: 8px;
        left: -120px;
        transform: translateX(0);
        transition: transform 4.0s linear;
        will-change: transform;
        filter: drop-shadow(0 4px 8px rgba(0,0,0,0.18));
      `;
      stage.appendChild(animal);

      // Each animal a bit behind the previous one. Stagger 220ms.
      const delay = i * 220;
      const distance = window.innerWidth + 240;
      setTimeout(() => {
        animal.style.transform = `translateX(${distance}px)`;
      }, delay);

      // Tiny acorn floating above each animal — celebratory cargo.
      const acorn = document.createElement("img");
      acorn.src = "/static/animals/Acorn.svg";
      acorn.alt = "";
      acorn.style.cssText = `
        position: absolute;
        height: 24px;
        bottom: 80px;
        left: -120px;
        transform: translateX(0);
        transition: transform 4.0s linear;
      `;
      stage.appendChild(acorn);
      setTimeout(() => {
        acorn.style.transform = `translateX(${distance}px)`;
      }, delay + 60);  // acorn slightly offset for layered movement
    });

    setTimeout(() => {
      stage.style.transition = "opacity 0.4s ease";
      stage.style.opacity = "0";
      setTimeout(() => { stage.remove(); paradeRunning = false; }, 500);
    }, 5000);
  }

  // Public hook so card.js can fire after a successful promote.
  window.fireParade = fireParade;

  // ---------------------------------------------------------------------------
  // Konami code — ↑ ↑ ↓ ↓ ← → ← → B A
  // ---------------------------------------------------------------------------
  const KONAMI = ["ArrowUp","ArrowUp","ArrowDown","ArrowDown","ArrowLeft","ArrowRight","ArrowLeft","ArrowRight","KeyB","KeyA"];
  let kIdx = 0;
  document.addEventListener("keydown", (e) => {
    if (e.code === KONAMI[kIdx]) {
      kIdx++;
      if (kIdx === KONAMI.length) {
        kIdx = 0;
        bearStomp();
      }
    } else {
      kIdx = (e.code === KONAMI[0]) ? 1 : 0;
    }
  });

  function bearStomp() {
    if (reduceMotion) return;
    const bear = document.createElement("img");
    bear.src = "/static/animals/Bear.svg";
    bear.alt = "";
    bear.style.cssText = `
      position: fixed;
      bottom: 24px;
      left: -180px;
      height: 160px;
      z-index: 9999;
      pointer-events: none;
      transition: transform 3.5s cubic-bezier(.5,0,.5,1);
      filter: drop-shadow(0 6px 12px rgba(0,0,0,0.3));
    `;
    document.body.appendChild(bear);
    requestAnimationFrame(() => {
      bear.style.transform = `translateX(${window.innerWidth + 240}px)`;
    });
    setTimeout(() => bear.remove(), 4000);
  }

  // ---------------------------------------------------------------------------
  // 5 quick clicks on the brand <h1> → mini parade
  // ---------------------------------------------------------------------------
  let brandClicks = 0;
  let brandTimer = null;
  document.addEventListener("click", (e) => {
    const h1 = e.target.closest && e.target.closest("header h1");
    if (!h1) return;
    brandClicks++;
    clearTimeout(brandTimer);
    brandTimer = setTimeout(() => { brandClicks = 0; }, 2000);
    if (brandClicks >= 5) {
      brandClicks = 0;
      fireParade();
    }
  });
})();
