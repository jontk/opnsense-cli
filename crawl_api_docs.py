#!/usr/bin/env python3
"""Crawl OPNsense API documentation and save as markdown files."""

import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

BASE_URL = "https://docs.opnsense.org/development/api.html"
DOCS_ORIGIN = "https://docs.opnsense.org"
OUTPUT_DIR = Path("docs/api")
MODELS_DIR = Path("docs/models")
DELAY = 0.5  # seconds between requests


def fetch_page(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_main_content(soup: BeautifulSoup) -> str:
    """Extract the main documentation content, excluding nav/sidebar/footer."""
    # OPNsense docs use a div with role="main" or class "document"/"body"
    main = (
        soup.find("div", attrs={"role": "main"})
        or soup.find("div", class_="document")
        or soup.find("div", class_="body")
    )
    if main is None:
        main = soup.find("body")
    return str(main) if main else ""


def html_to_markdown(html: str) -> str:
    """Convert HTML content to clean markdown."""
    markdown = md(
        html,
        heading_style="ATX",
        strip=["script", "style", "nav"],
    )
    # Clean up excessive blank lines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip() + "\n"


def discover_subpages(soup: BeautifulSoup) -> list[str]:
    """Find all API subpage links from the main API page."""
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(BASE_URL, href)
        parsed = urlparse(full_url)
        # Only follow links under /development/api/
        if (
            parsed.netloc == urlparse(DOCS_ORIGIN).netloc
            and "/development/api/" in parsed.path
            and parsed.path.endswith(".html")
            and full_url not in links
        ):
            links.append(full_url)
    return links


def url_to_filepath(url: str) -> Path:
    """Convert a URL to a local file path for the markdown output."""
    parsed = urlparse(url)
    # e.g. /development/api/core/firewall.html -> core/firewall.md
    path = parsed.path
    # Strip the common prefix
    path = path.replace("/development/api/", "")
    path = path.replace(".html", ".md")
    return OUTPUT_DIR / path


def crawl_and_save():
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "opnsense-cli-doc-crawler/1.0 (documentation tool)"}
    )

    print(f"Fetching main API page: {BASE_URL}")
    main_soup = fetch_page(BASE_URL, session)

    # Save the main API page
    main_html = extract_main_content(main_soup)
    main_md = html_to_markdown(main_html)
    main_path = OUTPUT_DIR / "index.md"
    main_path.parent.mkdir(parents=True, exist_ok=True)
    main_path.write_text(main_md)
    print(f"  Saved: {main_path}")

    # Discover all subpages
    subpages = discover_subpages(main_soup)
    print(f"Found {len(subpages)} API subpages\n")

    for i, url in enumerate(subpages, 1):
        filepath = url_to_filepath(url)
        print(f"[{i}/{len(subpages)}] {url}")
        print(f"  -> {filepath}")

        try:
            soup = fetch_page(url, session)
            html = extract_main_content(soup)
            markdown = html_to_markdown(html)

            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(markdown)
        except requests.RequestException as e:
            print(f"  ERROR: {e}")

        time.sleep(DELAY)

    print(f"\nDone! Saved {len(subpages) + 1} files to {OUTPUT_DIR}/")

    # Second pass: download XML model files
    download_xml_models(session)


def download_xml_models(session: requests.Session):
    """Scan all .md files for <<uses>> rows and download referenced XML models."""
    xml_urls: set[str] = set()

    for md_file in OUTPUT_DIR.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        # Find all XML URLs in <<uses>> rows
        for match in re.finditer(r"\[.*?\]\((https://github\.com/[^)]+\.xml)\)", text):
            xml_urls.add(match.group(1))

    if not xml_urls:
        print("No XML model URLs found.")
        return

    print(f"\nFound {len(xml_urls)} unique XML model URLs")

    for i, url in enumerate(sorted(xml_urls), 1):
        # Convert blob URL to raw URL
        raw_url = url.replace(
            "github.com/opnsense/", "raw.githubusercontent.com/opnsense/"
        ).replace("/blob/master/", "/master/")

        # Derive local path: extract path after models/OPNsense/
        match = re.search(r"models/OPNsense/(.+\.xml)", url)
        if not match:
            print(f"  [{i}/{len(xml_urls)}] SKIP (no OPNsense path): {url}")
            continue

        rel_path = match.group(1)
        local_path = MODELS_DIR / "OPNsense" / rel_path

        if local_path.exists():
            print(f"  [{i}/{len(xml_urls)}] EXISTS: {local_path}")
            continue

        print(f"  [{i}/{len(xml_urls)}] {raw_url}")
        print(f"    -> {local_path}")

        try:
            resp = session.get(raw_url, timeout=30)
            resp.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(resp.text, encoding="utf-8")
        except requests.RequestException as e:
            print(f"    ERROR: {e}")

        time.sleep(DELAY)

    print(f"\nDone downloading XML models to {MODELS_DIR}/")


if __name__ == "__main__":
    crawl_and_save()
