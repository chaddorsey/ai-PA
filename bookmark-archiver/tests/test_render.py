from bookmark_archiver import render

BM = {"id": "100", "author_handle": "aaronp613", "text": "Netflix shipped a CLAUDE.md",
      "url": "https://x.com/aaronp613/status/100", "created_at": "Wed Jun 10 02:54:33 +0000 2026",
      "media": [{"type": "photo", "url": "https://pbs.twimg.com/m.jpg"}],
      "links": ["https://example.com/post"], "in_reply_to": None,
      "quoted": {"handle": "bob", "text": "orig", "url": "https://x.com/bob/status/9"}}

def test_render_bookmark_has_core_fields():
    md = render.bookmark_entry(BM, {"title": "Netflix CLAUDE.md leak",
                                    "summary": "An app shipped a config file."}, knowledge_anchor=None)
    assert "## @aaronp613 — Netflix CLAUDE.md leak" in md
    assert "https://x.com/aaronp613/status/100" in md
    assert "https://pbs.twimg.com/m.jpg" in md
    assert "https://example.com/post" in md
    assert "Quoting @bob" in md and "https://x.com/bob/status/9" in md
    assert "An app shipped a config file." in md

def test_render_bookmark_with_knowledge_pointer():
    md = render.bookmark_entry(BM, {"title": "T", "summary": "S"}, knowledge_anchor="twitter-reply-knowledge.md#100")
    assert "reply-chain notes" in md.lower()
    assert "twitter-reply-knowledge.md#100" in md

def test_render_knowledge_entry():
    k = {"has_durable_value": True, "group_sense": "Crowd shared repos.",
         "artifacts": [{"type": "repo", "ref": "https://github.com/a/b", "note": "agent lib"}],
         "topics": ["agents", "loops"]}
    md = render.knowledge_entry(BM, k, anchor="100")
    assert "<a id=\"100\">" in md or "#100" in md
    assert "agents" in md and "loops" in md
    assert "https://github.com/a/b" in md and "agent lib" in md
    assert "Crowd shared repos." in md
    assert "https://x.com/aaronp613/status/100" in md
