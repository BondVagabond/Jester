#!/usr/bin/env python
"""
D&D Play Reports & Transcripts Scraper
--------------------------------------
Filename: scrape_dd_reports.py

Targets (initial seed list):
- https://diyanddragons.blogspot.com/2018/10/links-to-play-reports.html
- https://smolderingwizard.wordpress.com/category/play-reports-2/page/2/
- https://merricb.com/category/session-report-2/
- https://criticalrole.fandom.com/wiki/Dungeons_%26_Dragons_Campaign_Tips/Transcript
- https://dimension20.fandom.com/wiki/Episode_Transcripts

What it does:
- Recursively crawls *within the same domain* starting from the seed URLs
- Respects robots.txt & uses a polite rate limit
- Extracts main article text using trafilatura, with site-specific fallbacks
- Normalizes & saves results as JSONL (one record per page)
- Avoids duplicates and skips non-HTML resources

Usage (Python 3.10+ recommended):
    pip install aiohttp beautifulsoup4 trafilatura tqdm tldextract lxml
# Optional (speed-ups; skip on Windows if they error):
# pip install aiodns chardet
    # PowerShell
    python .\scrape_dd_reports.py --out out\reports.jsonl
    # CMD.exe (use carets for line breaks)
    python scrape_dd_reports.py ^
      --out out\reports.jsonl

Optional flags:
    --max-pages 2000           # global cap on pages crawled (default 2000)
    --concurrency 8            # parallel fetches (default 8)
    --timeout 30               # seconds per request (default 30)
    --save-html                # also save raw HTML files next to JSONL
    --include subpath          # include-only URL substring (can repeat)

Notes:
- This is a focused crawler. By default it only follows links that remain on the same eTLD+1 (e.g., *.fandom.com).
- It prioritizes pages containing likely markers: play, session, transcript, report, episode, recap.
- You can extend the DOMAIN_RULES below to add more precise allow/deny URL regexes and per-domain extraction.
"""

from __future__ import annotations
import asyncio
import aiohttp
import async_timeout
import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional, Set, Dict, Callable, Tuple, List

import tldextract
from bs4 import BeautifulSoup
import trafilatura
from trafilatura.sitemaps import sitemap_search
from urllib.parse import urljoin, urlparse, urldefrag
from urllib import robotparser

# ------------------ Configuration ------------------
USER_AGENT = "JesterCrawler/1.0 (+https://example.org)"
LIKELY_MARKERS = [
    "play", "session", "transcript", "report", "episode", "recap", "actual play"
]

SEED_URLS = [
    "https://diyanddragons.blogspot.com/2018/10/links-to-play-reports.html",
    "https://smolderingwizard.wordpress.com/category/play-reports-2/page/2/",
    "https://merricb.com/category/session-report-2/",
    "https://criticalrole.fandom.com/wiki/Dungeons_%25_Dragons_Campaign_Tips/Transcript",
    "https://dimension20.fandom.com/wiki/Episode_Transcripts",
]

# Domain-specific allow/deny URL rules & extraction hints
DOMAIN_RULES: Dict[str, Dict] = {
    # Blogger (DIY & Dragons): individual posts typically under /YYYY/MM/
    "blogspot.com": {
        "allow": [r"/\d{4}/\d{2}/"],
        "deny": [r"/search\?", r"/archive"],
    },
    # WordPress (Smoldering Wizard & MerricB): category pages -> posts
    "wordpress.com": {
        "allow": [r"/\d{4}/\d{2}/\d{2}/"],
    },
    "merricb.com": {
        "allow": [r"/\d{4}/\d{2}/\d{2}/", r"/category/session-report-2/"],
        "deny": [r"/tag/", r"/author/"],
    },
    # Fandom wikis: transcripts live on subpages; keep within fandom.com
    "fandom.com": {
        "allow": [r"/wiki/"],
        "deny": [r"/f\?", r"Special:", r"User:", r"Help:", r"File:", r"Category:"],
    },
}

# Site-specific content extractors (fallbacks when trafilatura is weak)
Extractor = Callable[[str], Optional[str]]


