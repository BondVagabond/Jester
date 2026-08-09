import re
from typing import List, Dict, Any
from utils import normalize_ws, strip_headers_footers, dehyphenate, approx_words
import numpy as np
import pandas as pd

# ===== Runtime environment integrity check =====
def _assert_env_integrity(require_featuretools: bool = False):
    import importlib
    required = ["numpy", "pandas", "sklearn", "nltk"]
    if require_featuretools:
        required.append("featuretools")
    missing = []
    for mod in required:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    if missing:
        raise RuntimeError(
            "Missing required dependencies: " + ", ".join(missing) +
            ". Please `pip install -r requirements.txt`."
        )
    # Verify NLTK resources
    import nltk
    needed = [
        ("tokenizers/punkt", "punkt"),
        ("taggers/averaged_perceptron_tagger", "averaged_perceptron_tagger"),
        ("chunkers/maxent_ne_chunker", "maxent_ne_chunker"),
        ("corpora/words", "words"),
    ]
    for path, res in needed:
        try:
            nltk.data.find(path)
        except LookupError:
            raise RuntimeError(f"Missing NLTK resource: {res}. Run the NLTK downloader before executing.")

_assert_env_integrity(require_featuretools=False)

from story_elements import split_sections, extract_story_elements, map_to_seven_acts

READ_ALOUD_PAT = re.compile(r"(?:^|\n)(?:Read(?:\s+the)?\s+following\s+aloud|Boxed Text)[:\-]?\s*(.+?)(?:\n\n|\Z)", re.I | re.S)
CHOICE_PAT = re.compile(r"(?:If the (?:characters|players)[^\.]+\.|Players may[^\.]+\.|The party may[^\.]+\.|Alternatively[^\.]+\.|If you choose[^\.]+\.|Decide to[^\.]+\.|\bchoice\b[^\.]*\.)", re.I)
SOLO_JUMP_PAT = re.compile(r"\b(?:go|turn)\s+to\s+(\d+)|paragraph\s*(\d+)", re.I)

def clean_text(raw: str) -> str:
    raw = raw if isinstance(raw, str) else ''
    t = strip_headers_footers(raw)
    t = dehyphenate(t)
    t = normalize_ws(t)
    return t

def sectionize(text: str) -> List[Dict[str, Any]]:
    sections = split_sections(text or '')
    out = []
    for sec in sections:
        meta = extract_story_elements(sec)
        acts = map_to_seven_acts(sec)
        read_alouds = READ_ALOUD_PAT.findall(sec) or []
        choices = CHOICE_PAT.findall(sec) or []
        solo_jumps = SOLO_JUMP_PAT.findall(sec) or []
        solo_targets = [j[0] or j[1] for j in solo_jumps if (j[0] or j[1])]
        out.append({
            'text': sec or '',
            'read_aloud': [ (r or '').strip() for r in read_alouds if (r or '').strip() ],
            'interrupt_points': [ (c or '').strip() for c in choices if (c or '').strip() ],
            'solo_targets': solo_targets,
            'acts': acts,
            'story': meta or {}
        })
    return out

def chunk_sections(sections: List[Dict[str, Any]], min_words=120, max_words=600):
    chunks = []
    buf = []
    wcount = 0
    for s in sections:
        text = s.get('text','')
        words = approx_words(text)
        if words > max_words * 1.5:
            paras = [p for p in text.split('\n\n') if (p or '').strip()]
            sub = []
            cur = []
            curw = 0
            for p in paras:
                pw = approx_words(p)
                if curw + pw > max_words and cur:
                    sub.append('\n\n'.join(cur))
                    cur = [p]; curw = pw
                else:
                    cur.append(p); curw += pw
            if cur: sub.append('\n\n'.join(cur))
            for part in sub:
                scopy = {k:v for k,v in s.items()}
                scopy['text'] = part
                chunks.append(scopy)
            continue
        if wcount + words > max_words and buf:
            merged = merge(buf)
            chunks.append(merged)
            buf = [s]; wcount = words
        else:
            buf.append(s); wcount += words
        if wcount >= min_words and (wcount >= max_words or len(buf) >= 3):
            merged = merge(buf); chunks.append(merged); buf=[]; wcount=0
    if buf:
        chunks.append(merge(buf))
    return chunks

def merge(secs: List[Dict[str,Any]]):
    merged_text = '\n\n'.join((s.get('text','') or '') for s in secs)
    read_aloud = sum([s.get('read_aloud', []) for s in secs], [])
    interrupt_points = sum([s.get('interrupt_points', []) for s in secs], [])
    solo_targets = sum([s.get('solo_targets', []) for s in secs], [])
    acts = sorted(set(sum([s.get('acts', []) for s in secs], [])))
    meta = {}
    for s in secs:
        story = s.get('story', {}) or {}
        for k,v in story.items():
            if k=='cues':
                meta.setdefault('cues', {})
                for ck,cv in (v or {}).items():
                    meta['cues'][ck] = meta['cues'].get(ck, False) or bool(cv)
            elif isinstance(v, list):
                meta.setdefault(k, [])
                for it in v:
                    val = (it or '').strip() if isinstance(it, str) else it
                    if val and val not in meta[k]:
                        meta[k].append(val)
            else:
                meta[k] = v
    return {
        'text': merged_text,
        'read_aloud': read_aloud,
        'interrupt_points': interrupt_points,
        'solo_targets': solo_targets,
        'acts': acts,
        'story': meta
    }
