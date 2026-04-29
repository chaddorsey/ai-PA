#!/usr/bin/env python3
"""
seed-canonical-userinfo.py — populate agents-canonical/reference/ with
user/people/projects/orgs from authoritative sources.

Phases (in priority order — run independently):

  --phase core (default)
      Deterministic seed from MC's important_people block + concord.org
      staff/directors pages. ~30-40 people total. Cross-refs Slack profile
      and Letta identities. Highest-confidence pass.

  --phase candidates
      Empirical ranked list from Gmail (replied threads, 24mo) + Calendar
      (attendees, 24mo) + Drive (collaborators, 24mo). Output is a ranked
      report for user review — does NOT auto-seed.

  --phase enrich
      For people already seeded, refresh Slack signals (shared channels,
      MPDM co-occurrence, @-mention freq) and update their priority +
      interaction_signal frontmatter fields.

  --phase mine-color
      Periodic pass: mine vibe-checks, Granola transcripts, Slack DMs for
      durable color/preference signals; append to canonical body sections.

All phases default to --dry-run. Use --commit to actually write to
agents-canonical via Gitea API.

Path conventions follow letta-code's initializing-memory skill:
  reference/user/identity.md            (~40 lines, Chad's core)
  reference/user/prefs/*.md             (split: communication, working_hours,
                                         conferencing, guardrails)
  reference/people/<email-slug>.md      (~40 lines, frontmatter + body)
  reference/monitoring_priorities.md    (compact index w/ [[link]]s)

Frontmatter `description:` is purpose, not summary — what kind of file
this is, not what it says.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


ENV_PATH = "/Volumes/main-drive/ai-PA/.env"
GITEA_HOST = "http://localhost:3030"
CANONICAL_REPO = "agents/agents-canonical"
MC_AGENT_ID = "agent-90b2e860-6345-49a7-98f1-8d5ae4d9c4ef"


def env(name):
    return os.popen(
        f"grep -E '^{name}=' {ENV_PATH} | head -1 | cut -d= -f2- | tr -d '\"'"
    ).read().strip()


SLACK_USER_TOKEN = env("SLACK_MCP_XOXP_TOKEN")
GITEA_TOKEN = env("GITEA_MEMFS_TOKEN") or env("GITEA_TOKEN")


# ---------- Slug + path helpers ----------


def email_slug(email: str) -> str:
    """jdoe@concord.org → jdoe; firstname.last@x.com → firstname-last-x"""
    if not email or "@" not in email:
        return re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-")
    local, domain = email.split("@", 1)
    if domain.lower() == "concord.org":
        return re.sub(r"[^a-z0-9]+", "-", local.lower()).strip("-")
    domain_short = domain.split(".")[0].lower()
    return re.sub(r"[^a-z0-9]+", "-", f"{local}-{domain_short}".lower()).strip("-")


def name_to_slug(name: str) -> str:
    """Helen Quinn → helen-quinn"""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# Common nickname/full-name pairs (extend as needed; people own files can
# also list `aliases: [...]` to enrich)
NICKNAME_MAP = {
    "sue": ["susan", "susanne", "susannah"],
    "susan": ["sue", "susie"],
    "bob": ["robert"], "robert": ["bob", "rob", "bobby"],
    "bill": ["william"], "william": ["bill", "billy", "will"],
    "rick": ["richard"], "richard": ["rick", "dick"],
    "mike": ["michael"], "michael": ["mike", "mikey"],
    "dan": ["daniel"], "daniel": ["dan", "danny"],
    "kate": ["katherine", "kathryn"], "katherine": ["kate", "kathy", "katie"],
    "kathy": ["katherine", "kathryn", "kate"],
    "liz": ["elizabeth"], "elizabeth": ["liz", "beth", "betsy"],
    "chris": ["christopher"], "christopher": ["chris"],
    "tom": ["thomas"], "thomas": ["tom", "tommy"],
    "jim": ["james"], "james": ["jim", "jimmy"],
    "joe": ["joseph"], "joseph": ["joe", "joey"],
    "dave": ["david"], "david": ["dave", "davey"],
    "matt": ["matthew"], "matthew": ["matt"],
    "jen": ["jennifer"], "jennifer": ["jen", "jenny"],
}


def fuzzy_name_match(target: str, candidates: List[str]) -> Optional[str]:
    """Match `target` against `candidates`. Returns matched candidate or None.
    Tries: exact, alias-normalized, last-name + first-letter."""
    t_norm = re.sub(r"\s+", " ", target.lower()).strip()
    cand_lower = {c.lower(): c for c in candidates}
    if t_norm in cand_lower:
        return cand_lower[t_norm]

    t_parts = t_norm.split()
    if not t_parts:
        return None
    t_first = t_parts[0]
    t_last = t_parts[-1]

    # Alias-aware: if target's first name has known full-name equivalents,
    # try each
    first_candidates = {t_first} | set(NICKNAME_MAP.get(t_first, []))
    for first in first_candidates:
        candidate = f"{first} {t_last}"
        if candidate in cand_lower:
            return cand_lower[candidate]

    # Last-name + first-letter fallback
    for cl, original in cand_lower.items():
        c_parts = cl.split()
        if not c_parts:
            continue
        if c_parts[-1] == t_last and c_parts[0][0] == t_first[0]:
            return original

    return None


# ---------- Fetchers ----------


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ai-PA-canonical-seed/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_staff_listing(html: str) -> List[Dict[str, str]]:
    """Returns [{name, title, slug, profile_url}] for each staff member."""
    pat = re.compile(
        r'<a\s+title="([^"]+)"\s+href="(https?://[^"]+/about/staff/([^/]+)/)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    out = []
    for m in pat.finditer(html):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        url = m.group(2)
        slug = m.group(3)
        inner = m.group(4)
        text = re.sub(r"<[^>]+>", "|", inner)
        parts = [p.strip() for p in text.split("|") if p.strip()]
        title = parts[1] if len(parts) >= 2 else ""
        title = title.replace("&amp;", "&")
        if name and title:
            out.append({"name": name, "title": title, "slug": slug, "profile_url": url})
    return out


def parse_staff_profile(html: str, full_name: str) -> Dict[str, str]:
    """Extract bio + email + phone from an individual staff profile page."""
    body_m = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.DOTALL | re.IGNORECASE)
    body = body_m.group(1) if body_m else html
    cleaned = re.sub(
        r"<(nav|footer|header|script|style|form|aside)[^>]*>.*?</\1>",
        "",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", cleaned)
    text = re.sub(r"\s+", " ", text).strip()

    email_m = re.search(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", text)
    email = email_m.group(1) if email_m else ""
    phone_m = re.search(r"\b\(\d{3}\)\s*\d{3}-\d{4}\b", text)
    phone = phone_m.group(0) if phone_m else ""

    bio = ""
    if email:
        bio_end = text.find(email)
        # Trim contact-label trailers (e.g., "... Email") and the optional "Phone" label
        bio_text = text[:bio_end].rstrip()
        for trailer in (" Email", " Phone"):
            if bio_text.endswith(trailer):
                bio_text = bio_text[: -len(trailer)].rstrip()
        bio = trim_bio_preamble(bio_text, full_name)

    return {"bio": bio.strip(), "email": email, "phone": phone}


def trim_bio_preamble(text: str, full_name: str) -> str:
    """Trim concord.org page-nav text from the start of a bio.

    The pages have a fixed nav prefix ("Staff More in this Section ...
    Subscribe <Name> <Title> <Name> <bio starts here>"). We anchor on the
    SECOND occurrence of the person's first name to find the bio start —
    the first occurrence is in the page header, the second begins the bio
    proper.
    """
    if not full_name:
        return text
    first = full_name.split()[0]
    last = full_name.split()[-1]

    # Find all occurrences of the first name in the text
    occurrences = [m.start() for m in re.finditer(r"\b" + re.escape(first) + r"\b", text)]
    if len(occurrences) >= 2:
        # The bio typically starts at the second-to-last occurrence of the
        # first name (the start of the bio paragraph itself). Equivalently,
        # find the first occurrence that is followed by a verb-like pattern.
        for idx in occurrences:
            tail = text[idx:idx + 200]
            # Bio-style verbs: "<Name> is", "<Name> oversees", "<Name> leads",
            # "<Name> joined", etc. The pattern is "<Name>[ <Last>]? <verb>"
            if re.match(
                rf"\b{re.escape(first)}\b\s+(?:{re.escape(last)}\s+)?"
                r"(is|was|leads|oversees|joined|works|serves|directs|manages|coordinates|"
                r"researches|teaches|holds|earned|received|received|brings|graduated)",
                tail,
                re.IGNORECASE,
            ):
                return text[idx:]

    # Fallback: trim known nav prefix tokens
    nav_pat = re.compile(
        r"(Staff |Directors |More in this Section |Our Impact |Board of Directors |"
        r"Financial Information |Collaborators |Newsletter |Careers |Blog |Contact |"
        r"Events |Subscribe )+",
        re.IGNORECASE,
    )
    text = nav_pat.sub("", text, count=1).strip()
    return text


def derive_aliases(
    full_name: str,
    important_names: set,
    slack_display_name: Optional[str] = None,
) -> List[str]:
    """Derive aliases from EMPIRICAL evidence only:
    - The first-name form Chad actually uses in `important_people` (if it
      differs from the canonical first name on concord.org)
    - The Slack display_name (if it differs from the real name)

    Does NOT pre-populate from a generic nickname map. Aliases must reflect
    how the person is actually referred to.
    """
    if not full_name:
        return []
    canonical_first = full_name.split()[0]
    last = full_name.split()[-1]
    aliases: List[str] = []

    # Source 1: important_people uses a different first name
    for name in important_names:
        parts = name.split()
        if not parts or parts[-1].lower() != last.lower():
            continue
        empirical_first = parts[0]
        if empirical_first.lower() != canonical_first.lower() and empirical_first not in aliases:
            aliases.append(empirical_first)

    # Source 2: Slack display name (often the informal first name)
    if slack_display_name:
        # Strip any trailing space-separated last name
        slack_first = slack_display_name.split()[0] if slack_display_name else ""
        if (
            slack_first
            and slack_first.lower() != canonical_first.lower()
            and slack_first not in aliases
        ):
            aliases.append(slack_first)

    return aliases


def parse_directors(html: str) -> List[Dict[str, str]]:
    """Returns [{name, title, bio, role}] for each board member."""
    name_starts = [m.start() for m in re.finditer(
        r'class="board-member__name"', html
    )]
    out = []
    for i, start in enumerate(name_starts):
        end = name_starts[i + 1] if i + 1 < len(name_starts) else len(html)
        chunk = html[start:end]
        nm = re.search(r"class=\"board-member__name\"[^>]*>([^<]+)<", chunk)
        ti = re.search(r"class=\"board-member__title\"[^>]*>([^<]+)<", chunk)
        bi = re.search(r"class=\"board-member__bio\"[^>]*>(.*?)</p>", chunk, re.DOTALL)
        if not nm:
            continue
        name_full = re.sub(r"\s+", " ", nm.group(1)).strip()
        # Split off role suffix: "Helen R. Quinn, Chair" → name=Helen R. Quinn role=Chair
        role = ""
        if "," in name_full:
            name_full, role = [s.strip() for s in name_full.split(",", 1)]
        title = re.sub(r"\s+", " ", ti.group(1)).strip() if ti else ""
        bio = ""
        if bi:
            bt = re.sub(r"<[^>]+>", " ", bi.group(1))
            bio = re.sub(r"\s+", " ", bt).strip()
        out.append({"name": name_full, "title": title, "bio": bio, "role": role})
    return out


# ---------- Slack + Letta cross-refs ----------


def slack_lookup_by_email(email: str) -> Optional[Dict[str, Any]]:
    if not SLACK_USER_TOKEN or not email:
        return None
    url = f"https://slack.com/api/users.lookupByEmail?{urllib.parse.urlencode({'email': email})}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SLACK_USER_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        if d.get("ok"):
            u = d.get("user", {})
            prof = u.get("profile", {})
            return {
                "slack_user_id": u.get("id"),
                "display_name": prof.get("display_name") or prof.get("real_name") or u.get("name"),
                "real_name": prof.get("real_name"),
                "title": prof.get("title"),
                "timezone": u.get("tz"),
                "phone": prof.get("phone"),
            }
    except Exception:
        return None
    return None


def list_letta_identities() -> List[Dict[str, Any]]:
    try:
        with urllib.request.urlopen("http://localhost:8283/v1/identities/?limit=100") as r:
            return json.loads(r.read())
    except Exception:
        return []


def match_letta_identity(name: str, identities: List[Dict[str, Any]]) -> Optional[str]:
    """Fuzzy match name → letta identity_id. Last name + first initial match."""
    name_norm = re.sub(r"\s+", " ", name.lower()).strip()
    for ident in identities:
        ident_name = (ident.get("name") or "").strip()
        if not ident_name:
            continue
        if ident_name.lower() == name_norm:
            return ident.get("id")
        # Last-name match (only if last names are unique enough)
        n_parts = name_norm.split()
        i_parts = ident_name.lower().split()
        if n_parts and i_parts and n_parts[-1] == i_parts[-1] and n_parts[0][0] == i_parts[0][0]:
            return ident.get("id")
    return None


# ---------- Important_people seed ----------


def read_mc_important_people() -> str:
    """Read the current important_people content from MC's block."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:8283/v1/agents/{MC_AGENT_ID}/core-memory/blocks"
        ) as r:
            blocks = json.loads(r.read())
        for b in blocks:
            if b.get("label", "").endswith("important_people"):
                return b.get("value", "") or ""
    except Exception:
        pass
    return ""


