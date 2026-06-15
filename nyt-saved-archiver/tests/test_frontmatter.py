from nyt_saved_archiver.frontmatter import build_document


def test_build_document_has_type_and_fields():
    art = {"title": "T", "byline": "By X", "published": "2024-01-02T09:00:00Z",
           "url": "https://www.nytimes.com/2024/01/02/world/a.html", "markdown": "Body."}
    doc = build_document(art, saved_date="2026-06-14")
    assert doc.startswith("---\n")
    assert "type: nyt-article" in doc
    assert "source: nyt-saved" in doc
    assert "Body." in doc
