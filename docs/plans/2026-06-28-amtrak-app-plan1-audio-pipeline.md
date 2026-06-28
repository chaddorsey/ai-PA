# Amtrak Companion — Plan 1: Build‑time Audio + Pronunciation Pipeline

> **For agentic workers:** REQUIRED SUB‑SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task‑by‑task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn the committed narration (`route_narration.json`, 6 legs, ~2,900 units) into **per‑leg offline bundles** — premium Chirp3‑HD audio with guaranteed proper‑noun pronunciation, plus the data + a predicted‑position table the app consumes offline.

**Architecture:** A pure‑Python pipeline (reuses the existing `tools/amtrak-position-engine/` engine + data). Stages: extract proper nouns → build a pronunciation lexicon (IPA) → render each unit via Google **Chirp3‑HD** with `customPronunciations` to **OGG/Opus** → assemble a per‑leg bundle (units + coords + audio manifest + data layers) → export a predicted‑position table. Everything is self‑testable headlessly; no device or app code here.

**Tech Stack:** Python 3.9+ (stdlib), the existing engine modules, Google Cloud Text‑to‑Speech REST (`text:synthesize`, `OGG_OPUS`, `customPronunciations`), `pytest`. Audio stays Opus (Google returns it directly — no transcode).

> **Sequencing (proxy‑first).** We build the whole app (Plans 2–4) against a **thin proxy bundle** — a small sampler (~30 representative units of one leg via a `--sample N` flag on `run render`, a few minutes of audio) or the short CONO leg — produced by Tasks 1–7. The **full ~42‑hour corpus render (Task 8) is DEFERRED to the very end**, run once only after the app works end‑to‑end and the Chirp3 voice is locked. This avoids generating scores of hours of audio before the player that consumes it exists, and keeps the first real charge late.

## Global Constraints
- Package root: `tools/amtrak-position-engine/`; new pipeline code under `tools/amtrak-position-engine/pipeline/`; tests under `tools/amtrak-position-engine/pipeline/tests/`.
- Engine = **Google Chirp3‑HD** voice (default `en-US-Chirp3-HD-Charon`, configurable) with `customPronunciations` (verified to honor IPA overrides). Audio encoding **OGG_OPUS**.
- Pronunciation IPA encoding: `PHONETIC_ENCODING_IPA`.
- Secrets from repo `.env` (gitignored): `GOOGLE_TTS_API_KEY`. Never print/commit key values.
- Outputs: data/JSON committed; **audio + bundles gitignored** (regenerable, large) under `tools/amtrak-position-engine/bundles/`.
- **Ops gate (human):** switch the GCP project to a separate billing card BEFORE the full‑corpus render (the first significant charge). A dry‑run/cost‑estimate task precedes any full render.
- Cost frame: full corpus ≈ 2.25M chars ≈ ~$67 at Chirp3‑HD rates; per‑unit incremental re‑render is cents.
- Idempotent + cached: re‑running renders only changed units (hash of text+lexicon+voice).

---

## File structure
- `pipeline/proper_nouns.py` — extract candidate proper nouns across all legs → `data/proper_nouns.json`.
- `pipeline/lexicon.py` — load/merge/apply the pronunciation lexicon (`data/pron_lexicon.json`: term→IPA) + a hand‑curated overrides file; produce per‑unit `customPronunciations` lists.
- `pipeline/render.py` — Chirp3‑HD synth of one unit (text + customPronunciations) → Opus bytes; content‑hash cache; retry/backoff; cost estimate (dry run).
- `pipeline/bundle.py` — assemble a per‑leg bundle (units + coords + audio manifest + data layers) + validation.
- `pipeline/position_table.py` — export a clock‑time→milepost predicted‑position table per leg.
- `pipeline/run.py` — CLI orchestrator (`extract`, `lexicon`, `estimate`, `render <leg>`, `bundle <leg>`, `postable <leg>`, `all <leg>`).
- `pipeline/tests/` — pytest for each module (sample‑driven, offline except the live‑render smoke test).

---

### Task 1: Proper‑noun extraction
**Files:**
- Create: `pipeline/proper_nouns.py`, `pipeline/tests/test_proper_nouns.py`
- Reads: `data/route_narration.json`, `data/route_lore.json`, `data/route_connections.json`

**Interfaces:**
- Produces: `extract_proper_nouns(narration, lore, connections) -> dict[str, dict]` mapping `term -> {"count": int, "legs": [str], "kind": "place"|"person"|"other"}`; and `write_proper_nouns(path)` → `data/proper_nouns.json`.

