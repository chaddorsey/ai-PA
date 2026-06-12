"""Pure extraction of rich fields from a raw X `tweet_results.result` object."""
from typing import Any


def _screen_name(result: dict) -> str:
    core = (((result.get("core") or {}).get("user_results") or {}).get("result") or {})
    return (core.get("core") or {}).get("screen_name") or (core.get("legacy") or {}).get("screen_name") or "_"


def _media(legacy: dict) -> list[dict]:
    out = []
    for m in (legacy.get("extended_entities") or {}).get("media", []) or []:
        mtype = m.get("type", "photo")
        if mtype in ("video", "animated_gif"):
            variants = [v for v in (m.get("video_info") or {}).get("variants", []) if v.get("url")]
            best = max(variants, key=lambda v: v.get("bitrate", 0), default=None)
            url = best["url"] if best else m.get("media_url_https", "")
        else:
            url = m.get("media_url_https", "")
        if url:
            out.append({"type": mtype, "url": url})
    return out


def _links(legacy: dict) -> list[str]:
    out = []
    for u in (legacy.get("entities") or {}).get("urls", []) or []:
        exp = u.get("expanded_url") or ""
        if exp and "twitter.com/i/web/status" not in exp and "/x.com/i/web/status" not in exp:
            out.append(exp)
    return out


def enrich_tweet(result: dict) -> dict[str, Any]:
    """Return {media, links, in_reply_to, quoted} for a tweet_results.result obj."""
    legacy = result.get("legacy") or {}
    in_reply_to = None
    rid = legacy.get("in_reply_to_status_id_str")
    if rid:
        h = legacy.get("in_reply_to_screen_name") or "_"
        in_reply_to = {"id": rid, "handle": h, "url": f"https://x.com/{h}/status/{rid}"}
    quoted = None
    qr = ((result.get("quoted_status_result") or {}).get("result") or {})
    if qr:
        qleg = qr.get("legacy") or {}
        qh = _screen_name(qr)
        qid = qr.get("rest_id") or qleg.get("id_str", "")
        quoted = {"id": qid, "handle": qh, "text": qleg.get("full_text", ""),
                  "url": f"https://x.com/{qh}/status/{qid}"}
    return {"media": _media(legacy), "links": _links(legacy),
            "in_reply_to": in_reply_to, "quoted": quoted}
