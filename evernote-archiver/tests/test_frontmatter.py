from pathlib import Path

import yaml

from evernote_archiver.frontmatter import augment_frontmatter

FIX = Path(__file__).parent / "fixtures" / "sample-note.md"


def _split(text):
    _, fm_raw, body = text.split("---", 2)
    return yaml.safe_load(fm_raw), body


def test_augment_adds_type_and_preserves_fields():
    out = augment_frontmatter(FIX.read_text())
    fm, body = _split(out)
    assert fm["type"] == "evernote-note"          # OKF-style discriminator added
    assert fm["tags"] == ["coffee", "gear"]        # existing tags preserved
    assert fm["title"] == "Espresso dialing-in notes"
    assert fm["source"] == "evernote"              # provenance stamp
    assert "Grind finer" in body                   # body untouched


def test_augment_is_idempotent():
    once = augment_frontmatter(FIX.read_text())
    twice = augment_frontmatter(once)
    assert once == twice
