"""Pure parser: `read tweet` GraphQL -> top-N replies by engagement."""


def _iter_reply_results(entries):
    for e in entries:
        content = e.get("content") or {}
        if content.get("entryType") != "TimelineTimelineModule":
            continue
        for item in content.get("items") or []:
            result = (((item.get("item") or {}).get("itemContent") or {})
                      .get("tweet_results") or {}).get("result") or {}
            if result.get("legacy"):
                yield result


def parse_reply_chain(graphql: dict, top_n: int = 25) -> list[dict]:
    """Return up to top_n replies sorted by (favorite+reply) desc.

    Each: {handle, text, engagement, favorite_count, reply_count, links}.
    """
    insts = (((graphql.get("data") or {})
              .get("threaded_conversation_with_injections_v2") or {})
             .get("instructions") or [])
    entries = []
    for i in insts:
        if i.get("type") == "TimelineAddEntries":
            entries = i.get("entries") or []
            break
    replies = []
    for r in _iter_reply_results(entries):
        legacy = r.get("legacy") or {}
        core = (((r.get("core") or {}).get("user_results") or {}).get("result") or {})
        handle = (core.get("core") or {}).get("screen_name") or "_"
        favs = legacy.get("favorite_count", 0) or 0
        reps = legacy.get("reply_count", 0) or 0
        links = [u.get("expanded_url") for u in (legacy.get("entities") or {}).get("urls", [])
                 if u.get("expanded_url")]
        replies.append({
            "handle": handle, "text": legacy.get("full_text", ""),
            "engagement": favs + reps, "favorite_count": favs,
            "reply_count": reps, "links": links,
        })
    replies.sort(key=lambda x: x["engagement"], reverse=True)
    return replies[:top_n]
