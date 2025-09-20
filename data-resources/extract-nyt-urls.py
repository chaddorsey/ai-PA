#!/usr/bin/env python3
"""
extract_nyt_urls.py

Extract URLs from <a class="css-19j5qfu" href="https://www.nytimes.com/..."> tags
in an HTML file and write them (one per line) to an output text file.

Usage:
  python extract_nyt_urls.py input.html -o nyt_urls.txt
"""

import argparse
from html.parser import HTMLParser
from urllib.parse import urljoin


class NYTLinkExtractor(HTMLParser):
    def __init__(self, target_class="css-19j5qfu"):
        super().__init__(convert_charrefs=True)
        self.target_class = target_class
        self.base_url = None
        self.links = []
        self._seen = set()

    def handle_starttag(self, tag, attrs):
        if tag == "base":
            # capture <base href="..."> if present
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self.base_url = href
            return

        if tag != "a":
            return

        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        classes = attrs_dict.get("class", "") or ""
        class_tokens = set(classes.split())

        if href and self.target_class in class_tokens and href.startswith("https://www.nytimes.com"):
            # Resolve relative links if any (keeps absolute as-is)
            final = urljoin(self.base_url, href) if self.base_url else href
            if final not in self._seen:
                self._seen.add(final)
                self.links.append(final)


def main():
    ap = argparse.ArgumentParser(description="Extract NYTimes URLs from specific anchor tags.")
    ap.add_argument("html_file", help="Path to the input HTML file")
    ap.add_argument("-o", "--out", default="nyt_urls.txt", help="Path to output text file (default: nyt_urls.txt)")
    ap.add_argument("--class", dest="target_class", default="css-19j5qfu",
                    help="Anchor class to match (default: css-19j5qfu)")
    args = ap.parse_args()

    # Read HTML
    with open(args.html_file, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    # Parse & extract
    parser = NYTLinkExtractor(target_class=args.target_class)
    parser.feed(html)

    # Write output: one URL per line
    with open(args.out, "w", encoding="utf-8") as out_f:
        for url in parser.links:
            out_f.write(url + "\n")

    print(f"Extracted {len(parser.links)} URLs to {args.out}")


if __name__ == "__main__":
    main()