# ---------- Person file composer ----------


def compose_person_file(person: Dict[str, Any]) -> str:
    """Build a reference/people/<domain>/<slug>.md content string.

    Frontmatter shape:
      description, emails (map), phones (map), calendar_ids (map),
      slack (map: user_id, display_name), aliases (list), title,
      organization, relationship, primary_domain, domains (list),
      priority, updated_by, updated_at.
    """
    fm = ["---"]
    desc = person.get("description") or (
        f"{person['name']} — {person.get('title','')}".strip(" —")
    )
    fm.append(f"description: {desc}")

    # Emails as a labeled map
    emails = person.get("emails") or {}
    if isinstance(emails, list):
        emails = {"primary": emails[0]} if emails else {}
    if emails:
        fm.append("emails:")
        for k, v in emails.items():
            fm.append(f"  {k}: {v}")

    # Phones as a labeled map
    phones = person.get("phones") or {}
    if phones:
        fm.append("phones:")
        for k, v in phones.items():
            fm.append(f"  {k}: {json.dumps(v)}")

    # Calendar IDs as a labeled map (default primary = primary email for Google)
    cals = person.get("calendar_ids") or {}
    if not cals and emails.get("primary"):
        cals = {"primary": emails["primary"]}
    if cals:
        fm.append("calendar_ids:")
        for k, v in cals.items():
            fm.append(f"  {k}: {v}")

    # Slack
    slack = person.get("slack") or {}
    if slack:
        fm.append("slack:")
        for k, v in slack.items():
            fm.append(f"  {k}: {v}")

    # Aliases (nicknames, informal forms, alternate names)
    aliases = person.get("aliases") or []
    if aliases:
        fm.append("aliases: [" + ", ".join(json.dumps(a) for a in aliases) + "]")

    # Identity
    if person.get("title"):
        fm.append(f"title: {json.dumps(person['title'])}")
    if person.get("organization"):
        fm.append(f"organization: {json.dumps(person['organization'])}")
    if person.get("timezone"):
        fm.append(f"timezone: {person['timezone']}")

    # Relationship
    if person.get("relationship"):
        fm.append(f"relationship: {json.dumps(person['relationship'])}")
    if person.get("primary_domain"):
        fm.append(f"primary_domain: {person['primary_domain']}")
    if person.get("domains"):
        fm.append("domains: [" + ", ".join(person["domains"]) + "]")
    if person.get("priority"):
        fm.append(f"priority: {person['priority']}")

    if person.get("concord_profile"):
        fm.append(f"concord_profile: {person['concord_profile']}")

    fm.append("updated_by: claude-bootstrap")
    fm.append(f"updated_at: {datetime.now(tz=timezone.utc).isoformat()}")
    fm.append("---")
    fm.append("")

    # Body
    body = [f"# {person['name']}", ""]
    if person.get("title") and person.get("organization"):
        body.append(f"**{person['title']}**, {person['organization']}")
        body.append("")
    elif person.get("title"):
        body.append(f"**{person['title']}**")
        body.append("")
    if person.get("bio"):
        body.append("## Bio")
        body.append(person["bio"])
        body.append("")
    body.append("## Relationship to Chad")
    body.append("(populate as context emerges)")
    body.append("")
    body.append("## Communication preferences")
    body.append("(populate as patterns emerge)")
    body.append("")
    body.append("## Active projects")
    body.append("(link via [[reference/projects/<slug>]] as project files exist)")
    body.append("")
    body.append("## Recent interaction context")
    body.append("(periodically refreshed by mine-color phase)")
    body.append("")
    return "\n".join(fm) + "\n".join(body) + "\n"


