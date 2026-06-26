# Amtrak Position Query Engine — Design & Architecture

## Quick start

Self-contained and offline-ready — the engine loads a pre-parsed data bundle in `data/`, so it needs only **Python 3.9+ (standard library only — no third-party packages, no network)**. (It uses stdlib `zoneinfo`, falling back to `pytz` if ever needed.)

```bash
python3 position_engine.py "2026-07-13 1:30 PM"   # predicted position + P10–P90 window
python3 position_engine.py "2026-07-13 12:30 PM" --tz US/Central   # any timezone
python3 position_engine.py now      # live position if online (Amtraker), else cached, else predicted
python3 position_engine.py "2026-07-13 8:00 PM" --at MOT --delay 90   # CONDITIONED on your real delay
python3 position_engine.py eta SPK --at MOT --delay 90   # ETA to a station (conditioned)
python3 position_engine.py --train 3   # probe ANY running train right now (live-feed test)
python3 position_engine.py test     # full July-2026 itinerary suite
python3 backtest_engine.py          # validation: unconditioned (NEW ≈ 0.66 SD) + conditioned sweep
```

- **`now`** resolves **live → cached-fix → predictor**, labelling which it used; on the train this gives a real-time position (lat/lon, speed, delay, next-stop ETA) and degrades gracefully when signal drops.
- Predicted queries report the most-likely position plus the **P10–P90 uncertainty window**, with lat/lon snapped to the actual track geometry.
- **Conditioned forecasting** (`--at <station> --delay <min>`, or auto from the live feed): reweights the historical ensemble toward runs that were as late as you are at the point you've reached. In backtest this cuts forecast error **~35%** (MAE 38→25 mi) while holding coverage. A Gaussian kernel (`--sigma`, default 25 min) auto-widens to keep enough analogs. `eta <STATION>` reports the weighted P10/P50/P90 arrival time. Design: `docs/plans/2026-06-26-amtrak-conditioned-forecasting-design.md`.

Use `query_position(date, time_ET, all_runs, all_schedules, route_sched, station_lookup, leg_shapes)` programmatically — see `main()` for the wiring.

**Files:** `position_engine.py` (engine + CLI), `live.py` (Amtraker live feed + offline cache), `backtest_engine.py` (validation), `data/` (committed bundle: `asmad_runs.json` = pre-parsed runs, `leg_shapes.json` = on-track GTFS geometry, plus the geo/schedule JSONs). The live cache (`.live_cache.json`) is gitignored.

**Refreshing data** (after new ASMAD pulls — raw HTML is NOT in git, it lives in Dropbox `letta-shared-files/amtrak-data/`):
```bash
python3 position_engine.py --build ~/Dropbox/letta-shared-files/amtrak-data
# or: AMTRAK_SRC=/path/to/raw python3 position_engine.py --build
```
This re-parses the HTML + geo JSONs into `data/`, and also downloads Amtrak's GTFS feed to rebuild `leg_shapes.json` (on-track geometry); commit the regenerated bundle. (Building needs `beautifulsoup4` + network.)

---

## Goal

Answer: **"Where will I be on July XX at HH:MM Eastern time?"** during Chad's July 2026 cross-country Amtrak trip.

The engine returns a p10/p50/p90 position estimate (latitude, longitude, milepost, nearest stations) derived from ~350 historical runs per route, anchored to the published July 2026 timetable for each leg.

---

## Data sources

