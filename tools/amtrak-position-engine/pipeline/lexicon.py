"""
pipeline/lexicon.py — Task 2: Build and apply the pronunciation lexicon.

Public API
----------
build_lexicon(proper_nouns, overrides) -> dict[str, dict]
    term -> {"ipa": str|None, "source": str, "confidence": float,
             "risk": float, "freq": int}

custompron_for(text, lexicon) -> list[dict]
    Returns [{"phrase", "phoneticEncoding": "PHONETIC_ENCODING_IPA",
              "pronunciation"}] for TRUSTED terms (confidence >= 0.8 or override)
    that appear in the text.
"""

import re
from typing import Optional

# Trust gate: terms with confidence < this are NOT emitted as customPronunciations
_TRUST_THRESHOLD = 0.8

# Phonetic encoding constant for Google TTS
_PHONETIC_ENCODING_IPA = "PHONETIC_ENCODING_IPA"


def build_lexicon(
    proper_nouns: "dict[str, dict]",
    overrides: "dict[str, str]",
) -> "dict[str, dict]":
    """
    Build the pronunciation lexicon from the proper nouns dict and overrides.

    Parameters
    ----------
    proper_nouns : {name: {"count": int, "legs": [...], "kind": str, "pageid": str|None}}
        Output of extract_proper_nouns.
    overrides : {name: ipa_str}
        Hand-curated IPA overrides (confidence 1.0).

    Returns
    -------
    {term: {"ipa": str|None, "source": str, "confidence": float,
            "risk": float, "freq": int}}
    """
    from pipeline.sources import source_ipa
    from pipeline.risk import risk_score

    lexicon: "dict[str, dict]" = {}

    for name, info in proper_nouns.items():
        pageid = info.get("pageid")
        freq = info.get("count", 0)

        # Override check is done inside source_ipa, but we also check the
        # passed-in overrides dict (which may differ from the loaded file).
        if name in overrides:
            ipa_result = {
                "ipa": overrides[name],
                "source": "override",
                "confidence": 1.0,
            }
        else:
            ipa_result = source_ipa(name, pageid=pageid)

        lexicon[name] = {
            "ipa": ipa_result["ipa"],
            "source": ipa_result["source"],
            "confidence": ipa_result["confidence"],
            "risk": risk_score(name),
            "freq": freq,
        }

    return lexicon


def custompron_for(text: str, lexicon: "dict[str, dict]") -> "list[dict]":
    """
    Return a list of customPronunciations entries for TRUSTED terms in text.

    Only terms whose confidence >= _TRUST_THRESHOLD (or source == "override")
    are included. Terms are matched at word boundaries.

    Parameters
    ----------
    text    : The narration text to search.
    lexicon : Output of build_lexicon.

    Returns
    -------
    [{"phrase": str,
      "phoneticEncoding": "PHONETIC_ENCODING_IPA",
      "pronunciation": str}]
    Sorted by descending phrase length to prefer longer matches.
    """
    # Sort by length descending so multi-word phrases take priority over
    # single-word subsets
    candidates = [
        (name, entry)
        for name, entry in lexicon.items()
        if entry.get("ipa") is not None
        and (entry.get("source") == "override"
             or entry.get("confidence", 0.0) >= _TRUST_THRESHOLD)
    ]
    # Sort by phrase length descending
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    results = []
    # Track matched spans so we don't double-match subsets
    matched_spans: "list[tuple[int, int]]" = []

    for name, entry in candidates:
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            # Check for overlap with already-matched spans
            overlaps = any(
                not (end <= ms or start >= me)
                for ms, me in matched_spans
            )
            if overlaps:
                continue
            matched_spans.append((start, end))
            results.append({
                "phrase": name,
                "phoneticEncoding": _PHONETIC_ENCODING_IPA,
                "pronunciation": entry["ipa"],
            })

    # Return in text order (sort by start position captured above is tricky
    # since we iterated by candidate; sort results by appearance in text)
    results.sort(key=lambda r: text.index(r["phrase"]) if r["phrase"] in text else 0)

    # Deduplicate (same phrase could match multiple times; keep first occurrence only)
    seen_phrases: "set[str]" = set()
    deduped = []
    for r in results:
        if r["phrase"] not in seen_phrases:
            seen_phrases.add(r["phrase"])
            deduped.append(r)

    return deduped