def compose_user_identity(chad: Dict[str, Any]) -> str:
    fm = [
        "---",
        "description: Chad Dorsey's core identity — name, role, contact slots, organization. Slow-changing identity facts only. Preferences split out under reference/user/prefs/. Detail bio in body.",
    ]

    emails = chad.get("emails") or {}
    if emails:
        fm.append("emails:")
        for k, v in emails.items():
            fm.append(f"  {k}: {v}")

    phones = chad.get("phones") or {}
    if phones:
        fm.append("phones:")
        for k, v in phones.items():
            fm.append(f"  {k}: {json.dumps(v)}")

    cals = chad.get("calendar_ids") or {}
    if not cals and emails.get("primary"):
        cals = {"primary": emails["primary"]}
    if cals:
        fm.append("calendar_ids:")
        for k, v in cals.items():
            fm.append(f"  {k}: {v}")

    slack = chad.get("slack") or {}
    if slack:
        fm.append("slack:")
        for k, v in slack.items():
            fm.append(f"  {k}: {v}")

    if chad.get("aliases"):
        fm.append("aliases: [" + ", ".join(json.dumps(a) for a in chad["aliases"]) + "]")
    if chad.get("timezone"):
        fm.append(f"timezone: {chad['timezone']}")

    fm.append(f"title: {json.dumps(chad.get('title','President & CEO'))}")
    fm.append(f"organization: {json.dumps(chad.get('organization','Concord Consortium'))}")
    if chad.get("concord_profile"):
        fm.append(f"concord_profile: {chad['concord_profile']}")
    fm.append("updated_by: claude-bootstrap")
    fm.append(f"updated_at: {datetime.now(tz=timezone.utc).isoformat()}")
    fm.append("---")
    fm.append("")
    body = [
        "# Chad Dorsey",
        "",
        f"**{chad.get('title','President & CEO')}**, {chad.get('organization','Concord Consortium')}",
        "",
        "## Bio",
        chad.get("bio", "(no bio captured)"),
        "",
        "## Discovery paths",
        "- [[reference/user/prefs/communication]] — communication style + guardrails",
        "- [[reference/user/prefs/working_hours]] — protected blocks + scheduling rules",
        "- [[reference/user/prefs/conferencing]] — Zoom PMI, dial-ins (existing ✓)",
        "- [[reference/user/prefs/guardrails]] — hard rules (don't send email, etc.)",
        "- [[reference/monitoring_priorities]] — priority senders/channels",
        "- [[reference/people/overview]] — top-level people index",
        "",
    ]
    return "\n".join(fm) + "\n".join(body) + "\n"


