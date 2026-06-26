# Amtrak Position Engine — Future Enhancements (ideas + viability)

**Date:** 2026-06-26 · **Status:** ideas / planning · **Package:** `tools/amtrak-position-engine/`

Captures three enhancement directions raised after shipping the core engine (CLI, live feed, on-track geometry, conditioned forecasting). **Key framing:** all of these are *additive layers* on the foundation we already have — the GTFS route polylines, the milepost frame, `eta_to`, and the Amtraker live feed. None require a rewrite.

---

## Area 1 — Real-time as a model-improvement loop

**The idea:** use real-time data to *evaluate and improve* the model, not just display position.

### 1a. Live scoring (online, continuous)
A background job (launchd) polls Amtraker for our six lines (and optionally others — Zephyr, Cardinal — as extra training signal), runs the conditioned model for each active train, and logs **predicted vs. actual**. Over days this builds a live calibration record: rolling forecast error, bias drift, coverage. Pre-trip, it tells us whether the model is currently well-calibrated for each route.
- **Builds on:** live feed + model. Nearly free — we have both.
- **Effort:** low. **Value:** high (continuous validation; de-risks the trip).

### 1b. Backtest against historical real-time (the modeling upside)
**`github.com/piemadd/amtrak-historical-data`** archives past Amtrak GPS tracking — so we can replay real between-station movement, not just station arrivals (which is all ASMAD gives us today). Uses:
1. **Validate the on-track interpolation** against real GPS paths.
2. **Per-segment speed profiles** — derive how trains actually accelerate/slow on each track section, replacing linear-by-time interpolation between stations. Likely the single biggest position-accuracy gain in the slow, curvy gaps.
3. **Richer conditioning** — add *current speed* (and maybe recent speed trend) as a conditioning variable alongside delay.
- **Builds on:** milepost frame + conditioning machinery. Requires ingesting/aligning the GPS archive to our frame.
- **Effort:** medium. **Value:** high (real accuracy gain + better conditioning). **Viability:** confirmed — the data is public and free.

### Variations
- Log our own live feed *forward* (simplest) vs. ingest the historical archive *now* (richer, immediate).
- Continuous scoring (dashboard) vs. periodic batch evaluation.

---

## Area 2 — Surroundings brain ("what's out the window")

**The idea:** on the train, "where are we?" and "where will we be?" both want **context** — towns/stops AND geography (mountains, deserts, rivers, bridges, tunnels, scenic spots) — with **advance alerts** before notable/scenic stretches.

### 2a. Towns & stops
We already have stations + mileposts. Add a **gazetteer** (GeoNames, free) for nearby towns by position → "passing Trinidad, CO."

### 2b. Geographic / engineering / scenic features
We **already have the route polylines** (GTFS shapes), which makes this tractable — intersect them with feature sources, producing a **milepost-indexed feature list per leg**:
- **OpenStreetMap** along the rail line: `railway=tunnel`/`bridge` tags, water crossings (rivers/lakes), place names. (Free.)
- **Elevation** (SRTM/USGS) sampled along the polyline → grade, summits, passes ("climbing Raton Pass, ~7,800 ft").
- **Protected areas / biomes** — national parks & forests boundaries, desert/biome layers (free).
- **Scenic highlights** — ingest a published Amtrak route guide (they exist mile-by-mile) and/or curate a short list of marquee sights per route.

### 2c. The "brain" + lookahead alerts
Current/predicted milepost + the feature layer + **`eta_to`** (already built) → a `lookahead` view: "now / next 30 min / next 2 hours," with **timed alerts** before scenic or notable features. An LLM narration layer sits thinly on top of this data.
- **Builds on:** route polylines + `eta_to`. The feature guide can be **precomputed offline** and shipped in the data bundle (offline-friendly).
- **Effort:** medium. **Value:** highest trip-value-per-effort.
- **Variations:** static curated guide (fast, reliable) · fully-automated OSM/elevation extraction (richer) · **hybrid** (auto features + curated scenic highlights) — recommended.

---

## Area 3 — The ultimate: app + 3D fly-ahead

### 3a. iPhone app + AR
A native app using the **phone's own GPS** (exact, no feed dependency) + compass/orientation (CoreMotion) + **ARKit**: point the phone at a peak → identify it from bearing + a peaks database; overlay upcoming towns/features; tie in the predictive model for "what's coming."
- **Precedent:** PeakFinder / PeakVisor / Star Walk do exactly this (point-and-identify with an offline peak/terrain DB).
- **Effort:** high (real Swift/ARKit project). **Value:** highest "wow," longest road.
- **Variation:** ship a **non-AR SwiftUI app first** (map + lookahead + ETAs off our engine), add AR later.

### 3b. Google Earth / Maps "fly ahead"
- **Google Earth KML tour** — generate a KML of the route + current position + features + a scripted `<gx:Tour>` fly-through. Free, well-precedented, builds straight off our polyline. **Effort: low. The cheapest "wow."**
- **Web 3D (CesiumJS + Google Photorealistic 3D Tiles)** — a web app that flies the camera along the route / sits at the current position in photorealistic 3D. **Free CesiumJS client; Google 3D Tiles free tier ≈ 1,000 sessions/month (a session ≈ 3 hrs) — effectively free for personal use.** **Effort: medium** (web dev). This is the realistic path to the "fly ahead in 3D" dream.

---

## My right-now take — relative viability (value ÷ effort)

| Rank | Enhancement | Effort | Value | Notes |
|---|---|---|---|---|
| 1 | **Live model-scoring loop (1a)** | low | high | de-risks the trip; we have all the parts |
| 2 | **Route-guide feature layer + lookahead/alerts (2)** | medium | highest (trip) | polylines + `eta_to` make it tractable; offline-friendly |
| 3 | **Google Earth KML tour (3b-lite)** | low | high (wow) | an afternoon off the existing polyline |
| 4 | **Historical-GPS modeling (1b)** | medium | high (accuracy) | speed profiles; data is public & free |
| 5 | **Cesium + Google 3D web fly-ahead (3b-full)** | medium | high (wow) | viable + ~free for personal use |
| 6 | **iPhone AR app (3a)** | high | highest (wow) | moonshot; start non-AR |

**Suggested order:** 1 → 2 → 3 (KML) before the trip (real, usable value + a cheap wow), then 4 and 5 as the trip-and-after upgrades, with 6 as the long-term moonshot.

**Through-line:** items 2, 3, 5, and 6 all consume the *same* milepost↔lat/lon↔feature spine. Build that feature/route-guide layer (item 2) well once, and the KML tour, the 3D fly-ahead, and the iPhone app are all renderers on top of it.

## Sources
- Historical real-time data: https://github.com/piemadd/amtrak-historical-data · Amtraker API: https://amtraker.com/
- Google Photorealistic 3D Tiles (pricing/usage): https://developers.google.com/maps/documentation/tile/usage-and-billing · CesiumJS integration: https://cesium.com/learn/cesiumjs-learn/cesiumjs-photorealistic-3d-tiles/
- ASMAD (station-arrival archive, already used): https://juckins.net/asmad/index.php
