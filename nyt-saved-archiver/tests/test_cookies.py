from nyt_saved_archiver.cookies import parse_cookies_txt


def test_parse_netscape_cookies(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text(
        "# Netscape HTTP Cookie File\n"
        ".nytimes.com\tTRUE\t/\tTRUE\t1789000000\tNYT-S\tabc123\n"
        "#HttpOnly_.nytimes.com\tTRUE\t/\tTRUE\t0\tnyt-jkidd\txyz\n"
        "\n"
        "malformed line without tabs\n"
    )
    by = {c["name"]: c for c in parse_cookies_txt(str(f))}
    assert by["NYT-S"]["value"] == "abc123"
    assert by["NYT-S"]["domain"] == ".nytimes.com"
    assert by["NYT-S"]["secure"] is True
    assert by["NYT-S"]["expires"] == 1789000000
    assert by["nyt-jkidd"]["httpOnly"] is True
    assert by["nyt-jkidd"]["expires"] == -1     # 0 -> session cookie
    assert "malformed" not in by
