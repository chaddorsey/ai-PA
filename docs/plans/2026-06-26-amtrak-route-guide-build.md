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
- *area (statistical):* `county`, `tract` — areal units that carry a `stats` payload (Phase E, §5b)

**Optional `stats` field.** Area features (and, if useful, any feature) may carry a `stats` object — a free-form key→value map (population, density, income, occupations, land-cover mix, etc.) with `source` + `vintage`. It's additive: consumers that don't know about `stats` ignore it.

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

## 5b. Statistical corridor profile — land use · demographics · occupations · socioeconomics (Phase E)

Answers the questions you actually ask out the window: *what is the land around me used for, who lives here, what do they do for a living, how is this place doing?* This is a **different kind of layer** from the scenic features — it's **areal and continuous**, not discrete points. At any milepost you're *inside* a county (and a land-cover mix); the profile changes as you cross county lines and as the land shifts from cropland to range to forest to town. It still keys to the milepost axis — modeled as **county-traversal spans** carrying a `stats` payload, plus a sampled land-cover summary per segment.

### Data model
A county traversal becomes an `area` span feature: `class: area`, `kind: county`, `from_mi`/`to_mi` = where the route enters/exits the county, low `salience` (so it never clutters scenic alerts but is always available via `current_context` / a `profile` query), with a `stats` object, e.g.:

```jsonc
"stats": {
  "geo": "Finney County, KS",
  "population": 38470, "density_per_sqmi": 35, "median_age": 31.2,
  "median_hh_income": 58200, "poverty_rate": 0.14,
  "education": { "hs_or_higher": 0.78, "ba_or_higher": 0.19 },
  "top_industries":  ["agriculture & meatpacking", "education/health", "retail"],
  "top_occupations": ["production", "farming/fishing/forestry", "service"],
  "land_cover": { "cropland": 0.58, "grassland_pasture": 0.30, "developed": 0.06, "other": 0.06 },
  "top_crops": ["corn", "winter wheat", "sorghum"],
  "source": "ACS 2023 5-yr · USGS NLCD 2021 · USDA CDL 2024", "vintage": 2023
}
```

### Sources (all free, US)
| Source | Gives | Access |
|---|---|---|
| **US Census ACS** (api.census.gov) | population, density, age, income, poverty, education, **occupation (table C24010), industry (C24030), class of worker** | free API (key) |
| **TIGER/Line** | county / tract boundary polygons (for point-in-polygon: which unit is each milepost in) | free GIS, build-time |
| **USGS NLCD** | 30 m land cover — cropland, pasture/grassland, forest, developed, water, wetland, shrub | free raster, build-time |
| **USDA Cropland Data Layer** | specific crops (corn, soy, wheat, cotton, rice…) — "what's growing" | free raster, build-time |

### Build pipeline (build-time heavy → compact artifact)
Per leg: walk the polyline; point-in-polygon against TIGER → the ordered **county sequence with entry/exit mileposts**; pull ACS stats per county; sample NLCD/CDL every ~3–5 mi within each segment → land-cover mix + dominant crops; emit `area` span features with `stats`. Only the **distilled per-county summaries** are committed (~a few hundred KB for ~250 counties across six legs); rasters and boundary files are never committed.

