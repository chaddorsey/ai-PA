"""LiteLLM-proxy summarization (Fireworks-backed) + robust output parsing.

Reasoning models can prepend chain-of-thought to `content`, so all parsing is
tolerant: delimited fields for the core summary, last-JSON-object for reply mining.
"""
import json
import os
import re
import urllib.error
import urllib.request

BASE = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
MODEL = os.environ.get("BOOKMARK_SUMMARY_MODEL", "kimi-k2p6")
_KEY = os.environ.get("LITELLM_MASTER_KEY", "")


def _post(body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}/chat/completions", data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def call_llm(prompt: str, max_tokens: int = 500, model: str | None = None) -> str:
    """Return assistant content, or '' on failure."""
    try:
        d = _post({"model": model or MODEL, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]})
        choices = d.get("choices") or []
        return ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return ""


CORE_PROMPT = """You are archiving a saved tweet. Given the tweet, output EXACTLY three lines and nothing else:
TITLE: <=10 word descriptive title (no hashtags)
SUMMARY: one factual sentence on what it says/links to
REPLY_WORTH: yes only if the replies likely contain durable knowledge (links, repos, tools, techniques, expert debate); otherwise no

Tweet by @{handle} ({reply_count} replies):
{text}"""

REPLY_PROMPT = """Below are the top replies to a bookmarked tweet. Extract ONLY durable, reusable knowledge the crowd added (links, repos, tools, named techniques, expert consensus/correction). Ignore jokes, praise, and noise.

Output ONLY a JSON object (no prose) with keys:
  has_durable_value (bool), group_sense (<=2 sentences or ""),
  artifacts (list of {{type, ref, note}}; type in link|repo|tool|technique|claim),
  topics (1-3 short kebab-case tags)
If nothing durable, return has_durable_value=false with empty artifacts.

Original tweet by @{handle}: {text}

Top replies:
{replies}"""


def parse_core(raw: str) -> dict:
    """Tolerant parse of TITLE/SUMMARY/REPLY_WORTH lines from possibly-noisy output."""
    def grab(label):
        m = re.search(rf"^{label}:\s*(.+)$", raw, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""
    rw = grab("REPLY_WORTH").lower()
    return {"title": grab("TITLE") or "(untitled)",
            "summary": grab("SUMMARY"),
            "reply_worth": rw.startswith("y")}


def parse_reply_json(raw: str) -> dict | None:
    """Extract the last top-level balanced {...} JSON object from raw; None if unparseable.

    Scans from right-to-left for the last '}', then walks backward to find its
    matching '{', so nested objects inside the target don't get returned instead.
    """
    ends = [m.start() for m in re.finditer(r"\}", raw)]
    for e in reversed(ends):
        # Walk backward from e to find the matching opening brace
        depth = 0
        for i in range(e, -1, -1):
            if raw[i] == "}":
                depth += 1
            elif raw[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[i:e + 1])
                    except json.JSONDecodeError:
                        break
    return None


def summarize_core(bm: dict) -> dict:
    raw = call_llm(CORE_PROMPT.format(handle=bm.get("author_handle", "_"),
                                      reply_count=bm.get("reply_count", 0),
                                      text=bm.get("text", "")), max_tokens=300)
    return parse_core(raw) if raw else {"title": "(untitled)", "summary": "(summary unavailable)", "reply_worth": False}


def mine_replies(bm: dict, replies: list[dict]) -> dict | None:
    corpus = "\n".join(f"- @{r['handle']} ({r['engagement']}): {r['text']}"
                       + ("  links: " + ", ".join(r["links"]) if r["links"] else "")
                       for r in replies)
    raw = call_llm(REPLY_PROMPT.format(handle=bm.get("author_handle", "_"),
                                       text=bm.get("text", ""), replies=corpus), max_tokens=700)
    out = parse_reply_json(raw) if raw else None
    if not out or not out.get("has_durable_value") or not out.get("artifacts"):
        return None
    return out
