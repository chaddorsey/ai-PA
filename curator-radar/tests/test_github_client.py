import pytest
from curator_radar.github_client import RateLimitState


def test_rate_limit_state_defaults():
    state = RateLimitState()
    assert state.remaining == 5000
    assert state.reset_at == 0.0
