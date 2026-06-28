"""
pipeline/risk.py — Task 2: Pronunciation risk scoring.

Public API
----------
risk_score(name) -> float
    Returns 0.0–1.0. Higher = likely irregular pronunciation.
    High risk: Spanish/French/Native-origin markers, non-English vowel clusters,
               uncommon letter patterns.
    Low risk: Common English place names, major US cities.
"""

import re

# ---------------------------------------------------------------------------
# Known low-risk (common English / major US cities) — engine already nails these
# ---------------------------------------------------------------------------
_LOW_RISK_NAMES = {
    # Major US cities / well-known states
    "chicago", "kansas", "denver", "boston", "portland", "dallas", "houston",
    "phoenix", "atlanta", "seattle", "detroit", "memphis", "nashville",
    "cleveland", "columbus", "indianapolis", "jacksonville", "austin",
    "baltimore", "milwaukee", "minneapolis", "oklahoma", "albuquerque",
    "sacramento", "san", "los", "new",
    # States / regions
    "texas", "california", "florida", "ohio", "michigan", "illinois",
    "indiana", "missouri", "georgia", "virginia", "carolina",
    "colorado", "arizona", "nevada", "utah", "montana", "wyoming",
    "nebraska", "iowa", "minnesota", "wisconsin", "kentucky", "tennessee",
    "arkansas", "louisiana", "mississippi", "alabama",
    # Common English place-name words
    "city", "town", "spring", "springs", "lake", "falls", "creek",
    "ridge", "valley", "grove", "meadow", "wood", "field", "fort",
    "junction", "station",
}

# ---------------------------------------------------------------------------
# High-risk patterns (additive, each adds to raw score)
# ---------------------------------------------------------------------------

# French-origin suffixes
_FRENCH_PATTERNS = [
    re.compile(r"oire\b", re.I),    # Purgatoire, Berthoud Passe (Berthoud)
    re.compile(r"aux\b", re.I),     # Bordeaux, Primeaux
    re.compile(r"ieu\b", re.I),     # Richelieu
    re.compile(r"eau\b", re.I),     # Château, Bordeaux
    re.compile(r"que\b", re.I),     # Albuquerque
    re.compile(r"^beau", re.I),     # Beaumont
    re.compile(r"lle\b", re.I),     # Versailles, Marysville (minor)
    re.compile(r"^la\s", re.I),     # La Junta
    re.compile(r"^le\s", re.I),     # Le Roy
    re.compile(r"ville\b", re.I),   # Versailles (minor French overlap)
]

# Spanish-origin patterns
_SPANISH_PATTERNS = [
    re.compile(r"ón\b", re.I),      # Tucson, Raton (with accent)
    re.compile(r"j\b", re.I),       # Cajon (j=h sound in Spanish)
    re.compile(r"ll", re.I),        # Amarillo, La Jolla
    re.compile(r"ñ", re.I),         # Spanish tilde-n
    re.compile(r"^[A-Z][a-z]+j", re.I),  # Cajon pattern
    re.compile(r"on\b", re.I),      # Raton, Cimarron, Tucson
    re.compile(r"arr", re.I),       # Cimarron, Carrizo
    re.compile(r"^[Cc]a[hj]", re.I),  # Cajon, Cahon
    re.compile(r"uqu", re.I),       # Albuquerque
    re.compile(r"^[Mm]oj", re.I),   # Mojave (j=h)
    re.compile(r"ave\b", re.I),     # Mojave
    re.compile(r"^[Pp]ec", re.I),   # Pecos
]

# Native American language patterns
_NATIVE_PATTERNS = [
    re.compile(r"cum", re.I),       # Tucumcari
    re.compile(r"mcar", re.I),      # Tucumcari
    re.compile(r"atchee", re.I),    # Natchitoches
    re.compile(r"[aeiou]{3}", re.I), # Three vowels in a row
    re.compile(r"kw", re.I),        # Native cluster
    re.compile(r"tlh", re.I),       # Navajo pattern
    re.compile(r"sh[aeiou]w", re.I), # Shaw... patterns
    re.compile(r"^[A-Z][a-z]*[kqx][a-z]", re.I),  # uncommon consonant
    re.compile(r"chi\b", re.I),     # Apache
    re.compile(r"pach", re.I),      # Apache
    re.compile(r"navaj", re.I),     # Navajo
]