def compose_monitoring_priorities(priority_people: List[Dict[str, Any]]) -> str:
    fm = [
        "---",
        "description: Index of priority senders for MC's monitoring (Slack DMs, email, calendar). Compact list of [[link]]s to person files. MC reads this when triaging incoming messages.",
        "updated_by: claude-bootstrap",
        f"updated_at: {datetime.now(tz=timezone.utc).isoformat()}",
        "---",
        "",
        "# Monitoring priorities",
        "",
        "MC should treat these senders as elevated by default. Each links to the detail file under `reference/people/<domain>/`.",
        "",
        "## Internal staff (work)",
        "",
    ]
    work_priority = [p for p in priority_people if p.get("primary_domain") == "work"]
    board_priority = [p for p in priority_people if p.get("primary_domain") == "board"]
    if work_priority:
        for p in work_priority:
            slug = email_slug(p["emails"]["primary"]) if p.get("emails", {}).get("primary") else name_to_slug(p["name"])
            line = f"- [[reference/people/work/{slug}]] — {p.get('title','')}".rstrip(" —")
            fm.append(line)
    else:
        fm.append("(none yet)")
    fm.append("")
    fm.append("## Board")
    fm.append("")
    if board_priority:
        for p in board_priority:
            slug = name_to_slug(p["name"])
            line = f"- [[reference/people/board/{slug}]] — {p.get('title','')[:80]}".rstrip(" —")
            fm.append(line)
    else:
        fm.append("(none yet)")
    fm.append("")
    fm.append("## External partners")
    fm.append("")
    fm.append("(populate as `reference/people/external/` is built out — Phase B)")
    fm.append("")
    return "\n".join(fm)


def compose_people_overview(work, board, family) -> str:
    """Top-level cross-domain people index."""
    fm = [
        "---",
        "description: Top-level index of people files. Linked-out by domain (work, board, family, personal, external). Use this as the entry point when looking for someone across domains.",
        "updated_by: claude-bootstrap",
        f"updated_at: {datetime.now(tz=timezone.utc).isoformat()}",
        "---",
        "",
        "# People — top-level index",
        "",
        "Files live at `reference/people/<domain>/<slug>.md`. Each has a frontmatter `domains: [...]` field for cross-classification (e.g., a colleague who's also a sports teammate).",
        "",
        "## Domains",
        "",
        f"- **work** — {len(work)} files. Concord Consortium internal staff. See [[reference/people/work/]].",
        f"- **board** — {len(board)} files. Concord Consortium directors. See [[reference/people/board/]].",
        f"- **family** — {len(family)} stub files. Immediate family. Bodies to fill as context emerges.",
        f"- **personal** — 0 files. Friends, church, sports teammates, social. Populated organically.",
        f"- **external** — 0 files. External work collaborators (program officers, foundation contacts, partners). Populated via Phase B candidate review.",
        f"- **services** — 0 files. Vendors, doctors, accountants, lawyers. Populated as referenced.",
        "",
        "## Quick links",
        "",
        "- [[reference/monitoring_priorities]] — priority senders MC watches",
        "- [[reference/user/identity]] — Chad himself",
        "",
        "## Search by name",
        "",
        "Slugs follow `<email-local>` for concord.org folks (e.g. `dkehoe`) or `<first>-<last>` otherwise (e.g. `helen-quinn`). Aliases on each file enable nickname → file resolution.",
        "",
    ]
    return "\n".join(fm)