- [ ] **Step 1: Failing test**
```python
# pipeline/tests/test_proper_nouns.py
from pipeline.proper_nouns import extract_proper_nouns
def test_extracts_place_names_from_lore_titles_and_text():
    narr = {"3": [{"kind":"squib","mile":1087,"place":"Morley, Colorado","text":"Morley was a coal town."}]}
    lore = {"3": {"lore":[{"title":"Morley, Colorado","peak_mi":1087}]}}
    conn = {"3": {"nodes":{"w1":{"title":"Morley, Colorado","named_after":None}}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Morley" in out and out["Morley"]["kind"] == "place"
```
- [ ] **Step 2: Run → fail** — `cd tools/amtrak-position-engine && python3 -m pytest pipeline/tests/test_proper_nouns.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** — `extract_proper_nouns`: collect candidate terms from (a) lore `title` + `place` fields (kind=place), (b) connections `named_after`/`part_of` labels (kind=person/other), (c) capitalized multi‑word sequences in unit `text` not in a common‑word stoplist; normalize ("Morley, Colorado"→"Morley" + keep full form); tally count + legs. `write_proper_nouns` dumps sorted JSON.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Run on real data** — `python3 -m pipeline.run extract` → writes `data/proper_nouns.json`; eyeball count (expect a few thousand candidates, dominated by place names).
- [ ] **Step 6: Commit** — `git add pipeline/proper_nouns.py pipeline/tests/test_proper_nouns.py data/proper_nouns.json && git commit -m "feat(pipeline): proper-noun extraction across the narrative"`

---

### Task 2: Pronunciation lexicon — multi‑source auto‑fill + risk‑ranked audio review

> **Coverage probe findings (2026‑06‑28, `pipeline_probe_pronunciation.py`):** 1,485 unique proper nouns, **1,138 actually spoken**, 18 persons. Auto‑source IPA coverage is **partial** — Wikipedia ~15% (by exact pageid), Wiktionary ~39% — so auto‑sourcing alone CANNOT guarantee correctness. **Key insight:** the most‑spoken names are common and the engine already says them right (Chicago, Kansas, Santa Fe, San Antonio, Los Angeles, Tucson…); pronunciation **risk is concentrated in the irregular tail** (Raton, Tucumcari, Purgatoire, Cimarron…). So the guarantee comes from: auto‑fill IPA where available, **risk‑rank** every spoken name, and **human‑verify a risk×frequency‑sorted AUDIO review sheet** (finite, cheap, definitive). A name is only given a `customPronunciations` override when it has a TRUSTED IPA (curated or high‑confidence source); regular names keep the engine default. The probe also showed extraction noise (e.g. "Santa Fe" mis‑tagged person, "Quaternary sediment"/"state line" as names) → Task 1 extraction must filter common words + a stoplist before this task consumes it.

**Files:**
- Create: `pipeline/sources.py` (Wikipedia/Wiktionary/CMUdict/G2P IPA lookups), `pipeline/risk.py`, `pipeline/lexicon.py`, `pipeline/review_sheet.py`, their tests, and `data/pron_overrides.json` (seed with known‑hard route names).
- Produces: `data/pron_lexicon.json`, `data/pron_review.html` (audio review sheet; gitignored with the name clips).

**Interfaces:**
- Produces: `source_ipa(name, pageid=None) -> {"ipa":str|None,"source":str,"confidence":float}` (tiered: overrides→wikipedia(pageid)→wiktionary→cmudict→g2p); `risk_score(name) -> float` (0–1, high = likely irregular); `build_lexicon(proper_nouns, overrides) -> dict[str,dict]` (`term -> {"ipa","source","confidence","risk","freq"}`); `custompron_for(text, lexicon) -> list[dict]` emitting `[{"phrase","phoneticEncoding":"PHONETIC_ENCODING_IPA","pronunciation"}]` for **trusted** terms only; `build_review_sheet(lexicon, render_fn, out_html)`.

- [ ] **Step 1: Failing test — tiered sourcing**
```python
# pipeline/tests/test_sources.py
from pipeline.sources import source_ipa
def test_override_beats_all_and_source_is_tagged(monkeypatch):
    monkeypatch.setattr("pipeline.sources.OVERRIDES", {"Raton":"rəˈtoʊn"})
    r = source_ipa("Raton"); assert r["ipa"]=="rəˈtoʊn" and r["source"]=="override" and r["confidence"]==1.0
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement `sources.py`** — `OVERRIDES` loaded from `data/pron_overrides.json`. `wikipedia_ipa(pageid)` (fetch wikitext, extract `{{IPAc-en|…}}`/`{{IPA|…}}` → IPA, confidence 0.9), `wiktionary_ipa(name)` (`{{IPA|en|/…/}}`, 0.8), `cmudict_ipa(name)` (ARPABET→IPA map, 0.6), `g2p_ipa(name)` (predict, 0.3). `source_ipa` returns the first hit in order with its source+confidence.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Failing test — risk score**
```python
# pipeline/tests/test_risk.py
from pipeline.risk import risk_score
def test_irregular_names_score_higher_than_common():
    assert risk_score("Tucumcari") > risk_score("Chicago")
    assert risk_score("Purgatoire") > risk_score("Kansas")
```
- [ ] **Step 6: Run → fail.**
- [ ] **Step 7: Implement `risk.py`** — heuristics: +risk for Spanish/French/Native markers (e.g. trailing `-oire`,`-cari`,`-ton` loan patterns, `qu`/`x`/double‑vowel clusters, tilde/accent), +risk if not in a common‑English‑word/major‑city list, −risk for plain CVC English. Normalize to 0–1.
- [ ] **Step 8: Run → pass.**
- [ ] **Step 9: Failing test — lexicon trust gate**
```python
# pipeline/tests/test_lexicon.py
from pipeline.lexicon import build_lexicon, custompron_for
def test_only_trusted_entries_emit_custompron():
    pn = {"Raton":{"freq":5,"pageid":None}, "Lamar":{"freq":1,"pageid":None}}
    ov = {"Raton":"rəˈtoʊn"}                      # Lamar has no override
    lex = build_lexicon(pn, ov)
    assert lex["Raton"]["ipa"]=="rəˈtoʊn" and lex["Raton"]["confidence"]==1.0
    cps = custompron_for("Ahead lies Raton Pass near Lamar.", lex)
    assert cps == [{"phrase":"Raton","phoneticEncoding":"PHONETIC_ENCODING_IPA","pronunciation":"rəˈtoʊn"}]
```
- [ ] **Step 10: Run → fail.**
- [ ] **Step 11: Implement `lexicon.py`** — `build_lexicon`: for each proper noun, `source_ipa` + `risk_score`, carry `freq`. `custompron_for`: word‑boundary match terms present in the text whose entry is **trusted** (`confidence ≥ 0.8` or override) → the customPronunciations list. Low‑confidence (g2p/cmudict‑only) entries are listed but NOT emitted until a human confirms them in the review sheet.
- [ ] **Step 12: Run → pass.**
- [ ] **Step 13: Seed overrides** — write `data/pron_overrides.json` with the known‑hard route names and IPA (Raton `rəˈtoʊn`, Tucumcari `ˌtukəmˈkɛri`, Purgatoire `ˈpɝɡətwɑr`, Cimarron `ˈsɪmərɑn`, Mojave `moʊˈhɑvi`, Cajon `kəˈhoʊn`, Pecos `ˈpeɪkəs`, Cairo‑IL `ˈkɛroʊ`, Pierre‑SD `pɪr`, Las Animas, etc.).
- [ ] **Step 14: Build the lexicon** — `python3 -m pipeline.run lexicon` → `pron_lexicon.json` (auto‑filled IPA + source + confidence + risk + freq for all spoken names).
- [ ] **Step 15: Implement + build the audio review sheet** — `build_review_sheet`: render each spoken unique name (Chirp3 + its current best IPA via `render.synth`) and emit `pron_review.html` with rows **sorted by `risk × freq` descending**: `name | freq | source | confidence | IPA | ▶ audio | [override IPA field]`. Run `python3 -m pipeline.run review`.
- [ ] **Step 16: HUMAN REVIEW (the guarantee)** — skim the sheet top‑down: the risky/most‑spoken names are first; the common head confirms instantly by ear. For any wrong one, add the correct IPA to `pron_overrides.json` (becomes trusted, confidence 1.0) and re‑run `lexicon`. Stop when the trusted set covers the risk you care about.
- [ ] **Step 17: Commit** — `git add pipeline/sources.py pipeline/risk.py pipeline/lexicon.py pipeline/review_sheet.py pipeline/tests/ data/pron_overrides.json data/pron_lexicon.json && git commit -m "feat(pipeline): multi-source pronunciation lexicon + risk-ranked audio review"` (review.html + name clips gitignored).

