# Train Tracking & Stop‑Time Prediction — Capability Synopsis

**Date:** 2026‑06‑28 · **Role:** second input to the app brainstorm (alongside the app design/data‑contract spec and implementation plan) · **Package:** `tools/amtrak-position-engine/`

**In one line.** A position‑and‑timing engine that answers *"where is / will the train be, and when does it reach the upcoming stops?"* — fusing ~3,800 historical runs, the live feed, and the published timetable, all projected onto on‑track geometry. It is the layer the narration backbone already rides on, and a reusable capability in its own right.

---

## 1. Data foundation
- **ASMAD full‑history** — **3,781 historical runs across 7 routes** (Southwest Chief, Sunset, City of New Orleans, Empire Builder, Cardinal/7, Coast Starlight, Texas Eagle), each a per‑station record of *scheduled vs. actual* times, lateness, and service‑disruption flags → `asmad_runs.json`. This is the statistical backbone.
- **Published timetables** — full station sequences with times and time zones per leg → `amtrak_published_timetables.json`.
- **Station catalog** — **937 stations** with lat/lon, timezone, codes (Transitdocs) → `amtrak_station_catalog.json`.
- **Route mileposts + on‑track geometry** — GTFS shape polylines as `[mile, lat, lon]` (`leg_shapes.json`) + milepost references; this defines the anchor‑relative **milepost ↔ lat/lon** axis everything keys to.
- **Live feed** — real‑time position / speed / delay via the **Amtraker v3** community API (`api-v3.amtraker.com/v3/trains`), with a last‑fix cache for graceful degradation.

Runtime is **stdlib‑only and offline‑capable** (the live feed is optional; everything else is precomputed and committed).

## 2. What it computes
1. **Predicted position** — `query_position(date, time_ET, …)` → most‑likely milepost + lat/lon + **P10–P90 uncertainty window**. Method: *atomic historical‑vector sampling with time‑since‑departure normalization* — for the queried elapsed time, sample where each historical run actually was at that same point in its journey, forming a distribution rather than a point guess.
2. **Conditioned forecasting** — given a known delay at a station already passed (`--at STATION --delay MIN`, or read automatically from the live feed), reweight the historical ensemble toward runs that were *similarly late at that same point* (Gaussian kernel, default σ≈25 min, auto‑widening to keep enough analogs). Cuts forecast error **~35% (MAE 38→25 mi)** while holding coverage.
3. **Live position** — `now` resolves **live → cached‑fix → predictor**, labeling which source it used; real‑time on the train, graceful when signal drops.
4. **ETAs to upcoming stops / points** — `eta_to(station)` and `eta_to_mile(milepost)` → conditioned **P10/P50/P90 arrival times** to any station or arbitrary milepost.
5. **Geometry projection** — `_milepost_latlon(mile)→lat/lon` and `project_to_leg(lat,lon)→(mile, offtrack_mi, side)`. The second is how a live GPS or feed fix becomes a milepost; both are pure, ~50 lines, portable to any client.

## 3. Accuracy & validation
- **Backtest harness** (`backtest_engine.py`) leaves runs out and scores **MAE** (accuracy) against **SDpos** (the inherent cross‑run spread at that time); the bar is **MAE/SDpos < 1.0** (agree within one SD).
- **Unconditioned ≈ 0.66 SD** — predictions land well inside the natural spread.
- **Conditioned ≈ 35% MAE reduction** once a real delay is known, with coverage preserved.

## 4. The capability surface (questions it can answer)
- *Where am I right now?* / *Where will I be at time T?* (with uncertainty)
- *When do we reach station X / milepost M?* — P10/P50/P90
- *How late are we, and how does that delay propagate to the downstream stops?*
- *How long is the dwell / how much time at the next stop?* (from timetable + position)
- *How confident is any of the above?* (the P‑window is first‑class, not hidden)

## 5. Current scope & limits
- Parsed for the **6‑leg July‑2026 itinerary** (7 ASMAD routes loaded); the method **generalizes** to any route that has ASMAD history + a timetable + a shape.
- Predictions are **statistical**, grounded in history + current delay — not a real‑time operational schedule API; they shine exactly where a schedule API is silent (between stations, and on *how a delay will play out*).
- Live feed depends on Amtraker (community‑run, can fail) → the cache + predictor are the fallback chain.
- Time handling is timezone‑correct (legs cross several zones).

## 6. Hooks into the app brainstorm
This engine is more than the narration trigger — it's a timing brain the app can surface directly:
- **Narration pacing** — position drives the always‑on track; *delay awareness* can re‑pace it ("we're running 40 late; here's what that shifts").
- **Proactive stop & sight cues** — "Raton in ~22 min (P50), ~18–27 (P10–P90)"; advance alerts before scenic stretches via `eta_to_mile`.
- **At‑station utility** — predicted dwell / "≈15 min off the train here," fresh‑air‑stop countdowns, board‑again warnings.
- **Trip‑level planning** — downstream‑stop arrival spreads, connection feasibility, "will we make the X?" framing under uncertainty.
- **Confidence as a feature** — show the P‑window, not a false‑precise single time.
- **Reusable service** — the same engine feeds the audio app, the KML/3D renderers, and any "where/when" query, online or offline.

**Files:** `position_engine.py` (engine + CLI), `live.py` (Amtraker + cache), `backtest_engine.py` (validation), `data/` (committed bundle: `asmad_runs.json`, timetables, station catalog, mileposts, `leg_shapes.json`). Design detail in `tools/amtrak-position-engine/README.md` and `docs/plans/2026-06-26-amtrak-conditioned-forecasting-design.md`.
