from evernote_archiver.reconcile import reconcile


def test_pass_when_within_tolerance():
    r = reconcile(db_count=1000, md_count=995, tolerance=0.02)
    assert r["ok"] is True
    assert r["missing"] == 5


def test_fail_when_drop_exceeds_tolerance():
    r = reconcile(db_count=1000, md_count=870, tolerance=0.02)
    assert r["ok"] is False
    assert r["missing"] == 130
