"""Tests for pipeline/review_sheet.py — review sheet generation."""
import json
import tempfile
from pathlib import Path


def test_build_review_sheet_creates_html(tmp_path):
    from pipeline.review_sheet import build_review_sheet

    lexicon = {
        "Raton": {"ipa": "rəˈtoʊn", "source": "override", "confidence": 1.0, "risk": 0.85, "freq": 10},
        "Chicago": {"ipa": "/ʃɪˈkɑːɡoʊ/", "source": "cmudict", "confidence": 0.6, "risk": 0.1, "freq": 5},
        "Tucumcari": {"ipa": "ˌtukəmˈkɛri", "source": "override", "confidence": 1.0, "risk": 0.9, "freq": 3},
    }
    out_html = tmp_path / "pron_review.html"
    build_review_sheet(lexicon, render_fn=None, out_html=str(out_html))
    assert out_html.exists()
    content = out_html.read_text()
    assert "Raton" in content
    assert "Tucumcari" in content
    assert "Chicago" in content
    # Should contain HTML table structure
    assert "<table" in content or "<tr" in content


def test_build_review_sheet_sorts_by_risk_times_freq(tmp_path):
    """Rows should be ordered by risk×freq descending."""
    from pipeline.review_sheet import build_review_sheet

    lexicon = {
        "Chicago": {"ipa": "/ʃɪˈkɑːɡoʊ/", "source": "cmudict", "confidence": 0.6, "risk": 0.1, "freq": 100},
        "Tucumcari": {"ipa": "ˌtukəmˈkɛri", "source": "override", "confidence": 1.0, "risk": 0.95, "freq": 3},
        "Raton": {"ipa": "rəˈtoʊn", "source": "override", "confidence": 1.0, "risk": 0.8, "freq": 10},
    }
    out_html = tmp_path / "pron_review.html"
    build_review_sheet(lexicon, render_fn=None, out_html=str(out_html))
    content = out_html.read_text()
    # Tucumcari: 0.95×3=2.85, Raton: 0.8×10=8.0, Chicago: 0.1×100=10.0
    # Chicago has highest risk×freq (10.0), then Raton (8.0), then Tucumcari (2.85)
    idx_chicago = content.index("Chicago")
    idx_raton = content.index("Raton")
    idx_tucumcari = content.index("Tucumcari")
    assert idx_chicago < idx_raton < idx_tucumcari


def test_build_review_sheet_calls_render_fn(tmp_path):
    """When render_fn is provided, it should be called for each entry."""
    from pipeline.review_sheet import build_review_sheet

    calls = []

    def fake_render(name, ipa):
        calls.append((name, ipa))
        return b"FAKEBYTES"

    lexicon = {
        "Raton": {"ipa": "rəˈtoʊn", "source": "override", "confidence": 1.0, "risk": 0.85, "freq": 5},
    }
    out_html = tmp_path / "pron_review.html"
    build_review_sheet(lexicon, render_fn=fake_render, out_html=str(out_html))
    assert len(calls) == 1
    assert calls[0][0] == "Raton"


def test_build_review_sheet_no_render_fn(tmp_path):
    """render_fn=None should produce a valid sheet without errors."""
    from pipeline.review_sheet import build_review_sheet

    lexicon = {
        "Raton": {"ipa": "rəˈtoʊn", "source": "override", "confidence": 1.0, "risk": 0.85, "freq": 5},
    }
    out_html = tmp_path / "pron_review.html"
    # Should not raise even with no render_fn
    build_review_sheet(lexicon, render_fn=None, out_html=str(out_html))
    assert out_html.exists()
