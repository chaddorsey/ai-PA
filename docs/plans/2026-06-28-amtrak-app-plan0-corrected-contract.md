# Amtrak Companion — Plan 0: Corrected Contract & Pre‑Flight (Remediation)

> **For agentic workers:** This document is the **source of truth** produced by the 2026‑06‑28 CE review remediation. Where Plans 1–4 contain inline types, signatures, audio formats, or scope that conflict with this doc, **Plan 0 governs.** Build Task 0 first. Findings rationale: `2026-06-28-amtrak-app-plan-review-findings.md`.

**Goal:** Lock the corrected cross‑plan contract and decisions before execution, and prove the device premise with a tracer bullet.

---

## Task 0 (NEW FIRST STEP): Device tracer bullet — prove the hybrid premise
A throwaway iOS build (not production code) that demonstrates, on a **real device**, all of:
- [ ] Background **CoreLocation** fixes continue with the **screen locked** (log fixes for 30 min).
- [ ] **AVAudioPlayer** loops an **MP3** with `UIBackgroundModes: audio` — audio continues screen‑locked/backgrounded.
- [ ] `AVAudioSession.playback + .duckOthers` **ducks Apple Music**, then restores it (no app restart).
- [ ] Survives a **30‑min screen‑lock** still playing + still receiving location.
- [ ] Survives a **phone‑call interruption** and resumes.
**Acceptance:** all five observed on device. **If any fail, STOP** — the "hybrid is required and sufficient" premise needs rework before building Plans 1–4.

---

## Corrected contract (governs)

### A. Audio format — MP3 (was OGG_OPUS)
iOS/AVFoundation cannot play OGG/Opus. Render Chirp3‑HD with `audioConfig.audioEncoding = "MP3"`; files are `.mp3`; played by `AVAudioPlayer`. (Plan 1 T3/T5, Plan 3 T3, design §8.) **Render endpoint: `/v1beta1/text:synthesize`** — `customPronunciations` is rejected by `v1`; nest it as `input.customPronunciations.pronunciations[]` (confirmed live, Plan 1 T3). If bandwidth ever demands Opus, remux to **Opus‑in‑CAF** in the pipeline — never ship `.ogg`.

### B. Bundle schema (per leg `bundle.json`) — adds stations, geometry, timing provenance, real ETA
```jsonc
{
  "leg": "3",                                   // string id (NOT an object)
  "schedule_basis": {                            // NEW — timing provenance + honesty
    "kind": "trip-actual" | "generic-scheduled",
    "valid_dates": ["2026-07-12"]                // trip-actual only; [] for generic
  },
  "stations": [                                  // NEW — needed by map pins, station cards, ETA, itinerary
    {"code":"RAT","name":"Raton","mile":1087.0,"lat":36.9,"lon":-104.4,
     "sched_arr":"2026-07-12T15:42:00-06:00","sched_dep":"...","dwell_min":4}
  ],
  "geometry": {"type":"LineString","coordinates":[[lon,lat], ...]},  // NEW — the leg_shape polyline (map route)
  "units": [
    {"id":"u123","kind":"squib"|"interstitial",
     "mile":1087.2,                              // squib
     "from_mi":1080.0,"to_mi":1095.0,            // interstitial
     "place":"Morley, Colorado","side":"L"|"R"|"both"|null,
     "salience":4,                               // INTEGER 1–5
     "theme":"railroad-history","text":"...","lat":37.1,"lon":-104.5,
     "poi_lat":37.2,"poi_lon":-104.4,"offtrack_mi":0.8,
     "audio":"audio/<hash>.mp3","dur_s":42.5}
  ],
  "layers": {"guide":{},"lore":{},"science":{},"connections":{},"themes":{}},
  "position_table": [[elapsed_min, mile, lat, lon], ...],
  "eta_table": [                                  // NEW — real engine ensemble (trip-actual only; omit/[] for generic)
    {"station_code":"RAT","p10_min":138,"p50_min":151,"p90_min":167}
  ]
}
```
`INDEX.json`: `{ "legs":[ {"leg","audio_mb","units","version","basis":"trip-actual"|"generic-scheduled"} ] }`.
Producer = Plan 1 `build_bundle` (must emit stations from the station catalog, geometry from `leg_shapes`, `eta_table` from the engine ensemble, `schedule_basis`). Validator (Plan 1 + Plan 2) enforces all fields. **Delete Plan 4's `bundle.leg as {…}` casts** — read `bundle.stations` / `bundle.geometry` / `bundle.schedule_basis`.

### C. Salience — integer 1–5 everywhere
Validator rejects outside 1–5; `highlightOnly` keeps `salience >= 4`. Fix all Plan 4 fixtures (no 0–1 floats).

