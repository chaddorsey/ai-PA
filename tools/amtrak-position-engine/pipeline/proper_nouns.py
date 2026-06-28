"""
pipeline/proper_nouns.py — Task 1: Extract proper nouns from the route corpus.

Public API
----------
extract_proper_nouns(narration, lore, connections) -> dict[str, dict]
    Returns: {name: {"count": int, "legs": [str], "kind": "place"|"person"|"other",
                     "pageid": str|None}}

write_proper_nouns(path) -> None
    Loads real data files, extracts, writes sorted JSON.
"""
import json
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Common-word stoplist
# Words (and phrases) that may appear capitalized in the text but are NOT
# proper nouns we want to pronounce specially.  This list is intentionally
# broad — better to miss a marginal name than to include noise.
# ---------------------------------------------------------------------------
_STOPLIST_WORDS = {
    # Articles / prepositions
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "by", "with",
    "from", "as", "into", "through", "across", "along", "over", "under",
    "above", "below", "between", "among", "around", "near", "about",
    "up", "down", "out", "off", "if", "or", "and", "but", "so", "yet",
    "nor", "not",
    # Pronouns and contractions (We're, It's, That's, etc.)
    "i", "we", "our", "us", "you", "your", "they", "their", "them",
    "he", "she", "it", "his", "her", "its", "who", "what", "which",
    # Common verbs that start sentences
    "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "must", "shall", "can",
    # Time / relative
    "today", "now", "year", "years", "century", "decade", "decades", "era",
    "morning", "afternoon", "evening", "night", "day", "days",
    "past", "present", "future", "early", "late", "recent", "once",
    # Interrogatives / demonstratives that appear capitalized
    "look", "watch", "notice", "see", "just", "ahead", "behind",
    "here", "there", "this", "that", "these", "those",
    # Very common nouns that happen to capitalise
    "line", "state", "states", "county", "city", "town", "village",
    "river", "creek", "lake", "basin", "valley", "canyon", "pass",
    "mountain", "mountains", "hill", "hills", "plain", "plains",
    "desert", "range", "ridge", "peak", "summit",
    "road", "route", "highway", "trail", "bridge", "junction",
    "station", "depot", "terminal", "port", "harbor", "bay",
    "north", "south", "east", "west", "northern", "southern",
    "eastern", "western", "central", "upper", "lower",
    "united", "federal", "national", "american",
    # Geologic / scientific capitalized terms
    "quaternary", "jurassic", "cretaceous", "permian", "cambrian",
    "holocene", "pleistocene", "cenozoic", "mesozoic", "paleozoic",
    "sediment", "formation", "limestone", "granite", "basalt",
    # Other noise caught in real data
    "land", "grant", "ranch", "farm", "acres", "mile", "miles",
    "named", "known", "called", "built", "opened", "founded",
    "world", "great", "new", "old", "first", "last", "next",
    "second", "third", "high", "low", "long", "short", "wide",
    "large", "small", "big", "little", "many", "few", "most",
    "main", "major", "minor", "local", "regional",
    # Common adjectives/adverbs
    "spanish", "french", "english", "german", "chinese", "japanese",
    "native", "american", "western", "eastern",
    "civil", "welcome", "commerce", "trail", "union",
    "pacific", "gulf", "atlantic", "continental", "coast",
    "european", "african",
    # Sentence starters / common determiners that appear capitalized
    "every", "each", "both", "some", "any", "all", "no", "none",
    "when", "where", "while", "once", "before", "after", "since",
    "though", "although", "because", "unless", "until", "whether",
    "then", "than", "very", "more", "less", "much", "such", "only",
    "even", "still", "already", "always", "never", "sometimes",
    "often", "usually", "generally", "eventually", "finally", "later",
    "perhaps", "probably", "certainly", "clearly", "simply",
    # Single-word fragments that appear from multi-word phrases but aren't
    # standalone proper nouns worth extracting
    "mail", "rail", "pale", "black", "white", "red", "blue", "green",
    "gold", "silver", "iron", "steel", "coal", "oil", "gas",
    "rock", "stone", "sand", "clay", "water", "fire", "air",
    "light", "dark", "bright", "deep", "wide", "fast", "slow",
    "hot", "cold", "dry", "wet", "wild", "free", "open", "flat",
    "southwest", "southeast", "northwest", "northeast",
    "midwest", "midway", "inland",
    # These appear as fragments of place-names but are non-standalone
    "grande", "rio", "del", "de", "la", "los", "las", "san", "santa",
    "saint", "fort", "mount", "lake", "cape", "bay", "isle",
    "louis", "jose", "pedro", "barbara", "ana", "cruz", "juan",
    "antonio", "diego", "francisco", "angeles",
    # Common nouns and adjectives that appear capitalized mid-text
    "war", "army", "navy", "corps", "guard", "unit", "units", "troop",
    "nation", "nations", "sea", "ocean", "sky", "sun", "moon", "star",
    "pop", "population", "era", "age", "period",
    "other", "others", "another", "same", "different",
    "mexican", "canadian", "texan", "californian",
    "native", "indigenous", "tribal", "federal", "colonial",
    "industrial", "agricultural", "commercial", "residential",
    "democratic", "republican",
    # More geologic era terms
    "miocene", "oligocene", "eocene", "paleocene", "pliocene",
    "devonian", "ordovician", "silurian", "triassic",
    # Common given names that appear standalone as fragments
    # NOTE: do NOT add names that are standalone historical figures
    # (e.g., "Harvey" = Fred Harvey; "John" alone is too ambiguous)
    "francis",  # fragments like "St. Francis" -- the full compound is captured
}

