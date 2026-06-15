"""Extract a clean Markdown article from authenticated NYT HTML."""
from bs4 import BeautifulSoup
from markdownify import markdownify as md


def _meta(soup, **attrs):
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content") if tag and tag.get("content") else None


def extract_article(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("section", attrs={"name": "articleBody"})
    if body is None:                       # older layout fallback
        cols = soup.select("div.StoryBodyCompanionColumn")
        if cols:
            body = BeautifulSoup("<section></section>", "lxml").section
            for c in cols:
                body.append(c)
    if body is None or not body.get_text(strip=True):
        raise ValueError(f"no article body found for {url} (not logged in / paywalled / layout change)")

    title_tag = soup.find(attrs={"data-testid": "headline"}) or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else (soup.title.get_text() if soup.title else url)
    byline = _meta(soup, name="byl")
    published = _meta(soup, property="article:published_time")

    markdown = md(str(body), heading_style="ATX", strip=["script", "style"]).strip()
    return {"title": title, "byline": byline, "published": published,
            "url": url, "markdown": markdown}
