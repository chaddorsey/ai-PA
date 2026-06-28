#!/usr/bin/env python3
"""
Build pron_lexicon.json from proper_nouns.json.

- All entries get overrides-or-CMUdict sourced immediately (no live fetch).
- Top ~150 names by risk×freq (among those still without a trusted IPA)
  get live Wikipedia/Wiktionary lookups with a small on-disk cache
  and polite delay.
- Prints stats and top-20 risk×freq sample.
- Writes data/pron_lexicon.json.
"""
import json
import time
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CACHE_PATH = DATA / ".ipa_cache.json"
OVERRIDES_PATH = DATA / "pron_overrides.json"
PROPER_NOUNS_PATH = DATA / "proper_nouns.json"
LEXICON_PATH = DATA / "pron_lexicon.json"

LIVE_FETCH_LIMIT = 150
POLITENESS_DELAY = 0.3  # seconds between live fetches

# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------

overrides = json.loads(OVERRIDES_PATH.read_text())
proper_nouns = json.loads(PROPER_NOUNS_PATH.read_text())

# Load or create cache
if CACHE_PATH.exists():
    cache: "dict" = json.loads(CACHE_PATH.read_text())
else:
    cache = {}

def save_cache():
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# Import pipeline modules (reload OVERRIDES from file)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(BASE))
import pipeline.sources as src
import importlib
importlib.reload(src)  # ensure OVERRIDES are loaded from the seeded file

from pipeline.risk import risk_score

# ---------------------------------------------------------------------------
# Phase 1: quick pass — overrides + CMUdict (no live fetches)
# ---------------------------------------------------------------------------

print("Phase 1: overrides + CMUdict (no live fetches)...")
lexicon: "dict" = {}
cmudict = src._get_cmudict()

for name, info in proper_nouns.items():
    pageid = info.get("pageid")
    freq = info.get("count", 0)
    risk = risk_score(name)

    if name in overrides:
        entry = {
            "ipa": overrides[name],
            "source": "override",
            "confidence": 1.0,
            "risk": risk,
            "freq": freq,
        }
    elif name.lower() in cmudict:
        phones = cmudict[name.lower()]
        ipa = src._arpabet_to_ipa(phones)
        entry = {
            "ipa": ipa,
            "source": "cmudict",
            "confidence": 0.6,
            "risk": risk,
            "freq": freq,
        }
    else:
        entry = {
            "ipa": None,
            "source": "none",
            "confidence": 0.0,
            "risk": risk,
            "freq": freq,
        }
    lexicon[name] = entry

# ---------------------------------------------------------------------------
# Phase 2: live fetches for top-150 by risk×freq that still need IPA
# ---------------------------------------------------------------------------

# Candidates: no trusted IPA yet (overrides already have conf 1.0)
candidates_for_live = [
    name for name, entry in lexicon.items()
    if entry["confidence"] < 0.8 and proper_nouns[name].get("freq", entry["freq"]) > 0
]
# Sort by risk×freq descending
candidates_for_live.sort(
    key=lambda n: lexicon[n]["risk"] * lexicon[n]["freq"],
    reverse=True,
)
live_queue = candidates_for_live[:LIVE_FETCH_LIMIT]

print(f"Phase 2: live fetching up to {LIVE_FETCH_LIMIT} names "
      f"({len(candidates_for_live)} candidates, {len(live_queue)} selected)...")

fetched = 0
for name in live_queue:
    # Check cache first
    cache_key = f"name:{name}"
    pageid = proper_nouns[name].get("pageid")
    wp_cache_key = f"wp:{pageid}" if pageid else None

    result = None

    # Wikipedia (by pageid) — check cache
    if pageid and wp_cache_key:
        if wp_cache_key in cache:
            cached = cache[wp_cache_key]
            if cached.get("ipa"):
                result = {"ipa": cached["ipa"], "source": "wikipedia", "confidence": 0.9}
        if result is None:
            # Live fetch
            wt = src._fetch_wikitext_by_pageid(pageid)
            if wt:
                ipa = src._extract_ipa_from_wp_wikitext(wt)
                cache[wp_cache_key] = {"ipa": ipa}
                save_cache()
                if ipa:
                    result = {"ipa": ipa, "source": "wikipedia", "confidence": 0.9}
            else:
                cache[wp_cache_key] = {"ipa": None}
                save_cache()
            fetched += 1
            time.sleep(POLITENESS_DELAY)

    # Wiktionary — check cache
    if result is None:
        wt_cache_key = f"wt:{name}"
        if wt_cache_key in cache:
            cached = cache[wt_cache_key]
            if cached.get("ipa"):
                result = {"ipa": cached["ipa"], "source": "wiktionary", "confidence": 0.8}
        if result is None:
            # Live fetch
            wt = src._fetch_wiktionary_wikitext(name)
            if wt:
                ipa = src._extract_ipa_from_wt_wikitext(wt)
                cache[wt_cache_key] = {"ipa": ipa}
                save_cache()
                if ipa:
                    result = {"ipa": ipa, "source": "wiktionary", "confidence": 0.8}
            else:
                cache[wt_cache_key] = {"ipa": None}
                save_cache()
            fetched += 1
            time.sleep(POLITENESS_DELAY)

    if result and result["ipa"]:
        lexicon[name].update({
            "ipa": result["ipa"],
            "source": result["source"],
            "confidence": result["confidence"],
        })

    if fetched % 20 == 0 and fetched > 0:
        print(f"  ... {fetched} live fetches done")

print(f"  Done. {fetched} total live fetches.")

# ---------------------------------------------------------------------------
# Write lexicon
# ---------------------------------------------------------------------------

LEXICON_PATH.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n")
print(f"\nWrote {len(lexicon)} entries → {LEXICON_PATH}")

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

by_source: "dict[str, int]" = {}
trusted = 0
for entry in lexicon.values():
    src_name = entry["source"]
    by_source[src_name] = by_source.get(src_name, 0) + 1
    if entry["confidence"] >= 0.8 or entry["source"] == "override":
        trusted += 1

print("\n--- Trusted IPA by source ---")
for s, n in sorted(by_source.items(), key=lambda x: -x[1]):
    print(f"  {s:12s}: {n}")
print(f"  TOTAL trusted (conf≥0.8 or override): {trusted} / {len(lexicon)}")

# ---------------------------------------------------------------------------
# Top-20 risk×freq
# ---------------------------------------------------------------------------

top20 = sorted(
    [(n, e) for n, e in lexicon.items() if e["freq"] > 0],
    key=lambda kv: kv[1]["risk"] * kv[1]["freq"],
    reverse=True,
)[:20]

print("\n--- Top 20 by risk×freq ---")
print(f"{'Name':<25} {'Freq':>5} {'Risk':>6} {'RxF':>6} {'Source':<12} {'IPA'}")
for name, e in top20:
    rxf = e["risk"] * e["freq"]
    ipa = e["ipa"] or "(none)"
    print(f"{name:<25} {e['freq']:>5} {e['risk']:>6.2f} {rxf:>6.1f} {e['source']:<12} {ipa}")
