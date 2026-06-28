# Amtrak Route Guide → App — Implementation Plan

**Date:** 2026-06-28 · **Status:** 🟡 **DRAFT for review** (planned without live dialogue — default choices are made and flagged, not silently guessed) · **Package under test:** `tools/amtrak-position-engine/`

> **Source spec:** `docs/plans/2026-06-28-amtrak-app-design-and-data-contract.md` (read it first; this plan assumes its §1–§5).
>
> **For agentic workers:** REQUIRED SUB-SKILL once approved — use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement task-by-task. P1 tasks use checkbox (`- [ ]`) syntax for tracking. **Do not** modify the engine or any file under `tools/amtrak-position-engine/data/` — the bundle is a frozen read-only contract.

**Goal.** Ship a position-aware, offline-first audio rail-travel guide that plays the committed 2,900-unit narration as the train moves, with on-demand modes (What's that? / Say More / Why) and fill/highlight/theme controls — built as one more **renderer over the milepost contract** (the spec's framing; `kml_tour.py` already proves it).

---

## 0. Decisions needing the product owner's confirmation (read this first)

These are the choices a human should confirm or redirect **before** building. My recommendation + rationale for each is in §1; here is the short list of what genuinely needs you.

1. **Platform = native iOS (SwiftUI), single target, iOS 17+.** The spec leans this way; I am defaulting to it. *Confirm* you do not also need an Android/PWA build in the first release — that flips the whole stack (§1.1). **This is the highest-leverage decision; everything below assumes Swift.**
2. **Offline LLM for arbitrary Say-More/Why (P3) — defer the on-device model; ship pre-generated cards (P2) + online-only live generation first.** I recommend *not* committing to a quantized on-device model until P1/P2 prove demand. *Confirm* you are OK with "live follow-ups require signal OR are limited to pre-gen cards offline" for the first shippable app (§1.3).
3. **Audio strategy = synthesize on device with AVSpeechSynthesizer at runtime (no pre-rendered audio in the bundle) for P1–P3; revisit pre-rendered audio in P4.** *Confirm* you accept Apple's neural system voices for v1 rather than a premium cloud voice (ElevenLabs/OpenAI), which would require pre-rendering ~2,900 clips and a much larger per-leg download (§1.2, §1.4).
4. **Trip model = ship the 6 fixed July-2026 legs as the only "trip"; user picks the active leg manually (with an auto-suggest from date + GPS).** No general Amtrak trip-builder, no live train-number lookup in v1. *Confirm* this matches intent (the data only exists for these 6 legs) (§1.6).
5. **A pre-generation step is required before P2** to produce the offline Say-More/Why cards from `route_connections` + `route_themes` (+ `timeline.yml`). *Confirm* this build-time job (Sonnet, same pipeline as narration) is in scope and who runs it — the *app* never calls Sonnet at runtime (§1.3, §5).
6. **One open data gap to accept or fix:** `timeline.yml` is referenced by the contract (§3.5) but is **not** in `data/` — it lives in the generation pipeline. For P3 live generation it must be exported into the bundle, or Why-cards drop the "contemporaneity" edges. *Decide:* export it, or scope it out of v1 (§3 note).

Everything else (TTS-on-device, port-the-projection, GPS↔predictor blend, pre-fetch) I consider safe defaults and have decided in §1 — flagged but not blocking.

---

## 1. Resolving the open decisions (spec §4)

Each item: **recommendation** + one-paragraph rationale. Defaults follow the spec's leanings (iOS-native first) unless noted.

### 1.1 Platform — **native iOS (SwiftUI), iOS 17+** ✅ default
Native iOS wins on every hard requirement this app has: reliable background GPS without cell signal, on-device TTS (`AVSpeechSynthesizer`) that is free and offline, robust local file storage for the bundle, and a clean path to on-device LLM (Core ML / MLX) later. A PWA cannot get dependable background location or background audio on iOS, and offline storage of a ~3.5 MB bundle + audio is awkward. The spec already names the iPhone/AR aim. **Caveat for the PO:** this is single-platform; if Android matters for v1, reconsider a Flutter/React-Native shell — but that trades away the on-device LLM and TTS quality story. I recommend iOS-first, port later if validated.

