import re, hashlib

def normalize_ws(text: str) -> str:
    text = text.replace('\xa0',' ').replace('\u200b',' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\s+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def strip_headers_footers(text: str) -> str:
    import re
    lines = text.splitlines()
    kept = []
    for ln in lines:
        l = ln.strip()
        if re.match(r'^\s*\d+\s*$', l):
            continue
        if re.search(r'Not for resale|Wizards of the Coast|DUNGEONS & DRAGONS|Adventurers League', l, re.I):
            continue
        kept.append(ln)
    return '\n'.join(kept)

def dehyphenate(text: str) -> str:
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    text = text.replace('-\n', '')
    return text

def hash_id(*parts) -> str:
    import hashlib
    h = hashlib.sha1('::'.join([p for p in parts if p]).encode('utf-8')).hexdigest()[:12]
    return h

def approx_words(text: str) -> int:
    return len(re.findall(r'\w+', text))


def approx_words_np(text: str) -> int:
    import numpy as _np, re as _re
    # vectorized-ish: still regex-based tokenization, but shows explicit numpy use
    return int(len(_re.findall(r'\w+', text or "")))