# ---------- Gitea writes ----------


def gitea_get_sha(path: str) -> Optional[str]:
    url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}?ref=main"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def gitea_write(path: str, content: str, message: str) -> str:
    url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}"
    sha = gitea_get_sha(path)
    body = {
        "branch": "main",
        "content": base64.b64encode(content.encode()).decode("ascii"),
        "message": message,
    }
    if sha:
        body["sha"] = sha
    method = "PUT" if sha else "POST"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"token {GITEA_TOKEN}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
        return (d.get("content") or {}).get("html_url", "")


# ---------- Phase A: core seed ----------


def phase_core(args) -> int:
    print("=== Phase A — core seed ===\n")

    # Step 1: Read MC's important_people (priority signal)
    important_blob = read_mc_important_people()
    important_names = set()
    for line in important_blob.splitlines():
        for n in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\b", line):
            important_names.add(n)
    print(f"Names in MC's important_people block: {len(important_names)}")
    for n in sorted(important_names):
        print(f"  - {n}")
    print()

    # Step 2: Fetch + parse staff
    print("Fetching concord.org/about/staff ...")
    staff_html = fetch_url("https://concord.org/about/staff")
    staff = parse_staff_listing(staff_html)
    staff_names = [s["name"] for s in staff]
    print(f"  parsed {len(staff)} staff entries")

    # Step 3: Fetch + parse directors
    print("Fetching concord.org/about/directors ...")
    dir_html = fetch_url("https://concord.org/about/directors")
    directors = parse_directors(dir_html)
    director_names = [d["name"] for d in directors]
    print(f"  parsed {len(directors)} board members\n")

    # Step 4: Resolve important_names against staff/director rosters via fuzzy match
    elevated_canonical_names = set()
    family_names = set()
    unmatched = []
    for n in sorted(important_names):
        match = fuzzy_name_match(n, staff_names)
        if match:
            elevated_canonical_names.add(match)
            continue
        match = fuzzy_name_match(n, director_names)
        if match:
            elevated_canonical_names.add(match)
            continue
        # Heuristic for family: same surname as Chad (Dorsey) and not in concord.org rosters
        if n.split()[-1].lower() == "dorsey" and n != "Chad Dorsey":
            family_names.add(n)
            continue
        unmatched.append(n)
    print(f"  important_names matched to staff/board: {len(elevated_canonical_names)}")
    for n in sorted(elevated_canonical_names):
        print(f"    elevated → {n}")
    print(f"  inferred family stubs: {sorted(family_names)}")
    if unmatched:
        print(f"  UNMATCHED (no roster hit; create personal/external as needed): {unmatched}")
    print()

    # Step 5: Build staff records
    print("Building staff person records (bio fetch + Slack lookup) ...")
    people_work = []
    chad = None
    for s in staff:
        is_chad = s["name"] == "Chad Dorsey"
        try:
            print(f"  · {s['name']} ({s['title']}) ...", end="", flush=True)
            profile_html = fetch_url(s["profile_url"])
            profile = parse_staff_profile(profile_html, s["name"])
            time.sleep(0.3)
        except Exception as e:
            print(f" FETCH FAIL: {e}")
            continue
        email = profile.get("email", "").lower()
        slack = slack_lookup_by_email(email) if email else None
        priority = "elevated" if s["name"] in elevated_canonical_names else "routine"
        record = {
            "name": s["name"],
            "title": s["title"],
            "organization": "Concord Consortium",
            "emails": {"primary": email} if email else {},
            "phones": ({"work": profile.get("phone")} if profile.get("phone") else {}),
            "calendar_ids": ({"primary": email} if email else {}),
            "slack": ({"user_id": slack["slack_user_id"], "display_name": slack["display_name"]}
                     if slack else {}),
            "timezone": (slack or {}).get("timezone"),
            "aliases": derive_aliases(
                s["name"],
                important_names,
                (slack or {}).get("display_name"),
            ),
            "bio": profile.get("bio", ""),
            "relationship": "internal-staff",
            "primary_domain": "work",
            "domains": ["work"],
            "priority": priority,
            "concord_profile": s["profile_url"],
        }
        if is_chad:
            chad = record
        else:
            people_work.append(record)
        print(f" email={email} slack={record['slack'].get('user_id') or '-'}")

    print(f"\nstaff records built: {len(people_work)} (plus Chad)\n")

    # Step 6: Build director records
    print("Building director records ...")
    people_board = []
    for d in directors:
        priority = "elevated" if d["name"] in elevated_canonical_names else "routine"
        record = {
            "name": d["name"],
            "title": d["title"],
            "organization": "Concord Consortium Board",
            "emails": {},
            "calendar_ids": {},
            "slack": {},
            "aliases": [],
            "bio": d["bio"],
            "relationship": "board-member" + (f" ({d['role']})" if d.get("role") else ""),
            "primary_domain": "board",
            "domains": ["board"],
            "priority": priority,
            "concord_profile": "https://concord.org/about/directors",
        }
        people_board.append(record)
        print(f"  · {d['name']} ({d['title'][:60]})")

    print()

    # Step 7: Build family stubs (no concord.org bio; minimal frontmatter)
    print("Building family stubs ...")
    people_family = []
    for n in sorted(family_names):
        record = {
            "name": n,
            "title": "",
            "organization": "",
            "emails": {},
            "phones": {},
            "calendar_ids": {},
            "slack": {},
            "aliases": [],
            "bio": "",
            "relationship": "family",
            "primary_domain": "family",
            "domains": ["family"],
            "priority": "routine",
            "description": f"{n} — family",
        }
        people_family.append(record)
        print(f"  · {n}")
    print()

    # Step 8: Plan files to write
    print("=== Files to write ===\n")
    plan = []
    if chad:
        plan.append(("reference/user/identity.md", compose_user_identity(chad)))
    for p in people_work:
        slug = email_slug(p["emails"]["primary"]) if p["emails"].get("primary") else name_to_slug(p["name"])
        plan.append((f"reference/people/work/{slug}.md", compose_person_file(p)))
    for p in people_board:
        slug = name_to_slug(p["name"])
        plan.append((f"reference/people/board/{slug}.md", compose_person_file(p)))
    for p in people_family:
        slug = name_to_slug(p["name"])
        plan.append((f"reference/people/family/{slug}.md", compose_person_file(p)))

    # Monitoring priorities — work + board people marked elevated
    priority_people = [p for p in people_work + people_board if p.get("priority") == "elevated"]
    plan.append(("reference/monitoring_priorities.md",
                 compose_monitoring_priorities(priority_people)))

    # People overview index (cross-domain)
    plan.append(("reference/people/overview.md",
                 compose_people_overview(people_work, people_board, people_family)))

    for path, content in plan:
        print(f"  {path}  ({len(content)} bytes)")

    print(f"\ntotal files planned: {len(plan)}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        # Optionally save the plan to /tmp for review
        report = "\n\n".join(f"# {p}\n\n{c}" for p, c in plan)
        out = "/tmp/seed-canonical-userinfo-report.md"
        with open(out, "w") as f:
            f.write(report)
        print(f"full content dumped to: {out}")
        return 0

    print("\n--commit: writing to canonical ...")
    for path, content in plan:
        try:
            url = gitea_write(path, content, f"reference: seed {path} (Phase A)")
            print(f"  ✓ {path} -> {url}")
        except Exception as e:
            print(f"  ✗ {path}: {e}")
    return 0


# ---------- Phase B: candidates (stub for now — real run is heavier) ----------


def gws_run(*args_list, timeout=300) -> Dict[str, Any]:
    """Run gws CLI inside the letta container, return parsed JSON.

    The letta container has gws auth configured. We exec from host.
    """
    import subprocess
    cmd = ["docker", "exec", "ai-pa-letta-1", "/usr/local/bin/gws"] + list(args_list)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"_error": f"timeout after {timeout}s"}
    if r.returncode != 0:
        # gws prints "Using keyring backend: keyring" to stderr on every run
        err = r.stderr.replace("Using keyring backend: keyring\n", "").strip()
        return {"_error": f"rc={r.returncode}: {err[:300]}", "_stdout": r.stdout[:300]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"_error": "non-JSON output", "_stdout": r.stdout[:300]}


