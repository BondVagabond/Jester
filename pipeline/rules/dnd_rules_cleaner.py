# dnd_rules_cleaner.py
from __future__ import annotations

import re

# ---------- low-level normalizers ----------

RE_SPACES = re.compile(r"[ \t]+")
RE_MULTI_NL = re.compile(r"\n{3,}")
RE_SOFT_HYPHEN_WRAP = re.compile(r"(\w+)-\n(\w+)")                   # word-\nword  -> wordword
RE_BULLET = re.compile(r"^\s*[•·●►▪\-–—]\s*")                        # bullets at line start
RE_NUMBERED = re.compile(r"^\s*(\d+[\).]|\(\d+\)|[a-z]\))\s+")       # 1) (1) a) ...
RE_DASHES = re.compile(r"[–—]+")                                     # normalize en/em dashes to '-'
RE_GLYPHS = [
    (re.compile("\u00A0"), " "),     # nbsp
    (re.compile("\u200B"), ""),      # zero-width space
    (re.compile("\ufb01"), "fi"),    # ligatures
    (re.compile("\ufb02"), "fl"),
]

def _fix_ligatures(s: str) -> str:
    for rx, rep in RE_GLYPHS:
        s = rx.sub(rep, s)
    return s

def _fix_hyphenation(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # de-hyphenate across wraps (common in PDFs)
    s = RE_SOFT_HYPHEN_WRAP.sub(r"\1\2", s)
    return s

def _normalize_whitespace(s: str) -> str:
    s = RE_SPACES.sub(" ", s)
    s = RE_MULTI_NL.sub("\n\n", s)
    return s.strip()

def _normalize_punctuation_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        ln = RE_DASHES.sub("-", ln)
        # normalize bullets and ordered list markers minimally (keep list-ness)
        if RE_BULLET.match(ln):
            ln = RE_BULLET.sub("- ", ln)
        elif RE_NUMBERED.match(ln):
            m = RE_NUMBERED.match(ln)
            ln = f"{m.group(1)} " + ln[m.end():]
        out.append(ln)
    return out

# ---------- repeating header/footer removal ----------

def _remove_repeating_lines(lines: list[str], min_len: int = 12, min_repeats: int = 4) -> list[str]:
    """
    Heuristic: detect lines that repeat across many pages (running headers/footers)
    and drop them. Keeps short, meaningful rules like 'Armor Class (AC)...'
    """
    from collections import Counter
    # Count normalized candidates
    norm = [re.sub(r"\s+", " ", ln).strip() for ln in lines]
    counts = Counter([ln for ln in norm if len(ln) >= min_len])
    frequent = {ln for ln, c in counts.items() if c >= min_repeats}

    out: list[str] = []
    for raw, nrm in zip(lines, norm, strict=False):
        if nrm in frequent:
            # Allow numeric page-only lines to be dropped without counting
            continue
        # drop bare page numbers or obvious toc markers
        if re.fullmatch(r"\s*\d+\s*", raw):
            continue
        if raw.strip().lower() in {"index", "contents", "table of contents"}:
            continue
        out.append(raw)
    return out

# ---------- public cleaners ----------

def clean_pdf_text(raw: str) -> str:
    """
    PDF cleaner tuned for rulebooks:
    - fixes ligatures/soft hyphen wraps
    - removes repeating headers/footers & page numbers
    - normalizes bullets/dashes
    - collapses excessive blank lines
    """
    s = _fix_ligatures(raw)
    s = _fix_hyphenation(s)

    # work line-by-line for header/footer logic
    lines = s.split("\n")
    lines = _remove_repeating_lines(lines, min_len=14, min_repeats=4)
    lines = _normalize_punctuation_lines(lines)

    s = "\n".join(lines)
    s = _normalize_whitespace(s)
    return s

def clean_html_text(raw: str) -> str:
    """
    HTML cleaner: lighter touch (the extractor already tries to keep main content).
    - normalize ligatures, bullets, dashes
    - tighten whitespace
    """
    s = _fix_ligatures(raw)
    s = _fix_hyphenation(s)
    lines = s.split("\n")
    lines = _normalize_punctuation_lines(lines)
    s = "\n".join(lines)
    s = _normalize_whitespace(s)
    return s
