"""Render an article dict into a frontmatter Markdown document for qmd."""
import yaml


def build_document(art: dict, saved_date: str | None = None) -> str:
    fm = {
        "type": "nyt-article",
        "source": "nyt-saved",
        "title": art.get("title"),
        "byline": art.get("byline"),
        "url": art.get("url"),
        "published": art.get("published"),
        "saved_date": saved_date,
        "tags": [],
    }
    fm = {k: v for k, v in fm.items() if v is not None}
    head = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{head}\n---\n\n# {art.get('title','')}\n\n{art['markdown']}\n"
