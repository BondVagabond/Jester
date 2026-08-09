
from __future__ import annotations
from pathlib import Path
from typing import Tuple, List, Dict, Any
import json
import tldextract
import trafilatura
from bs4 import BeautifulSoup

LIKELY_TEXT_KEYS = ["text","content","body","transcript","document","story","notes"]
LIKELY_TITLE_KEYS = ["title","name","heading","headline"]

def read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def extract_text(html: str) -> str:
    # favor_recall grabs more content for long transcripts
    txt = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )
    if txt:
        return txt
    # Fallback: very light BS4 text get
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("article") or soup.find("main") or soup
    for sel in ["script","style","nav","header","footer","aside"]:
        for el in main.select(sel):
            el.decompose()
    return main.get_text("\n", strip=True)

def guess_domain(url_or_path: str) -> str:
    # If a real URL is passed, tldextract gives eTLD+1;
    # if it's a file, just return 'localfile'
    if url_or_path.startswith(("http://","https://")):
        ext = tldextract.extract(url_or_path)
        return ext.registered_domain or url_or_path
    return "localfile"

def extract_title_from_html(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else None

def _json_pick_title_text(obj: Any) -> Tuple[str, str]:
    # Title
    title = None
    if isinstance(obj, dict):
        for k in LIKELY_TITLE_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                title = v.strip()
                break
    # Text
    text = None
    if isinstance(obj, dict):
        for k in LIKELY_TEXT_KEYS:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                text = v
                break
        if text is None:
            # join long-ish string fields
            parts = [v for v in obj.values() if isinstance(v, str) and len(v.split()) > 20]
            if parts:
                text = "\n\n".join(parts)
    elif isinstance(obj, str):
        text = obj
    if title is None:
        title = "untitled"
    if text is None:
        text = ""
    return title, text

def extract_from_path(path: str) -> Tuple[str, str, str]:
    """
    Unified extractor for .html/.htm/.xhtml, .txt, .json, .jsonl files.
    Returns: (title, text, source_domain)
    """
    p = Path(path)
    suffix = p.suffix.lower()

    # .txt
    if suffix == ".txt":
        raw = p.read_text(encoding="utf-8", errors="ignore")
        return p.stem, raw, "localfile"

    # .jsonl
    if suffix == ".jsonl":
        lines = [json.loads(l) for l in p.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
        pieces = []
        for o in lines:
            _, txt = _json_pick_title_text(o)
            if txt:
                pieces.append(txt)
        title = p.stem
        return title, "\n\n".join(pieces), "localfile"

    # .json
    if suffix == ".json":
        obj = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        if isinstance(obj, list):
            pieces = []
            for o in obj:
                _, txt = _json_pick_title_text(o)
                if txt:
                    pieces.append(txt)
            title = p.stem
            return title, "\n\n".join(pieces), "localfile"
        else:
            title, text = _json_pick_title_text(obj)
            return (title or p.stem), text, "localfile"

    # HTML family
    html = read_html(p)
    text = extract_text(html)
    title = extract_title_from_html(html) or p.stem
    domain = guess_domain(path)
    return title, text, domain
