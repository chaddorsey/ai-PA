"""Post-process the yarle output corpus in place: augment frontmatter, reconcile."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .frontmatter import augment_frontmatter
from .reconcile import count_md, reconcile


def _db_active_count(db_path: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT count(*) FROM notes WHERE is_active = 1").fetchone()[0]
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    touched = 0
    for md in corpus.rglob("*.md"):
        if "_resources" in md.parts or md.name.lower() in {"index.md", "log.md"}:
            continue
        original = md.read_text(encoding="utf-8")
        updated = augment_frontmatter(original)
        if updated != original:
            md.write_text(updated, encoding="utf-8")
            touched += 1

    rec = reconcile(_db_active_count(args.db), count_md(str(corpus)), args.tolerance)
    Path(args.state).write_text(json.dumps({"reconcile": rec, "frontmatter_touched": touched}, indent=2))
    print(json.dumps(rec, indent=2))
    if not rec["ok"]:
        print(f"RECONCILE FAILED: {rec['missing']} notes missing "
              f"({rec['fraction']:.1%}) — investigate before trusting the corpus", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
