#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BehindTheName usage pages scraper
---------------------------------
Scrapes the given BehindTheName "usage" pages for personal names and outputs:
- a CSV file with category, name
- a JSON file with {category: [names...]}
- a TXT file with one name per line (unique, sorted)

Notes:
- Be considerate: this script is single-threaded and rate-limited.
- Check and respect the website's Terms of Use and robots.txt before heavy use.
- Tested on usage pages like:
    history, literature, ancient, medieval, mythology

Run:
    python scrape_btn_names.py

Dependencies:
    pip install requests beautifulsoup4 lxml
"""
import csv
import json
import re
import time
from typing import Dict, List, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.behindthename.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

# Allow letters (incl. many Latin diacritics), spaces, apostrophes, and hyphens.
# This is intentionally permissive; we still enforce BTN link pattern (/name/...).
NAME_CHARS = r"A-Za-zÀ-ÖØ-öø-ÿ'‑\-\s"  # includes hyphen and non-breaking hyphen
NAME_RE = re.compile(rf"^[{NAME_CHARS}]+$", re.UNICODE)

def clean_name(text: str) -> str:
    """Normalize whitespace and remove leading/trailing artifacts."""
    text = text.strip()
    # Replace multiple spaces with single
    text = re.sub(r"\s+", " ", text)
    # Remove trailing commas/periods if any slipped in
    text = re.sub(r"[.,;:]\s*$", "", text)
    return text

def is_probably_name(text: str) -> bool:
    """Heuristic: allow letters/diacritics, spaces, apostrophes, hyphens only."""
    return bool(NAME_RE.match(text))

def extract_names_from_soup(soup: BeautifulSoup) -> List[str]:
    """
    Extract names from a usage page soup.

    Based on observed structure:
      <span class="listname">
        <a href="/name/aang" class="nll">Aang</a>
      </span>

    We rely on the anchor href starting with /name/ and (often) class 'nll'.
    """
    names: List[str] = []
    for a in soup.select("span.listname a[href^='/name/']"):
        text = clean_name(a.get_text())
        # filter non-name anchors defensively
        if not text or not is_probably_name(text):
            continue
        names.append(text)
    return names

def get_page(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def paginate_usage(usage_slug: str) -> Iterable[str]:
    """
    Yield names from all pages of a given usage slug.
    Pagination pattern appears to be:
      /names/usage/{slug}
      /names/usage/{slug}/2
      /names/usage/{slug}/3
      ... until a page returns no names.
    """
    page = 1
    seen_empty = 0
    while True:
        url = f"{BASE}/names/usage/{usage_slug}" + ("" if page == 1 else f"/{page}")
        soup = get_page(url)
        batch = extract_names_from_soup(soup)
        if not batch:
            # Stop after first empty page in case of gaps
            seen_empty += 1
            if seen_empty >= 1:
                break
        else:
            seen_empty = 0
            for n in batch:
                yield n
        page += 1
        time.sleep(0.8)  # be polite

def scrape_categories(usages: Dict[str, str]) -> Dict[str, List[str]]:
    """
    usages: mapping of label -> slug (the bit after /usage/)
    """
    out: Dict[str, List[str]] = {}
    for label, slug in usages.items():
        print(f"Scraping {label} ...", flush=True)
        names = list(dict.fromkeys([n for n in paginate_usage(slug)]))  # dedupe, keep order
        print(f"  -> {len(names)} names")
        out[label] = names
    return out

def save_outputs(by_cat: Dict[str, List[str]]) -> None:
    # CSV (category, name)
    with open("btn_names.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "name"])
        for cat, names in by_cat.items():
            for n in names:
                w.writerow([cat, n])

    # JSON
    with open("btn_names.json", "w", encoding="utf-8") as f:
        json.dump(by_cat, f, ensure_ascii=False, indent=2)

    # TXT (unique, sorted)
    flat = sorted(set(n for names in by_cat.values() for n in names))
    with open("btn_names_unique.txt", "w", encoding="utf-8") as f:
        for n in flat:
            f.write(n + "\n")

    print("Saved: btn_names.csv, btn_names.json, btn_names_unique.txt")

def main():
    usages = {
        "history": "history",
        "literature": "literature",
        "ancient": "ancient",
        "medieval": "medieval",
        "mythology": "mythology",
    }
    data = scrape_categories(usages)
    total_unique = len(set(n for v in data.values() for n in v))
    print("\nSummary")
    for cat, names in data.items():
        print(f"  {cat:11s}: {len(names)}")
    print(f"  total unique: {total_unique}")
    save_outputs(data)

if __name__ == "__main__":
    main()