# Multi-word stoplist phrases (lowercased for comparison)
_STOPLIST_PHRASES = {
    "state line", "county line", "city limits",
    "national park", "national forest", "state park",
    "iron horse", "land grant", "right of way",
    "sea level",
}

# ---------------------------------------------------------------------------
# Suffixes / tokens that indicate a term is NOT a proper noun when the
# *base word alone* is a generic descriptor.
# ---------------------------------------------------------------------------
_GENERIC_SUFFIXES = {
    "creek", "river", "lake", "ridge", "range", "peak", "hill", "hills",
    "valley", "canyon", "pass", "plain", "plains", "desert", "basin",
    "mountain", "mountains", "county", "city", "town", "station",
    "junction", "state", "highway", "road", "trail", "bridge", "harbor",
    "bay", "port", "line", "yard",
}


def _is_stopword(token: str) -> bool:
    return token.lower() in _STOPLIST_WORDS


def _is_phrase_noise(phrase: str) -> bool:
    return phrase.lower() in _STOPLIST_PHRASES


def _core_name(title: str) -> str:
    """'Morley, Colorado' -> 'Morley'; 'Cicero (town)' -> 'Cicero'."""
    return title.split(",")[0].split(" (")[0].strip()


def _is_clean_proper_noun(name: str) -> bool:
    """Return True if *name* passes basic noise filters."""
    if not name or len(name) <= 2:
        return False
    # Must start with a capital letter
    if not name[0].isupper():
        return False
    # Reject contractions and possessives (We're, It's, Trail's, etc.)
    if "'" in name or "’" in name:
        return False
    # If the whole phrase is in the stop-phrase list
    if _is_phrase_noise(name):
        return False
    # All tokens must pass: at least one non-stopword token
    tokens = name.split()
    if all(_is_stopword(t) for t in tokens):
        return False
    # Single token that is only a generic suffix → noise
    if len(tokens) == 1 and tokens[0].lower() in _GENERIC_SUFFIXES:
        return False
    # For single-token names: reject if the word itself is a stopword
    if len(tokens) == 1:
        if name.lower() in _STOPLIST_WORDS:
            return False
        if name.lower() in _GENERIC_SUFFIXES:
            return False
    # For multi-word names: reject if ALL tokens are stopwords
    # (already covered above), but also reject if first token is a
    # known article/preposition/pronoun that can't start a place name
    _LEADING_STOPWORDS = {
        "a", "an", "the", "of", "in", "on", "at", "to", "for", "by",
        "with", "from", "as", "or", "and", "but", "so", "nor", "not",
        "if", "is", "are", "was", "were", "be", "been",
        "do", "does", "did", "will", "would", "could", "should",
        "i", "we", "our", "us", "you", "your", "they", "their", "them",
        "he", "she", "it", "his", "her", "its", "who", "what", "which",
    }
    if len(tokens) > 1 and tokens[0].lower() in _LEADING_STOPWORDS:
        return False
    return True


# ---------------------------------------------------------------------------
# Candidate extraction from text (capitalized multi-word sequences)
# ---------------------------------------------------------------------------

# Matches a run of 1–4 capitalized words (Title Case tokens).
# Exclude tokens containing apostrophes (contractions like We're, It's, That's).
_CAP_RUN = re.compile(
    r'\b([A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+){0,3})\b'
)


