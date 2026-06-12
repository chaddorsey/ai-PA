from bookmark_archiver import canonical

def test_prepend_entries_starts_new_file_with_frontmatter():
    out = canonical.prepend_entries("", ["## entry A\n---"], title="Twitter Bookmarks")
    assert out.startswith("---\n")
    assert "description: Twitter Bookmarks" in out
    assert "## entry A" in out

def test_prepend_entries_inserts_after_frontmatter_newest_first():
    existing = "---\ndescription: X\n---\n\n## old entry\n---\n"
    out = canonical.prepend_entries(existing, ["## new entry\n---"], title="X")
    assert out.count("---\ndescription") == 1
    assert out.index("## new entry") < out.index("## old entry")
