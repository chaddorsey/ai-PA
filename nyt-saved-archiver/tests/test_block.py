from pathlib import Path

from nyt_saved_archiver.block import is_blocked

BLOCKED = (Path(__file__).parent / "fixtures" / "blocked.html").read_text()
OK = "<html><body><section name='articleBody'><p>hi</p></section></body></html>"


def test_detects_block_page():
    assert is_blocked(BLOCKED, status=200) is True


def test_detects_block_status():
    assert is_blocked(OK, status=403) is True


def test_clean_page_not_blocked():
    assert is_blocked(OK, status=200) is False