### 1.2 TTS — **on-device `AVSpeechSynthesizer`, runtime synthesis, user-variable rate** ✅ default
On-device TTS is offline, free, and the modern Apple neural voices are good enough for a companion track. Critically, **reading rate is a first-class input to the fill math** (`read_seconds = words / (TTS_wpm)`), and runtime synthesis lets the user drag a rate slider and have the time-budget recompute live — impossible with pre-rendered clips without re-rendering. Voice selection = expose installed `AVSpeechSynthesisVoice`s (let the user download a premium system voice in iOS Settings). **Flag:** if the PO wants a signature premium narrator voice (ElevenLabs-class), that forces the pre-rendered-audio path (§1.4) and a build-time render job — defer to P4.

### 1.3 On-device / offline LLM for Say-More/Why — **defer; pre-generate cards (build time) + online-only live generation** ⚠️ flagged
The runtime model is a *separate, smaller* pick from the Sonnet author, and choosing/shipping a quantized model is a real cost with uncertain payoff before we know users even use these modes. Recommendation: **(a)** at build time, pre-generate the top-N Say-More/Why expansions per high-salience POI (Sonnet, reusing the narration pipeline + the same `route_connections`/`themes` grounding) and ship them in the bundle — these cover the offline 80%; **(b)** for arbitrary follow-ups, generate live via the hub LiteLLM **only when connected**; **(c)** revisit an on-device quantized model (MLX, e.g. a 3–4B instruct model) in P3 *only if* logs show users hitting "no pre-gen card + no signal." This keeps the app's grounding identical either way (spec §3.5) so there is no hallucination regardless of which path serves a card.

### 1.4 Offline bundle + audio — **ship text (synthesize on device); per-leg download; no pre-rendered audio in v1** ✅ default
Ship `route_narration.json` (~2.7 MB) + the supporting layers (each ~0.2–0.7 MB) + pre-gen cards as a **per-leg** download, and synthesize audio on device. Per-leg keeps each download to roughly: narration slice + that leg's `leg_shapes` polyline (the big one — `leg_shapes.json` is 1.2 MB across 6 legs) + the leg's slices of guide/lore/science/connections/themes ≈ 1–2 MB per leg. Pre-rendered audio would be instant-start and enable premium voices but multiplies bundle size by ~10× and freezes the rate slider — defer to P4 behind a "download high-quality audio" toggle. **Bundle packaging decision (default):** split each artifact into per-leg files at build time so the client never parses the whole multi-leg JSON; download lazily, verify with a manifest checksum.

### 1.5 Position blending (GPS ↔ predictor) — **reuse the engine's live → cached-fix → predicted ladder, ported to Swift; GPS is primary on the train** ✅ default
The engine already specifies the right degradation ladder (live feed → cached fix → predictor). On the train, **GPS hardware works without cell signal**, so live GPS → `project_to_leg` → milepost is the primary source and is fully offline. The predictor (clock-time → milepost) is the fallback when GPS is unavailable (tunnels, dead sensor) or for a pre-trip preview. Blend rule: trust GPS when `offtrack_mi` is small and accuracy is good; fall back to the predicted milepost (advanced by elapsed clock time) and snap back to GPS when it returns. The Amtraker live *train* feed (`live.py`) is an online nicety for delay-conditioning, not required for playback.

### 1.6 Trip / train selection + multi-leg — **fixed 6-leg itinerary; manual active-leg pick with date+GPS auto-suggest** ⚠️ flagged
The data exists for exactly these six legs, so v1 is not a general Amtrak app. Model the trip as an ordered list of the six legs with their July-2026 dates; the app auto-suggests the active leg from today's date and the nearest polyline (GPS `project_to_leg` across all six → smallest `offtrack_mi`), and the user can override. No live train-number entry, no arbitrary-route support in v1. **Flag:** if the PO wants this to generalize to any Amtrak trip, that is a different (much larger) product and a different data pipeline.

