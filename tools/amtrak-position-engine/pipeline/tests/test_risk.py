"""Tests for pipeline/risk.py — risk scoring."""


def test_irregular_names_score_higher_than_common():
    from pipeline.risk import risk_score
    assert risk_score("Tucumcari") > risk_score("Chicago")
    assert risk_score("Purgatoire") > risk_score("Kansas")


def test_spanish_marker_raises_risk():
    from pipeline.risk import risk_score
    # Raton has Spanish origin, Mojave is non-English
    assert risk_score("Raton") > risk_score("Denver")
    assert risk_score("Mojave") > risk_score("Portland")


def test_french_marker_raises_risk():
    from pipeline.risk import risk_score
    # Purgatoire is French-origin
    assert risk_score("Purgatoire") > risk_score("Springfield")


def test_native_name_raises_risk():
    from pipeline.risk import risk_score
    # Cimarron has native-language/Spanish origin
    assert risk_score("Cimarron") > risk_score("Boston")


def test_common_english_cities_score_low():
    from pipeline.risk import risk_score
    # Well-known English cities should have low risk
    for name in ["Chicago", "Kansas", "Denver", "Portland", "Boston"]:
        assert risk_score(name) < 0.5, f"Expected {name} to have low risk, got {risk_score(name)}"


def test_risk_score_range():
    from pipeline.risk import risk_score
    for name in ["Tucumcari", "Chicago", "Purgatoire", "Kansas", "Raton", "Pierre"]:
        score = risk_score(name)
        assert 0.0 <= score <= 1.0, f"{name}: risk score {score} out of range"


def test_versailles_il_scores_high():
    from pipeline.risk import risk_score
    # Versailles (KY/IL): French spelling, non-standard US pronunciation
    assert risk_score("Versailles") > risk_score("Chicago")