---

### Task 3: Chirp3‑HD render (one unit) + cache + cost estimate
**Files:**
- Create: `pipeline/render.py`, `pipeline/tests/test_render.py`
- Reads `.env` `GOOGLE_TTS_API_KEY`.

**Interfaces:**
- Produces: `synth(text, custompron, voice="en-US-Chirp3-HD-Charon") -> bytes` (Opus); `render_unit(unit, lexicon, outdir, voice) -> dict` (`{"file","bytes","chars","cached"}`); `estimate_cost(narration) -> dict` (`{"chars","usd_low","usd_high"}`).

- [ ] **Step 1: Failing test (offline — mock the HTTP)**
```python
# pipeline/tests/test_render.py
from pipeline import render
def test_render_unit_caches_by_content_hash(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(render, "synth", lambda text, cp, voice="x": (calls.append(text) or b"OPUSBYTES"))
    u = {"id":"w1","text":"Raton Pass."}
    r1 = render.render_unit(u, {}, tmp_path, "v"); r2 = render.render_unit(u, {}, tmp_path, "v")
    assert r1["file"].endswith(".opus") and r2["cached"] is True and len(calls) == 1
def test_estimate_cost_scales_with_chars():
    e = render.estimate_cost({"3":[{"text":"x"*1000}]})
    assert e["chars"] == 1000 and e["usd_high"] >= e["usd_low"] >= 0
```
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — `synth`: POST `text:synthesize` with `input.text` + `input.customPronunciations`, `voice` Chirp3‑HD, `audioConfig.audioEncoding=OGG_OPUS`; base64‑decode `audioContent`; retry/backoff on 429/5xx. `render_unit`: hash(text+custompron+voice) → cache filename `<hash>.opus`; skip synth if exists (`cached=True`). `estimate_cost`: total chars × Chirp3 rate range (`$30/1M` low, `$45/1M` high).
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Live smoke test** — `python3 -c "from pipeline import render,lexicon,json; lex=json.load(open('data/pron_lexicon.json')); u={'id':'t','text':'Ahead lies Raton Pass.'}; print(render.render_unit(u, lex, 'bundles/_smoke', 'en-US-Chirp3-HD-Charon'))"` → an `.opus` file written; play it to confirm "Raton" correct.
- [ ] **Step 6: Commit** — `git add pipeline/render.py pipeline/tests/test_render.py && git commit -m "feat(pipeline): Chirp3-HD Opus render with customPronunciations + content-hash cache + cost estimate"`