### 1.7 Audio caching / pre-fetch — **synthesize the next K units ahead of position into an in-memory/disk audio queue** ✅ default
Because we synthesize on device, "pre-fetch" means *pre-synthesize*: maintain a small look-ahead queue (e.g. the next 2–3 scheduled units) rendered to PCM/AAC just ahead of the trigger milepost so playback starts the moment we reach the cue (the spec's "small lookahead so TTS starts a touch early"). This is cheap with `AVSpeechSynthesizer`'s buffer API and needs no network. If P4 adds pre-rendered audio, the same queue abstraction streams files instead of synth buffers.

---

## 2. App architecture

### 2.1 The contract the client consumes (from spec §3, verified against the data)

Confirmed by inspecting `data/`:
- `route_narration.json` = `{ "<legKey>": [unit, …] }`, 6 legs, **2,900 units** (1,535 squibs + 1,365 interstitials — note: the spec's appendix said 1,612/1,288; the **actual** split is 1,535/1,365). Salience 1–5 distribution: `{5:200, 4:577, 3:1090, 2:856, 1:177}`.
- **squib** keys: `kind, mile, place, side, salience, theme, text, lat, lon` + (for 1,293 of 1,535 named-POI squibs) `poi_lat, poi_lon, offtrack_mi`. **242 squibs have no `poi_lat`** — the client must treat POI coords as optional and fall back to the on-track `lat/lon`.
- **interstitial** keys: `kind, from_mi, to_mi, salience, theme, text, lat, lon`.
- `theme` is a free-text thesis handle (e.g. `"The Persistent Corridor"`) **or compound** (`"The Persistent Corridor / Ghosts on the Land"`) **or null** — the theme filter must match on substring/membership, not equality.
- `leg_shapes.json` = `{ "<legKey>": [[mile, lat, lon], …] }`, ascending mile, ~7,500 pts/leg. Element order is **[mile, lat, lon]**.
- `route_connections.json` = `{ "<legKey>": { "nodes": {poiId: {…}}, "categories": [...] } }` — Say-More/Why grounding.
- `route_themes.json` = `{ "<legKey>": { "overture", "theses": [...], "movements": [...] } }` — re-entry "where we are in the story" + theme menu.
- `route_guide.json` / `route_lore.json` / `route_science.json` — map POIs, station list, profiles (P4 map + What's-that? elaboration).
- **Gap:** `timeline.yml` (contemporaneity edges for Why) is **not** in `data/` — see §0 item 6.

### 2.2 Port vs. service-call the engine — **PORT the projection math to Swift**

The two functions the app needs (`_milepost_latlon`, `project_to_leg`, plus the tiny `_project_point_seg` and a haversine) are **pure, stdlib-only, ~50 lines total**, read directly from `leg_shapes.json`, and have no third-party deps. Porting them to a small Swift `RouteProjection` type makes the app fully self-contained and offline with zero IPC — the right call for an offline-first app. Verbatim port (do not re-derive):
- `milepostToLatLon(poly, mile) -> (lat,lon)` — linear interpolation between bracketing polyline points (engine lines 313–327).
- `projectToLeg(poly, lat, lon) -> (mile, offtrackMi, side)` — nearest-segment projection; `side` from the cross product of travel-direction × feature-direction; `ahead` when `offtrack < 0.3` mi (engine lines 341–362).

The **predictor** (`query_position`, the historical-ensemble model) is *not* small and is **not** ported in v1. Instead: (a) for offline clock-time position, ship a **pre-computed per-leg position table** generated at build time by the engine (milepost vs. scheduled elapsed minutes, with P10/P50/P90), which the client reads as plain JSON and interpolates — this gives the offline predicted-milepost fallback without porting Python; (b) the live Amtraker train feed and full conditioned forecasting stay an **online service call** to the engine (P3+, optional). This keeps P1 100% Swift while preserving the degradation ladder. **Flag (PO):** confirm a build-time `position_table.json` export per leg is acceptable (small, derived, no engine port).

### 2.3 Client modules (SwiftUI + a thin Swift core)

```
AmtrakGuide/
├── Core (pure Swift, unit-testable, no UIKit)
│   ├── RouteProjection.swift      // ported milepost↔lat/lon (§2.2)
│   ├── BundleLoader.swift         // load + decode per-leg JSON, manifest/checksum
│   ├── Models.swift               // Unit (squib|interstitial), Leg, ThemeTag, ConnectionNode…
│   ├── PositionService.swift      // GPS→milepost | predicted-table fallback | blend (§1.5)
│   ├── UnitScheduler.swift        // trigger model + fill/highlight/theme selection (§2.4)
│   └── SayMoreStore.swift         // pre-gen card lookup; live-gen client (P3)
├── Audio
│   ├── TTSEngine.swift            // AVSpeechSynthesizer wrapper, rate, voice
│   └── AudioQueue.swift           // pre-synthesize-ahead queue (§1.7), AVAudioSession
├── Features (SwiftUI views/viewmodels)
│   ├── PlayerView / PlayerVM      // always-on track, fill slider, highlight, theme
│   ├── WhatsThatView (P2)
│   ├── SayMoreView / WhyView (P2/P3)
│   ├── MapView (P4)               // MapKit polyline + position + nearby POIs
│   └── TripPickerView             // active-leg selection (§1.6)
└── App
    └── DownloadManager.swift      // per-leg lazy download + cache (§1.4)
```

### 2.4 The trigger / playback model (spec §3.4) — `UnitScheduler`

The core algorithm, position-driven, recomputed as the milepost advances:
1. **Position → milepost** on the active leg (`PositionService`).
2. **Squibs:** fire the squib whose `mile` we have just reached, with a small lookahead (start TTS a few hundred meters early so audio lands at the cue).
3. **Interstitials:** between consecutive squibs, choose the subset whose `[from_mi, to_mi]` contains the current milepost such that total talk time ≈ `fill% × available_time`, where `available_time = (Δmiles / speed) ` and each unit's talk time = `words / TTS_wpm`. Greedy by descending salience until the budget is met; the rest become silence.
4. **Highlight / theme filters** narrow the candidate set *before* scheduling: highlight = `salience ≥ threshold`; theme = `theme` contains the selected thesis handle (substring match — themes are compound, §2.1).
5. **Re-entry** (returned after a gap): prefer an interstitial (carries the throughline) + a brief theme-anchored "where we are in the larger story" assembled from `route_themes` (overture/nearest movement) + recent theme-tagged units.

### 2.5 Offline-first data flow

```
build time (engine + Sonnet, NOT in app):
  route_narration.json ─┐
  leg_shapes.json ──────┤  split per-leg + checksum manifest
  guide/lore/science/   ├─►  per-leg bundle files  ─────────────► CDN / app asset
  connections/themes ───┤
  position_table.json (NEW, derived from query_position) ─┘
  saymore_cards.json   (NEW, pre-gen Sonnet, P2) ─────────┘

runtime (app, offline-capable):
  GPS ─► RouteProjection.projectToLeg ─► milepost ─┐
  (no GPS) clock ─► position_table interp ─────────┴─► PositionService
        │
        ▼
  UnitScheduler (fill/highlight/theme) ─► next units ─► TTSEngine ─► AudioQueue ─► speaker
        │
        └─ on-demand: What'sThat (squib proximity rank) | SayMore/Why (pre-gen card; live if online)
```

Network is touched only for: initial per-leg download, optional live train-delay conditioning, and optional online live Say-More/Why. **Playback, position, What's-that?, and pre-gen cards never need network.**

---

## 3. Phased plan (P1 → P4)

Phasing follows spec §5. **P1 is broken into bite-sized, individually testable tasks** with file/module, key signatures, and verification. P2–P4 are coarse.

### P1 — Read-only player (proves the contract end-to-end)
**Definition of done:** on a device (or simulator with a simulated GPX route), the app loads one leg's bundle, derives the current milepost from position, plays squibs at their mileposts with interstitial fill, and the fill slider + highlight + theme filters audibly change what plays. No on-demand modes, no map, no live generation.

> Every Core task is verified by **XCTest** against the real `data/` files (copied read-only into the test bundle — never modified). UI tasks verified by running in the simulator with a simulated route.

- [ ] **P1.1 — Project scaffold + bundle fixtures.** SwiftUI app target (iOS 17+), `AmtrakGuideCore` Swift package, and a test target. Copy the real per-leg JSON (or the whole `data/*.json` for now) into the test resources read-only.
  *Verify:* `swift test` runs (empty), app launches to a blank screen in the simulator.

- [ ] **P1.2 — `Models.swift` (decode the contract).** `enum Unit { case squib(Squib); case interstitial(Interstitial) }` decoding the real keys; `Squib` has optional `poiLat/poiLon/offtrackMi`; `theme: String?`. `Leg`, `LegKey`.
  *Signatures:* `init(from decoder:)` keyed on `kind`. *Verify:* XCTest decodes all 2,900 units from the real file with **zero** decode errors; asserts counts per leg (3→572, 2→502, 58→244, 27→560, 11→292, 422→730) and the 1,293/242 poi split.

- [ ] **P1.3 — `RouteProjection.swift` (ported math).** Port `milepostToLatLon`, `projectToLeg`, `projectPointSeg`, `haversineMi` verbatim from `position_engine.py` (§2.2).
  *Signatures:* `func milepostToLatLon(_ poly:[[Double]], _ mile:Double) -> (Double,Double)?`; `func projectToLeg(_ poly:[[Double]], _ lat:Double, _ lon:Double) -> (mile:Double, offtrackMi:Double, side:String)?`.
  *Verify:* XCTest **cross-checks against Python** — generate a fixture of ~50 `(lat,lon)→(mile,offtrack,side)` and `mile→(lat,lon)` pairs by running `python3 position_engine.py` helpers on real `leg_shapes`, assert the Swift port matches within tolerance (≤0.01 mi). This is the single most important correctness gate.

- [ ] **P1.4 — `BundleLoader.swift`.** Load + decode a leg's narration + that leg's `leg_shapes` polyline from the app's documents/asset dir.
  *Signatures:* `func loadLeg(_ key:LegKey) throws -> LoadedLeg(units:[Unit], poly:[[Double]])`.
  *Verify:* XCTest loads each of the 6 legs; units are milepost-ascending (assert ordering); poly is mile-ascending.

- [ ] **P1.5 — `PositionService.swift` (GPS only first).** `CLLocationManager` → `projectToLeg` → published `currentMile`, `side`, `offtrackMi`. Background location authorization + a simulated-route mode (Xcode GPX) for testing.
  *Signatures:* `@Published var position: TrackPosition?` where `TrackPosition = (mile, latlon, offtrackMi, source: .gps)`.
  *Verify:* run in simulator with a GPX file traced along leg-3's polyline; assert `currentMile` increases monotonically and `offtrackMi` stays small.

- [ ] **P1.6 — `UnitScheduler.swift` (squibs only).** Fire the next squib at its `mile` with a lookahead constant.
  *Signatures:* `func unitsToPlay(at mile:Double, advancing:Bool) -> [Unit]`; `let LOOKAHEAD_MI: Double`.
  *Verify:* XCTest drives a synthetic milepost sequence over leg-3; assert each squib fires exactly once, in order, slightly before its `mile`.

- [ ] **P1.7 — `TTSEngine.swift`.** `AVSpeechSynthesizer` wrapper: speak a unit's `text`, expose `rateWpm`, `voice`, and a completion callback. Configure `AVAudioSession` for background playback + ducking.
  *Signatures:* `func speak(_ text:String, completion: @escaping ()->Void)`; `var rateWpm:Int`.
  *Verify:* manual — plays audible speech in simulator; rate slider changes speed; XCTest asserts `estimatedSeconds(for:text)` math = `words/rateWpm*60`.

- [ ] **P1.8 — `AudioQueue.swift` (pre-synthesize-ahead).** Maintain a queue; pre-render the next K units; play in order; surface "now playing."
  *Signatures:* `func enqueue(_ units:[Unit])`; `let PREFETCH_COUNT:Int`. *Verify:* XCTest with a stub TTS asserts ordering, no gaps, no double-play; manual: continuous audio in simulator.

- [ ] **P1.9 — Fill budget in `UnitScheduler` (interstitials).** Add the §2.4 step-3 budget: select interstitials by descending salience until `talk ≈ fill% × available_time`.
  *Signatures:* `func scheduleSpan(fromMile:Double, toMile:Double, speedMph:Double, fillPct:Double, rateWpm:Int) -> [Unit]`.
  *Verify:* XCTest over a leg-3 span: at `fill=1.0` total talk ≈ span time; at `fill=0.3` only top-salience units selected and total talk ≈ 30%; never exceeds available time.

- [ ] **P1.10 — Highlight + theme filters.** Pre-filter candidates: `salience ≥ threshold`; `theme` substring-contains selected handle (handle compound themes, §2.1).
  *Verify:* XCTest: highlight=on yields only `salience≥4`; theme="Ghosts on the Land" yields only units whose theme contains it (incl. the compound ones).

- [ ] **P1.11 — `PlayerView` + `PlayerVM` (wire it together).** Position → scheduler → audio queue; controls: play/pause, fill slider, rate slider, highlight toggle, theme picker, "now playing" text, current milepost/place.
  *Verify:* run in simulator with the leg-3 GPX route; squibs fire near their places, fill slider audibly thins/thickens narration, theme picker restricts content. **This is the P1 end-to-end acceptance.**

- [ ] **P1.12 — Predicted-position fallback (offline, no GPS).** Read a build-time `position_table.json` (milepost vs scheduled-elapsed-min, P50) for the active leg; when GPS is unavailable, advance the milepost by clock time. (Requires the §2.2 build export — coordinate with whoever runs the engine; if not ready, stub with a constant cruise speed and flag.)
  *Signatures:* `func predictedMile(legKey:, at:Date) -> Double?`. *Verify:* XCTest with a fixture table; simulator with location disabled still advances the player.

**P1 exit criteria:** P1.3 cross-check green; P1.11 acceptance demoed; the bundle is consumed unmodified.

### P2 — On-demand modes (coarse)
- **What's that?** — rank nearby squibs by `proximity × side-match × prominence(offtrack_mi, salience, kind)` at the current milepost; answer from the squib `text` (offline). New `WhatsThatView` + a ranking function in `UnitScheduler`.
- **Pre-gen Say-More / Why cards** — build-time Sonnet job produces `saymore_cards.json` keyed by POI id + dimension/why, grounded in `route_connections` + `route_themes` (+ `timeline.yml` if exported); `SayMoreStore` looks them up offline. `SayMoreView` / `WhyView` driven by a unit's `theme` + the POI's connection node to build the menu (spec §2.3/§3.5).
- **Build task (prereq):** the pre-generation pipeline (§0 item 5) — Sonnet, top-N per high-salience POI.

### P3 — Live depth (coarse)
- **Online live generation** — `SayMoreStore` falls back to a hub LiteLLM call (when connected) for arbitrary follow-ups, sending the exact §3.5 grounding payload (anchor unit + connection node + theses + timeline events) so output matches pre-gen.
- **Optional on-device model** — only if logs justify it (§1.3): MLX-hosted small instruct model behind the same `SayMoreStore` interface; its own mini-audition (latency, quality) before adoption.
- **Live train-delay conditioning** — optional online call to the engine's conditioned forecaster to sharpen ETAs / predicted position.

### P4 — Map + polish (coarse)
- **MapView** — MapKit polyline from `leg_shapes` + live position marker + nearby POIs from `route_lore`/`route_guide`; tap a POI → What's-that?/Say-More.
- **Re-entry catch-up** UI (the §2.4 step-5 logic surfaced as a "catch me up" affordance).
- **Pre-rendered audio** option (premium voice; build-time render; DownloadManager "HQ audio" toggle; AudioQueue streams files).
- **Other renderers on the same contract** — Cesium 3D / AR, reusing `RouteProjection` + the bundle.

---

## 4. Risks & notes
- **`timeline.yml` not in the bundle** — blocks the "contemporaneity" edges of Why-cards; export it or scope out (§0.6).
- **Predictor not ported** — relies on a build-time `position_table.json` export; if that export isn't produced, the offline no-GPS fallback degrades to a constant-speed estimate (acceptable but flagged) (§2.2, P1.12).
- **Salience split mismatch** — the spec appendix (1,612/1,288) disagrees with the actual file (1,535/1,365); trust the file. Tests assert the real counts.
- **Compound/null themes** — theme filtering must be substring/membership, never equality (§2.1, P1.10).
- **242 squibs without POI coords** — POI coords are optional; fall back to on-track `lat/lon` for What's-that? ranking and map pins.
- **Background audio + location** entitlements and battery — validate on a real device early (GPS + TTS for hours is the real-world test).

---

## 5. What the app never does (guardrails)
- Never modifies `tools/amtrak-position-engine/` or its `data/` — read-only contract.
- Never calls Sonnet at runtime — Sonnet is build-time only (narration + pre-gen cards). Runtime live generation, if any, is the hub LiteLLM or an on-device model, with identical grounding.
- Never assumes network for playback, position, What's-that?, or pre-gen cards.