def harvest_email_threads(months: int) -> Dict[str, int]:
    """Aggregate distinct threads where Chad replied, by other-participant email.

    Excludes spam, trash, promotions, social, updates per user spec.
    Returns dict: {email_lowercase: thread_count}
    """
    from collections import Counter
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=months * 30)).isoformat().replace("-", "/")
    print(f"  email cutoff: {cutoff} (after:)", flush=True)

    # Step 1: list distinct thread IDs Chad has sent in
    # Strategy: paginate `from:me after:cutoff -in:spam -in:trash` and collect threadIds.
    counts: Counter = Counter()
    seen_threads = set()
    page_token = None
    page_no = 0
    while True:
        page_no += 1
        params = {
            "userId": "me",
            "q": (f"from:me after:{cutoff} -in:spam -in:trash "
                  "-category:promotions -category:social -category:updates"),
            "maxResults": 100,
        }
        if page_token:
            params["pageToken"] = page_token
        r = gws_run("gmail", "users", "messages", "list", "--params", json.dumps(params),
                    timeout=120)
        if "_error" in r:
            print(f"  ! gmail list page {page_no} error: {r['_error']}", flush=True)
            break
        result = r.get("result") or r
        for m in result.get("messages", []) or []:
            tid = m.get("threadId")
            if tid:
                seen_threads.add(tid)
        page_token = result.get("nextPageToken")
        if not page_token:
            break
        if page_no % 5 == 0:
            print(f"    list page {page_no} threads={len(seen_threads)}", flush=True)
    print(f"  distinct sent threads: {len(seen_threads)}", flush=True)

    # Step 2: for each thread, fetch metadata; extract non-Chad From addresses
    fetched = 0
    for tid in seen_threads:
        params = {
            "userId": "me",
            "id": tid,
            "format": "metadata",
            "metadataHeaders": ["From", "To", "Cc"],
        }
        r = gws_run("gmail", "users", "threads", "get", "--params", json.dumps(params),
                    timeout=30)
        if "_error" in r:
            continue
        thread = r.get("result") or r
        emails_in_thread = set()
        for msg in thread.get("messages", []) or []:
            for h in msg.get("payload", {}).get("headers", []) or []:
                if h.get("name") in ("From", "To", "Cc"):
                    val = h.get("value", "")
                    for e in re.findall(r"<([^>]+@[^>]+)>|\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", val):
                        em = (e[0] or e[1]).lower().strip()
                        if em and "cdorsey@concord.org" not in em:
                            emails_in_thread.add(em)
        for em in emails_in_thread:
            counts[em] += 1
        fetched += 1
        if fetched % 100 == 0:
            print(f"    fetched {fetched}/{len(seen_threads)} threads", flush=True)
    print(f"  email aggregation done: {len(counts)} distinct counterparts", flush=True)
    return dict(counts)


