"""Tests for fox-likelihood heuristics."""
import datetime as _dt
import time

from frigate_curator.heuristics import fox_likelihood


def _at(hour: int, minute: int = 0) -> float:
    """Unix timestamp for a given hour today, in local TZ."""
    now = _dt.datetime.now()
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()


def test_non_fox_label_returns_zero():
    assert fox_likelihood(_at(2), "person", 0.9) == 0.0
    assert fox_likelihood(_at(2), "car", 0.9) == 0.0


def test_night_dog_is_high_likelihood():
    score = fox_likelihood(_at(3), "dog", 0.7)
    assert score >= 0.8, f"got {score}"


def test_midday_cat_is_low_likelihood():
    score = fox_likelihood(_at(13), "cat", 0.7)
    assert score < 0.4, f"got {score}"


def test_dusk_tracks_correctly():
    # 19:00 should be substantially higher than 13:00
    assert fox_likelihood(_at(19), "dog", 0.7) > fox_likelihood(_at(13), "dog", 0.7)


def test_low_confidence_downweights():
    high_conf = fox_likelihood(_at(2), "dog", 0.9)
    low_conf = fox_likelihood(_at(2), "dog", 0.3)
    assert low_conf < high_conf
