"""Normalize yarle-emitted frontmatter for the qmd evernote corpus."""
import yaml

TYPE = "evernote-note"
SOURCE = "evernote"


def augment_frontmatter(text: str) -> str:
    """Add type/source discriminators without disturbing existing fields or body.

    Idempotent: re-running yields identical output (safe for weekly re-convert).
    Tolerates notes that have no frontmatter (yarle still emits it, but be safe).
    """
    if text.startswith("---"):
        _, fm_raw, body = text.split("---", 2)
        fm = yaml.safe_load(fm_raw) or {}
    else:
        fm, body = {}, "\n" + text
    fm["type"] = TYPE
    fm["source"] = SOURCE
    fm.setdefault("tags", [])
    new_fm = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{new_fm}\n---{body}"
