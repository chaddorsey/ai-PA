from pathlib import Path

import pytest

from nyt_saved_archiver.extract import extract_article

HTML = (Path(__file__).parent / "fixtures" / "article.html").read_text()


def test_extract_pulls_title_byline_date_and_body():
    art = extract_article(HTML, url="https://www.nytimes.com/2024/01/02/world/a.html")
    assert art["title"] == "Test Headline"
    assert art["byline"] == "By Jane Doe"
    assert art["published"] == "2024-01-02T09:00:00Z"
    assert "First paragraph of the body." in art["markdown"]
    assert "Second paragraph" in art["markdown"]
    assert "Cap text." in art["markdown"]           # caption preserved
    assert art["markdown"].strip()                   # non-empty


def test_extract_raises_on_missing_body():
    with pytest.raises(ValueError):
        extract_article("<html><body><p>no article body</p></body></html>", url="u")