# Irregular vowel clusters (non-standard English pronunciation cues)
_VOWEL_CLUSTER_PATTERNS = [
    re.compile(r"[aeiou]{3}", re.I),    # triple vowel run
    re.compile(r"oi", re.I),            # unusual in place names
    re.compile(r"ua", re.I),            # unusual
    re.compile(r"eau"),                  # French
]

# Specific known-tricky names (hard-coded risk bump)
_HARD_CODED_HIGH = {
    "raton", "tucumcari", "purgatoire", "cimarron", "mojave", "cajon",
    "pecos", "cairo", "pierre", "versailles", "albuquerque", "wichita",
    "tucson", "los alamos", "taos", "espanola", "socorro", "bernalillo",
    "cuyahoga", "schenectady", "poughkeepsie", "kissimmee", "alachua",
    "tallahassee", "cheyenne", "laramie", "pawnee", "arapaho", "comanche",
    "kiowa", "osage", "sequoyah", "tishomingo", "anadarko", "muskogee",
    "okmulgee", "poteau", "sequoyah", "natchitoches", "opelousas",
    "baton", "iberville", "terrebonne", "plaquemines", "thibodaux",
    "houma", "abbeville", "mamou", "eunice", "opelousas",
    "spokane", "coeur", "boise", "payette", "challis",
    "butte", "bozeman", "missoula", "havre", "glasgow",
    "huron", "sioux", "bismarck", "wahpeton", "jamestown",
    "eau claire", "fond du lac", "oconomowoc", "waukesha",
    "ypsilanti", "kalamazoo", "sault", "saginaw", "pontiac",
    "chillicothe", "coshocton", "muskingum", "scioto",
    "kanawha", "monongalia", "pocahontas",
}


def risk_score(name: str) -> float:
    """
    Return a risk score 0.0–1.0 for a proper noun.
    High = likely-irregular pronunciation that Chirp3-HD may mispronounce.
    Low = standard English pronunciation the engine already handles.
    """
    name_l = name.lower().strip()

    # Hard-coded high-risk names
    if name_l in _HARD_CODED_HIGH:
        return 0.90

    # Hard-coded low-risk (major cities / common English words)
    if name_l in _LOW_RISK_NAMES:
        return 0.05

    # Accumulate risk score from heuristics
    raw = 0.0

    # French patterns
    french_hits = sum(1 for p in _FRENCH_PATTERNS if p.search(name))
    raw += french_hits * 0.18

    # Spanish patterns
    spanish_hits = sum(1 for p in _SPANISH_PATTERNS if p.search(name))
    raw += spanish_hits * 0.15

    # Native patterns
    native_hits = sum(1 for p in _NATIVE_PATTERNS if p.search(name))
    raw += native_hits * 0.14

    # Vowel clusters
    vowel_hits = sum(1 for p in _VOWEL_CLUSTER_PATTERNS if p.search(name))
    raw += vowel_hits * 0.10

    # Length bonus: very long multi-syllable foreign-ish names
    if len(name) > 10:
        raw += 0.05
    if len(name) > 14:
        raw += 0.05

    # Non-ASCII characters (accents, tildes) → almost certain irregular
    if any(ord(c) > 127 for c in name):
        raw += 0.30

    # Single-word, not in CMUdict is already handled by source selection
    # But a lack of common English digraphs is a mild risk signal
    common_english = re.compile(r"^[a-z]+(ing|tion|land|field|wood|burg|ville|ford|port|wick|ton)$", re.I)
    if common_english.match(name):
        raw -= 0.10  # common English compound — lower risk

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, raw))
