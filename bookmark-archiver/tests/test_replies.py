from bookmark_archiver.replies import parse_reply_chain

def _reply(text, favs, replies, handle, urls=None):
    return {"content": {"entryType": "TimelineTimelineModule", "items": [
        {"item": {"itemContent": {"tweet_results": {"result": {
            "legacy": {"full_text": text, "favorite_count": favs, "reply_count": replies,
                       "entities": {"urls": [{"expanded_url": u} for u in (urls or [])]}},
            "core": {"user_results": {"result": {"core": {"screen_name": handle}}}},
        }}}}}]}}

def _graphql(main_id, reply_entries):
    main = {"content": {"entryType": "TimelineTimelineItem",
                        "entryId": f"tweet-{main_id}"}}
    return {"data": {"threaded_conversation_with_injections_v2": {"instructions": [
        {"type": "TimelineAddEntries", "entries": [main, *reply_entries]}]}}}

def test_top_n_by_engagement_excludes_main():
    g = _graphql("100", [
        _reply("low", 1, 0, "a"),
        _reply("high", 500, 10, "b", urls=["https://github.com/x/y"]),
        _reply("mid", 50, 2, "c"),
    ])
    out = parse_reply_chain(g, top_n=2)
    assert [r["handle"] for r in out] == ["b", "c"]
    assert out[0]["text"] == "high"
    assert out[0]["links"] == ["https://github.com/x/y"]
    assert out[0]["engagement"] == 510

def test_empty_chain_returns_empty():
    assert parse_reply_chain(_graphql("1", []), top_n=5) == []

def test_handles_missing_keys_gracefully():
    g = {"data": {}}
    assert parse_reply_chain(g, top_n=5) == []