| # | Source | Format | Coverage | Key fields |
|---|--------|--------|----------|-----------|
| 1 | **ASMAD full-history HTML** | `AMNN-full.html` files in `letta-shared-files/amtrak-data/` | ~350 runs per long-distance route, 2020-2026 | origin_date, station_code, scheduled_arrival_date_time, actual_arrival_comment (e.g. "Ar: 56 min late"), service_disruption flag |
| 2 | **Published timetables** (pasted by Chad) | Parsed into `/tmp/amtrak_published_timetables.json` | Full station sequence for all 6 itinerary legs | station_code, arrival_time, departure_time, timezone, city/state |
| 3 | **Transitdocs station catalog** | `/tmp/amtrak_station_catalog.json` (fetched from `https://asm-backend.transitdocs.com/stationInfo`) | 937 stations worldwide | lat, lon, timezone, city, state, alternate_codes |
| 4 | **Transitdocs route mileposts** | `/tmp/amtrak_route_mileposts.json` + `/tmp/amtrak_milepost_2.json` (fetched from `https://asm-backend.transitdocs.com/train/{date}/A/{train}`) | One daily pull per route | station_code, miles_from_origin |
| 5 | **ASMAD arrival-delay history** | `AMNN-delays.html` files in `letta-shared-files/amtrak-data/` | Destination-only arrival delays, ~2,000 runs per route | Used for delay statistics (mean/median/p90/max); not directly used in position interpolation |

### File locations

```
letta-shared-files/amtrak-data/
├── AM3-full.html              ASMAD all-stations history — Southwest Chief
├── AM2-full.html              ASMAD all-stations history — Sunset Limited
├── AM58-full.html             ASMAD all-stations history — CONO
├── AM7-full.html              ASMAD all-stations history — Empire Builder (CHI→SEA)
├── AM27-full.html             ASMAD all-stations history — Empire Builder (SPK→PDX)
├── AM11-full.html             ASMAD all-stations history — Coast Starlight
├── AM22-full.html             ASMAD all-stations history — Texas Eagle
├── AM3-delays.html            ASMAD destination-delay history — SW Chief
├── AM2-delays.html            ASMAD destination-delay history — Sunset Ltd
├── AM58-delays.html           ASMAD destination-delay history — CONO
├── AM27-delays.html           ASMAD destination-delay history — Empire Builder PDX
├── AM11-delays.html           ASMAD destination-delay history — Coast Starlight
├── AM22-delays.html           ASMAD destination-delay history — Texas Eagle
├── amtrak-disruptions-cancellations.html   ASMAD service disruption log
├── amtrak_arrival_events_1yr.csv            Full CSV of 13,836 station events
├── POSITION_ENGINE.md                       This document
└── *_files/                                 Web assets (ignored)
```

Cached artifacts in `/tmp/`:
```
/tmp/amtrak_published_timetables.json   Parsed timetables with station codes, times, timezones
/tmp/amtrak_station_catalog.json        937-station catalog with lat/lon
/tmp/amtrak_route_mileposts.json        Milepost data for routes 3, 7, 11, 22, 27, 58
/tmp/amtrak_milepost_2.json             Milepost data for route 2 (Sunset Limited)
```

---

## Itinerary (July 2026)

| Leg | Train | Dep date | Dep time | Origin | Destination | TT key | ASMAD train | Geo train |
|-----|-------|----------|----------|--------|-------------|--------|-------------|-----------|
| 1 | SW Chief 3 | Jul 6 | 1:30 PM CT | CHI | LAX | `3` | `3` | `3` |
| 2 | Sunset Ltd 2 | Jul 8 | 10:00 PM PT | LAX | NOL | `2` | `2` | `2` |
| 3 | CONO 58 | Jul 11 | 3:45 PM CT | NOL | CHI | `58` | `58` | `58` |
| 4 | Empire Builder | Jul 12 | 3:05 PM CT | CHI | PDX | `27` | `7` | `27`/`7` |
| 5 | Coast Starlight 11 | Jul 16 | 2:22 PM PT | PDX | LAX | `11` | `11` | `11` |
| 6 | TX Eagle 422 | Jul 19 | 10:00 PM PT | LAX | CHI | `422` | `22` | `22` |

Note: Empire Builder uses timetable key `27` (the published schedule for the Chicago→Portland route) but ASMAD train `7` for historical delay data, because ASMAD's full-history for train 27 only covers SPK→PDX (the post-Spokane split section). Train 7 covers CHI→SEA (full route including the shared portion).