### D. Timing strategy — hybrid (A for our legs, B otherwise) + live override
Priority order in the app:
1. **Live feed (Amtraker), when online** — real position + delay for the actual train; overrides all, any user/leg.
2. **`trip-actual` baked table + `eta_table`** — confident source **only when** `schedule_basis.kind=="trip-actual"` **AND today ∈ `valid_dates`**. → accurate ETA + honest P10/P50/P90 band + real on‑time/late. (Our six July legs.)
3. **B fallback** — GPS‑primary position; offline timing shown as **"estimated"** from the generic schedule; **no confident on‑time** without live data; ETA shown as a single labeled time, no band.
A **date‑match guard** drops even our legs to B if ridden off their `valid_dates`. The generalized runtime per‑train schedule‑fetch service is **deferred** (the seam — `generic-scheduled` path + the strategy — is built; the general modeling is not).

### E. Companion‑core API (Plan 2 = producer of record; reconciled)
```ts
loadBundle(legId: string, resolvePath: (legId: string) => Promise<unknown>): Promise<Bundle>
projection.milepostToLatLon(leg, mile): {lat, lon}
projection.projectToLeg(leg, lat, lon): {mile, offtrackMi, side: 'L'|'R'|'ahead'}   // 'ahead' = within deadband
type Position = {mile, lat, lon, source:'live'|'gps'|'deadreckon'|'predicted', direction:1|-1, leg, stopped:boolean}
PositionService:
  onFix(lat, lon, ts, speed?): void
  setDeparture(epochMs): void                    // app supplies actual departure
  tick(nowMs): Position
  current(): Position
  // ROBUSTNESS (required): speed≈0 ⇒ stopped=true, HOLD milepost (no forward dead-reckon);
  //   flip direction only after N consecutive consistent fixes; reject fixes with offtrackMi > threshold
  //   (emit 'off-route' state); cap dead-reckon age (after T min no GPS ⇒ stop advancing, mark 'predicted');
  //   on resume, re-acquire GPS before ticking the scheduler; smooth jitter (EMA / min-displacement gate).
Scheduler(bundle, settings: {fillPct: number /*0–1*/, themes: Set<string>, highlightOnly: boolean}):
  select(position: Position): {nowPlaying: Unit|null, queue: Unit[], silenceUntilMile: number}
Eta(bundle):
  toMile(mile: number, position: Position): EtaResult
  toStation(code: string, position: Position): EtaResult
  // EtaResult = {p10:number, p50:number, p90:number, estimated:boolean}  — ABSOLUTE epoch-ms.
  //   trip-actual ⇒ real ensemble from eta_table, estimated:false; else p10===p50===p90 (single time), estimated:true.
Favorites(adapter):
  add(unit: Unit, leg: string, position: Position, kind: 'star'|'tellmore', note?: string): Promise<Favorite>
  list(): Promise<Favorite[]> ; get(id): Promise<Favorite> ; attachDive(id, dive: DiveCard): Promise<void>
// Canonical Favorite + DiveCard types live in companion-core; Plan 4 IMPORTS them (no local redefinition).
diveGrounding(...)  // Phase 2 — type only; impl deferred
```
Settings field is **`fillPct`** (Plan 4 renames `defaultFill`→`fillPct`). `silenceUntilMile` sentinel `-Infinity` = no active silence (documented).

### F. Native plugin interfaces (Plan 3 = producer; async corrected)
```ts
BackgroundLocation.watch(cb:(fix:{lat,lon,ts,speed})=>void): Promise<string> ; clear(handle): Promise<void>
AudioSession.play(fileUri:string, opts:{duckOthers:boolean}): Promise<void>
AudioSession.pause(): Promise<void> ; resume(): Promise<void> ; setRate(r:number): Promise<void>
AudioSession.addListener('ended'|'interrupt', cb): {remove():void}
  // session stays ACTIVE for the whole journey; modulate ducking only; setActive(false, .notifyOthersOnDeactivation)
  // ONLY on a real full stop (user silence/quit), never between units/gaps.
BundleStore.download(legId:string, url:string): Promise<void>
BundleStore.getPath(legId:string): Promise<string>     // ASYNC (was sync path()); resolves from disk
BundleStore.list(): Promise<string[]>                   // ASYNC; prime any cache from disk on boot
  // Unzip with ZIPFoundation / Apple Compression — NOT Process()/`/usr/bin/unzip` (unavailable on iOS).
LiveActivity.*  // Phase 2 — ship a JS stub only in the beta
```
Plan 4 consumers: `await BundleStore.getPath(legId)`; `await audioSession.pause()/resume()`; treat `pause/resume/setRate` as async.