def harvest_calendar_attendees(months: int) -> Dict[str, Dict[str, int]]:
    """Aggregate calendar events; weight 2 if Chad organized, 1 if attendee.
    Returns {email: {"organized_with": int, "invited_to": int, "score": int}}
    """
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone as tz_

    time_min = (datetime.now(tz=tz_.utc) - timedelta(days=months * 30)).isoformat()
    time_max = datetime.now(tz=tz_.utc).isoformat()
    print(f"  calendar window: {time_min[:10]} → {time_max[:10]}", flush=True)

    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"organized_with": 0, "invited_to": 0, "score": 0})
    seen_recurring = set()
    page_token = None
    page_no = 0
    total_events = 0
    while True:
        page_no += 1
        params = {
            "calendarId": "primary",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": 250,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if page_token:
            params["pageToken"] = page_token
        r = gws_run("calendar", "events", "list", "--params", json.dumps(params),
                    timeout=120)
        if "_error" in r:
            print(f"  ! calendar page {page_no} error: {r['_error']}", flush=True)
            break
        result = r.get("result") or r
        for ev in result.get("items", []) or []:
            if ev.get("status") == "cancelled":
                continue
            # Dedup recurring: count once per recurring series (use first instance)
            rec_id = ev.get("recurringEventId")
            if rec_id:
                if rec_id in seen_recurring:
                    continue
                seen_recurring.add(rec_id)
            total_events += 1
            org_email = (ev.get("organizer") or {}).get("email", "").lower()
            chad_organized = org_email == "cdorsey@concord.org"
            attendees = ev.get("attendees") or []
            for a in attendees:
                em = (a.get("email") or "").lower()
                if not em or em == "cdorsey@concord.org" or a.get("resource"):
                    continue
                # Skip declined attendees
                if a.get("responseStatus") == "declined":
                    continue
                if chad_organized:
                    counts[em]["organized_with"] += 1
                    counts[em]["score"] += 2
                else:
                    counts[em]["invited_to"] += 1
                    counts[em]["score"] += 1
        page_token = result.get("nextPageToken")
        if not page_token:
            break
        if page_no % 5 == 0:
            print(f"    page {page_no} events={total_events} counterparts={len(counts)}", flush=True)
    print(f"  calendar aggregation: {total_events} distinct events, {len(counts)} counterparts", flush=True)
    return dict(counts)


def harvest_drive_collaborators(months: int, max_files: int = 5000) -> Dict[str, int]:
    """Drive doc collaborators (modified by Chad in last N months).
    Capped at max_files to bound runtime — Chad's Drive is large.
    Returns {email: doc_count}.
    """
    from collections import Counter
    from datetime import datetime, timedelta, timezone as tz_

    cutoff = (datetime.now(tz=tz_.utc) - timedelta(days=months * 30)).isoformat()
    print(f"  drive cutoff: {cutoff[:10]} (modifiedTime >)  cap={max_files}", flush=True)

    counts: Counter = Counter()
    page_token = None
    page_no = 0
    total = 0
    while total < max_files:
        page_no += 1
        params = {
            "q": f"modifiedTime > '{cutoff}' and trashed = false",
            "fields": "nextPageToken, files(id, owners, lastModifyingUser, sharingUser)",
            "pageSize": 100,
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            params["pageToken"] = page_token
        r = gws_run("drive", "files", "list", "--params", json.dumps(params),
                    timeout=120)
        if "_error" in r:
            print(f"  ! drive page {page_no} error: {r['_error']}", flush=True)
            break
        result = r.get("result") or r
        files = result.get("files", []) or []
        for f in files:
            total += 1
            seen_in_doc = set()
            for src in (f.get("owners") or []) + [f.get("lastModifyingUser"), f.get("sharingUser")]:
                if not src:
                    continue
                em = (src.get("emailAddress") or "").lower()
                if em and em != "cdorsey@concord.org":
                    seen_in_doc.add(em)
            for em in seen_in_doc:
                counts[em] += 1
        page_token = result.get("nextPageToken")
        if not page_token:
            break
        if page_no % 5 == 0:
            print(f"    drive page {page_no} files={total} counterparts={len(counts)}", flush=True)
    print(f"  drive aggregation: {total} files, {len(counts)} counterparts", flush=True)
    return dict(counts)


def existing_canonical_emails() -> set:
    """Read all reference/people/*/<slug>.md files; collect known emails."""
    out = set()
    for domain in ("work", "board", "family", "personal", "external"):
        url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/reference/people/{domain}"
        req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                listing = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for entry in listing:
            if entry.get("type") != "file":
                continue
            file_url = (
                f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{entry['path']}?ref=main"
            )
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(
                        file_url, headers={"Authorization": f"token {GITEA_TOKEN}"}
                    ),
                    timeout=10,
                ) as fr:
                    fdata = json.loads(fr.read())
                content = base64.b64decode(fdata["content"]).decode()
                for em in re.findall(r"\bprimary:\s*(\S+@\S+)\b", content):
                    out.add(em.lower())
                for em in re.findall(
                    r"^\s*[a-z_]+:\s*(\S+@\S+)\s*$", content, re.MULTILINE
                ):
                    out.add(em.lower())
            except Exception:
                continue
    return out


# Common automation/no-reply patterns to filter
NOISE_EMAIL_PATTERNS = [
    r"^no[\.\-_]?reply@",
    r"^notifications?@",
    r"^automated?@",
    r"^donotreply@",
    r"^do[-\.]not[-\.]reply@",
    r"^bounce[s]?@",
    r"^postmaster@",
    r"^mailer[-\.]daemon@",
    r"^calendar[\.\-_]?(notification|update)?s?@",
    r"^reply[+\.][a-z0-9]{4,}@",  # gmail forwarding addresses
]
NOISE_RE = re.compile("|".join(NOISE_EMAIL_PATTERNS), re.IGNORECASE)


def is_noise_email(email: str) -> bool:
    if NOISE_RE.search(email):
        return True
    # Self-aliases: cdorsey@concord.org and any +-tag variants
    if email.startswith("cdorsey+") and email.endswith("@concord.org"):
        return True
    if email == "cdorsey@concord.org":
        return True
    # Generic catch-all: a long alphanumeric local part is usually a forwarding hash
    local = email.split("@")[0]
    if len(local) >= 30 and re.match(r"^[a-f0-9]+$", local):
        return True
    return False


def phase_candidates(args) -> int:
    print(f"=== Phase B — candidate aggregation ({args.months}mo) ===\n")

    months = args.months

    print("Step 1: harvest Gmail replied threads ...")
    email_counts = harvest_email_threads(months)
    print()

    print("Step 2: harvest Calendar attendees ...")
    cal_counts = harvest_calendar_attendees(months)
    print()

    print("Step 3: harvest Drive collaborators ...")
    drive_counts = harvest_drive_collaborators(months, max_files=args.drive_cap)
    print()

    # Step 4: existing canonical emails — exclude these (already seeded)
    print("Step 4: load already-seeded canonical emails ...")
    seeded = existing_canonical_emails()
    print(f"  already seeded: {len(seeded)} emails\n")

    # Step 5: aggregate
    print("Step 5: aggregate + rank ...")
    all_emails = set(email_counts) | set(cal_counts) | set(drive_counts)
    rows = []
    for em in all_emails:
        if em in seeded or is_noise_email(em):
            continue
        e_count = email_counts.get(em, 0)
        c = cal_counts.get(em, {"organized_with": 0, "invited_to": 0, "score": 0})
        c_score = c["score"]
        d_count = drive_counts.get(em, 0)
        # Composite: email replies × 1.0 + calendar score × 1.0 + drive × 0.5
        composite = e_count + c_score + 0.5 * d_count
        rows.append({
            "email": em,
            "email_threads": e_count,
            "cal_organized_with": c["organized_with"],
            "cal_invited_to": c["invited_to"],
            "drive_docs": d_count,
            "composite": composite,
        })

    rows.sort(key=lambda r: -r["composite"])

    # Step 5b: split into external vs concord-internal alt-email candidates
    external_rows = [r for r in rows if not r["email"].endswith("@concord.org")]
    internal_alts = [r for r in rows if r["email"].endswith("@concord.org")]

    # Step 6: render report
    out_path = "/tmp/seed-candidates-report.md"
    lines = [
        f"# Phase B candidate report ({months}mo window)",
        "",
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        f"External candidates (after de-dup + noise filter): **{len(external_rows)}**",
        f"Concord-internal alt-emails not matched to a seeded primary: **{len(internal_alts)}**",
        "",
        "Columns: `composite` = email_threads + (2×organized_with + 1×invited_to) + 0.5×drive_docs",
        "Rank top-down; cut at the threshold where signal becomes noise.",
        "",
        "## Concord-internal alt-emails",
        "",
        "These are @concord.org addresses that don't match a seeded person's "
        "primary email. Each likely needs to be merged as `emails.alt: ...` into "
        "an existing `reference/people/work/<slug>.md`, OR represents an ex-staff "
        "member or shared mailbox.",
        "",
        "| Rank | Email | Threads | Cal-org | Cal-inv | Drive | Composite |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(internal_alts[:50], 1):
        lines.append(
            f"| {i} | `{r['email']}` | {r['email_threads']} | "
            f"{r['cal_organized_with']} | {r['cal_invited_to']} | "
            f"{r['drive_docs']} | {r['composite']:.1f} |"
        )
    lines.append("")
    lines.append("## External candidates (potential `reference/people/external/` seeds)")
    lines.append("")
    lines.append("These are non-Concord emails Chad has interacted with via Gmail/Calendar/Drive. "
                 "Mark candidates for promotion to seeded with their target domain (external | personal | services).")
    lines.append("")
    lines.append("| Rank | Email | Threads | Cal-org | Cal-inv | Drive | Composite |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(external_rows[:200], 1):
        lines.append(
            f"| {i} | `{r['email']}` | {r['email_threads']} | "
            f"{r['cal_organized_with']} | {r['cal_invited_to']} | "
            f"{r['drive_docs']} | {r['composite']:.1f} |"
        )
    if len(external_rows) > 200:
        lines.append("")
        lines.append(f"*(showing top 200 of {len(external_rows)} external candidates)*")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written: {out_path}")
    print(f"  internal alts (top 5):")
    for r in internal_alts[:5]:
        print(f"    {r['email']:50s}  composite={r['composite']:.1f}  "
              f"e={r['email_threads']} c={r['cal_organized_with']}/{r['cal_invited_to']} d={r['drive_docs']}")
    print(f"  external (top 10):")
    for r in external_rows[:10]:
        print(f"    {r['email']:50s}  composite={r['composite']:.1f}  "
              f"e={r['email_threads']} c={r['cal_organized_with']}/{r['cal_invited_to']} d={r['drive_docs']}")
    return 0


def phase_enrich(args) -> int:
    print("=== Phase C — Slack signal enrichment ===\n")
    print("NOT YET IMPLEMENTED — runs after Phase A is committed.")
    return 0


def phase_mine_color(args) -> int:
    print("=== Phase D — mine vibe-checks/Granola/DMs for color ===\n")
    print("NOT YET IMPLEMENTED — runs as periodic enrichment.")
    return 0


# ---------- Main ----------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=("core", "candidates", "enrich", "mine-color"),
                   default="core")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--commit", action="store_true",
                   help="Actually write to canonical (overrides --dry-run)")
    p.add_argument("--months", type=int, default=24,
                   help="Phase B time window (months back from today). Default 24.")
    p.add_argument("--drive-cap", type=int, default=5000,
                   help="Phase B max Drive files to scan. Default 5000.")
    args = p.parse_args()
    if args.commit:
        args.dry_run = False

    if not GITEA_TOKEN:
        print("missing GITEA_MEMFS_TOKEN in .env", file=sys.stderr)
        return 2
    if not SLACK_USER_TOKEN:
        print("WARNING: SLACK_MCP_XOXP_TOKEN not set — Slack cross-refs will be skipped",
              file=sys.stderr)

    if args.phase == "core":
        return phase_core(args)
    elif args.phase == "candidates":
        return phase_candidates(args)
    elif args.phase == "enrich":
        return phase_enrich(args)
    elif args.phase == "mine-color":
        return phase_mine_color(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
