# Amtrak Position Engine — Conditioned Forecasting (Extension #3) — Design

**Date:** 2026-06-26 · **Status:** design, pre-build · **Package:** `tools/amtrak-position-engine/`

## 1. Problem

Today the engine, at a query time, pools **all** historical runs for the leg (anchored to scheduled departure) and reports unweighted p10/p50/p90. Every historical run counts equally — the on-time ones and the 5-hours-late ones alike. That's correct *before* you board, but wasteful once you're rolling: you already know **how late you actually are** at the stations you've passed. A run that's 90 min late at Minot should be forecast from the historical runs that were *also* ~90 min late there — not from the whole ensemble.

Conditioning on the observed delay does two things:
1. **Tightens** the uncertainty window (rules out the on-time and the disaster runs).
2. **Captures real dynamics** — if trains 90-min-late at Minot typically claw back 30 min by Spokane (or lose another hour), the forecast reflects that instead of assuming the 90 min rides along unchanged.

## 2. Core idea — kernel-weighted analog forecasting

Each historical run is a **delay trajectory** (delay at each milepost). "Now" we have an **observed delay state** (our delay at the most-recently-passed point). Weight each historical run by how closely its delay matched ours at that point, then take **weighted** percentiles forward.

This is k-nearest-analog / kernel regression in delay-space — a Bayesian-flavored update:
- **prior** = all runs (uniform weight) → today's behavior
- **likelihood** = similarity of a run's past delay to our observed delay
- **posterior** = reweighted runs → forecast from the weighted ensemble

Crucially it is a **strict superset** of the current engine: with no observation, all weights = 1 and you get exactly today's output.

## 3. Mechanics

### Observation
- `M0` = current milepost (anchor-relative). From the live feed (#2) map lat/lon → milepost; or from "last passed station".
- `D0` = current delay in minutes. From the live feed directly (`arr − schArr` at the last station), or manual.

### Weighting
For each historical run `r` on the leg:
1. Interpolate `r`'s delay at milepost `M0` → `D_hist(r)` (between its reported stations; skip/down-weight runs with no coverage near `M0`).
2. `w(r) = exp( −(D_hist(r) − D0)² / (2σ²) )`  (Gaussian kernel, bandwidth σ minutes).

Optional trend term (see Decision 1): also match the **delta** of delay over the last two passed stations, multiplying in `exp(−(Δhist − Δobs)²/(2σ_Δ²))`.

### Forecast
For the future query offset `T` (and for ETAs, each upcoming station's milepost):
- Interpolate each run's position at `T` (exactly as the engine does now) → `pos(r)`.
- Report **weighted** percentiles of `{pos(r)}` with weights `{w(r)}`.

### Adaptive bandwidth (the safety knob)
Compute effective sample size `ESS = (Σw)² / Σw²`. If `ESS < ESS_min`, widen σ and recompute until `ESS ≥ ESS_min` (or σ hits a cap, at which point it's ≈ unconditioned). This guarantees we never forecast from 3 lucky analogs.

## 4. What it unifies (graceful degradation)

| Situation | Observation | Behavior |
|---|---|---|
| Before boarding / offline, no info | none | uniform weights → **today's engine exactly** |
| Known departure delay (#3a) | `D0` at `M0≈0` | condition on early delay |
| Live mid-trip (#3b) | `M0,D0` from live feed | condition on current delay state |

One weight vector; turning it off = uniform. No separate code paths.

## 5. Integration with the existing engine

`query_position` today builds `positions` (one dict per contributing run-interpolation) and takes index-based percentiles. Changes:
- Carry a **weight** alongside each position (the run's `w(r)`).
- Replace index percentiles with a **weighted-percentile** helper.
- New optional params: `observed=(M0, D0)` and `sigma` (default adaptive). When `observed is None` → all weights 1 (unchanged).

New pieces:
- `condition_weights(leg_runs, frame, M0, D0, sigma) -> {run_idx: weight}`
- `weighted_percentile(values_with_weights, p) -> value`
- `eta_to(frame_station_milepost, leg_runs, weights) -> p10/p50/p90 clock times`  *(see Decision 2)*

CLI:
- `now` already pulls the live delay + position (#2) → feed it as `observed` → conditioned forecast for future times.
- `--delay 90` / `--at "MOT +90"` manual override for when you know your delay without live signal.
- An ETA mode: `position_engine.py eta ABQ` → "you'll reach Albuquerque ~p10/p50/p90 clock time."

## 6. Validation (extends `backtest_engine.py`)

Leave-one-run-out, but now **two-stage**: for each held-out run, pick an observation point `M0` (= a milepost it actually passed) with that run's real delay `D0`; condition on the *other* runs; forecast the held-out run's position at later offsets; compare to its actual.

Measure, as a function of how far into the trip the observation is taken:
- conditioned MAE vs unconditioned MAE (expect conditioned ≤ unconditioned, gap widening the further you've traveled),
- window width (expect tighter),
- coverage stays ≥ ~0.75,
- ESS never below floor.

**Acceptance:** conditioned beats or matches unconditioned on MAE at every observation distance, coverage holds, ESS floor respected.

## 7. Open decisions (resolve before building)

1. **Conditioning signal** — current-delay-only (simplest, robust; delays are highly autocorrelated) **[recommended]** vs add a trend term (richer; needs runs to report the same recent stations). *Could ship current-only and add trend if backtest shows it helps.*
2. **ETA-to-stations output** — build now (high value on the train, same weighted machinery) **[recommended]** vs defer.
3. **Manual override** — support `--delay`/`--at` in addition to live-auto **[recommended both]** vs live-only.
4. **σ default + ESS floor** — proposed σ≈25 min, ESS_min≈30, auto-widen. Confirm or tune via backtest.

## 8. Risks / subtleties

- **Sparse legs** (Sunset Limited, few reporting stations): the observation station may be far back / stale — the kernel + ESS floor handle it by widening toward unconditioned.
- **Delay isn't perfectly autocorrelated** (trains recover) — but that's exactly the dynamic the analog ensemble captures; don't model recovery explicitly, let the data show it.
- **Never condition on a station not yet passed.**
- **Live delay is clean** (`schArr` vs `arr` from Amtraker) — the observation comes nearly free once #2 is wired.
- **Whole-trip vs per-leg**: conditioning is per current leg; a fresh leg with no live fix starts unconditioned (or conditioned on its departure delay if known).

## 9. Build sketch (once decisions are locked)

1. `weighted_percentile` + `condition_weights` (pure functions, unit-tested).
2. Thread `observed`/`sigma` through `query_position`; weighted percentiles; keep unconditioned default identical (regression-test against current outputs).
3. Wire `now` to pass the live observation; add `--delay`/`--at` overrides.
4. ETA mode (if Decision 2 = now).
5. Extend `backtest_engine.py` with the two-stage conditioned backtest; tune σ/ESS to the acceptance bar.
6. Update README.