### G. Map — corridor PMTiles (Protomaps), not bundled OSM raster
A single corridor **PMTiles** file (commercial‑OK, ODbL "© OpenStreetMap contributors"), rendered by MapLibre via the `pmtiles` protocol. Add a pipeline task (Plan 1) to `pmtiles extract` the corridor bbox. (Bundling `tile.openstreetmap.org` raster violates the OSM tile policy.)

---

## Scope cuts → Phase 2 (keep JS stubs + data‑model fields only)
- **Live Activity / Dynamic Island** Swift + Widget Extension (Plan 3 T5) → Phase 2. Keep `LiveActivity` JS stub.
- **Live‑dive flow**: FocusingDialog, FocusQuestions, `DiveService`, `diveGrounding` impl, DiveCard rendering (Plan 4 T9/T11, Plan 2 T7) → Phase 2. Keep `Favorite.dive`/`attachDive` data model + a "no dive yet (online)" SavedItem state.
- **Dive backend + dive‑TTS** → Phase 2 (hosted endpoint contract; ElevenLabs for dive TTS — Google strictly for pre‑rendered narration content).

## Minor corrections (apply in passing)
- Sunrise/sunset: use **`suncalc`** (not the hand‑rolled formula).
- **Cut the G2P tier** in the pronunciation pipeline (below the 0.8 trust gate; outputs ARPABET not IPA) — or name `gruut`/`phonemizer` and convert. Default: cut.
- **Leg‑id format**: use the bundle's real ids (numeric strings like `"3"`,`"58"`); Plan 4 `LEG_ORDER`/fixtures must match (no `"leg58"`).
- **OTA**: use `@capawesome/capacitor-live-update` (not the speculative `setServerBasePath`).
- `orchestrator` exported as a singleton via context; `ApproachCue` as a class (no module‑level state).
- Plan 4: add an explicit **Trip home `+page.svelte` assembly** task and a **bundle‑init / first‑run (no bundle → "Download your trip")** task.
- Pronunciation: reframe copy as **"reviewed for the launch corpus"** (not a blanket guarantee); add a regression fixture set of tricky local readings (Cairo‑IL, Versailles‑KY, Pierre‑SD…).
- **Bundle size budget**: emit real per‑leg MB in `INDEX.json`; add Settings download‑manager (size display + eviction).
- **Location entitlement**: prefer When‑In‑Use + background‑audio; design the denied→predicted‑fallback path; request "Always" only if needed.
- **Voice lock**: render a **full leg** in the final voice and listen end‑to‑end before the full corpus (a voice change re‑renders/re‑downloads everything; add a `voice_version` to bundle/INDEX so a swap forces clean re‑download).

---

## Per‑plan deltas (what each plan must change)
- **Plan 1:** audio→MP3; emit `stations`/`geometry`/`schedule_basis`/`eta_table`/`voice_version` into bundles; add **PMTiles corridor extract** task; cut/justify the G2P tier; validator covers the new fields + per‑leg MB; keep proxy‑first; full render still last.
- **Plan 2:** adopt the corrected `Bundle` type (new fields, salience int, `leg:string`); `loadBundle(legId, resolvePath)`; `PositionService` robustness (stopped/direction‑debounce/off‑route/age‑cap/resume/smoothing) + `setDeparture`; `Eta` returns absolute‑ms `EtaResult{…,estimated}` from `eta_table`/strategy; `Favorites.add(unit, leg, position, kind, note?)`; canonical `Favorite`/`DiveCard`; `diveGrounding` type‑only (impl Phase 2); add the **timing‑strategy** module (live>trip‑actual>generic).
- **Plan 3:** AVAudioPlayer + **MP3**; session **stays active**, duck‑modulate only; `BundleStore` async `getPath`/`list` + **ZIPFoundation** unzip + boot‑prime; `pause/resume/setRate` async; **cut Live Activity to Phase 2** (JS stub kept); OTA via `@capawesome/capacitor-live-update`; location entitlement strategy.
- **Plan 4:** read `bundle.stations`/`bundle.geometry`/`bundle.schedule_basis` (drop casts); salience int fixtures; `fillPct`; `await` async plugin calls + `getPath`; **PMTiles** map source + the P10–P90 band via `milepostToLatLon`; import canonical `Favorite`/`DiveCard`; **cut T9/T11 (dives) to Phase 2**; add **Trip home assembly** + **bundle‑init/first‑run** tasks; `suncalc`; singleton `orchestrator`; class `ApproachCue`; leg‑id format.

## Corrected build order
**Task 0 (tracer bullet)** → Plan 1 (proxy bundle, corrected schema/MP3/PMTiles) → Plan 2 (corrected core + timing strategy) → Plan 4 (UI, beta scope) ∥ Plan 3 (shell, beta scope) → device integration → **Plan 1 full render last** (voice locked via a full‑leg listen first).
