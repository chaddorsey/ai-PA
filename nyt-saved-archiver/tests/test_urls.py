from nyt_saved_archiver.urls import load_urls


def test_load_filters_dedupes_and_strips(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(
        "https://www.nytimes.com/2024/01/02/world/a.html?smid=x\n"
        "  https://www.nytimes.com/2024/01/02/world/a.html  \n"   # dup after query strip
        "https://example.com/not-nyt\n"
        "\n# a comment\n"
        "https://www.nytimes.com/2023/05/05/science/b.html\n"
    )
    urls = load_urls(str(f))
    assert urls == [
        "https://www.nytimes.com/2024/01/02/world/a.html",
        "https://www.nytimes.com/2023/05/05/science/b.html",
    ]
