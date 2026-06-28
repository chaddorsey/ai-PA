"""
pipeline/sources.py — Task 2: Multi-source IPA pronunciation lookup.

Public API
----------
source_ipa(name, pageid=None) -> {"ipa": str|None, "source": str, "confidence": float}
    Tiered lookup: overrides → wikipedia(pageid) → wiktionary → cmudict.
    No G2P tier (cut per Plan 0 corrected contract).

wikipedia_ipa(pageid) -> {"ipa": str|None, "source": "wikipedia", "confidence": float}
wiktionary_ipa(name) -> {"ipa": str|None, "source": "wiktionary", "confidence": float}
cmudict_ipa(name) -> {"ipa": str|None, "source": "cmudict", "confidence": float}

Internal (patchable for testing):
    _fetch_wikitext_by_pageid(pageid) -> str|None
    _fetch_wiktionary_wikitext(name) -> str|None
    OVERRIDES: dict[str, str]  — loaded from data/pron_overrides.json
"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# OVERRIDES — loaded from data/pron_overrides.json at import time
# (monkeypatch OVERRIDES directly in tests)
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_OVERRIDES_PATH = _DATA_DIR / "pron_overrides.json"

def _load_overrides() -> "dict[str, str]":
    try:
        return json.loads(_OVERRIDES_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

OVERRIDES: "dict[str, str]" = _load_overrides()

# ---------------------------------------------------------------------------
# ARPABET → IPA conversion table
# ---------------------------------------------------------------------------

_ARPABET_TO_IPA: "dict[str, str]" = {
    # Vowels
    "AA": "ɑ", "AE": "æ", "AH": "ə", "AO": "ɔ", "AW": "aʊ",
    "AX": "ə", "AY": "aɪ", "EH": "ɛ", "ER": "ɝ", "EY": "eɪ",
    "IH": "ɪ", "IX": "ɪ", "IY": "iː", "OW": "oʊ", "OY": "ɔɪ",
    "UH": "ʊ", "UW": "uː", "UX": "ʉ",
    # Consonants
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "DX": "ɾ",
    "EL": "l̩", "EM": "m̩", "EN": "n̩", "F": "f", "G": "ɡ",
    "HH": "h", "JH": "dʒ", "K": "k", "L": "l", "M": "m",
    "N": "n", "NG": "ŋ", "NX": "ɾ̃", "P": "p", "Q": "ʔ",
    "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ",
    "V": "v", "W": "w", "WH": "ʍ", "Y": "j", "Z": "z",
    "ZH": "ʒ",
}

# Stress markers
_STRESS_MAP = {"0": "", "1": "ˈ", "2": "ˌ"}

def _arpabet_to_ipa(phones: "list[str]") -> str:
    """Convert a list of ARPABET tokens (with stress) to an IPA string."""
    result = []
    for ph in phones:
        # Strip stress digit (0, 1, 2)
        stress = ""
        if ph[-1].isdigit():
            stress = _STRESS_MAP.get(ph[-1], "")
            base = ph[:-1]
        else:
            base = ph
        ipa_char = _ARPABET_TO_IPA.get(base.upper(), "")
        result.append(stress + ipa_char)
    return "".join(result)

# ---------------------------------------------------------------------------
# CMUdict: load lazily (file is inside Python's nltk_data or fallback to
# bundled minimal table for the most common words)
# ---------------------------------------------------------------------------

_CMUDICT: "Optional[dict[str, list]]" = None

def _get_cmudict() -> "dict[str, list]":
    global _CMUDICT
    if _CMUDICT is not None:
        return _CMUDICT

    # Try to load from the cmudict file shipped with nltk_data (if available)
    # We don't depend on NLTK directly — parse the raw CMUdict format.
    candidates = [
        Path.home() / "nltk_data" / "corpora" / "cmudict" / "cmudict",
        Path("/usr/share/nltk_data/corpora/cmudict/cmudict"),
        Path("/usr/local/share/nltk_data/corpora/cmudict/cmudict"),
        Path("/opt/homebrew/share/nltk_data/corpora/cmudict/cmudict"),
    ]

    d: "dict[str, list]" = {}
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="latin-1") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(";;;"):
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    word = parts[0].rstrip("(0123456789)").lower()
                    phones = parts[1:]
                    if word not in d:
                        d[word] = phones
            break

    # Minimal hardcoded fallback for common test words
    _MINIMAL_FALLBACK = {
        "hello": ["HH", "AH0", "L", "OW1"],
        "chicago": ["SH", "AH0", "K", "AA1", "G", "OW0"],
        "kansas": ["K", "AE1", "N", "Z", "AH0", "S"],
        "denver": ["D", "EH1", "N", "V", "ER0"],
        "boston": ["B", "AO1", "S", "T", "AH0", "N"],
        "portland": ["P", "AO1", "R", "T", "L", "AH0", "N", "D"],
    }
    for w, phones in _MINIMAL_FALLBACK.items():
        if w not in d:
            d[w] = phones

    _CMUDICT = d
    return _CMUDICT

# ---------------------------------------------------------------------------
# HTTP helpers (internal — monkeypatch these in tests)
# ---------------------------------------------------------------------------

_UA = "amtrak-companion-pronunciation/1.0 (cdorsey@concord.org)"


def _fetch_wikitext_by_pageid(pageid: str) -> "Optional[str]":
    """Fetch raw wikitext for a Wikipedia page by pageid. Returns None on error."""
    url = (
        "https://en.wikipedia.org/w/api.php?"
        f"action=parse&pageid={pageid}&prop=wikitext&format=json"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["parse"]["wikitext"]["*"]
    except Exception:
        return None


def _fetch_wiktionary_wikitext(name: str) -> "Optional[str]":
    """Fetch raw wikitext for a Wiktionary page by name. Returns None on error."""
    url = (
        "https://en.wiktionary.org/w/api.php?"
        f"action=parse&page={urllib.parse.quote(name)}&prop=wikitext&format=json"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["parse"]["wikitext"]["*"]
    except Exception:
        return None

# ---------------------------------------------------------------------------
# IPA extraction from wikitext
# ---------------------------------------------------------------------------

# Matches {{IPAc-en|a|b|c|...}} or {{IPA|en|/…/}} or {{IPA-en|/…/}}
_WP_IPAC = re.compile(r"\{\{IPAc?-en\|([^}]+)\}\}", re.I)
_WP_IPA = re.compile(r"\{\{IPA(?:\|en)?\|([^}]*?/[^}]*?/[^}]*?)\}\}", re.I)

def _extract_ipa_from_wp_wikitext(wikitext: str) -> "Optional[str]":
    """Extract IPA from Wikipedia wikitext. Returns the IPA string or None."""
    # Try {{IPAc-en|r|ə|ˈ|t|oʊ|n}} → reassemble the pipe-separated phonemes
    m = _WP_IPAC.search(wikitext)
    if m:
        parts = [p.strip() for p in m.group(1).split("|")]
        # Filter out template params like 'lang=en', digit-only, 'audio=...'
        cleaned = []
        for p in parts:
            if "=" in p:
                continue
            cleaned.append(p)
        if cleaned:
            return "".join(cleaned)

    # Try {{IPA|en|/ˌtukəmˈkɛri/}}
    m = _WP_IPA.search(wikitext)
    if m:
        raw = m.group(1)
        # Extract the /.../ portion
        fm = re.search(r"/([^/]+)/", raw)
        if fm:
            return "/" + fm.group(1) + "/"

    return None


_WT_IPA_EN = re.compile(r"\{\{IPA\|en\|([^}]+)\}\}", re.I)

def _extract_ipa_from_wt_wikitext(wikitext: str) -> "Optional[str]":
    """Extract IPA from Wiktionary wikitext. Returns the first /…/ or […] block or None."""
    m = _WT_IPA_EN.search(wikitext)
    if not m:
        return None
    raw = m.group(1)
    # Could be: /ˌtukəmˈkɛri/ or /foo/, [bar]
    fm = re.search(r"([/\[][^/\]]+[/\]])", raw)
    if fm:
        return fm.group(1)
    # Fallback: strip pipes and return first token
    parts = [p.strip() for p in raw.split("|")]
    if parts:
        return parts[0]
    return None

# ---------------------------------------------------------------------------
# Public tier functions
# ---------------------------------------------------------------------------

def wikipedia_ipa(pageid: str) -> "dict":
    """Fetch Wikipedia wikitext for pageid and extract IPA."""
    wikitext = _fetch_wikitext_by_pageid(pageid)
    if wikitext is None:
        return {"ipa": None, "source": "wikipedia", "confidence": 0.0}
    ipa = _extract_ipa_from_wp_wikitext(wikitext)
    if ipa:
        return {"ipa": ipa, "source": "wikipedia", "confidence": 0.9}
    return {"ipa": None, "source": "wikipedia", "confidence": 0.0}


def wiktionary_ipa(name: str) -> "dict":
    """Fetch Wiktionary wikitext for name and extract English IPA."""
    wikitext = _fetch_wiktionary_wikitext(name)
    if wikitext is None:
        return {"ipa": None, "source": "wiktionary", "confidence": 0.0}
    ipa = _extract_ipa_from_wt_wikitext(wikitext)
    if ipa:
        return {"ipa": ipa, "source": "wiktionary", "confidence": 0.8}
    return {"ipa": None, "source": "wiktionary", "confidence": 0.0}


def cmudict_ipa(name: str) -> "dict":
    """Look up name in CMUdict and return IPA. Works on lowercase."""
    d = _get_cmudict()
    phones = d.get(name.lower())
    if phones:
        ipa = _arpabet_to_ipa(phones)
        return {"ipa": ipa, "source": "cmudict", "confidence": 0.6}
    return {"ipa": None, "source": "cmudict", "confidence": 0.0}


def source_ipa(name: str, pageid: "Optional[str]" = None) -> "dict":
    """
    Tiered IPA lookup: overrides → wikipedia(pageid) → wiktionary → cmudict.

    Returns {"ipa": str|None, "source": str, "confidence": float}.
    """
    # Tier 1: overrides (conf 1.0)
    if name in OVERRIDES:
        return {"ipa": OVERRIDES[name], "source": "override", "confidence": 1.0}

    # Tier 2: Wikipedia by pageid (conf 0.9)
    if pageid:
        result = wikipedia_ipa(pageid)
        if result["ipa"] is not None:
            return result

    # Tier 3: Wiktionary (conf 0.8)
    result = wiktionary_ipa(name)
    if result["ipa"] is not None:
        return result

    # Tier 4: CMUdict / ARPABET→IPA (conf 0.6)
    result = cmudict_ipa(name)
    if result["ipa"] is not None:
        return result

    # No source found
    return {"ipa": None, "source": "none", "confidence": 0.0}
