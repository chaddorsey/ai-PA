"""
read_recent_signals Letta tool.

Cycle-1 Layer-5 read API. Lists recent agent-produced signals from the
shared canonical store (Gitea: agents/agents-canonical), filtered by
attention level and time window. Returns each signal's frontmatter +
a body excerpt + a permalink to the full file in Gitea.

Use cases:
- MC pulls recent elevated signals during plate refresh to keep the
  unified-executive view current with what worker agents have surfaced.
- Any agent can call this to discover what other agents have flagged
  recently (cycle-1 signals dir is the de facto cross-agent signal bus).

Layer-5 path convention (per cycle-1 plan):
    signals/YYYY-MM-DD/<source>-<slug>.md

Frontmatter fields:
    description, source, attention_level, mentioned_entities, date

Tool: read_recent_signals
"""

from typing import Dict, Any, Optional


def read_recent_signals(
    attention_level_min: Optional[str] = None,
    days_back: Optional[int] = None,
    source_filter: Optional[str] = None,
    max_signals: Optional[int] = None,
    body_excerpt_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Read recent signals from agents-canonical/signals/.

    Args:
        attention_level_min: Minimum attention level to include. One of
                             'routine', 'elevated', 'urgent'. Default
                             'routine' (returns everything). Optional.
        days_back: Number of past days to include (counting from today).
                   Default 3. Capped at 30. Optional.
        source_filter: Optional substring filter on the signal's
                       `source` frontmatter field (e.g., 'pulse-monitor'
                       returns only pulse-monitor signals). Optional.
        max_signals: Cap on signals returned. Default 12. Capped at 50.
                     Optional.
        body_excerpt_chars: Character cap for the body excerpt of each
                            signal. Default 500. Capped at 2000. Optional.

    Returns:
        Dictionary with:
        - status: "ok" or "error"
        - signals: list of dicts, each with keys path, source,
                   attention_level, description, mentioned_entities,
                   date, body_excerpt, html_url, last_modified
        - signals_count: int
        - days_scanned: int
        - error_message: present only when status="error"
    """
    # ALL IMPORTS INSIDE FUNCTION (Letta sandbox extraction)
    import base64
    import json
    import os
    import traceback
    import urllib.error
    import urllib.parse
    import urllib.request
    from datetime import datetime, timedelta, timezone

    try:
        # ── Bound inputs ──
        ATTENTION_RANK = {"routine": 0, "elevated": 1, "urgent": 2}
        min_rank = ATTENTION_RANK.get((attention_level_min or "routine").lower(), 0)

        if days_back is None or days_back < 1:
            days_back = 3
        if days_back > 30:
            days_back = 30

        if max_signals is None or max_signals < 1:
            max_signals = 12
        if max_signals > 50:
            max_signals = 50

        if body_excerpt_chars is None or body_excerpt_chars < 0:
            body_excerpt_chars = 500
        if body_excerpt_chars > 2000:
            body_excerpt_chars = 2000

        # ── Gitea config ──
        gitea_token = os.environ.get("GITEA_MEMFS_TOKEN", "")
        gitea_base = os.environ.get(
            "GITEA_BASE_URL", "http://gitea:3000"
        ).rstrip("/")
        if not gitea_token:
            return {
                "status": "error",
                "signals": [],
                "signals_count": 0,
                "days_scanned": 0,
                "error_message": "GITEA_MEMFS_TOKEN env var not set",
            }
        auth_h = {"Authorization": f"token {gitea_token}"}

        # ── Walk signals/YYYY-MM-DD/ for the past N days ──
        signals = []
        today = datetime.now(timezone.utc).date()
        for offset in range(days_back):
            day = today - timedelta(days=offset)
            day_str = day.strftime("%Y-%m-%d")
            list_url = (
                f"{gitea_base}/api/v1/repos/agents/agents-canonical"
                f"/contents/signals/{day_str}?ref=main"
            )
            try:
                req = urllib.request.Request(list_url, headers=auth_h)
                with urllib.request.urlopen(req, timeout=10) as r:
                    listing = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as he:
                if he.code == 404:
                    continue  # No signals on that date — normal
                raise
            if not isinstance(listing, list):
                continue

            for entry in listing:
                if entry.get("type") != "file":
                    continue
                if not (entry.get("name", "") or "").endswith(".md"):
                    continue
                file_path = entry.get("path", "")
                # Fetch the file's content (the listing endpoint gives
                # only paths/SHAs; we need content for frontmatter parsing).
                f_url = (
                    f"{gitea_base}/api/v1/repos/agents/agents-canonical"
                    f"/contents/{urllib.parse.quote(file_path)}?ref=main"
                )
                try:
                    fr = urllib.request.Request(f_url, headers=auth_h)
                    with urllib.request.urlopen(fr, timeout=10) as fresp:
                        fdata = json.loads(fresp.read().decode("utf-8"))
                except Exception:
                    continue
                content_b64 = fdata.get("content", "") or ""
                if not content_b64:
                    continue
                try:
                    raw = base64.b64decode(content_b64).decode("utf-8", "replace")
                except Exception:
                    continue

                # Parse YAML frontmatter inline (no PyYAML dependency).
                # Format: leading "---\n", lines of `key: value`, "---\n".
                fm = {}
                body = raw
                if raw.startswith("---\n") or raw.startswith("---\r\n"):
                    # Find closing fence
                    lines = raw.split("\n")
                    # Skip the opening "---"
                    end_idx = -1
                    for idx in range(1, len(lines)):
                        if lines[idx].strip() == "---":
                            end_idx = idx
                            break
                    if end_idx > 0:
                        for fline in lines[1:end_idx]:
                            if ":" in fline:
                                k, _, v = fline.partition(":")
                                fm[k.strip()] = v.strip()
                        body = "\n".join(lines[end_idx + 1:]).lstrip("\n")

                # Filter by attention_level
                attn = (fm.get("attention_level") or "routine").lower()
                if ATTENTION_RANK.get(attn, 0) < min_rank:
                    continue

                # Filter by source substring
                src = fm.get("source", "")
                if source_filter and source_filter.lower() not in src.lower():
                    continue

                # Build the entry. mentioned_entities is YAML-list-ish:
                # `["a", "b"]` — try a tolerant parse, fall back to raw.
                me_raw = fm.get("mentioned_entities", "[]")
                mentioned = []
                try:
                    mentioned = json.loads(me_raw) if me_raw else []
                    if not isinstance(mentioned, list):
                        mentioned = []
                except Exception:
                    mentioned = []

                signals.append({
                    "path": file_path,
                    "source": src,
                    "attention_level": attn,
                    "description": fm.get("description", ""),
                    "mentioned_entities": mentioned,
                    "date": fm.get("date", day_str),
                    "body_excerpt": body[:body_excerpt_chars],
                    "html_url": fdata.get("html_url", ""),
                    "last_modified": fm.get(
                        "last_refreshed_at",
                        fm.get("composed_at", ""),
                    ),
                })

        # Sort: highest attention first, then most recent date first.
        signals.sort(
            key=lambda s: (
                -ATTENTION_RANK.get(s["attention_level"], 0),
                s["date"] or "",
                s["last_modified"] or "",
            ),
            reverse=False,
        )
        # Re-sort properly: descending by attention, descending by date.
        signals.sort(
            key=lambda s: (
                ATTENTION_RANK.get(s["attention_level"], 0),
                s["date"] or "",
                s["last_modified"] or "",
            ),
            reverse=True,
        )
        signals = signals[:max_signals]

        return {
            "status": "ok",
            "signals": signals,
            "signals_count": len(signals),
            "days_scanned": days_back,
        }

    except Exception as e:
        return {
            "status": "error",
            "signals": [],
            "signals_count": 0,
            "days_scanned": 0,
            "error_message": f"{e}\n{traceback.format_exc()}",
        }