def fandom_extractor(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one(".mw-parser-output")
    if not main:
        return None
    # Remove tables, navboxes, and scripts
    for sel in ["table", "script", "style", ".navbox", ".toc"]:
        for el in main.select(sel):
            el.decompose()
    text = main.get_text("\n", strip=True)
    return text or None


def default_extractor(html: str) -> Optional[str]:
    # Try trafilatura first
    try:
        txt = trafilatura.extract(html, include_comments=False, include_tables=False)
        if txt and len(txt.split()) > 50:
            return txt
    except Exception:
        pass
    # Fallback: simple readability using BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    article = soup.find("article") or soup.find("main") or soup.find("div", class_=re.compile(r"post|entry|content"))
    if article:
        for el in article.select("script, style, nav, header, footer, aside"):
            el.decompose()
        txt = article.get_text("\n", strip=True)
        if txt and len(txt.split()) > 50:
            return txt
    # Last resort: whole page
    body = soup.find("body")
    if body:
        txt = body.get_text("\n", strip=True)
        if txt and len(txt.split()) > 100:
            return txt
    return None


EXTRACTOR_BY_DOMAIN: Dict[str, Extractor] = {
    "fandom.com": fandom_extractor,
}

# ------------------ Helpers ------------------

def canon(url: str) -> str:
    # Remove fragments, normalize scheme/host
    url = urldefrag(url)[0]
    if url.endswith('/'):
        url = url[:-1]
    return url


def same_etld1(a: str, b: str) -> bool:
    ea = tldextract.extract(a)
    eb = tldextract.extract(b)
    a_dom = ea.top_domain_under_public_suffix
    b_dom = eb.top_domain_under_public_suffix
    return (a_dom == b_dom) and bool(a_dom)



def allowed_by_rules(url: str, seed_domain: str) -> bool:
    rd = tldextract.extract(seed_domain).top_domain_under_public_suffix
    rules = DOMAIN_RULES.get(rd, {}) or DOMAIN_RULES.get(seed_domain.split(':')[-1], {})
    path = urlparse(url).path
    allow = rules.get("allow", [])
    deny = rules.get("deny", [])
    if any(re.search(p, path) for p in deny):
        return False
    if allow:
        return any(re.search(p, path) for p in allow)
    return True  # if no allow list, accept within-domain links


@dataclass
class Page:
    url: str
    title: Optional[str]
    text: Optional[str]
    raw_path: Optional[str]
    ts: float
    source_domain: str


# ------------------ Crawler ------------------
class Crawler:
    def __init__(self, seeds: List[str], out_jsonl: str, *, max_pages=2000, concurrency=8, timeout=30,
                 save_html=False, includes: List[str] | None = None):
        self.seeds = [canon(s) for s in seeds]
        self.out_jsonl = out_jsonl
        self.max_pages = max_pages
        self.sem = asyncio.Semaphore(concurrency)
        self.timeout = timeout
        self.save_html = save_html
        self.includes = includes or []

        self.session: Optional[aiohttp.ClientSession] = None
        self.robots: Dict[str, robotparser.RobotFileParser] = {}
        self.queue: asyncio.Queue[Tuple[str, str]] = asyncio.Queue()
        self.seen: Set[str] = set()
        self.visited: int = 0

        os.makedirs(os.path.dirname(out_jsonl) or '.', exist_ok=True)
        self.out_fp = open(out_jsonl, 'w', encoding='utf-8')

    async def __aenter__(self):
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=self.timeout, sock_read=self.timeout)
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        # seed the queue with (url, seed_domain)
        for s in self.seeds:
            await self.queue.put((s, s))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()
        self.out_fp.close()

    async def load_robots(self, base_url: str) -> robotparser.RobotFileParser:
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self.robots:
            return self.robots[origin]
        rp = robotparser.RobotFileParser()
        rp.set_url(origin + "/robots.txt")
        try:
            async with self.session.get(rp.url) as resp:
                if resp.status == 200 and 'text' in resp.headers.get('content-type',''):
                    rp.parse((await resp.text()).splitlines())
                else:
                    rp.default_allow = True
        except Exception:
            rp.default_allow = True
        self.robots[origin] = rp
        return rp

    async def fetch(self, url: str) -> Optional[Tuple[str, bytes]]:
        assert self.session is not None
        async with self.sem:
            try:
                async with async_timeout.timeout(self.timeout):
                    async with self.session.get(url, allow_redirects=True) as resp:
                        ctype = resp.headers.get('content-type', '')
                        if resp.status != 200 or 'text/html' not in ctype:
                            return None
                        content = await resp.read()
                        return resp.url.human_repr(), content
            except Exception:
                return None

    def match_includes(self, url: str) -> bool:
        if not self.includes:
            return True
        return any(substr.lower() in url.lower() for substr in self.includes)

    async def crawl(self):
        assert self.session is not None
        while self.visited < self.max_pages and not self.queue.empty():
            url, seed = await self.queue.get()
            url = canon(url)
            if url in self.seen:
                continue
            self.seen.add(url)

            # Stay in same eTLD+1 as the *seed* origin
            if not same_etld1(url, seed):
                continue

            # robots.txt
            rp = await self.load_robots(seed)
            if not rp.can_fetch(USER_AGENT, url):
                continue

            # include filters
            if not self.match_includes(url):
                continue

            # allow/deny rules
            if not allowed_by_rules(url, seed):
                continue

            fetched = await self.fetch(url)
            if not fetched:
                continue

            final_url, content = fetched
            html = content.decode(errors='ignore')
            page = await self.process_page(final_url, html)
            if page and page.text and self.is_likely_target(page):
                self.write_record(page)

            # Enqueue new links
            for link in self.extract_links(final_url, html):
                if link not in self.seen:
                    await self.queue.put((link, seed))

            self.visited += 1

    def is_likely_target(self, page: Page) -> bool:
        text = (page.title or "") + "\n" + (page.text or "")
        text_low = text.lower()
        return any(m in text_low for m in LIKELY_MARKERS) and len(text.split()) > 150

    def extract_links(self, base: str, html: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('#'):
                continue
            href = urljoin(base, href)
            if href.startswith('mailto:') or href.startswith('javascript:'):
                continue
            # normalize & strip fragments
            href = canon(href)
            links.append(href)
        return links

    async def process_page(self, url: str, html: str) -> Optional[Page]:
        title = self.extract_title(html)
        domain = tldextract.extract(url).top_domain_under_public_suffix or urlparse(url).netloc
        extractor = None
        # pick best extractor
        for key, func in EXTRACTOR_BY_DOMAIN.items():
            if domain.endswith(key):
                extractor = func
                break
        if extractor is None:
            extractor = default_extractor

        text = extractor(html)
        raw_path = None
        if self.save_html and text:
            raw_dir = os.path.join(os.path.dirname(self.out_jsonl), 'html')
            os.makedirs(raw_dir, exist_ok=True)
            fname = hashlib.sha256(url.encode()).hexdigest() + ".html"
            raw_path = os.path.join(raw_dir, fname)
            with open(raw_path, 'w', encoding='utf-8') as fp:
                fp.write(html)

        return Page(url=url, title=title, text=text, raw_path=raw_path, ts=time.time(), source_domain=domain)

    def extract_title(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find('h1')
        return h1.get_text(strip=True) if h1 else None

    def write_record(self, page: Page):
        rec = {
            "url": page.url,
            "title": page.title,
            "text": page.text,
            "raw_html_path": page.raw_path,
            "ts": int(page.ts),
            "source_domain": page.source_domain,
        }
        self.out_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.out_fp.flush()


# ------------------ CLI ------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Crawl D&D play reports & transcripts")
    p.add_argument('--out', required=True, help='Output JSONL path')
    p.add_argument('--max-pages', type=int, default=2000)
    p.add_argument('--concurrency', type=int, default=8)
    p.add_argument('--timeout', type=int, default=30)
    p.add_argument('--save-html', action='store_true')
    p.add_argument('--include', action='append', default=[], help='Substring filter; may repeat')
    p.add_argument('--seed', action='append', default=[], help='Additional seed URL; may repeat')
    return p.parse_args(argv)


async def main_async(args):
    seeds = SEED_URLS + args.seed
    async with Crawler(seeds, args.out, max_pages=args.max_pages, concurrency=args.concurrency,
                       timeout=args.timeout, save_html=args.save_html, includes=args.include) as crawler:
        await crawler.crawl()


def main(argv=None):
    args = parse_args(argv)
    try:
        if sys.platform.startswith('win'):
            # Avoid Proactor _call_connection_lost WinError 10022 on shutdown
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)


if __name__ == '__main__':
    main()