### Resolution choice
**County-level is the robust default** — stable (you're in it for many miles) and ACS county estimates are reliable. **Tract-level** gives finer detail near cities but ~10× the data and much larger ACS margins of error; offer it as an optional overlay for urban approaches, not the base.

### Runtime / query
`current_context` already returns the span you're inside, so a `profile` (or `where`) command surfaces it: *"Finney County, KS — ~38k people, ~35/sq mi; mostly farming & meatpacking; median HH income ~$58k; land ~58% cropland (corn, wheat, sorghum), 30% rangeland."* `lookahead` can flag the **next** county / land-use transition ("entering wheat country in ~20 min").

### Display (deferred — once the data's in)
All read the same `stats` payload: an enroute "this area" card that updates at county lines; a **choropleth overlay** in the Cesium/3D or a map layer (color counties by a chosen metric); a **land-cover ribbon** along the track; or LLM narration. Decide the surfacing after we have the data.

### Framing / sensitivity
Present Census aggregates **factually and neutrally**, always with source + vintage, and show margins of error where they're large (small counties, tracts). This is public, aggregate, place-level data answering honest travel curiosity — keep it descriptive, never editorial, and don't infer anything about individuals.

## 5c. Narrative & lore layer — interesting facts + LLM narration (Phase F)

The companion's "soul": the who / what / why of the places you pass, as **sourced color**, plus an LLM that turns it into narration. **Principle (same as everything else): facts are milepost-keyed DATA; narration is an LLM transform over the facts near you** — so it's groundable, reviewable, and offline-capable.

### Sources (all free; license noted)
| Source | Gives | Access | License |
|---|---|---|---|
| **Wikipedia REST summary** | concise lead "what's notable" for any city/county/park/river/landform | `/api/rest_v1/page/summary/<title>` | CC BY-SA |
| **Wikipedia GeoSearch** | geotagged articles near a point — finds ghost towns, historic sites, battles, landforms, not just cities | `w/api.php?list=geosearch` | CC BY-SA |
| **Wikipedia Pageviews** | popularity → rank/filter geosearch to the genuinely notable (cuts the radio-station noise) | `/metrics/pageviews/...` | CC0 |
| **Wikidata** | structured facts (named-after, founded, notable people, `instance of` for filtering) + geo queries | SPARQL / entity API | CC0 |
| **GNIS** (USGS Geographic Names) | official landform names + types (so summits/passes/streams get real names) | dump / API | public domain |
| **NRHP** (National Register of Historic Places) | historic places, lat/lon + significance | NPS GIS | public domain |
| **Wikivoyage** | travel-oriented, evocative city/region prose ("understand" sections) | API | CC BY-SA |
| **WPA American Guide Series** (1930s–40s) | richly descriptive period *route tours* of exactly these places | archive.org (OCR text) | public domain |
| **Historical Marker Database (HMdb)** | roadside-marker texts — dense local history/color | site (check ToS) | community |

Don't reproduce copyrighted travel writing or Amtrak's own guide text — reference only. Keep excerpts short, attribute CC BY-SA sources, and **ground narration in the sourced facts** (no free-floating hallucination).

### Derivation → a facts layer (`route_lore.json`)
Kept as a **sibling file** so the lean `route_guide.json` stays geometry/stats and the verbose text loads on demand; keyed by feature id / milepost:
1. **Annotate existing features** — fetch the Wikipedia summary for each city/county/park/river/named-summit → `notes` (1–2 sentences). Resolve the article via Wikidata or title + disambiguation.
2. **Discover lore points** — GeoSearch every ~12 mi (radius ~8 mi) → candidates → filter by Wikidata `instance of` (drop schools/stations) + rank by pageviews + length → keep the top notable → summaries → `kind: lore` features (historic site, ghost town, landmark, battle, natural feature), deduped against existing.
3. **Name the landforms** — GNIS gives the elevation/NLCD-detected summits/passes real names.
4. **Deeper history (later)** — NRHP points near the route; WPA-Guide excerpts matched to places.

### LLM narration (a transform over the facts)
- **Pre-generated track (offline default):** at build time, segment each leg (by notable clusters / ~20–30 min) → feed the LLM that segment's features + notes + land/demographic context → a tight, engaging paragraph → store milepost-keyed `narration` segments. Offline-ready (no LLM on the train), reviewable, attributable; built via the hub LiteLLM. The "soul" you play as you ride.
- **Live grounded Q&A (online / local model):** RAG over the facts near the current milepost → the LLM answers "what's that town? / tell me about here" dynamically — the laptop's local model offline, or the hub LiteLLM when connected. The facts layer is the grounding that prevents hallucination.

### Phasing
- **F.1 — facts layer (no LLM):** Wikipedia summaries on features + ranked GeoSearch lore points + GNIS names → `route_lore.json`. Sourced, reviewable; immediately enriches `around`/`profile`. *Start here — the durable substrate everything narrative builds on.*
- **F.2 — pre-generated narration track:** LLM over the facts → offline narration segments.
- **F.3 — live grounded Q&A:** RAG over facts + local/hub LLM for "ask anything."
- Deeper sources (WPA Guides, HMdb, NRHP) enrich F.1 over time.

## 5d. Scientific substrate & dual-granularity narration (Phase F.2)

The narration POC (Raton Pass, claude-sonnet-4-6 over the F.1 facts) validated the voice. Two upgrades make it the experience we want: a **scientific substrate** (travel with an expert geologist/ecologist) and a **dual-granularity** model (short stories overlaid on the large gradients of the unfolding country).

### Decisions (2026-06-27)
- Voice: keep the POC register (warm, literate, economical). Density: **denser / nearly always talking**. Grounding: **allow brief, well-known context** beyond the packet (e.g. orogeny names), kept honest by real data.
- Scientific layers (all chosen): **geology, ecoregion, climate, hydrology** + extras **fossils, night-sky, volcanoes/faults**. Geology depth: **full deep-time + tectonics**.

### Scientific layers (sources, confirmed status)
| Layer | Source | Gives | Status |
|---|---|---|---|
| **Geology** | Macrostrat `/geologic_units/map` (keyless) | formation, age (Ma), lithology, description → micro ("60-Ma arkosic sandstone") + macro (orogeny, seeded by real units) | ✅ confirmed |
| **Ecoregion** | EPA L3/L4 ArcGIS (keyless) | full biome hierarchy (L1→L4); also encodes climate ("Semi-Arid Prairies") | ✅ confirmed |
| **Fossils** | Paleobiology DB (bbox, keyless) | taxa near track + age ("Ankylosaurus", "Western Interior Seaway plesiosaurs") | ✅ confirmed |
| **Hydrology** | USGS WBD ArcGIS (keyless) | watershed (HUC) + **Continental Divide crossings** (HUC2 region change); aquifer (Ogallala) as bonus | ✅ WBD confirmed |
| **Climate** | derived: 100th-meridian (longitude) + ecoregion climate semantics + elevation (rain-shadow) | the aridity gradient & climate story — no flaky API needed | ✅ via derivation; PRISM/Köppen raster = later quant. polish |
| **Night sky** (extra) | VIIRS/Bortle light-pollution | dark-sky quality for overnight legs | ⏳ to source |
| **Volcanoes/faults** (extra) | USGS Quaternary Faults / volcanoes ArcGIS | Raton-Clayton field, Rio Grande rift, Cascades | ⏳ to source |

Built via `science.py` (same sample-along-track pattern as elevation/NLCD) → `data/route_science.json` continuous profiles. Keyless; cached in `.cache/science.json`.

### Dual-granularity model
Most macro gradients are **computable from layers we already store** — we keep continuous profiles and detect trends/transitions over a lookahead/lookback window (~150 mi ≈ 2–3 hrs):
- elevation trend (have), land-cover regime shift (have NLCD), demographic drift (have ACS), state/county crossings (have);
- biome transition (ecoregion), geologic/tectonic province (geology), aridity line (longitude), divide/watershed (WBD).

A `macro_context(leg, mile)` rolls up **current** (rock, biome, climate, elevation) + **ahead 2–3 hrs** (trends + next transitions) + **contrast with behind**. The narrator (`narrate.py`) becomes a **polymath companion** (geologist, ecologist, historian, economist) weaving the immediate stories onto the deep-time and biome gradients, talking nearly continuously.

## 5e. Level 3 — connections, the why/how, and the temporal axis (Phase F.3)

L1 (facts) + L2 (gradients) give *what* and *how it changes*. L3 is *why and how it all connects* — the pinnacle. Touchstones: **James Burke** (lateral causal chains), **William Cronon** (nature⇄capital⇄people as one system), **Ken Burns** (throughline + telling detail). Standing instruction: the narrator never just names — it pursues **why a thing is here, how it came to be, and what it connects to.**

### Connective substrate → `route_connections.json` (confirmed sources)
Per key lore point, a **connection bundle**: ranked Wikipedia outbound links + their 1-hop summaries (deeper nodes), Wikidata typed relations, and Wikipedia categories. Derive **themes** from categories — the trip-recurring threads (Santa Fe Trail · cattle frontier · coal & company towns · the Arkansas/Rio Grande corridors · Western Interior Seaway · aridity & the 100th meridian · the railroad's own story · Indigenous land & displacement · Dust Bowl & reclamation). Probed ✓: Santa Fe Trail → 196 links; Dodge City categories → "American frontier/Boot Hill/Gunsmoke/Arkansas River"; Wikidata → "named after" etc.

### Temporal axis (the connective key)
Contemporaneity is itself an edge — same-decade events are connectable across domains and across 500 mi of route, producing the emergent cross-cuts. Index everything in time:
- **Human time** from Wikidata `P571/P576/P585` (Dodge City 1872 ✓), category years (regex "1872 establishments" ✓), and summary text (Morley "1878–1956"); **deep time** from Macrostrat/PBDB ages.
- **`timeline.yml`** — curated national backbone (~50–100 era events: Homestead Act, Pacific Railway Acts, barbed wire 1874, cattle-drive era 1866–86, Panics, Dawes Act, frontier-closed 1890, Dust Bowl, Reclamation, Interstate era).
- Two modes: **synchronic** ("the year barbed wire was patented…") and **diachronic** ("camp 1878 → rails 1880 → strike 1913 → bypassed 1956"). `temporal_context(leg, mile)` hands the narrator the segment's dates + contemporaneous national events + co-temporal route events. Braids deep + human time.

### Making the whole narration connective
1. **Why/how prompt** — trace causation across domains; weave active themes every segment.
2. **Per-leg thematic spine** (build-time LLM pass, strong model) — a narrative bible naming the dominant threads + causal throughlines; segments generated *against it* so they cohere.
3. **Running story-state** — segments generated in order carrying open threads → foreshadow + call back; a trip-level **overture** sets the meta-arc.
Default on-train track **leans dense** (connection + contemporaneity woven in by default), with Say More/Why for further depth.

### Interactive modes (three anchors)
| Mode | Anchored to | Answers |
|---|---|---|
| **What's that?** | current position (engine `now`/live → leg+mile+latlon, optional window/bearing) | what am I looking at right now (quiet mode) |
| **Say More ▸** | a topic (narrated or tapped) | more on this dimension (menu) |
| **Why is that?** | a statement/feature | the causal/temporal chain (Burke mode) |

- **What's that?** picks the single most *plausibly-visible* feature near current mile, ranked by proximity × **side** (stored on every lore point) × prominence (off-track distance × salience × kind — landforms/water read at distance, towns up close). **Most offline-robust:** answers with zero LLM from the stored summary + window; local/hub LLM just makes it conversational. Composes into Say More / Why.
- Each segment is generated with structured **expansion hooks** — referenced entities/threads tagged by dimension (geology/history/culture/economy/ecology/person/event/theme/**what-else-happened-then**) carrying their grounding bundle; the hooks are the Say-More menu (a woven moment is multi-dimensional). **Why is that?** = causal/temporal deepening; **Say more about X** = topical deepening on that bundle, recursive (each deep-dive exposes new hooks).
- **Offline:** pre-generate the top expansion cards per segment + the per-feature "what's that" answers; **live:** laptop local model offline or hub online for arbitrary follow-ups grounded in the stored bundle. All three modes share one substrate (facts + connection bundles + temporal index); they differ only in anchor and depth.

### Pipeline
`connect.py` (bundles + themes + dates) → `timeline.yml` (authored) → per-leg thematic-spine pass → enhanced in-order segment narration (+ expansion hooks) → app: play track, hooks→menu, tap→pre-gen card or live LLM. Sequencing: after L2/science + the dual-granularity narrator validate.

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
- **Phase E — Statistical corridor profile (§5b).** County-traversal `area` spans with ACS demographics/occupations/socioeconomics + NASS land use + NLCD land cover, plus a `profile`/`where` query. Depends on Phase C's areal plumbing — do it **with or right after C**.
- **Phase F — Narrative & lore layer (§5c).** Sourced facts/color per place (Wikipedia summaries + ranked GeoSearch lore points + GNIS names → `route_lore.json`), then an LLM narration track over them (pre-generated offline; live grounded Q&A online). The "soul." F.1 (facts) is the substrate; F.2/F.3 are the narration.

Recommend building **Phase A end-to-end first** (proves the contract + runtime + CLI with real, hand-quality data), then layering B/C/D/E into the same `route_guide.json`. C and E are the two areal layers and share point-in-polygon machinery, so they pair naturally.

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
6. **Statistical resolution (Phase E)** — county vs tract. *Rec:* county as the base (stable, reliable estimates); tract only as an optional urban-approach overlay. Confirm at Phase E kickoff.
