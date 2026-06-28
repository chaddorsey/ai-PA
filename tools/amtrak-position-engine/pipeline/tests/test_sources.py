"""Tests for pipeline/sources.py — tiered IPA sourcing."""
import pytest


# ---------------------------------------------------------------------------
# Helper: patch OVERRIDES and HTTP at the module level
# ---------------------------------------------------------------------------

def test_override_beats_all_and_source_is_tagged(monkeypatch):
    import pipeline.sources as src
    monkeypatch.setattr(src, "OVERRIDES", {"Raton": "rəˈtoʊn"})
    r = src.source_ipa("Raton")
    assert r["ipa"] == "rəˈtoʊn"
    assert r["source"] == "override"
    assert r["confidence"] == 1.0


def test_no_override_falls_through_to_wikipedia(monkeypatch):
    import pipeline.sources as src
    monkeypatch.setattr(src, "OVERRIDES", {})
    monkeypatch.setattr(src, "wikipedia_ipa", lambda pageid: {"ipa": "/ˌtukəmˈkɛri/", "source": "wikipedia", "confidence": 0.9})
    r = src.source_ipa("Tucumcari", pageid="12345")
    assert r["source"] == "wikipedia"
    assert r["confidence"] == 0.9
    assert r["ipa"] is not None


def test_wikipedia_miss_falls_to_wiktionary(monkeypatch):
    import pipeline.sources as src
    monkeypatch.setattr(src, "OVERRIDES", {})
    monkeypatch.setattr(src, "wikipedia_ipa", lambda pageid: {"ipa": None, "source": "wikipedia", "confidence": 0.0})
    monkeypatch.setattr(src, "wiktionary_ipa", lambda name: {"ipa": "/ˌtukəmˈkɛri/", "source": "wiktionary", "confidence": 0.8})
    r = src.source_ipa("Tucumcari", pageid="12345")
    assert r["source"] == "wiktionary"
    assert r["confidence"] == 0.8


def test_wiktionary_miss_falls_to_cmudict(monkeypatch):
    import pipeline.sources as src
    monkeypatch.setattr(src, "OVERRIDES", {})
    monkeypatch.setattr(src, "wikipedia_ipa", lambda pageid: {"ipa": None, "source": "wikipedia", "confidence": 0.0})
    monkeypatch.setattr(src, "wiktionary_ipa", lambda name: {"ipa": None, "source": "wiktionary", "confidence": 0.0})
    # "Chicago" is in CMUdict: SH AH0 K AA1 G OW0
    r = src.source_ipa("Chicago")
    assert r["source"] == "cmudict"
    assert r["confidence"] == 0.6
    assert r["ipa"] is not None


def test_no_source_returns_none(monkeypatch):
    import pipeline.sources as src
    monkeypatch.setattr(src, "OVERRIDES", {})
    monkeypatch.setattr(src, "wikipedia_ipa", lambda pageid: {"ipa": None, "source": "wikipedia", "confidence": 0.0})
    monkeypatch.setattr(src, "wiktionary_ipa", lambda name: {"ipa": None, "source": "wiktionary", "confidence": 0.0})
    r = src.source_ipa("ZXQWERTY")  # guaranteed miss in cmudict
    assert r["ipa"] is None
    assert r["source"] == "none"
    assert r["confidence"] == 0.0


def test_wikipedia_ipa_extracts_from_ipaс_en(monkeypatch):
    """wikipedia_ipa should extract IPA from {{IPAc-en|…}} wikitext."""
    import pipeline.sources as src

    fake_wikitext = "{{IPAc-en|r|ə|ˈ|t|oʊ|n}} is a city in New Mexico."

    monkeypatch.setattr(src, "_fetch_wikitext_by_pageid", lambda pid: fake_wikitext)
    result = src.wikipedia_ipa("99999")
    assert result["ipa"] is not None
    assert result["source"] == "wikipedia"
    assert result["confidence"] == 0.9


def test_wiktionary_ipa_extracts_from_template(monkeypatch):
    """wiktionary_ipa should extract IPA from {{IPA|en|/…/}} wikitext."""
    import pipeline.sources as src

    fake_wikitext = "==English==\n===Pronunciation===\n* {{IPA|en|/ˌtukəmˈkɛri/}}"

    monkeypatch.setattr(src, "_fetch_wiktionary_wikitext", lambda name: fake_wikitext)
    result = src.wiktionary_ipa("Tucumcari")
    assert result["ipa"] == "/ˌtukəmˈkɛri/"
    assert result["source"] == "wiktionary"
    assert result["confidence"] == 0.8


def test_cmudict_ipa_converts_arpabet():
    """cmudict_ipa should return an IPA string for a known word."""
    import pipeline.sources as src
    result = src.cmudict_ipa("hello")
    assert result["ipa"] is not None
    assert result["source"] == "cmudict"
    assert result["confidence"] == 0.6
