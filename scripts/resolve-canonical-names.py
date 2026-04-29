#!/usr/bin/env python3
"""
resolve-canonical-names.py — backfill real names into canonical person files
from Gmail From: headers.

For each reference/people/**/*.md file:
  1. Read primary email from frontmatter
  2. Query Gmail (via gws CLI in letta container) for messages from that email
  3. Extract the friendly name from the From: header
  4. If the harvested name beats the current placeholder, patch the file:
     - frontmatter `description:` line
     - body `# <Name>` heading
     - body opener line if it referenced the placeholder

Idempotent: only patches when harvested name > placeholder. Skips when Gmail
has no record or returns the same name.

Usage:
    python3 scripts/resolve-canonical-names.py --dry-run    # default
    python3 scripts/resolve-canonical-names.py --commit
    python3 scripts/resolve-canonical-names.py --domain work-alumni  # only this domain
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


ENV_PATH = "/Volumes/main-drive/ai-PA/.env"
GITEA_HOST = "http://localhost:3030"
CANONICAL_REPO = "agents/agents-canonical"


def env(name):
    return os.popen(
        f"grep -E '^{name}=' {ENV_PATH} | head -1 | cut -d= -f2- | tr -d '\"'"
    ).read().strip()


GITEA_TOKEN = env("GITEA_MEMFS_TOKEN")


def gws(*args, timeout=60):
    cmd = ["docker", "exec", "ai-pa-letta-1", "/usr/local/bin/gws"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def gmail_friendly_name(email):
    """Query Gmail for a recent From: <email> and extract the friendly name.
    Returns the cleanest 'Firstname Lastname' form found across recent messages,
    or None if no usable name."""
    params = json.dumps({"userId": "me", "q": f"from:{email}", "maxResults": 5})
    r = gws("gmail", "users", "messages", "list", "--params", params)
    if not r:
        return None
    msgs = (r.get("result") or r).get("messages", []) or []
    if not msgs:
        return None

    found_names = []
    for m in msgs[:3]:
        mid = m.get("id")
        params = json.dumps({
            "userId": "me", "id": mid, "format": "metadata",
            "metadataHeaders": ["From"]
        })
        r = gws("gmail", "users", "messages", "get", "--params", params)
        if not r:
            continue
        msg = r.get("result") or r
        for h in msg.get("payload", {}).get("headers", []) or []:
            if h.get("name") == "From":
                # Parse 'Friendly Name <email@addr>' or 'email@addr'
                val = h.get("value", "")
                m2 = re.match(r'^\s*"?([^"<]+?)"?\s*<', val)
                if m2:
                    name = m2.group(1).strip().strip("'\"").strip()
                    # skip if it's just the email
                    if "@" not in name and len(name) >= 2:
                        found_names.append(name)
        time.sleep(0.1)

    if not found_names:
        return None

    # Pick the most common; tiebreak on length (longer ≈ more complete)
    from collections import Counter
    c = Counter(found_names)
    best, _ = max(c.items(), key=lambda kv: (kv[1], len(kv[0])))
    return best


def normalize(s):
    return re.sub(r"\s+", " ", s).strip()


def is_placeholder(name, email):
    """Heuristic: is the current name a placeholder derived from the email-local?"""
    if not name:
        return True
    local = email.split("@")[0]
    cleaned_local = re.sub(r"\d+", "", local).replace(".", " ").replace("-", " ").replace("_", " ")
    name_norm = name.lower().replace(".", "")
    cleaned_local_norm = cleaned_local.lower()
    # If the name is just the cleaned-up email-local, it's a placeholder
    if name_norm.replace(" ", "") == cleaned_local_norm.replace(" ", ""):
        return True
    # If the name is a single word that matches the email-local, placeholder
    if " " not in name and name.lower() in cleaned_local.lower().split():
        return True
    # If single capitalized word from email-local: e.g., "Lbehan", "Mharding"
    if " " not in name and name.lower() == local.lower():
        return True
    return False


def list_canonical_people(domain_filter=None):
    """List all reference/people/**/*.md files."""
    out = []
    for domain in ("work", "work-alumni", "board", "board-alumni", "family", "personal", "external", "services"):
        if domain_filter and domain != domain_filter:
            continue
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
            if entry.get("type") == "file" and entry.get("name", "").endswith(".md"):
                out.append(entry["path"])
    return out


def read_file(path):
    url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}?ref=main"
    req = urllib.request.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
    return d["sha"], base64.b64decode(d["content"]).decode()


def write_file(path, content, sha, msg):
    url = f"{GITEA_HOST}/api/v1/repos/{CANONICAL_REPO}/contents/{path}"
    body = {
        "branch": "main",
        "content": base64.b64encode(content.encode()).decode("ascii"),
        "message": msg,
        "sha": sha,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"token {GITEA_TOKEN}", "Content-Type": "application/json"},
        method="PUT",
    )
    urllib.request.urlopen(req, timeout=20)


def parse_current(content):
    """Extract current name + primary email from a person file."""
    # primary email
    em_match = re.search(r"^\s*primary:\s*(\S+@\S+)\s*$", content, re.MULTILINE)
    primary_email = em_match.group(1) if em_match else None
    # name from first body heading
    h1 = re.search(r"^# (.+)$", content, re.MULTILINE)
    current_name = h1.group(1).strip() if h1 else None
    # description
    desc = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
    description = desc.group(1).strip() if desc else None
    return primary_email, current_name, description


def patch_name(content, old_name, new_name):
    # Replace in description: "<OldName> — ..." → "<NewName> — ..."
    content = re.sub(
        r"(^description:\s*)" + re.escape(old_name) + r"(\s*[—-])",
        rf"\g<1>{new_name}\g<2>",
        content, count=1, flags=re.MULTILINE,
    )
    # Body H1: "# <OldName>" → "# <NewName>"
    content = re.sub(
        r"^# " + re.escape(old_name) + r"\s*$",
        f"# {new_name}",
        content, count=1, flags=re.MULTILINE,
    )
    # Body opener line if it starts with the old name
    content = re.sub(
        r"^(\*\*[^*]+\*\*),?\s*" + re.escape(old_name) + r",",
        rf"\1, {new_name},",
        content, count=1, flags=re.MULTILINE,
    )
    # Update updated_at + updated_by
    content = re.sub(
        r"^updated_by:.*$",
        f"updated_by: claude-name-resolver",
        content, count=1, flags=re.MULTILINE,
    )
    content = re.sub(
        r"^updated_at:.*$",
        f"updated_at: {datetime.now(tz=timezone.utc).isoformat()}",
        content, count=1, flags=re.MULTILINE,
    )
    # Strip the "*Name from email-local — Chad to refine.*" marker if present
    content = re.sub(
        r"\n\*Name from email-local — Chad to refine\.\*\n",
        "\n",
        content,
    )
    return content


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--commit", action="store_true")
    p.add_argument("--domain", help="Limit to one domain (work-alumni, external, ...)")
    p.add_argument("--max", type=int, default=200, help="Max files to process")
    args = p.parse_args()
    if args.commit:
        args.dry_run = False

    files = list_canonical_people(args.domain)
    print(f"Scanning {len(files)} canonical person files...")

    updates = []
    skipped_no_placeholder = 0
    skipped_no_email = 0
    skipped_no_gmail = 0

    for path in files[: args.max]:
        try:
            sha, content = read_file(path)
        except Exception as e:
            print(f"  ✗ {path}: read fail: {e}")
            continue
        primary_email, current_name, description = parse_current(content)
        if not primary_email:
            skipped_no_email += 1
            continue
        if not is_placeholder(current_name, primary_email):
            skipped_no_placeholder += 1
            continue

        # Query Gmail
        new_name = gmail_friendly_name(primary_email)
        if not new_name:
            skipped_no_gmail += 1
            print(f"  · {path:60s} {current_name!r:30s} → no Gmail hit")
            continue
        if normalize(new_name) == normalize(current_name):
            print(f"  · {path:60s} {current_name!r:30s} → already correct")
            continue

        updates.append((path, sha, content, current_name, new_name, primary_email))
        print(f"  ★ {path:60s} {current_name!r:30s} → {new_name!r}")

    print(f"\nSummary: {len(updates)} updates, "
          f"{skipped_no_placeholder} non-placeholder, "
          f"{skipped_no_gmail} no-Gmail-hit, "
          f"{skipped_no_email} no-email")

    if args.dry_run:
        print("--dry-run: not committing.")
        return 0

    print("\nCommitting...")
    for path, sha, content, old_name, new_name, email in updates:
        new_content = patch_name(content, old_name, new_name)
        write_file(path, new_content, sha,
                   f"reference: resolve {path.split('/')[-1]} name → {new_name} (Gmail header)")
        print(f"  ✓ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
