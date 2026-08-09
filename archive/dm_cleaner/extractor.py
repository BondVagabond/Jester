
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Any, List, Iterable
import json

def _iter_strings(obj: Any) -> Iterable[str]:
    """Yield strings from any nested mix of dict/list/str; ignore whitespace-only."""
    if obj is None:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= 1:
            yield s
        return
    if isinstance(obj, dict):
        # Extended priority keys to catch catalog-like JSONs
        priority = (
            "text","content","body","description","desc","notes","transcript","story",
            "entry","entries","rule","rules","value","values","data",
            "name","shortdesc","title","heading","label"
        )
        for k in priority:
            if k in obj:
                yield from _iter_strings(obj[k])
        for k, v in obj.items():
            if k in priority:
                continue
            yield from _iter_strings(v)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)
        return

def _extract_text_from_json_tuple(path: str) -> Tuple[str, str]:
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.stem, ""
    try:
        if p.suffix.lower() == ".jsonl":
            recs = []
            for line in raw.splitlines():
                if line.strip():
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        recs.append(line)
        else:
            obj = json.loads(raw)
            recs = obj if isinstance(obj, list) else [obj]
        pieces: List[str] = list(_iter_strings(recs))
        text = "\n\n".join(pieces).strip()
        return p.stem, text
    except Exception:
        return p.stem, raw

def _extract_text_from_txt_tuple(path: str) -> Tuple[str, str]:
    p = Path(path)
    try:
        return p.stem, p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.stem, ""

def _extract_text_html_tuple(path: str) -> Tuple[str, str]:
    from bs4 import BeautifulSoup
    import trafilatura
    p = Path(path)
    try:
        html = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.stem, ""
    text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_recall=True)
    if not text:
        soup = BeautifulSoup(html, "lxml")
        main = soup.find("article") or soup.find("main") or soup
        for sel in ["script","style","nav","header","footer","aside"]:
            for el in main.select(sel):
                el.decompose()
        text = main.get_text("\n", strip=True)
    title = p.stem
    try:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip() or title
        else:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True) or title
    except Exception:
        pass
    return title, text or ""

def _is_probably_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5).startswith(b"%PDF-")
    except Exception:
        return False

def _extract_text_pdf_strict_tuple(path: str) -> Tuple[str, str]:
    title = Path(path).stem
    text = ""
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = []
            for i in range(len(reader.pages)):
                try:
                    pages.append(reader.pages[i].extract_text() or "")
                except Exception:
                    pages.append("")
            text = "\n\n".join(pages).strip()
    except Exception:
        try:
            from pdfminer.high_level import extract_text as _pm_extract
            text = (_pm_extract(path) or "").strip()
        except Exception as e:
            raise RuntimeError(f"PDF extraction failed for {path}: {e}")
    return title, text

def _extract_text_from_any_tuple(path: str) -> Tuple[str, str]:
    suf = Path(path).suffix.lower()
    if suf in {".json",".jsonl"}:
        return _extract_text_from_json_tuple(path)
    if suf == ".txt":
        return _extract_text_from_txt_tuple(path)
    if suf == ".pdf":
        return _extract_text_pdf_strict_tuple(path) if _is_probably_pdf(path) else _extract_text_from_txt_tuple(path)
    if suf in {".html",".htm",".xhtml"}:
        return _extract_text_html_tuple(path)
    p = Path(path)
    try:
        return p.stem, p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return p.stem, ""

# Public API (cleaner expects str)
def extract_text_from_json(path: str) -> str:      return _extract_text_from_json_tuple(path)[1]
def extract_text_from_txt(path: str) -> str:       return _extract_text_from_txt_tuple(path)[1]
def extract_text_html(path: str) -> str:           return _extract_text_html_tuple(path)[1]
def extract_text_pdf(path: str) -> str:
    suf = Path(path).suffix.lower()
    if suf != ".pdf" or not _is_probably_pdf(path):
        return _extract_text_from_any_tuple(path)[1]
    return _extract_text_pdf_strict_tuple(path)[1]
def extract_text_from_any(path: str) -> str:       return _extract_text_from_any_tuple(path)[1]
