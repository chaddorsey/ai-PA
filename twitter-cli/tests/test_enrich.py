from twitter_cli.enrich import enrich_tweet

def _result(**legacy):
    base = {"legacy": {"full_text": "hi", **legacy}}
    return base

def test_media_photo_and_video():
    r = _result(extended_entities={"media": [
        {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/a.jpg"},
        {"type": "video", "media_url_https": "https://pbs.twimg.com/x.jpg",
         "video_info": {"variants": [
             {"bitrate": 100, "url": "https://video.twimg.com/lo.mp4"},
             {"bitrate": 900, "url": "https://video.twimg.com/hi.mp4"}]}},
    ]})
    out = enrich_tweet(r)
    assert out["media"] == [
        {"type": "photo", "url": "https://pbs.twimg.com/media/a.jpg"},
        {"type": "video", "url": "https://video.twimg.com/hi.mp4"},
    ]

def test_external_links_exclude_tco_selfref():
    r = _result(entities={"urls": [
        {"expanded_url": "https://arxiv.org/pdf/123"},
        {"expanded_url": "https://twitter.com/i/web/status/1"},
    ]})
    assert enrich_tweet(r)["links"] == ["https://arxiv.org/pdf/123"]

def test_quoted_and_parent():
    r = _result(in_reply_to_status_id_str="555", in_reply_to_screen_name="alice")
    r["quoted_status_result"] = {"result": {
        "rest_id": "999",
        "legacy": {"full_text": "quoted body"},
        "core": {"user_results": {"result": {"core": {"screen_name": "bob"}}}},
    }}
    out = enrich_tweet(r)
    assert out["in_reply_to"] == {"id": "555", "handle": "alice",
                                  "url": "https://x.com/alice/status/555"}
    assert out["quoted"] == {"id": "999", "handle": "bob", "text": "quoted body",
                             "url": "https://x.com/bob/status/999"}

def test_empty_when_absent():
    out = enrich_tweet(_result())
    assert out == {"media": [], "links": [], "in_reply_to": None, "quoted": None}
