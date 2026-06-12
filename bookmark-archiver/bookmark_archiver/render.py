"""Pure markdown rendering for the bookmark archive + reply-knowledge surfaces."""


def bookmark_entry(bm: dict, core: dict, knowledge_anchor: str | None) -> str:
    h = bm.get("author_handle", "_")
    lines = [f"## @{h} — {core.get('title', '(untitled)')}"]
    body = (bm.get("text") or "").strip().replace("\n", "\n> ")
    lines.append(f"> {body}")
    q = bm.get("quoted")
    if q:
        qt = (q.get("text") or "").strip().replace("\n", " ")
        lines.append(f"> *Quoting @{q.get('handle','_')}:* {qt[:200]}")
    p = bm.get("in_reply_to")
    lines.append("")
    lines.append(f"- **Tweet:** {bm.get('url','')}")
    if p:
        lines.append(f"- **Parent:** {p.get('url','')}")
    if q:
        lines.append(f"- **Quoted:** {q.get('url','')}")
    for m in bm.get("media", []) or []:
        lines.append(f"- **Media ({m.get('type','')}):** {m.get('url','')}")
    for ln in bm.get("links", []) or []:
        lines.append(f"- **Link:** {ln}")
    if core.get("summary"):
        lines.append(f"- **Summary:** {core['summary']}")
    if knowledge_anchor:
        lines.append(f"- ↳ **reply-chain notes:** [{knowledge_anchor}]({knowledge_anchor})")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def knowledge_entry(bm: dict, k: dict, anchor: str) -> str:
    topics = " ".join(f"`{t}`" for t in k.get("topics", []) or [])
    lines = [f'## <a id="{anchor}"></a>@{bm.get("author_handle","_")} — reply-chain knowledge {topics}']
    lines.append(f"- **Source:** {bm.get('url','')}")
    if k.get("group_sense"):
        lines.append(f"- **Group sense:** {k['group_sense']}")
    if k.get("artifacts"):
        lines.append("- **Gems:**")
        for a in k["artifacts"]:
            lines.append(f"  - *{a.get('type','')}* — {a.get('ref','')} — {a.get('note','')}")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)
