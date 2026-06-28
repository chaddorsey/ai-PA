"""Tests for pipeline.proper_nouns — proper-noun extraction."""
from pipeline.proper_nouns import extract_proper_nouns


# ---------------------------------------------------------------------------
# Plan 1 Task 1 canonical test
# ---------------------------------------------------------------------------

def test_extracts_place_names_from_lore_titles_and_text():
    narr = {"3": [{"kind": "squib", "mile": 1087, "place": "Morley, Colorado",
                   "text": "Morley was a coal town."}]}
    lore = {"3": {"lore": [{"id": "w12345", "title": "Morley, Colorado", "peak_mi": 1087}]}}
    conn = {"3": {"nodes": {"w1": {"title": "Morley, Colorado", "named_after": None}}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Morley" in out, f"expected 'Morley' in {list(out.keys())[:20]}"
    assert out["Morley"]["kind"] == "place"


# ---------------------------------------------------------------------------
# Person extraction (named_after)
# ---------------------------------------------------------------------------

def test_extracts_person_from_named_after():
    narr = {"3": [{"kind": "squib", "mile": 10, "place": "Lincoln, Nebraska",
                   "text": "Named after Abraham Lincoln by settlers."}]}
    lore = {"3": {"lore": []}}
    conn = {"3": {"nodes": {"w999": {"title": "Lincoln, Nebraska",
                                      "named_after": "Abraham Lincoln"}}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Abraham Lincoln" in out or "Lincoln" in out
    # At least one of the person names should be marked 'person'
    person_entries = [k for k, v in out.items() if v["kind"] == "person"]
    assert len(person_entries) >= 1, f"no persons extracted; got: {out}"


# ---------------------------------------------------------------------------
# Stoplist / noise-filter tests
# ---------------------------------------------------------------------------

def test_common_words_not_extracted():
    """Words from the common-word stoplist must not appear as proper nouns."""
    narr = {"3": [{"kind": "squib", "mile": 100, "place": "Denver, Colorado",
                   "text": "The state line is just ahead. Look for the Santa Fe railroad."}]}
    lore = {"3": {"lore": []}}
    conn = {"3": {"nodes": {}}}
    out = extract_proper_nouns(narr, lore, conn)
    # "state line", "look", "just" should never appear
    assert "state line" not in out
    assert "State" not in out or out.get("State", {}).get("kind") != "place"
    assert "Look" not in out

def test_quaternary_sediment_not_extracted():
    """Scientific/geologic terms that slip in as capitalized text shouldn't appear."""
    narr = {"3": [{"kind": "squib", "mile": 200, "place": "Raton, New Mexico",
                   "text": "Quaternary sediment layers underlie this valley."}]}
    lore = {"3": {"lore": []}}
    conn = {"3": {"nodes": {}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Quaternary" not in out, f"'Quaternary' should be filtered; got: {list(out.keys())[:30]}"
    assert "Quaternary sediment" not in out

def test_count_reflects_spoken_occurrences():
    """Count = how many times the name appears in unit text (not just titles)."""
    narr = {"3": [{"kind": "squib", "mile": 1087, "place": "Raton, New Mexico",
                   "text": "Raton Pass is famous. Raton is a gateway."},
                  {"kind": "squib", "mile": 1090, "place": "Maxwell, New Mexico",
                   "text": "Maxwell Land Grant borders Raton to the north."}]}
    lore = {"3": {"lore": [{"id": "w11111", "title": "Raton, New Mexico", "peak_mi": 1087}]}}
    conn = {"3": {"nodes": {}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Raton" in out
    assert out["Raton"]["count"] == 3, f"expected count=3, got {out.get('Raton', {}).get('count')}"


def test_multi_leg_name_aggregates():
    """A name that appears in multiple legs accumulates count + leg list."""
    narr = {
        "3":  [{"kind": "squib", "mile": 1, "place": "Chicago, Illinois",
                "text": "Chicago skyline to the east."}],
        "11": [{"kind": "squib", "mile": 2, "place": "Chicago, Illinois",
                "text": "Chicago is massive."}],
    }
    lore = {"3": {"lore": []}, "11": {"lore": []}}
    conn = {"3": {"nodes": {}}, "11": {"nodes": {}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Chicago" in out
    assert set(out["Chicago"]["legs"]) == {"3", "11"}
    assert out["Chicago"]["count"] == 2


def test_lore_id_carried_as_pageid():
    """Wikipedia pageid from lore id field (strips leading 'w') is preserved."""
    narr = {"3": [{"kind": "squib", "mile": 50, "place": "Cicero, Illinois",
                   "text": "Cicero was once notorious."}]}
    lore = {"3": {"lore": [{"id": "w110961", "title": "Cicero, Illinois", "peak_mi": 50}]}}
    conn = {"3": {"nodes": {}}}
    out = extract_proper_nouns(narr, lore, conn)
    assert "Cicero" in out
    assert out["Cicero"].get("pageid") == "110961", f"expected pageid '110961', got {out.get('Cicero', {}).get('pageid')}"
