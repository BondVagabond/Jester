
import math
import re
from collections import Counter
from typing import List, Tuple, Dict, Any, Iterable

def tokenize_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9']+", text.lower())

def ngram_set(tokens: List[str], n: int) -> set:
    if n <= 0: return set()
    return set(tuple(tokens[i:i+n]) for i in range(max(0, len(tokens)-n+1)))

def jaccard_ngrams(a: str, b: str, n:int=3) -> float:
    ta, tb = tokenize_words(a), tokenize_words(b)
    A, B = ngram_set(ta, n), ngram_set(tb, n)
    if not A and not B: return 0.0
    return len(A & B) / max(1, len(A | B))

def cosine_similarity(a: str, b: str) -> float:
    # bag-of-words cosine without sklearn
    ta, tb = tokenize_words(a), tokenize_words(b)
    ca, cb = Counter(ta), Counter(tb)
    common = set(ca) & set(cb)
    num = sum(ca[t]*cb[t] for t in common)
    da = math.sqrt(sum(v*v for v in ca.values()))
    db = math.sqrt(sum(v*v for v in cb.values()))
    if da == 0 or db == 0: return 0.0
    return num/(da*db)

def shannon_entropy(tokens: List[str]) -> float:
    # base-2 entropy over token distribution
    if not tokens: return 0.0
    from collections import Counter
    c = Counter(tokens)
    total = sum(c.values())
    import math
    return -sum((v/total) * math.log2(v/total) for v in c.values())

def char_repetition_ratio(text: str, span:int=5) -> float:
    # simple anti-mode-collapse heuristic: fraction of repeated n-grams of chars
    seen = set()
    rep = 0
    total = 0
    for i in range(0, max(0, len(text)-span+1)):
        ng = text[i:i+span]
        total += 1
        if ng in seen:
            rep += 1
        else:
            seen.add(ng)
    if total == 0: return 0.0
    return rep/total

def hash_prompt(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

STOCK_OPENERS = [
    r"^\s*In the heart of\b",
    r"^\s*Amidst the\b",
    r"^\s*Within the\b",
    r"^\s*As the sun\b",
    r"^\s*The air is\s+(thick|heavy)\b",
]

def matches_stock_opener(text: str) -> bool:
    for rx in STOCK_OPENERS:
        if re.match(rx, text, flags=re.IGNORECASE):
            return True
    return False
