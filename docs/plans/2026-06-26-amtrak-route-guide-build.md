# Amtrak Route-Guide Layer — Build Doc (Enhancement #2, the keystone)

**Date:** 2026-06-26 · **Status:** scoped, pre-build · **Package:** `tools/amtrak-position-engine/`
**Why this first:** #2 is the spine that the KML tour (#3b-lite), the Cesium 3D fly-ahead (#3b-full), and the iPhone/AR app (#3a) all render on. Build the milepost↔lat/lon↔feature contract well once; everything else becomes a front-end.

---

## 1. Goal

Given a position (live or predicted) on a leg, answer:
- **"What's around me now?"** — towns, water, terrain, structures, parks, scenic sights near the current milepost, with which **window to look out**.
- **"What's coming?"** — the same, ahead, with **ETAs** (reusing `eta_to`) and **advance alerts** before notable/scenic stretches.

It must be **offline-capable** (precomputed, shipped in the bundle, stdlib-only runtime) and **additive** (no change to the existing engine's outputs).

## 2. Design principles

1. **One contract.** Every feature is keyed to the leg's **anchor-relative milepost** — the same axis the engine and `eta_to` already use. That single projection is what makes the guide compose with prediction and with every downstream renderer.
2. **Build heavy, run light.** All fetching/GIS/elevation work happens at `--build` time → a compact committed `data/route_guide.json`. Runtime reads JSON only.
3. **Editorial + automated, merged.** Curated highlights (high quality, low volume) and automated features (OSM/elevation/places, high volume) land in the *same* schema, distinguished by `source`.
4. **Direction-aware.** Features are authored as plain geography; projecting them onto each leg's *directed* polyline yields per-leg milepost ranges and **left/right side** correctly (opposite directions flip side automatically).
5. **Graceful + extensible.** Missing sources degrade (fewer features), never break. New feature kinds are new `kind` values, not new code paths.

## 3. The data model (THE contract)

`data/route_guide.json` — keyed by timetable leg key (`'3'`, `'2'`, `'58'`, `'27'`, `'11'`, `'422'`):

```jsonc
{
  "3": {
    "leg_miles": 2265,                  // total anchor-relative length (sanity/scale)
    "features": [
      {
        "id": "raton-pass",             // stable slug (dedupe / cross-reference)
        "name": "Raton Pass",
        "kind": "pass",                 // see enum below
        "class": "natural",             // natural | engineering | place | protected | scenic | station
        "from_mi": 1180.0,              // anchor-relative milepost SPAN (point ⇒ from==to)
        "to_mi": 1210.0,
        "peak_mi": 1195.0,              // the salient moment within the span (summit/bridge center/closest approach)
        "lat": 36.99, "lon": -104.43,   // representative point (at peak_mi)
        "side": "both",                 // left | right | both | ahead   (out which window)
        "elev_ft": 7834,                // optional
        "salience": 5,                  // 1–5 — drives alert thresholds & label priority
        "blurb": "Highest point on the route; 2% grades and sweeping high-desert views.",
        "source": "curated",            // curated | osm | gtfs | geonames | elevation | nps
        "tags": ["scenic", "mountain", "grade"]
      }
    ]
  }
}
```

**`kind` enum (open, grouped by `class`):**
- *natural:* `river`, `lake`, `bay`, `pass`, `summit`, `canyon`, `gorge`, `desert`, `forest`, `plain`, `coast`, `grade`, `region`
- *engineering:* `bridge`, `tunnel`, `loop`, `viaduct`, `trestle`, `wye`
- *place:* `town`, `city`
- *protected:* `national_park`, `national_forest`, `monument`, `wildlife_refuge`, `state_park`
- *scenic:* `viewpoint`, `landmark`, `look_note`
- *station:* `station` (mirrors the engine frame, so the guide is self-contained)

**Why spans + `peak_mi`:** points (bridge, town, summit) set `from==to==peak`; spans (a desert, a park, a long climb) carry the range you're *in it*, plus the one milepost worth announcing. Alerts fire on `peak_mi`; "you are in X" uses the span.

**Invariants** (validated at build): `from_mi ≤ peak_mi ≤ to_mi`; `lat/lon` is the point at `peak_mi`; `salience ∈ 1..5`; `id` unique within a leg; features sorted by `peak_mi`.

## 4. Milepost projection (reuse the engine)

The leg polyline already exists as `leg_shapes[tt] = [[mile, lat, lon], ...]` (anchor-relative miles, on-track). Two helpers formalize the contract:

```python
def project_to_leg(poly, lat, lon) -> (mile, offtrack_mi, side_hint)
    # nearest point on the polyline (segment projection, not just vertex);
    # returns its milepost, the perpendicular distance, and L/R from the
    # local heading × bearing-to-feature cross product.

def span_on_leg(poly, geometry) -> (from_mi, to_mi, peak_mi)
    # for a line/polygon (river, park): entry/exit mileposts where it meets
    # the corridor; peak = closest approach (or centroid for polygons).
```

`offtrack_mi` lets us keep distant-but-visible features (a mountain range 20 mi off) with an honest "visible from mi X–Y" and drop noise. `side` is computed here, at build time, and stored.

## 5. Data sources

| Source | Gives | Access | Notes |
|---|---|---|---|
| **Engine frame** | stations | have it | `kind:station`, free |
| **Curated YAML** (per corridor) | marquee scenic sights, "look left/right" notes, named regions | hand/LLM-authored | highest editorial value; where the soul is |
| **OpenStreetMap** (along the polyline) | `railway=tunnel`/`bridge`, waterway crossings (named rivers), notable loops | free (Overpass / extract) | query a buffer around the leg polyline |
| **Elevation (DEM)** | grade, passes, summits, "highest point", canyons | USGS 3DEP / SRTM, free | sample every ~0.25 mi along the polyline; detect local maxima + steep grade runs |
| **GeoNames** | populated places near route | free dump/API | filter by distance-to-polyline + population → salience |
| **NPS / USFS boundaries** | national parks/forests/monuments the route enters | free GIS | polygon → span via `span_on_leg` |
| **Ecoregions (EPA L3) / curated** | deserts, plains, named ranges | free / curated | coarse `region`/`desert`/`plain` spans |

All processed at build time. Licensing: OSM (ODbL — attribution), GeoNames (CC-BY), NPS/USGS/EPA (public domain). Attribution string carried in the bundle.

## 6. Build pipeline (`build_route_guide`)

Runs inside `--build` (online), after `leg_shapes` exist. Per leg:

1. Load the leg polyline (`leg_shapes[tt]`) and station frame.
2. For each source: fetch geometry → `project_to_leg`/`span_on_leg` → feature dicts (with `source`).
3. **Curated YAML**: parse `guides/<corridor>.yml`, geocode any name-only entries, project, merge. Curated `salience`/`blurb` win on conflict.
4. **Dedupe** by proximity + name/id (a river named in both OSM and curated → one feature, curated text).
5. **Salience defaults** per kind (park=5, named pass/major river=4, tunnel/bridge=3, town by pop, region=2) unless curated overrides.
6. Sort by `peak_mi`, validate invariants, write `data/route_guide.json`.

Compact target: a few hundred KB per leg (cap town count by population; cap elevation features to local extrema). Raw OSM/DEM never committed — only the distilled features.

## 7. Runtime API (`route_guide.py`, stdlib-only)

```python
load_guide() -> dict                      # data/route_guide.json (or {})
features_for(leg) -> list                 # sorted by peak_mi

around(leg, mile, radius_mi=15, min_salience=1) -> list
    # features whose span overlaps [mile-radius, mile+radius] OR peak within radius;
    # each annotated with: rel = peak_mi - mile (− behind / + ahead), side, dist_mi.

lookahead(ctx, leg, mile, observed=None, horizon_min=120, min_salience=2) -> list
    # upcoming features (peak_mi > mile) within the time horizon; each gets an ETA
    # via eta_to(ctx, <nearest station to peak>, observed)  →  weighted P50 + window,
    # OR a direct milepost-time interpolation when no station is adjacent.

alerts(ctx, leg, mile, observed=None, within_min=30, min_salience=4) -> list
    # high-salience features arriving within `within_min`, for proactive notices.

current_context(leg, mile) -> dict        # spans you're inside now (in this park / desert / on this bridge)
```

ETA note: `eta_to` is station-keyed today; add a thin `eta_to_mile(ctx, leg, target_mi, observed)` (same machinery, target a milepost instead of a station code) so features ETA precisely rather than snapping to the nearest station.

## 8. CLI surface

```bash
position_engine.py around                 # what's around me now (live mile → features, with side)
position_engine.py lookahead [--horizon 120] [--min-salience 2]
position_engine.py guide <leg>            # whole route guide for a leg (planning / printout)
position_engine.py alerts                 # high-salience things arriving soon
# all accept the conditioning flags (--at/--delay) and fall back to predicted mile offline
```
Output: grouped "Now / Next 30 min / Next 2 hours," each line `mile · ETA (P50, window) · side · name — blurb`.

## 9. Downstream-renderer contract (why this is the backbone)

Everything downstream consumes **`route_guide.json` + `leg_shapes` + `eta_to_mile`** — nothing re-derived:
- **KML tour (#3b-lite):** each feature → a `<Placemark>` at `(lat,lon)`; the polyline → a `<gx:Tour>` that flies along it and pauses/annotates at `salience≥4` features. Pure transform of the contract.
- **Cesium 3D (#3b-full):** features → billboards/labels; camera path = polyline; "fly ahead" = advance the camera by predicted milepost. Same inputs.
- **iPhone/AR (#3a):** query `around(leg, mile)` by the phone's GPS; AR overlay uses each feature's `lat/lon` + `side` + bearing. Same inputs.

**Stability guarantee:** the schema in §3 and the helpers in §4/§7 are the frozen interface. Downstream builds depend on those, not on internals.

## 10. Validation & QA

- **Coverage:** features per leg; flag stretches > ~40 mi with nothing `salience≥3` (gap to curate).
- **Landmark spot-checks:** known sights land at the right milepost & side — Raton Pass (SW Chief), the Mississippi River crossing (CONO), Glacier NP + Marias Pass (Empire Builder), the Cascades/Columbia Gorge (Empire Builder→PDX), the Pacific coast run (Coast Starlight).
- **Side correctness:** a handful of known "look left/right" sights checked against computed `side`.
- **Invariant tests:** schema invariants (§3) enforced in build + a unit test.
- **Editorial pass:** the curated YAML is the human QA — read each route's highlights end to end.

## 11. Phasing (each phase ships usable value into the same artifact)

- **Phase A — Backbone + curated guide.** Schema, `project_to_leg`/`span_on_leg`, `eta_to_mile`, the runtime API + CLI, and a **curated YAML per corridor** (stations + marquee scenic highlights + named regions). *This alone is a genuinely good companion and freezes the contract.*
- **Phase B — Automated natural/engineering.** OSM tunnels/bridges/water crossings; elevation-derived passes/summits/grades/canyons.
- **Phase C — Places + protected + biomes.** GeoNames towns; NPS/USFS spans; ecoregion deserts/plains.
- **Phase D — Polish.** Side-of-train everywhere, salience tuning, optional LLM narration over `around`/`lookahead`.

Recommend building **Phase A end-to-end first** (proves the contract + runtime + CLI with real, hand-quality data), then layering B/C/D into the same `route_guide.json`.

## 12. File layout

```
tools/amtrak-position-engine/
  route_guide.py            # runtime API (around/lookahead/alerts/current_context)
  build_route_guide.py      # build-time source fetch + projection + merge (or fold into --build)
  guides/                   # curated YAML, one per corridor (editorial source, git-tracked)
    southwest-chief.yml  sunset-limited.yml  city-of-new-orleans.yml
    empire-builder.yml   coast-starlight.yml  texas-eagle.yml
  data/route_guide.json     # committed, compiled artifact (offline runtime input)
```
`eta_to_mile` lands in `position_engine.py` (beside `eta_to`); `project_to_leg`/`span_on_leg` beside `_milepost_latlon`.

## 13. Open decisions (resolve at Phase A kickoff)

1. **Keying** — per-leg (`tt_key`, matches today) vs per-corridor reusable. *Rec:* author curated YAML per corridor (direction-agnostic), compile to per-leg `route_guide.json`. Best of both.
2. **ETA snapping** — build `eta_to_mile` now (precise) vs reuse station `eta_to` (coarser). *Rec:* `eta_to_mile` now; it's small and the renderers want it.
3. **Off-track visibility radius** — how far off the line a feature can be and still listed (e.g., a distant range). *Rec:* default 25 mi for `salience≥4`, 8 mi otherwise; tune in QA.
4. **Curated authoring** — hand-write vs LLM-draft-then-review the YAML. *Rec:* LLM-draft per route from public route guides, human edit; it's the editorial backbone, worth the pass.
5. **Town volume** — population cutoff for `geonames` towns. *Rec:* keep ≥2k pop within 8 mi, plus any named place the route is named-after; cap per leg.
