from routing import route_action


def test_online_capable_goes_direct():
    assert route_action("online", True) == "direct"


def test_online_not_capable_queues():
    assert route_action("online", False) == "queue"  # thin/uncredentialed action → hub


def test_offline_always_queues():
    assert route_action("offline", True) == "queue"
    assert route_action("offline", False) == "queue"