---

## Modeling approach

### Core method: atomic historical-vector sampling with time-since-departure normalization

**Step 1 — Compute our trip's schedule timestamps.**

The published timetable gives us scheduled arrival/departure times for every station along a route. We anchor these to our specific July departure date, computing UTC timestamps for each station, accounting for timezone changes across the route. For stations past midnight, we add 86,400 × N seconds until the timestamp is after the departure.

**Step 2 — For each historical ASMAD run, normalize to hours-since-its-own-departure.**

Each ASMAD run has actual arrival times at a subset of stations (typically 6-12 out of 20-40 timetable stations). We compute:

```
offset_i = (actual_utc_i - first_station_scheduled_utc) / 3600.0
```

This gives us, for each station in each historical run, "how many hours after the train's scheduled departure did it actually arrive at this station?"

**Step 3 — Compare our query offset to the historical offset vectors.**

For a query time T, we compute `our_offset_h = (T_utc - our_departure_utc) / 3600.0`. Then for each historical run, we find the pair of consecutive stations bracketing `our_offset_h`:

```
if off_i ≤ our_offset_h ≤ off_{i+1}:
    frac = (our_offset_h - off_i) / (off_{i+1} - off_i)
```

**Step 4 — Interpolate position proportionally.**

```
lat = station_i.lat + frac × (station_{i+1}.lat - station_i.lat)
lon = station_i.lon + frac × (station_{i+1}.lon - station_i.lon)
miles = station_i.miles + frac × (station_{i+1}.miles - station_i.miles)
```

Positions from all matching historical runs are collected.

**Step 5 — Sort by milepost, take percentiles.**

The collected positions are sorted by milepost. The 10th, 50th, and 90th percentile positions are reported as the "conservative," "median," and "optimistic" scenarios respectively. P10 = train is running faster/more ahead (higher milepost for a given time); P90 = train is running slower/more behind (lower milepost).

### Why not per-station independent sampling?

If you sample the delay at station A from historical run #47 and the delay at station B from historical run #218, you get physically impossible scenarios — a train that's 2 hours late at Dodge City but on time at La Junta. The atomic-vector approach preserves the correlation structure: each historical run is a coherent physical reality where delays propagate forward through the route.

### Why normalize to hours-since-departure rather than absolute time?

ASMAD runs span 2020-2026 across different months and seasons. Normalizing to "hours since departure" removes seasonal schedule changes and makes different origin dates comparable. It also aligns with our July 2026 departure: "2.5 hours after leaving Chicago" means roughly the same segment of track regardless of whether the historical run was from January or June.

---

## Station coverage (the coarse-interpolation problem)

ASMAD only reports actual arrival times at a subset of stations per route. Between reporting stations, position is linearly interpolated over potentially large distances.

| Route | ASMAD reporting stations | Total timetable stations | Largest gap |
|-------|-------------------------|------------------------|-------------|
| SW Chief 3 | KCY, DDG, LAJ, ABQ, FLG, LAX (6) | 32 | DDG → LAJ = 202 mi, ~2.5h |
| Sunset Ltd 2 | MRC, TUS, ELP, SAS, HOS, NOL (6) | 22 | ELP → SAS = 573 mi, ~20h |
| CONO 58 | JAN, GWD, MEM, CDL, CHI (5) | 20 | MEM → CDL = ~250 mi, ~6.5h |
| Empire Builder 7 | MKE, WIN, MSP, SCD, MOT, HAV, SBY, ESM, WFH, SPK, WEN, SEA (12) | 40 | HAV → SBY = ~112 mi |
| Empire Builder 27 | PSC, PDX (2) | 6 | PSC → PDX = ~200 mi, ~5h |
| Coast Starlight 11 | PDX, SAC, EMY, OKJ, SJC, LAX (6) | 24 | PDX → SAC = ~580 mi, ~16h |
| TX Eagle 22 | FTW, DAL, LRK, STL, CHI (5) | 43 | LRK → STL = ~300 mi, ~6h |