---

### Task 4: Cost estimate gate (dry run) — ops checkpoint
**Files:** Modify: `pipeline/run.py` (add `estimate` command).

- [ ] **Step 1:** Add `estimate` CLI → prints total chars + `$low–$high` for the full corpus and per leg, and a reminder line: **"⚠ switch GCP billing card before a full render."**
- [ ] **Step 2: Run** — `python3 -m pipeline.run estimate` → shows ~2.25M chars, ~$67 (range), per‑leg breakdown.
- [ ] **Step 3: Commit** — `git commit -am "feat(pipeline): cost-estimate gate before render"`
- [ ] **Step 4: HUMAN GATE** — confirm billing card swapped before any full‑leg render task is run.

---

### Task 5: Per‑leg render
**Files:** Modify: `pipeline/render.py` (add `render_leg`); Create: `pipeline/tests/test_render_leg.py`.

**Interfaces:**
- Produces: `render_leg(leg, narration, lexicon, voice, outdir) -> dict` → renders every unit, returns `{"leg","units","rendered","cached","seconds_est","audio_manifest": {unit_id: {"file","dur_s"}}}`.

- [ ] **Step 1: Failing test** (mock `render_unit`) — assert all units in a 3‑unit fake leg get a manifest entry; re‑run reports `cached`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — iterate the leg's units, `render_unit` each (cached), build the audio manifest (file + duration via Opus header or `chars/14.0` estimate), progress print every N.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Render the shortest real leg** (CONO, leg 58 — confirm the cheapest first) — `python3 -m pipeline.run render 58` → writes `bundles/leg58/audio/*.opus` + a manifest; spot‑check 3 clips by ear (incl. one with a hard place name).
- [ ] **Step 6: Commit** — `git commit -am "feat(pipeline): per-leg render + audio manifest"`

---

