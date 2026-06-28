"""Tests for pipeline/lexicon.py — lexicon building + custompron trust gate."""


def test_only_trusted_entries_emit_custompron(monkeypatch):
    """Lamar has no override and no auto-source IPA → must NOT appear in custompron."""
    import pipeline.sources as src
    # Mock all auto-sources so Lamar gets nothing (isolate from live HTTP)
    monkeypatch.setattr(src, "OVERRIDES", {"Raton": "rəˈtoʊn"})
    monkeypatch.setattr(src, "_fetch_wikitext_by_pageid", lambda pid: None)
    monkeypatch.setattr(src, "_fetch_wiktionary_wikitext", lambda name: None)

    from pipeline.lexicon import build_lexicon, custompron_for
    pn = {"Raton": {"count": 5, "legs": ["3"], "kind": "place", "pageid": None},
          "Lamar": {"count": 1, "legs": ["3"], "kind": "place", "pageid": None}}
    ov = {"Raton": "rəˈtoʊn"}   # Lamar has no override
    lex = build_lexicon(pn, ov)
    assert lex["Raton"]["ipa"] == "rəˈtoʊn"
    assert lex["Raton"]["confidence"] == 1.0
    # Lamar: no override, no wiki/wiktionary (mocked out), not in cmudict → no IPA
    # → must NOT appear in custompron
    cps = custompron_for("Ahead lies Raton Pass near Lamar.", lex)
    assert cps == [{"phrase": "Raton",
                    "phoneticEncoding": "PHONETIC_ENCODING_IPA",
                    "pronunciation": "rəˈtoʊn"}]


def test_lexicon_carries_risk_and_freq():
    from pipeline.lexicon import build_lexicon
    pn = {"Tucumcari": {"count": 3, "legs": ["3"], "kind": "place", "pageid": None}}
    ov = {"Tucumcari": "ˌtukəmˈkɛri"}
    lex = build_lexicon(pn, ov)
    entry = lex["Tucumcari"]
    assert "risk" in entry
    assert "freq" in entry
    assert entry["freq"] == 3
    assert 0.0 <= entry["risk"] <= 1.0


def test_low_confidence_entry_not_in_custompron(monkeypatch):
    """An entry sourced only from cmudict (conf 0.6) must NOT emit custompron."""
    import pipeline.sources as src
    from pipeline.lexicon import build_lexicon, custompron_for

    # Force cmudict as the only source so confidence = 0.6
    monkeypatch.setattr(src, "OVERRIDES", {})
    monkeypatch.setattr(src, "wikipedia_ipa", lambda pageid: {"ipa": None, "source": "wikipedia", "confidence": 0.0})
    monkeypatch.setattr(src, "wiktionary_ipa", lambda name: {"ipa": None, "source": "wiktionary", "confidence": 0.0})

    pn = {"Denver": {"count": 5, "legs": ["3"], "kind": "place", "pageid": None}}
    ov = {}
    lex = build_lexicon(pn, ov)
    cps = custompron_for("Welcome to Denver.", lex)
    # Denver from cmudict only → confidence 0.6 < 0.8 → no custompron
    assert cps == []


def test_custompron_for_multiple_trusted_terms():
    from pipeline.lexicon import build_lexicon, custompron_for
    pn = {
        "Raton": {"count": 5, "legs": ["3"], "kind": "place", "pageid": None},
        "Cimarron": {"count": 3, "legs": ["3"], "kind": "place", "pageid": None},
    }
    ov = {"Raton": "rəˈtoʊn", "Cimarron": "ˈsɪmərɑn"}
    lex = build_lexicon(pn, ov)
    text = "Between Raton and Cimarron lies the pass."
    cps = custompron_for(text, lex)
    phrases = {cp["phrase"] for cp in cps}
    assert "Raton" in phrases
    assert "Cimarron" in phrases


def test_custompron_word_boundary_match():
    """'Raton' must not match inside 'Ratoner' or similar."""
    from pipeline.lexicon import build_lexicon, custompron_for
    pn = {"Raton": {"count": 5, "legs": ["3"], "kind": "place", "pageid": None}}
    ov = {"Raton": "rəˈtoʊn"}
    lex = build_lexicon(pn, ov)
    # 'Rationalization' should not match 'Raton'
    cps = custompron_for("Rationalization is key.", lex)
    assert cps == []


def test_build_lexicon_returns_all_entries():
    """build_lexicon includes ALL proper nouns, not just trusted ones."""
    from pipeline.lexicon import build_lexicon
    pn = {
        "Raton": {"count": 5, "legs": ["3"], "kind": "place", "pageid": None},
        "SomeUnknownPlace": {"count": 1, "legs": ["3"], "kind": "place", "pageid": None},
    }
    ov = {"Raton": "rəˈtoʊn"}
    lex = build_lexicon(pn, ov)
    assert "Raton" in lex
    assert "SomeUnknownPlace" in lex