The largest gap is ELP→SAS on Sunset Limited (~20h of travel interpolated from two endpoints). Position accuracy within that stretch is necessarily coarse — "somewhere in West Texas" rather than "approaching Sanderson."

---

## Current status

### Working queries (8 of 13 tested)

| Date | Time ET | Train | +h | n | P50 position | Nearest stations |
|------|---------|-------|----|---|-------------|------------------|
| Jul 6 | 5:00 PM | SW Chief 3 | 2.5 | 350 | 38.65, -96.34 (551 mi) | Topeka, KS → Newton, KS |
| Jul 7 | 8:00 AM | SW Chief 3 | 17.5 | 362 | 35.25, -106.47 (1320 mi) | Lamy, NM → Albuquerque, NM |
| Jul 9 | 3:00 PM | Sunset Ltd 2 | 14.0 | 154 | 31.00, -103.91 (1012 mi) | El Paso, TX → Alpine, TX |
| Jul 11 | 10:00 PM | CONO 58 | 5.2 | 347 | 35.25, -90.02 (415 mi) | Memphis, TN → Newbern, TN |
| Jul 12 | 8:00 PM | Empire Builder | 3.9 | 351 | 43.97, -91.38 (293 mi) | La Crosse, WI → Winona, MN |
| Jul 13 | 1:00 PM | Empire Builder | 20.9 | 351 | 48.43, -106.36 (1200 mi) | Wolf Point, MT → Glasgow, MT |
| Jul 16 | 8:00 PM | Coast Starlight | 2.6 | 360 | 44.34, -122.48 (296 mi) | Albany, OR → Eugene, OR |
| Jul 20 | 10:00 AM | TX Eagle 422 | 9.0 | 332 | 34.58, -92.67 (640 mi) | Little Rock area, AR |

### Gap queries (5 of 13)

These queries fall outside the ASMAD offset window for their routes:

| Query | Issue |
|-------|-------|
| Jul 8 5:00 AM ET | SW Chief +38.5h — ASMAD covers ~34.5h max. You're arriving LAX around now. |
| Jul 10 6:00 PM ET | Sunset Ltd +41.0h — ASMAD max is ~41h. Request near NOLA approach. |
| Jul 14 12:00 PM ET | Empire Builder +43.9h — train 7 data ends SPK (~34h), train 27 window is SPK→PDX (~5h). Handoff gap. |
| Jul 17 3:00 PM ET | Coast Starlight +21.6h — ASMAD maxes at ~20h for this route. |
| Jul 21 6:00 PM ET | TX Eagle +41.0h — ASMAD maxes at ~38h. Request approaching CHI. |

### Not covered

- **Hiawatha connectors** (332 MKE→CHI and 339 CHI→MKE): No ASMAD data. These are ~90-minute legs, nearly always on-time (max 17 min delay per ASMAD destination stats).
- **Off-train periods**: Hotel nights in LA (Jul 8), New Orleans (Jul 10), Portland (Jul 14-15), and LA return (Jul 17-18).

---

## Known limitations

1. **Coarse interpolation in large ASMAD station gaps.** Between reporting stations, position is linearly interpolated. Real trains don't travel at uniform speed — they gain or lose time on specific track sections. The ELP→SAS gap on Sunset Limited (~20h) is the worst case.

2. **Offset window coverage gaps for end-of-route queries.** Several routes have ASMAD data that cuts off before the destination station. This may be because ASMAD stops reporting once a train passes its last major reporting point, or because the full-history files have fewer stations than the delay files.

3. **Empire Builder split handling.** The engine uses train 7 data for the CHI→SPK portion but can't cleanly hand off to train 27 for SPK→PDX. The ASMAD offset windows don't overlap.

