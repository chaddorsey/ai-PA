# Amtrak Companion — Plan Review Findings (CE adversarial/feasibility pass)

**Date:** 2026‑06‑28 · Reviewers: compound‑engineering feasibility, adversarial‑document, coherence, scope‑guardian (4 parallel agents over the design spec + Plans 1–4). "Convergence" = how many independent reviewers flagged it (higher = higher confidence).

> Overall: the plans are unusually well‑structured (TDD, locked contracts, honest device‑vs‑unit test split). The problems are concentrated at **platform‑contact points** and **cross‑plan seams** the plans hadn't validated. Fix these before executing.

---

## CRITICAL — fix before any code

### CR1. iOS cannot play OGG/Opus (convergence: feasibility)
AVFoundation has no OGG demuxer; `AVPlayer`/`AVAudioPlayer` reject `.opus`/`.ogg` (err ‑11828). The whole pipeline + player is built on Opus. **Fix:** render **MP3** from Chirp3‑HD (`audioConfig.audioEncoding = MP3`, one‑param change in Plan 1 T3) — plays natively everywhere on iOS; or remux to Opus‑in‑CAF. Update Plan 1 audio ext, the `audio` field, Plan 3 player, design §8.

### CR2. Bundle schema is contradictory AND missing core data (convergence: ALL 4)
Plan 2 types `Bundle.leg: string` with no stations/geometry/schedule; Plan 4 reads `bundle.leg.stations / .geometry / .schedule_offset_min`. **The bundle contains no station list and no route polyline** — yet the map, station pins, ETAs, approach cues, and itinerary all need them. **Fix:** reconcile in one place — add `stations[]`, `geometry` (the leg_shape polyline), `schedule_offset_min` as top‑level `Bundle` fields; Plan 1 `build_bundle` emits them; Plan 2 type + validator enforce; delete Plan 4's `as {…}` casts; keep `leg` a string id.

### CR3. Salience scale mismatch breaks the highlight filter (convergence: ALL 4)
Plan 2 types `salience: 1|2|3|4|5` (validator rejects outside; `highlightOnly` = `salience>=4`); Plan 4 fixtures use 0–1 floats. Either the validator rejects every unit or `highlightOnly` becomes a no‑op. **Fix:** pin to integer 1–5 (matches the engine/narration), fix Plan 4 fixtures + threshold.

### CR4. Built for ONE trip on ONE date, shipped to other users on other dates (convergence: adversarial)
`position_table`, ETA P10/50/90, and "on‑time/late" all read a table baked from the July‑2026 itinerary as ground truth; nothing regenerates it per trip, and the user's real departure time is never sourced. **Decision needed (see below):** make `position_table` a per‑trip artifact regenerated from schedule at trip‑load, OR demote it to a clearly‑labeled "estimated/scheduled" fallback that GPS overrides and that does NOT drive a confident on‑time claim.

### CR5. Phase‑2 scope built at Phase 1 (convergence: scope‑guardian) — this SHRINKS the build
Per design §7, these are Phase 2/3 but fully built now: Live Activity/Dynamic Island (Plan 3 T5), the live‑dive flow + FocusingDialog + FocusQuestions (Plan 4 T9/T11), `diveGrounding` (Plan 2 T7). **Fix:** cut to Phase 2; keep only the cheap JS interface stubs + the data‑model fields (`Favorite.dive`, `attachDive`). Net: less Phase‑1 work.

---

## IMPORTANT

### IM1. `/usr/bin/unzip` via `Process()` doesn't exist on iOS (convergence: ALL 4)
Plan 3 T4 BundleStore. **Fix:** ZIPFoundation / Apple `Compression`, or ship unzipped per‑file.

### IM2. `BundleStore.path()` sync cold‑start bug (convergence: 3)
Sync `path()` is cached only after `download()` ran this session → throws on a normal offline relaunch (the core on‑train scenario). `list()` is also declared sync but implemented async. **Fix:** make `path()`/`list()` async; prime from disk on boot; update the contract.

### IM3. Position ladder ignores stopped / reversed / off‑route / jitter (convergence: adversarial)
Dead‑reckons *forward* through station dwells (narrates scenery miles ahead while stopped); flips direction on one jittered fix; snaps wrong‑leg/pre‑boarding positions onto the route; no smoothing. **Fix:** stopped‑state (hold milepost when speed≈0), N‑fix direction debounce, `offtrack_mi` rejection threshold + "can't locate you" state, dead‑reckon age cap; add harness scenarios asserting *no* spurious squib fires.

### IM4. Background‑suspend → resume drops content (convergence: adversarial)
Hours backgrounded → huge dead‑reckon leap; re‑entry test asserts a tautology. **Fix:** re‑acquire GPS before ticking the scheduler on resume; cap dead‑reckon age; real re‑entry assertion.

### IM5. Audio ducking by session‑deactivation churns/strobes (convergence: 2)
Deactivating the session on every ≥2s gap fights the background‑audio assertion and pulses the user's own music up/down on sparse narration. **Fix:** keep the session active for the whole journey; modulate ducking only; `setActive(false,…)` only on a real full stop. Re‑verify on device with music playing across a full leg.

### IM6. ETA P10–P90 is fake precision (convergence: adversarial)
±5% of a deterministic lookup, presented as a statistical band; dangerous for the "can you step off?" decision. **Decision needed:** source real historical variance and widen honestly, OR drop the band and label "scheduled/estimated."

