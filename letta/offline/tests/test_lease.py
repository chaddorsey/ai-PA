import json
import tempfile

from lease import renew_lease, lease_state


def test_renew_writes_and_returns():
    p = tempfile.mktemp()
    out = renew_lease(p, "laptop", 90, now=1000.0)
    assert out == {"spoke_id": "laptop", "renewed_at": 1000.0, "ttl_secs": 90}
    assert json.load(open(p)) == out


def test_state_present_within_ttl():
    p = tempfile.mktemp()
    renew_lease(p, "laptop", 90, now=1000.0)
    assert lease_state(p, now=1050.0) == "present"  # 50s < 90s


def test_state_expired_past_ttl():
    p = tempfile.mktemp()
    renew_lease(p, "laptop", 90, now=1000.0)
    assert lease_state(p, now=1200.0) == "expired"  # 200s > 90s


def test_state_absent_when_no_file():
    assert lease_state(tempfile.mktemp(), now=1000.0) == "absent"
