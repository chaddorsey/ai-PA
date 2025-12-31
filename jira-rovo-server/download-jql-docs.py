#!/usr/bin/env python3
"""
Download Atlassian JQL documentation as markdown.
Downloads all pages under the JQL documentation section.
"""

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from pathlib import Path
from urllib.parse import urlparse
import re
import time
from datetime import datetime

BASE_URL = "https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/"
OUTPUT_DIR = Path("/Volumes/main-drive/ai-PA/docs/reference/jql-docs")

BASE_DOMAIN = "https://support.atlassian.com"
START_URL = "https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/"

# We'll extract links from the main page
JQL_DOC_PAGES = []

def sanitize_filename(url: str) -> str:
    """Convert URL to a safe filename."""
    # Extract the last part of the path
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    
    if path_parts:
        # Use the last meaningful part
        filename = path_parts[-1]
        # Remove query params and fragments
        filename = filename.split('?')[0].split('#')[0]
        # Replace special chars
        filename = re.sub(r'[^\w\-_\.]', '_', filename)
        if not filename:
            filename = "index"
    else:
        filename = "index"
    
    return filename + ".md"

def download_page(url: str, output_dir: Path):
    """Download a single page and save as markdown."""
    print(f"Downloading: {url}")
    
    try:
        # Set headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else 'Untitled'
        
        # Find main content - Atlassian docs typically use specific classes
        # Try to find the main article/content area
        main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'content|article|main'))
        
        if main_content:
            # Convert to markdown
            markdown = md(str(main_content), heading_style="ATX")
        else:
            # Fallback: convert body
            body = soup.find('body')
            if body:
                markdown = md(str(body), heading_style="ATX")
            else:
                markdown = md(response.text, heading_style="ATX")
        
        # Add metadata header
        header = f"""---
source_url: {url}
title: {title}
crawled_at: {datetime.now().isoformat()}
---

"""
        content = header + markdown
        
        # Save to file
        filename = sanitize_filename(url)
        output_path = output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  ✓ Saved to: {output_path}")
        return True
                
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def extract_links_from_page(url: str):
    """Extract all JQL-related documentation links from a page."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        links = set()
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            # Convert relative URLs to absolute
            if href.startswith('/'):
                full_url = BASE_DOMAIN + href
            elif href.startswith('http'):
                full_url = href
            else:
                continue
            
            # Filter for JQL-related docs
            if ('jira-service-management-cloud/docs' in full_url and 
                ('jql' in full_url.lower() or 
                 'advanced-search' in full_url.lower() or
                 'jql-functions' in full_url.lower() or
                 'jql-fields' in full_url.lower() or
                 'jql-keywords' in full_url.lower() or
                 'jql-operators' in full_url.lower())):
                links.add(full_url)
        
        return sorted(links)
    except Exception as e:
        print(f"Error extracting links: {e}")
        return []

def main():
    """Download all JQL documentation pages."""
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    
    # First, extract links from the main page
    print(f"Extracting links from: {START_URL}\n")
    all_links = extract_links_from_page(START_URL)
    
    # Always include the start URL
    if START_URL not in all_links:
        all_links.insert(0, START_URL)
    
    print(f"Found {len(all_links)} pages to download:\n")
    for link in all_links:
        print(f"  - {link}")
    print()
    
    # Download each page
    results = []
    for url in all_links:
        success = download_page(url, OUTPUT_DIR)
        results.append((url, success))
        # Small delay between requests
        time.sleep(1)
    
    # Summary
    print("\n" + "="*60)
    print("Download Summary:")
    print("="*60)
    successful = sum(1 for _, success in results if success)
    failed = len(results) - successful
    
    for url, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {url}")
    
    print(f"\nTotal: {len(results)} pages")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nFiles saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()

