# Goal Statement — Amtrak Companion App, Phase 1

**Date:** 2026‑06‑28 · **Governs:** execution of Plans 0–4 (`2026-06-28-amtrak-app-plan0-corrected-contract.md` is the contract of record). This statement defines *what success means*, *the conditions we hold to*, and *when to stop*.

---

## 1. Objective (the goal, one sentence)
Ship a robust, **offline‑first hybrid iOS travel‑companion** app — all three pillars present but thin — that runs **end‑to‑end on the July 2026 trip** with trip‑accurate timing, **degrades gracefully for other riders/dates**, and narrates the route in **premium MP3 voice with correctly‑pronounced proper nouns**.

## 2. Success metrics (Definition of Done — measurable)

**Gate A — Device premise (Task 0 tracer bullet):** all five observed on a real iPhone — background location with screen locked ≥30 min; background MP3 playback; `.duckOthers` ducks *and restores* Apple Music; survives a 30‑min screen‑lock still playing+locating; survives and resumes after a phone call. *(Binary; gates Plan 3.)*

**Audio pipeline (Plan 1):**
- Pipeline test suite green; proxy bundle (1 leg) renders MP3 and passes `validate_bundle`.
- Pronunciation: human‑confirmed overrides cover **≥95% of spoken proper‑noun occurrences** (frequency mass), risk‑ranked first; the regression fixture set (Cairo‑IL, Versailles‑KY, Pierre‑SD, Raton, Tucumcari, Purgatoire…) all pass by ear.
- Bundle size: **≤200 MB/leg** (audio+data); corridor PMTiles **≤400 MB**; a full multi‑leg trip resident **≤3 GB**.
- Full corpus render completes within **~$70 (bailout >$150)**, after the billing‑card swap and a full‑leg voice listen.

**Companion‑core (Plan 2):**
- vitest suite green; `tsc --noEmit` clean.
- Projection golden‑matches the Python engine within **0.001° / 0.01 mi**.
- Simulated‑train harness: **≥99% of squibs fire within ±0.3 mi** of their milepost on a clean run; **zero spurious fires** in the stopped / reversed / off‑route / background‑resume scenarios; fill ratio within ±10% of `fillPct`.
- Timing strategy returns a real ensemble band for `trip-actual` legs and a single `estimated:true` time otherwise; the date‑guard demotes correctly.

**Shell + plugins (Plan 3):**
- JS‑bridge unit tests green.
- Device‑verified: background location + background MP3 coexist for a full leg; burst‑ducking holds across a leg with music playing (music is *not* strobed on sparse narration); `BundleStore` downloads, and **`getPath()` resolves after an offline cold relaunch**; OTA update applies.

**Pillar UIs (Plan 4):**
- Component tests green.
- Device: corridor map renders (PMTiles) with live/predicted position + P10–P90 band + station pins; the companion track plays position‑triggered with working pause/silence/skip/★/Tell‑me‑more + fill/theme/highlight; capture (★/note/Tell‑me‑more) persists; **all four tabs work fully offline**; first‑run "Download your trip" flow works; generic (non‑trip) date shows "estimated" timing without crashing.

**End‑to‑end acceptance (the real bar):**
- **E2E‑1 (self‑run, no device):** feed leg‑58 a synthetic position track → the core emits the correct unit sequence, ETAs, and station data, fully offline. *(I verify.)*
- **E2E‑2 (on‑device):** a leg‑58 dry‑run on your iPhone — narration triggers at the right places backgrounded, ducks music, map+ETAs correct, capture works, airplane‑mode clean. *(You verify.)*
- **E2E‑3 (distribution):** a TestFlight build installs+runs on a **second device**; an off‑itinerary date degrades gracefully.

## 3. Operating conditions / constraints
- **Plan 0 governs.** Proxy‑first; **full render last** (after voice lock). MP3 only. Hybrid timing. Phase‑2 scope (Live Activity, live‑dive, strands) stays cut.
- **Verification split:** self‑testable core (Plans 1–2, JS bridges) verified by me; device behaviors (Plan 3, map/feel) verified by you.
- **Execution:** subagent‑driven, **one commit per task**, per‑task spec+quality review, fresh subagent per task.
- **Cost discipline:** only negligible per‑leg test renders until the billing card is swapped and the voice is locked via a full‑leg listen.
- **No scope creep:** anything beyond the Phase‑1 contract requires an explicit decision.

## 4. Milestone gates (go / no‑go)
| Gate | Criterion to pass | If it fails |
|---|---|---|
| **G0** | Tracer bullet (Gate A) all‑green | **Hard stop** — see bailout B1 |
| **G1** | Plan 1 proxy bundle + Plan 2 core suites green; E2E‑1 passes | fix‑forward; escalate if blocked |
| **G2** | Plan 3 + Plan 4 integrated; **E2E‑2** on device | fix‑forward; if device premise cracks → B1 |
| **G3** | Voice locked after a **full‑leg** listen (prosody + pronunciation) | B2 (voice bailout) |
| **G4** | Full corpus rendered; pronunciation ≥95% mass; sizes within budget | B3 / B4 |
| **G5** | **E2E‑3**: TestFlight on a 2nd device; generic mode graceful | resolve blocker or descope |

## 5. Exit / bailout criteria (when to stop, not push on)
- **B1 — Architecture (hard stop):** the tracer bullet fails, or G2 shows background audio+location can't coexist / ducking unworkable → **the hybrid premise is wrong.** Stop before further Plan 3/4 work; reassess approach with the user (don't thrash).
- **B2 — Voice:** no Chirp3 voice is acceptable across a *full real leg* → stop **before** the full render; revisit the engine (ElevenLabs) rather than mass‑rendering a failing voice.
- **B3 — Cost:** full‑render projection exceeds **$150** (≈2× estimate) → halt and re‑estimate before charging.
- **B4 — Pronunciation:** the risky‑name tail can't be driven to ≥95% confirmed mass within reasonable effort → stop, reassess the "reviewed pronunciation" claim and scope with the user.
- **B5 — App Store / legal:** an unresolvable feasibility blocker emerges (entitlement‑rejection risk, tile or TTS redistribution terms) → escalate the decision before continuing toward submission.
- **B6 — Schedule:** if a device‑ready Phase 1 won't make the July trip, fall back to the **trip‑critical spine** (position‑triggered narration + map/next‑stop + capture) and defer the rest — decide with the user, don't silently slip everything.
- **B7 — Per‑task:** any task **BLOCKED** after a context‑retry + model escalation → escalate to the user rather than attempt fix #4 (systematic‑debugging rule).

## 6. Out of scope (explicitly, for Phase 1)
Live Activity / Dynamic Island detail; the live‑LLM dive flow + focus questions; interest‑strand composition; the generalized runtime per‑train schedule service; Android; on‑device LLM. *(Seams are left in place; these are Phase 2/3.)*
