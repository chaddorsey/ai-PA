"""Reconcile SQLite note count vs converted .md count (yarle silent-drop guard)."""
from pathlib import Path


def count_md(corpus_dir: str) -> int:
    """Count .md files in the corpus, excluding yarle index/meta files."""
    root = Path(corpus_dir)
    return sum(
        1 for p in root.rglob("*.md")
        if "_resources" not in p.parts and p.name.lower() not in {"index.md", "log.md"}
    )


def reconcile(db_count: int, md_count: int, tolerance: float = 0.02) -> dict:
    """ok=True iff missing/db_count <= tolerance. Returns details for logging."""
    missing = db_count - md_count
    frac = (missing / db_count) if db_count else 0.0
    return {"ok": frac <= tolerance, "db_count": db_count,
            "md_count": md_count, "missing": missing, "fraction": round(frac, 4)}
