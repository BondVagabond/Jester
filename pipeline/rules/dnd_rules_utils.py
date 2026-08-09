
import hashlib
import re

WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")

def normalize_whitespace(s: str) -> str:
    s = s.replace('\xa0', ' ').replace('\u200b', ' ').replace('\ufb01', 'fi').replace('\ufb02', 'fl')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\s*\n\s*\n\s*', '\n\n', s)
    return s.strip()

def fix_hyphenation(s: str) -> str:
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = re.sub(r'(\w+)-\n(\w+)', r'\1\2', s)
    return s

def clean_text(s: str) -> str:
    return normalize_whitespace(fix_hyphenation(s))

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode('utf-8', 'ignore')).hexdigest()

DICE_RE = re.compile(r'\bd(?:2|3|4|6|8|10|12|20|100)\b|\b\d+d\d+\b', re.I)
RULE_TOKENS = [
    'advantage','disadvantage','saving throw','attack roll','armor class','initiative','proficiency',
    'spell save dc','bonus action','reaction','hit points','long rest','short rest','movement',
    'rules glossary','condition','feat','class features','equipment','spellcasting','damage type','resistance',
    'vulnerability','immunity','ability check','d20','difficulty class','dc','ranged attack','melee attack',
    'grappled','restrained','prone','unconscious','frightened','poisoned','stunned','blinded','deafened',
]
NON_RULE_TOKENS = [
    'stat block','challenge rating','legendary actions','lair actions','monster manual','bestiary',
    'noble','commoner','goblin','dragon','wyvern','spell list','index of stat blocks','credits','ogl','copyright'
]

def score_rulesyness(text: str) -> float:
    t = text.lower()
    score = 0.0
    score += 2.0 if DICE_RE.search(t) else 0.0
    for tok in RULE_TOKENS:
        if tok in t:
            score += 1.0
    for tok in NON_RULE_TOKENS:
        if tok in t:
            score -= 0.5
    if re.search(r'\byou (can|may|make|gain|add|have)\b', t):
        score += 0.4
    if len(re.findall(r'\b\d+\b', t)) > 24 and score < 1:
        score -= 0.5
    return score

def features(text: str) -> dict[str, float]:
    t = text.strip()
    low = t.lower()
    words = re.findall(r'\w+', low)
    n_words = len(words)
    url_cnt = len(re.findall(r'https?://\S+|www\.\S+', low))
    punct = len(re.findall(r'[;:,.!?]', t))
    caps_lines = sum(1 for ln in t.split('\n') if ln.strip() and ln.strip().upper()==ln.strip())
    return {
        "n_words": float(n_words),
        "url_density": (url_cnt / max(1, n_words)),
        "punct_density": (punct / max(1, n_words)),
        "caps_lines": float(caps_lines),
        "rulesyness": score_rulesyness(t),
    }

def bayes_quality_posterior(text: str, alpha: float = 6.0, beta: float = 2.0) -> tuple[float, dict[str, bool]]:
    f = features(text)
    flags = {
        "too_short": f["n_words"] < 40,
        "too_long": f["n_words"] > 400,
        "url_heavy": f["url_density"] > 0.02,
        "low_punct": f["punct_density"] < 0.005,
        "capsy": f["caps_lines"] > 2,
        "low_rulesyness": f["rulesyness"] < 0.5,
    }
    good_signals = sum(1 for v in flags.values() if not v)
    bad_signals  = sum(1 for v in flags.values() if v)
    post_alpha = alpha + good_signals
    post_beta  = beta + bad_signals
    posterior_mean = post_alpha / (post_alpha + post_beta)
    return posterior_mean, flags

def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in WORD_RE.finditer(text)]

def bigrams(tokens: list[str]) -> list[str]:
    return [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]

def chunk_for_ai(text: str, max_chars: int = 900) -> list[str]:
    chunks = []
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    cur = ""
    for p in paragraphs:
        if len(cur) + len(p) + 2 <= max_chars:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            if len(p) <= max_chars:
                cur = p
            else:
                for i in range(0, len(p), max_chars):
                    chunks.append(p[i:i+max_chars])
                cur = ""
    if cur:
        chunks.append(cur)
    return chunks

def make_record(source_path: str, page_from: int, page_to: int, heading: str, chunk: str, doc_type: str = "rules"):
    post, flags = bayes_quality_posterior(chunk)
    return {
        "id": sha1(f"{source_path}:{page_from}-{page_to}:{heading}:{chunk[:60]}"),
        "source": source_path,
        "page_from": page_from,
        "page_to": page_to,
        "heading": heading,
        "text": chunk,
        "doc_type": doc_type,
        "rules_score": score_rulesyness(chunk),
        "quality_posterior": round(post, 4),
        "quality_flags": flags,
    }