### IM7. Cross‑plan API signature mismatches (convergence: coherence) — the parallel‑drafting cost
A batch the contract was meant to prevent but the drafters drifted on: `Favorites.add` arg order; `fillPct` (Plan 2) vs `defaultFill` (Plan 4); `EtaResult` minutes vs absolute‑ms; `Eta.toStation` 1‑arg vs 2‑arg; `loadBundle` 1‑arg vs 2‑arg; `Favorite`/`DiveCard` defined twice; `AudioSession.pause/resume` sync vs async; leg id `"58"` vs `"leg58"`; `DiveService` never defined; `orchestrator` singleton vs class. **Fix:** one contract‑reconciliation pass — Plan 2 (+ Plan 3 for plugins) is the producer of record; rewrite Plan 4's consumer signatures to match verbatim.

### IM8. Offline map tiles unscoped + bundling OSM violates policy (convergence: 3)
No task generates/sizes/licenses corridor tiles; bundling raster OSM tiles breaks the OSM tile‑usage policy. **Fix:** ship a single corridor **PMTiles (Protomaps, commercial‑OK, ODbL attribution)** via MapLibre's `pmtiles` protocol; add a pipeline task to extract it; far smaller than loose PNGs.

### IM9. Bundle size budget unclosed (convergence: feasibility)
MP3 corpus ≈0.6–2.4 GB + tiles (hundreds of MB) + images; consecutive legs may need 3–6 resident → 2–4 GB plausible. **Fix:** state a budget, emit real per‑leg MB in `INDEX.json`, add download‑management UX (size display + eviction) in Settings.

### IM10. Dive backend + TTS terms for distribution (convergence: feasibility) — Phase 2
Home LiteLLM isn't a shippable backend for other users; on‑demand dive‑TTS edges toward Google's prohibited "competing TTS service." **Fix (Phase 2):** a small hosted dive endpoint with a defined contract; use ElevenLabs (perpetual commercial redistribution on paid tiers) for dive TTS; keep Google strictly for pre‑rendered narration content.

### IM11. Location entitlement strategy (convergence: feasibility)
Background‑location + background‑audio + "Always" is App‑Review‑risky and the denied path is untraced. **Fix:** prefer When‑In‑Use + background‑audio (audio keeps the app alive during a session); design the denied → predicted‑fallback UI; request "Always" only if truly needed.

### IM12. Front‑load a device tracer bullet (convergence: adversarial)
Proxy‑first correctly defers the render *cost* but also defers all *device‑integration risk* (background GPS + audio coexistence, ducking, OTA, MP3 playback, unzip) to the end — where the architecture's core premise is finally tested. **Fix:** a throwaway device spike FIRST — background GPS + looping MP3 playback + duck Apple Music + survive 30‑min screen‑lock + a call interruption — before committing the full build order.

---

## MINOR (fix in passing)
- **Voice lock:** render a *full leg* in the final voice and listen end‑to‑end before the full corpus + before locking the voice (a voice change re‑renders & re‑downloads everything). (adversarial)
- **Pronunciation "guarantee":** reframe as "reviewed for the launch corpus"; add a regression set of known tricky local readings (Cairo‑IL, Versailles‑KY, Pierre‑SD…); generalization needs an auto/crowd path before any "guarantee" copy. (adversarial)
- **G2P tier** (Plan 1 T2): unnamed lib + outputs ARPABET not IPA + below the 0.8 trust gate anyway → cut it or name `gruut`/`phonemizer`. (scope)
- **Sunrise/sunset:** replace the hand‑rolled formula (NaN at solstice, no DST) with `suncalc`. (feasibility/adversarial/scope)
- **OTA:** `setServerBasePath` isn't stable Capacitor‑6 API → use `@capawesome/capacitor-live-update`. (scope)
- **`+page.svelte` (Trip home) assembly** not explicitly tasked in Plan 4 → add it. (scope)
- **`orchestrator` singleton** expected by tests but exported as a class; **`ApproachCue`** module‑level state is test‑fragile. (scope)
- **Live Activity 8h limit** when it returns in Phase 2. (feasibility)
- **`projectToLeg` `side`**: Python returns `ahead`; contract is `L|R` — define a deadband/`null` for on‑track. (feasibility)

---

## Decisions needed from the user
1. **CR4 — per‑trip data:** regenerate `position_table`/schedule per trip at load, OR demote to a labeled "estimated" fallback (GPS overrides; no confident on‑time claim)?
2. **IM6 — ETA band:** source real historical variance, OR drop the P10/P90 band and show a single "scheduled/estimated" time?
3. Go‑ahead to **revise the plans** for all CRITICALs + IMPORTANTs (contract reconciliation, MP3, schema unification, scope cuts to Phase 2, position robustness, PMTiles, etc.) and add the **device tracer bullet as the new first step**?

## Recommended remediation order
0. Device tracer bullet (IM12) — prove the premise on a real device.
1. Reconcile the bundle schema (CR2) + salience (CR3) + the API seams (IM7) → one corrected contract.
2. MP3 (CR1), PMTiles (IM8), iOS unzip (IM1), async path (IM2).
3. Cut Phase‑2 scope (CR5).
4. Position robustness (IM3/IM4), ducking (IM5).
5. Decide CR4 + IM6, then update Plans 1/2/4 accordingly.