### Task 6: Per‑leg bundle assembly + validation
**Files:** Create: `pipeline/bundle.py`, `pipeline/tests/test_bundle.py`.

**Interfaces:**
- Produces: `build_bundle(leg, outdir) -> dict`; writes `bundles/leg<leg>/bundle.json` = `{leg, units:[{...unit, audio, dur_s}], coords already in units, layers:{guide,lore,science,connections,themes slice}, position_table}` + the `audio/` dir. `validate_bundle(leg) -> list[str]` (problems).

- [ ] **Step 1: Failing test** — given a fake leg manifest + narration, `build_bundle` emits a `bundle.json` where every unit has an `audio` path and `dur_s`; `validate_bundle` returns `[]`; if an audio entry is missing it returns a coverage error.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — merge narration units (with their lat/lon/poi coords) + the audio manifest; attach the leg's slices of the data layers; write `bundle.json`; `validate_bundle` checks: every unit has audio + dur, every squib has a mile, sizes within sanity, total audio MB reported.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Build the leg‑58 bundle** — `python3 -m pipeline.run bundle 58` → `bundle.json` + audio; `validate_bundle 58` → clean; print total MB (expect well under the ~150 MB/leg ceiling for the short leg).
- [ ] **Step 6: Commit** — `git commit -am "feat(pipeline): per-leg bundle assembly + validation"`

---

### Task 7: Predicted‑position table export (offline no‑GPS fallback)
**Files:** Create: `pipeline/position_table.py`, `pipeline/tests/test_position_table.py`; Modify `pipeline/bundle.py` to include it.

**Interfaces:**
- Produces: `export_position_table(leg, step_min=2) -> list[[elapsed_min, mile, lat, lon]]` from the engine's predictor, covering the leg's scheduled run.

- [ ] **Step 1: Failing test** — for a leg, the table is monotonic in `elapsed_min`, miles non‑decreasing, first row ~mile 0, last row ~`leg_miles`; lat/lon present.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — call the engine's predictor (or interpolate the scheduled timetable + `_milepost_latlon`) at `step_min` intervals → rows; include in the bundle as `position_table`.
- [ ] **Step 4: Run → pass.**
- [ ] **Step 5: Real run** — `python3 -m pipeline.run postable 58` → table in the leg‑58 bundle; sanity‑print first/last rows.
- [ ] **Step 6: Commit** — `git commit -am "feat(pipeline): predicted-position table export into the bundle"`

---

### Task 8 (DEFERRED to the end — only after the app is built and the Chirp3 voice is locked): Full‑corpus render + manifest
**Files:** Modify: `pipeline/run.py` (`all` over all legs); Create: `bundles/INDEX.json` (per‑leg sizes/versions).

- [ ] **Step 1:** `run all` = for each leg: render → bundle → postable; write `bundles/INDEX.json` (leg → {audio_mb, units, version hash}). Idempotent (cached units skipped).
- [ ] **Step 2: HUMAN GATE re‑confirm** billing card, then run `python3 -m pipeline.run estimate` once more.
- [ ] **Step 3: Render trip order** — `run all` (or per leg in itinerary order); monitor cost. Spot‑check a hard‑name unit per leg by ear; fix any mispronunciation via `pron_overrides.json` + re‑render that unit (cached others untouched).
- [ ] **Step 4: Commit** the JSON artifacts (lexicon, INDEX, bundle.json files) — audio stays gitignored — `git commit -m "feat(pipeline): full six-leg audio bundles rendered"`

---

## Self‑review
- **Spec coverage:** pre‑rendered Chirp3‑HD ✓ (T3/T5); customPronunciations guarantee ✓ (T2/T3); proper‑noun pipeline ✓ (T1/T2); per‑leg lazy bundles ✓ (T6); predicted‑position offline fallback ✓ (T7); incremental re‑render for beta ✓ (cache, T3/T8); billing gate ✓ (T4/T8). Opus per‑leg ≤ size budget ✓ (T6 report).
- **Placeholders:** none — every task has test code, real commands, and concrete implementations described.
- **Type consistency:** `render_unit`→manifest entry `{file,dur_s}` consumed by `build_bundle`; `custompron_for` output shape matches `synth`'s `customPronunciations` body; lexicon `term→IPA` consistent across T2/T3/T8.
- **Out of scope (later plans):** the TypeScript companion‑core, the hybrid shell/native plugins, and the pillar UIs (Plans 2–4). This plan produces the bundles those consume.