def _text_candidates(text: str) -> list:
    """Return all capitalized-run candidates found in *text*."""
    return [m.group(1) for m in _CAP_RUN.finditer(text)]


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_proper_nouns(
    narration: dict,
    lore: dict,
    connections: dict,
) -> "dict[str, dict]":
    """
    Extract proper nouns from narration, lore, and connections.

    Parameters
    ----------
    narration   : leg -> [unit-dict, ...]
    lore        : leg -> {"lore": [poi-dict, ...], ...}
    connections : leg -> {"nodes": {id: node-dict, ...}, ...}

    Returns
    -------
    {name: {"count": int, "legs": [str], "kind": "place"|"person"|"other",
             "pageid": str|None}}
    """
    # registry: core_name -> {kind, pageid, legs_set, count}
    registry: "dict[str, dict]" = {}

    def _register(name: str, kind: str, leg: str, pageid: Optional[str] = None, count: int = 0) -> None:
        """Add or update an entry in the registry."""
        if not _is_clean_proper_noun(name):
            return
        if name not in registry:
            registry[name] = {"kind": kind, "pageid": None, "legs": set(), "count": 0}
        entry = registry[name]
        # kind priority: person > place > other
        if kind == "person":
            entry["kind"] = "person"
        elif kind == "place" and entry["kind"] == "other":
            entry["kind"] = "place"
        if pageid and not entry["pageid"]:
            entry["pageid"] = pageid
        entry["legs"].add(leg)
        entry["count"] += count

    # ---- (a) lore titles → place ----------------------------------------
    for leg, d in lore.items():
        for poi in d.get("lore", []):
            title = poi.get("title", "")
            pid_raw = str(poi.get("id", ""))
            pageid = pid_raw[1:] if pid_raw.startswith("w") else (pid_raw or None)
            core = _core_name(title)
            if core:
                _register(core, "place", leg, pageid=pageid)
            # Also register the full title as an alias if different
            full_core = title.split(" (")[0].strip()
            if full_core and full_core != core:
                full_base = full_core.split(",")[0].strip()
                _register(full_base, "place", leg, pageid=pageid)

    # ---- (b) connections nodes and named_after ---------------------------
    for leg, d in connections.items():
        for nid, node in d.get("nodes", {}).items():
            node_title = node.get("title", "")
            if node_title:
                core = _core_name(node_title)
                _register(core, "place", leg)

            named_after = node.get("named_after")
            if named_after:
                # named_after is a person name string
                core_na = _core_name(named_after)
                _register(core_na, "person", leg)
                # Also register the full name if it's multi-word
                if named_after != core_na and _is_clean_proper_noun(named_after):
                    _register(named_after, "person", leg)

    # ---- (c) narration: place fields + capitalized runs in text ----------
    # Build a per-leg text blob for efficient substring counting
    for leg, units in narration.items():
        leg_text_parts = []
        for unit in units:
            # place field
            place = unit.get("place", "")
            if place:
                core = _core_name(place)
                _register(core, "place", leg)

            text = unit.get("text", "")
            leg_text_parts.append(text)

            # capitalized runs from text
            for cand in _text_candidates(text):
                core = _core_name(cand)
                _register(core, "place", leg)  # kind=place as default; persons come from named_after

        # Now count occurrences of each registered name across this leg's full text
        leg_blob = " ".join(leg_text_parts)
        for name in list(registry.keys()):
            if leg in registry[name]["legs"]:
                occ = leg_blob.count(name)
                # We'll recount properly below — just ensure leg is registered
                # (count already accumulated; we'll reset and recount globally)

    # ---- Recount globally: count = occurrences across ALL unit text ------
    # Build full corpus blob
    all_text_by_leg: "dict[str, str]" = {}
    for leg, units in narration.items():
        all_text_by_leg[leg] = " ".join(u.get("text", "") for u in units)

    full_blob = " ".join(all_text_by_leg.values())

    for name, entry in registry.items():
        entry["count"] = full_blob.count(name)

    # ---- Serialise legs set -> sorted list --------------------------------
    result: "dict[str, dict]" = {}
    for name, entry in sorted(registry.items()):
        result[name] = {
            "count": entry["count"],
            "legs": sorted(entry["legs"]),
            "kind": entry["kind"],
            "pageid": entry["pageid"],
        }

    return result


# ---------------------------------------------------------------------------
# write_proper_nouns
# ---------------------------------------------------------------------------

def write_proper_nouns(path: "Path | str") -> None:
    """
    Load real data, run extract_proper_nouns, write sorted JSON to *path*.
    """
    base = Path(__file__).resolve().parent.parent  # tools/amtrak-position-engine/
    narration = json.loads((base / "data" / "route_narration.json").read_text())
    lore = json.loads((base / "data" / "route_lore.json").read_text())
    connections = json.loads((base / "data" / "route_connections.json").read_text())

    proper_nouns = extract_proper_nouns(narration, lore, connections)

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(proper_nouns, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(proper_nouns)} proper nouns → {out_path}")