4. **No departure delay modeling.** The engine assumes the train departs on time (using published schedule departure). Historical departure delays aren't factored in. A train that departs 3 hours late will shift every subsequent position estimate by 3 hours.

5. **Station geo lookup fallback chain.** Position interpolation leans on lat/lon from the Transitdocs station catalog, but mileposts come from the Transitdocs route-milepost endpoint. The two data sources have slightly different station sets. The fallback chain (`get_geo()`) tries multiple keys to resolve each station code.

6. **Time-of-day no-conditioning.** Historical runs span January through December. Summer delays may differ from winter delays (track work, freight congestion, extreme weather). A season-filtered model (~90 summer runs) would have better relevance but lower precision.

---

## Improvement paths

### Short term (accessible without new data sources)

1. **Pull more ASMAD stations.** The `AMNN-delays.html` files have destination-arrival delays but may also contain intermediate station data. If the full-history files are missing the tail of each route, the delay files might fill those gaps.

2. **Add departure delay modeling.** Factor in the distribution of departure delays from ASMAD — shift all position estimates by the departure offset. This would make late queries more realistic (you probably won't be at mile 500 at +2.5h if the train left 2h late).

3. **Seasonal filtering.** Restrict ASMAD samples to June-August to improve relevance for a July trip.

4. **Better Empire Builder handoff.** Pull train 7 data for CHI→SPK and train 27 for SPK→PDX, align the SPK overlapping timestamps to bridge the gap.

### Medium term (requires new data)

5. **Amtrak GTFS data.** The official Amtrak GTFS feed has precise scheduled arrival/departure times at every station for specific dates, including service notes and schedule changes. This would eliminate the dependency on manually pasted timetable text.

6. **Live Train Status API.** Amtrak's Track Your Train Map API provides real-time position data. If accessible historically (via ASMAD or Transitdocs), this would give GPS-level position snapshots rather than station-to-station interpolation.

7. **Unified station-geometry database.** Combine the Transitdocs station catalog, route mileposts, and published timetable into a single joined table per route — one row per station with lat, lon, milepost, scheduled departure/arrival times, and timezone. This would eliminate the multi-source fallback chain.

---

## Code

The query engine is implemented as a Python script that:

1. Parses ASMAD `AMNN-full.html` files into `{origin_date → {station_code → {sch_ts, delay, act_ts}}}`
2. Parses published timetable text into station sequences with times and timezones
3. Loads station lat/lon from the Transitdocs catalog
4. Loads mileposts from the Transitdocs route endpoint
5. For each query, normalizes to hours-since-departure, samples historical runs, interpolates positions, and reports percentiles

The engine is `position_engine.py` (runs on stock Python 3.9+ with `beautifulsoup4`+`pytz`). Data artifacts are **persisted in `letta-shared-files/amtrak-data/`** (`amtrak_route_mileposts.json`, `amtrak_milepost_2.json`, `amtrak_station_catalog.json`, `amtrak_published_timetables.json`), with `/tmp/` as fallback. The validation harness is `backtest_engine.py`.

---

## Corrections & validation (2026-06-25)

A leave-one-run-out backtest (`backtest_engine.py`) — predict each historical run's milepost at its reported station times using all *other* runs, compare to the station's true milepost — surfaced that the original offset normalization put the query and the history on **different clocks**:

| method | n | bias | MAE | SDpos | **MAE/SD** | coverage(p10–p90) |
|--------|---|------|-----|-------|--------|----------|
| original (`act − first_reported_sch`) | 12,746 | +194 mi | **205 mi** | 75 | **2.74** | 0.10 |
| corrected (`sched_elapsed_from_anchor + delay`) | 13,636 | +10 mi | **31 mi** | 51 | **0.61** | 0.61 |

The original engine was **~205 mi off on average (2.74 SD)** — e.g. SW Chief "+2.5h" reported Kansas (mile 551) when the train is really near Galesburg, IL (~145 mi). Three coupled bugs:

1. **Wrong offset baseline** — offsets were relative to each run's *first ASMAD-reported station* (KCY for train 3, +7.4h), while the query offset is relative to *origin departure*. Fix: normalize to **scheduled-elapsed-from-anchor + measured delay**, where the anchor is the first station in *both* our timetable and the ASMAD route.
2. **Timezone distortion** — `parse_sch_ts` used `timegm` (local-as-UTC); the query side localized correctly. Fix: the corrected offset uses tz-correct **absolute epochs** from `route_mileposts`.
3. **Multi-day schedule mis-dating** — `compute_schedule` only handled one midnight wrap, mis-dating late stations on 2-day legs (and causing spurious end-of-route "NOT ON TRAIN"). Fix: enforce **monotonic UTC** along the route. (This recovered 3 of the original 5 "gap queries".)

Plus: an **origin anchor** `(offset 0, mile 0)` restores coverage before the first reported station (added only for a leg's first-segment train); **off-branch stations are dropped** by intersecting with our timetable (fixes the Empire Builder → Seattle leak); and milepost is reported **anchor-relative**. The p10/p50/p90 are ascending-by-milepost (p10 = furthest behind / slowest, p90 = furthest ahead / fastest) — the *opposite* labelling from the older "Modeling approach §5" prose above.

### Multi-source legs (2026-06-26) — both former gaps now closed with EXISTING data
Two legs are each covered by more than one ASMAD train, chained at a join station (`LEG_SOURCES`), with mileposts made continuous across the join:

- **Empire Builder** = train **7** (CHI→Spokane) + train **27** (Spokane→Pasco→PDX). Train 27 reports only PSC + PDX, but that anchors the Portland branch. *Bug found en route:* Sandpoint, **Idaho was missing from the timezone map** → defaulted to Central, fell *before* Libby in UTC, and the monotonic-wrap guard added a spurious day that pushed PDX to +70h. Fixed with `ID → America/Los_Angeles`. *Second bug:* the mile-0 origin anchor, added to every run, made sparse train-27 runs (PSC/PDX only) interpolate a 2026-mi straight chord CHI→Pasco through South Dakota; fixed by adding the anchor only for a leg's **first-segment** train.
- **Texas Eagle leg** = Sunset Limited train **2** (LAX→SAS — the 422 through-cars ride train 2; timetables are byte-identical LAX→SAS) + train **22** (SAS→CHI). No `AM422` ASMAD history exists or is needed.

**All 13 trip test queries now resolve** with schedule-consistent positions (0 "NOT ON TRAIN"), and the leave-one-out backtest still validates at **0.61 SD**.

### Supplementary delay history (2026-06-26) — Spokane→Pasco now bridged
`AM27-delay2.html` is a per-station delay history (~1,867 runs) merged into train 27 by origin_date (`DELAY_FILES`, union of stations per run). It adds the WIH/BNG/VAN Columbia-Gorge intermediates and — critically — **23 runs that report both Spokane and Pasco**, which bridge the otherwise non-stop SPK→PSC segment with real end-to-end delays. That stretch now resolves instead of returning "NOT ON TRAIN".

Because SPK→PSC is **non-stop** (no scheduled station between them) and train 7's data funnels everything through Spokane, the estimate inside that ~150-mi segment is necessarily coarse (Spokane→Pasco corridor) — but it's the best ASMAD can give, and there are no further reporting points to extract. **This is the limit of the available ASMAD data.** With the larger pool the leave-one-out backtest holds at **0.66 SD** (n=16,834; bias 7.7 mi). Every other point across all six legs is covered by real history.

---

## CSV export

A full CSV of all 13,836 ASMAD station events is available at:

`letta-shared-files/amtrak-data/amtrak_arrival_events_1yr.csv`

Columns: `train, name, origin_date, station_code, station_city, station_state, scheduled_arrival_utc, actual_arrival_utc, delay_min, latitude, longitude, miles`
