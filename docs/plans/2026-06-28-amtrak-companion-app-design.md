# Amtrak Companion App — Design Spec

**Date:** 2026‑06‑28 · **Status:** design approved; plans written + CE‑reviewed · **Package:** new app, building on `tools/amtrak-position-engine/`

> ⚠ **Post‑review remediation (2026‑06‑28):** the implementation contract was corrected after a CE adversarial/feasibility pass. Where this spec differs, **`2026-06-28-amtrak-app-plan0-corrected-contract.md` governs.** Key changes: audio is **MP3** (iOS can't play OGG/Opus); bundles add **stations + route geometry + `schedule_basis` + real ensemble `eta_table`**; **hybrid timing** (trip‑actual for our July legs, GPS+live+"estimated" otherwise); map uses **PMTiles**; Live Activity + live‑dive deferred to Phase 2. Findings: `2026-06-28-amtrak-app-plan-review-findings.md`.

**Relationship to existing docs.** This is the product/architecture design. It builds on three already‑written inputs: the **data‑contract spec** (`2026-06-28-amtrak-app-design-and-data-contract.md`), the first **implementation‑plan draft** (`2026-06-28-amtrak-app-implementation-plan.md` — now partly superseded by the decisions here, e.g. hybrid not pure‑native), and the **tracking/prediction synopsis** (`2026-06-28-train-tracking-prediction-synopsis.md`). The narration backbone (2,900 coordinate‑anchored units across six legs) and the position/timing engine are built.

---

## 1. Vision & scope
A **complete, offline‑capable, knowledgeable travel companion for long‑distance train travel.** Personalizable (not social). Amtrak‑specific now (the six prebuilt long‑haul legs), generalizable later. In beta. **Three pillars:**

1. **Trip & Tracking** — itinerary; past/current/upcoming train location + status; actual past stop times + scheduled/predicted upcoming; sunrise/sunset; an **interactive map** (route + position + call‑out cards).
2. **Stations** — info for selected stations + **stop lengths**.
3. **Narrative Companion** — configurable, themed, position‑triggered audio narration of the route and sights; deeper‑dive **story cards + historical images**; **on‑demand explainers**; **favoriting** with a free‑text note; a **Saved** collection; **focused live dives**; and (later) **personal interest‑strand stories**.

**Cross‑cutting requirements:** offline‑native with intermittent online sync; **highly location‑aware** (immediate "what's here now"); background/pocketed operation (screen‑off audio); **premium voice** (on‑device TTS is not acceptable for long‑haul listening); easy to update (beta); cross‑platform‑friendly for the future‑general goal.

---

## 2. Architecture — three layers
**(a) Backbone (shared, mostly built).** The committed data bundle (`route_narration` + `route_guide`/`lore`/`science`/`connections`/`themes` + `leg_shapes` + `asmad_runs`/timetables/station catalog) and the position/timing logic (predicted position, conditioned ETAs, `milepost↔lat/lon`). Packaged as **per‑leg bundles** = data + pre‑rendered premium audio.

**(b) Native shell (thin — hybrid).** **Capacitor** wrapping the web app, with native capability plugins: **background location**, **audio session** (pre‑rendered playback + nav‑style ducking + background), and **Live Activity / Dynamic Island** (deferred to polish). Provides **OTA web‑bundle updates** + per‑leg bundle download/sync + reliable large‑file storage. The small `milepost↔lat/lon` projection is ported here; the predictor ships as a precomputed **per‑time table** for the offline no‑GPS fallback.

**(c) Web app (the product — OTA‑updatable).** The three pillars as views over the backbone, plus cross‑cutting services: Position (GPS↔predictor ladder), Scheduler/Playback, Favorites/personalization store, Live‑LLM (online dives + on‑demand TTS), Sync manager, Settings.

**Online/offline split.** *Offline* = the entire core (track, map, tracking, stations, capture, re‑reading saved cards). *Online (intermittent)* = bundle download/refresh, OTA updates, live dives, premium‑TTS for dives, favorites sync.

Hybrid is required (not a pure PWA) specifically for **background location**, **background audio + ducking**, **Live Activity**, and **non‑evictable storage** — all unavailable to a pure PWA on iOS.

---

## 3. Position + audio runtime (the always‑on track)
**Position service — a labeled fallback ladder.** Native background GPS primary (works pocketed); each fix projected onto the active leg's polyline → `(milepost, off‑track, direction)`. On GPS loss: **live fix → dead‑reckon along the polyline at last speed → predicted‑position table**. Direction sets the left/right window mapping; active leg from itinerary + position.

**Scheduler.** At the current milepost, with the user's **fill % / highlight / theme** settings: fire **squibs** as we reach their `mile` (small lookahead). Between squibs, pack **interstitials** that fit the gap, chosen greedily by **salience** to hit the fill budget (`time‑to‑next‑squib × fill%`), leaving the rest as silence. Squibs are pinned "look‑now" moments; **interstitials never interrupt a squib** (fit‑or‑skip). Re‑entry after a gap resumes with a brief orientation (an interstitial + "where we are"), not a missed squib.

**Audio engine — native session, pre‑rendered files.** Each unit's Opus file plays via the native session: `.playback` + background mode; **rate via client playback‑speed** (pitch‑preserved); next unit pre‑decoded for instant trigger. **Ducking is per talking‑burst, not per unit** — other audio dips when a run begins and **swells back only during a real silence gap (≥ a few seconds)**, avoiding strobing.

**Controls.** Pause/silence (**always available**, including through station dwells — the track does **not** auto‑pause at stops), skip, ★, Tell‑me‑more. ★/Tell‑me‑more always capture the **currently‑playing unit**.

**Dynamic Island / Live Activity.** Glanceable state (current unit / next stop + ETA) + basic controls (play/pause, skip, ★, Tell me more) for pocketed use. Kept high‑level; specifics deferred.

---

## 4. Pillars — information architecture & UI
**Navigation.** Companion audio runs continuously across screens. A **persistent "now" bar** (current unit + ★ + pause) sits app‑wide; tap to expand the companion. Top‑level tabs (lean): **Trip/Map · Companion · Saved · Settings**. **Stations are contextual detail views** (from the map/itinerary or a proactive approach cue), not a browse tab. **Map/Trip is the home screen.**

**Pillar 1 — Trip & Tracking (home).** Interactive **map** (offline tiles + route polyline): live/predicted **position** (P10–P90 band when predicted), station pins, tappable **call‑out cards**. **Status strip:** on‑time/late, next‑stop predicted ETA (P50 + range), today's sunrise/sunset, "near X, mi Y." **Itinerary view:** the six legs, past/current/upcoming, each with actual past + scheduled/predicted upcoming stop times.

**Pillar 2 — Stations (contextual).** **Station card:** scheduled + predicted arrival/departure, **stop length** + "can you step off?", town/amenities/connections, a touch of lore. Surfaced from map/itinerary and **proactively on approach**. Offline.

**Pillar 3 — Companion.** **Companion view:** what's narrating (text shown) + controls (pause/silence, skip, ★, Tell me more) + **fill slider, theme filter, highlight toggle**. **Story cards:** deeper readable cards + **historical images** for marquee POIs, surfaced as you pass or browsable.

**Saved (pillar 3 deep layer).** Browse ★ / Tell‑me‑more captures → open → focusing → live dive → cached card; offline re‑read. Strands later.

**Settings:** voice, rate, default fill, **theme/interest emphasis**, per‑leg **download management**, sync.

---

## 5. Favorites → dive → strand (pillar‑3 data model)
Three **offline‑first local records** (synced when online); each snapshots its unit so later narration edits never orphan it.

**`Favorite` (capture).** From ★ or Tell‑me‑more on the currently‑playing unit. Fields: id · timestamp · leg · **unit snapshot** (kind, mile, place, theme, text) · `lat/lon` · grounding refs (`route_lore` POI id + `route_connections` node) · `kind` (**★ = light bookmark** / **Tell‑me‑more = dive‑intent, queued**) · **`note` — optional user free‑text** ("what interested you," enterable at the moment of marking, editable later, captured even offline).

**`Dive` (on‑demand, online).** Opening a saved item online runs an optional **focus step**: 1–2 questions **pre‑generated from the unit's dimensions** (offline‑capable UI) **plus the user's free‑text `note`/input**. Answer + grounding → **live LLM**, where grounding = unit text + the POI's `route_connections` bundle + `route_lore` summary/URL + `route_science` at that mile + the leg `route_themes` thesis + **deeper online sources** (linked Wikipedia/related entities). Output = a readable **deep‑dive card** (+ premium‑TTS audio when online), **cached back onto the Favorite** for offline re‑reading.

**`Strand` (later — c/d).** A named thread grouping Favorites (manual + auto‑cluster suggestions); **composed** online into a longer personalized narrative (per‑leg or whole‑trip) from its Favorites + dives + sources. Modeled now, built later.

**Flow:** listen → ★/Tell‑me‑more (+ note) → Saved → [online] focus → live dive (grounded) → cached card → [later] strands → composed story.

---

## 6. Offline storage, bundles, sync, update strategy
**Per‑leg bundle** = the leg's narration + data layers + `leg_shape` + predicted‑position table + **pre‑rendered Opus audio** (~100–150 MB/leg). Global: itinerary, station catalog, app shell, **offline map tiles** for the corridor. **Lazy per‑leg download** (+ pre‑fetch next); never all six at once.

**On device:** web/app shell (Capacitor + OTA layer); data JSON + favorites/dives/strands + settings (local store); **audio in the native filesystem** (reliable, non‑evictable); cached map tiles.

**Sync (intermittent online):** pull new/refreshed leg bundles (versioned, **delta** = changed‑unit JSON + only re‑rendered audio) and OTA app updates; push/pull single‑user favorites/dives/strands; run dives/strands via the **hub LiteLLM**.

**Update strategy — three speeds:** **web layer** (UI/logic/pillars) via **OTA** (instant, no store — the main iteration path); **content** (text/metadata) via small OTA JSON deltas, audio re‑rendered **incrementally**; **native shell + plugins** rebuilt rarely (TestFlight).

**Backend — minimal:** static/CDN hosting for versioned bundles + the OTA web bundle, the hub LiteLLM for dives, a light favorites‑sync store.

**Pre‑trip:** on wifi, download the itinerary's leg bundles (managed in Settings); on the train, all local.

---

## 7. Phasing
The trip is the beta target, and there is **comfortable time for the full Phase 1** (and likely some of Phase 2). The two **long poles start now** (slowest to get right): the **premium‑audio render** (voice audition → render legs in trip order) and the **hybrid shell + background‑location + audio‑session plugins**.

- **Phase 1 — full version A (trip‑ready, offline):** the always‑on, position‑aware, **backgrounded premium‑audio** track (pause/silence, skip, fill/theme/highlight); Pillar 1 map + live/predicted position + next‑stop ETA + itinerary/stop times + sunrise/sunset; Pillar 2 station card + stop length (proactive on approach); **capture** (★/note/Tell‑me‑more → Saved); per‑leg bundles + offline. All three pillars done properly.
- **Phase 2 — during/after trip (online‑leaning):** **Saved → focusing → live dive**, story‑card + historical‑image depth, **Dynamic Island** specifics, theme/fill tuning, sync hardening. Pull in what fits the window.
- **Phase 3 — post‑trip:** **strand composition** (c/d), fuller fleshing of all pillars, then generalization beyond Amtrak.

---

## 8. Key decisions (log)
- **Hybrid (Capacitor web + native shell)**, not pure PWA and not pure native — required for background location/audio + non‑evictable storage; keeps OTA updates + cross‑platform future.
- **Pre‑rendered premium audio** for the core track (TTS unacceptable long‑haul); **client playback‑speed** for the rate control; **per‑leg lazy Opus bundles**; on‑demand dives use the same engine when online.
- **Audio engine LOCKED: Google Chirp3‑HD** (clear prosody winner) **with `customPronunciations`** for guaranteed proper‑noun pronunciation (verified the override is honored). ~$67 full‑corpus render. The specific Chirp3 voice is finalized by ear during build (we keep listening as we go).
- **Proper‑noun pronunciation pipeline (first‑class build step):** extract every proper noun across the full narrative (place names from GNIS/lore, person names from connections, etc.) → source/curate correct IPA → store as a route pronunciation lexicon → apply via `customPronunciations` in the render step; spot‑check audio and fix any miss by editing the lexicon + re‑rendering that unit.
- **Pre‑render ops gate:** switch the GCP project to a separate billing card before the full batch render (cost isolation), since the corpus render is the first significant charge.
- **Nav‑style burst‑level audio ducking**; **track never auto‑pauses** (manual pause/silence always available).
- **Interstitials never interrupt squibs** (fit‑or‑skip); fill leaves real silence.
- **Map/Trip is home; Stations contextual; Saved its own tab; persistent now‑bar.**
- **Capture = ★ (light) / Tell‑me‑more (dive‑intent) + free‑text note**; dives online + cached back; **strands modeled now, composed later.**
- **Three‑speed updates** (OTA web/content; rare native rebuilds); **minimal backend.**

## 9. Open items / to explore
- **Voice audition — RESOLVED.** Auditioned ElevenLabs, OpenAI, Cartesia, Deepgram, Apple, and Google across many voices. **Engine = Google Chirp3‑HD + `customPronunciations`** (best prosody + verified pronunciation control + ~$67 render). Remaining: pick the specific Chirp3 voice by ear during build (Charon/Fenrir/etc.); ElevenLabs Brian/George remains a premium fallback (~$400–660) if desired later.
- **Pre‑generated Say‑More cards** — tentatively yes (likely high‑value, low‑lift); confirm during build.
- **Dynamic Island** specifics — defer until further in.
- **On‑device LLM — DISCARDED for all phases.** Dives (and any LLM use) are **online‑only**; nothing on‑device.
- **Web framework + map lib** (e.g., React/Svelte + MapLibre) and exact Capacitor plugins — settle in the implementation plan.
- **Predictor port vs. precomputed table** — confirm the table export covers the offline no‑GPS fallback adequately.
- **Backend specifics** (hosting, sync store, auth for the single user).
