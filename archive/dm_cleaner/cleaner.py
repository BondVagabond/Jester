# cleaner.py
"""
High-level PDF → cleaned chunks with logging, config, provenance, dedup/bias screen,
semantic near-dedup (optional), quality reporting, and knowledge tagging.

Public API (compatible):
    process_file(path: str, min_words: int | None = None, max_words: int | None = None, *,
                 return_rich: bool = False,
                 debug_dir: str | None = None,
                 report_path: str | None = None) -> list[dict] | dict

Defaults remain the same; extra features are opt-in via kwargs or env toggles.

Env toggles (safe defaults):
  # Semantic near-duplicate removal (graceful if deps missing)
  DM_SEM_DEDUP_ENABLED=0
  DM_SEM_DEDUP_MODEL=sentence-transformers/all-MiniLM-L6-v2
  DM_SEM_DEDUP_THRESH=0.92

  # Toxicity/NSFW filtering (flag or drop)
  DM_FILTER_TOXIC=0
  DM_FILTER_NSFW=0
  DM_FILTER_ACTION=flag   # or drop

  # Bias/term screening (simple lexicon)
  DM_BIAS_LEXICON=/path/to/terms.txt   # optional; else built-in small list

  # Doc ID policy (already supported)
  DM_DOC_ID_POLICY=stem | hash_stem
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from section_normalizer import normalize_sections
import hashlib
import json
import logging
import math
import os
import time
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

from datetime import datetime
from collections import Counter

# Pipeline stages
from extractor import extract_text_pdf
from parser import clean_text, sectionize, chunk_sections

# Central config + logging + dice regex
try:
    from config import (
        setup_logging,
        MIN_WORDS as CFG_MIN_WORDS,
        MAX_WORDS as CFG_MAX_WORDS,
        NORMALIZE,
        EXTRACT_RANDOM_ENCOUNTERS,
        ACT_STRUCTURE_ENABLED,
        DICE_REGEX,   # from config convenience
    )
    setup_logging()
except Exception:
    CFG_MIN_WORDS, CFG_MAX_WORDS = 120, 600
    NORMALIZE = {"unicode_form": "NFKC","collapse_spaces": True,"strip_headers_footers": True,"keep_lists_as_lines": True}
    EXTRACT_RANDOM_ENCOUNTERS = True
    ACT_STRUCTURE_ENABLED = True
    import re as _re
    DICE_REGEX = _re.compile(r"\b\d+d\d+(?:\+\d+)?\b", _re.I)

log = logging.getLogger("cleaner")

# -----------------------
# Errors / Guardrails
# -----------------------

class CleanerError(RuntimeError):
    def __init__(self, message: str, *, file: Optional[str] = None, stage: Optional[str] = None, stats: Optional[dict] = None):
        super().__init__(message)
        self.file = file
        self.stage = stage
        self.stats = stats or {}

# -----------------------
# Env helpers
# -----------------------

def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None: return default
    return str(v).strip().lower() in {"1","true","yes","on"}

def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None: return default
    try: return float(v)
    except Exception: return default

def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)

# Semantic dedup knobs
SEM_ENABLED   = _env_bool("DM_SEM_DEDUP_ENABLED", False)
SEM_MODEL     = _env_str("DM_SEM_DEDUP_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
SEM_THRESH    = _env_float("DM_SEM_DEDUP_THRESH", 0.92)

# Toxicity/NSFW knobs
FILTER_TOXIC  = _env_bool("DM_FILTER_TOXIC", False)
FILTER_NSFW   = _env_bool("DM_FILTER_NSFW", False)
FILTER_ACTION = _env_str("DM_FILTER_ACTION", "flag").lower()  # "flag" or "drop"

# Bias lexicon (optional file of terms, one per line)
BIAS_LEXICON_PATH = os.environ.get("DM_BIAS_LEXICON")

# -----------------------
# Utilities
# -----------------------

def _slugify(text: str) -> str:
    s = "".join(ch if ch.isalnum() else "_" for ch in text)
    s = "_".join([t for t in s.split("_") if t])
    return s.lower()[:80] or "document"

def _doc_id_for(path: Path) -> str:
    policy = os.environ.get("DM_DOC_ID_POLICY", "stem").lower()
    stem = _slugify(path.stem)
    if policy == "hash_stem":
        h = hashlib.sha1((stem + str(path.stat().st_size)).encode("utf-8")).hexdigest()[:10]
        return f"{stem}-{h}"
    return stem

def _supports_kw(fn, key: str) -> bool:
    try:
        import inspect
        return key in inspect.signature(fn).parameters
    except Exception:
        return False

def _write_debug(path: Path, name: str, content: str | dict | list) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")
    except Exception as e:
        log.debug("Failed writing debug artifact", extra={"file": name, "err": str(e)})

# -----------------------
# Bias lexicon (lightweight)
# -----------------------

def _load_bias_terms() -> List[str]:
    if BIAS_LEXICON_PATH:
        p = Path(BIAS_LEXICON_PATH)
        try:
            terms = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
            return terms
        except Exception as e:
            log.warning("Could not read DM_BIAS_LEXICON; falling back to built-in", exc_info=e)
    # Minimal built-in list (placeholder; expand as needed)
    return [
        "idiot","stupid","moron",
        "hate","kill yourself","racist","sexist",
    ]

BIAS_TERMS = _load_bias_terms()

def _screen_bias(text: str) -> List[str]:
    if not text: return []
    s = text.lower()
    hits = []
    for t in BIAS_TERMS:
        tt = t.lower()
        if tt in s:
            hits.append(t)
    # de-dup while preserving order
    seen=set(); out=[]
    for h in hits:
        if h.lower() not in seen:
            seen.add(h.lower()); out.append(h)
    return out

# -----------------------
# Simple toxicity/NSFW (graceful if deps missing)
# -----------------------

def _score_toxicity(texts: List[str]) -> List[float] | None:
    if not FILTER_TOXIC: return None
    try:
        # Try Detoxify (optional)
        from detoxify import Detoxify  # type: ignore
    except Exception:
        log.warning("Detoxify not installed; toxicity scores unavailable")
        return None
    try:
        # batch-friendly
        model = Detoxify('original-small')  # lightweight variant if available
        preds = model.predict(texts)
        # "toxicity" key usually present; fallback to mean of available keys
        scores=[]
        for i in range(len(texts)):
            val = preds.get("toxicity")
            if isinstance(val, (list, tuple)):
                scores.append(float(val[i]))
            elif isinstance(val, float):
                scores.append(float(val))
            else:
                # mean across keys at index i
                accum=[]
                for k,v in preds.items():
                    if isinstance(v, (list,tuple)) and i < len(v):
                        try: accum.append(float(v[i]))
                        except Exception: pass
                scores.append(sum(accum)/max(1,len(accum)) if accum else 0.0)
        return scores
    except Exception as e:
        log.warning("Detoxify failed; toxicity scores unavailable", exc_info=e)
        return None

def _flag_nsfw(texts: List[str]) -> List[bool] | None:
    if not FILTER_NSFW: return None
    # Minimal heuristic lexicon; replace with proper classifier if needed.
    nsfw_hits=[]
    bads={"nsfw","porn","sexual","explicit","xxx","nude","erotic"}
    for t in texts:
        s = (t or "").lower()
        nsfw_hits.append(any(b in s for b in bads))
    return nsfw_hits

# -----------------------
# Knowledge tagging (NER + dice)
# -----------------------

def _spacy_nlp():
    try:
        import spacy
        # Try a small English model
        for m in ("en_core_web_sm","en_core_web_md","en_core_web_lg"):
            try:
                return spacy.load(m)
            except Exception:
                continue
        return spacy.blank("en")  # fallback with no NER
    except Exception:
        return None

_NLP = _spacy_nlp()

def _tag_knowledge(texts: List[str]) -> List[Dict[str, Any]]:
    out=[]
    use_ner = _NLP and hasattr(_NLP, "pipe")
    if use_ner and getattr(_NLP, "has_pipe", lambda *_: False)("ner"):
        for t in texts:
            doc = _NLP(t)  # type: ignore
            ents = [{"text": e.text, "label": e.label_} for e in getattr(doc, "ents", [])]  # type: ignore
            out.append({"entities": ents})
    else:
        # No NER available; return empty placeholder per chunk
        out = [{"entities": []} for _ in texts]
    return out

def _find_dice(texts: List[str]) -> List[List[str]]:
    vals=[]
    for t in texts:
        vals.append(DICE_REGEX.findall(t or "") or [])
    return vals

# -----------------------
# Bayesian helpers (ABC / MSM) & numeric formatting
# -----------------------

def approximate_bayesian_computation(distance_fn, sampler, epsilon: float, max_draws: int = 1000):
    for _ in range(max_draws):
        s = sampler()
        if distance_fn(s) <= epsilon:
            return s
    return None

def method_of_simulated_moments(observed: dict, simulate_fn, theta0: dict, steps: int = 80, lr: float = 0.1):
    theta = dict(theta0)
    for _ in range(steps):
        sim = simulate_fn(theta)
        for k, v in observed.items():
            theta[k] = theta[k] - lr * (sim.get(k, 0.0) - v)
    return theta

class _NumericFmt:
    def pct(self, x: float, digits: int = 1) -> str:
        try: return f"{100.0 * x:.{digits}f}%"
        except Exception: return str(x)
    def fp(self, x: float, digits: int = 3) -> str:
        try: return f"{x:.{digits}f}"
        except Exception: return str(x)
numeric = _NumericFmt()

# -----------------------
# Stats / report helpers
# -----------------------

@dataclass
class StageStats:
    elapsed_sec: float
    chars: int = 0
    sections: int = 0
    chunks: int = 0

@dataclass
class RunStats:
    file: str
    doc_id: str
    extractor_backend: str | None
    ocr_pages: int | None
    t_extract: StageStats
    t_clean: StageStats
    t_section: StageStats
    t_chunk: StageStats
    total_elapsed_sec: float
    vocab_size: int = 0
    token_count: int = 0
    char_count: int = 0
    entropy_bits_per_token: float = 0.0
    bigram_diversity: float = 0.0
    duplicate_chunks: int = 0
    near_duplicates: int = 0
    flagged_toxic: int = 0
    flagged_nsfw: int = 0

    def to_dict(self) -> Dict[str, Any]:
        base = {
            "file": self.file,
            "doc_id": self.doc_id,
            "extractor_backend": self.extractor_backend,
            "ocr_pages": self.ocr_pages,
            "t_extract": asdict(self.t_extract),
            "t_clean": asdict(self.t_clean),
            "t_section": asdict(self.t_section),
            "t_chunk": asdict(self.t_chunk),
            "total_elapsed_sec": self.total_elapsed_sec,
            "vocab_size": self.vocab_size,
            "token_count": self.token_count,
            "char_count": self.char_count,
            "entropy_bits_per_token": self.entropy_bits_per_token,
            "bigram_diversity": self.bigram_diversity,
            "duplicate_chunks": self.duplicate_chunks,
            "near_duplicates": self.near_duplicates,
            "flagged_toxic": self.flagged_toxic,
            "flagged_nsfw": self.flagged_nsfw,
        }
        return base

def _tokenize(s: str) -> List[str]:
    import re
    return re.findall(r"\w+(?:'\w+)?", s.lower())

def _entropy(tokens: List[str]) -> float:
    if not tokens: return 0.0
    total = len(tokens)
    counts = Counter(tokens)
    h = 0.0
    for c in counts.values():
        p = c / total
        h -= p * math.log2(p)
    return h  # bits per token for unigram distribution

def _bigram_diversity(tokens: List[str]) -> float:
    if len(tokens) < 2: return 0.0
    bigrams = list(zip(tokens, tokens[1:]))
    unique = len(set(bigrams))
    return unique / max(1, len(bigrams))

# -----------------------
# Main API
# -----------------------

def process_file(
    path: str,
    min_words: Optional[int] = None,
    max_words: Optional[int] = None,
    *,
    return_rich: bool = False,
    debug_dir: Optional[str] = None,
    report_path: Optional[str] = None,
) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Extract → clean → sectionize → chunk a PDF, then run dedup/bias checks and AI enhancements.

    Args:
        path: PDF/TXT/MD path.
        min_words / max_words: overrides for chunking (defaults from config).
        return_rich: return {"chunks": [...], "stats": {...}} if True; else list of chunks.
        debug_dir: write debug artifacts (.raw.txt/.clean.txt/.sections.json/.chunks.json) when set.
        report_path: if provided, write a JSON report with quality stats & screening results.

    Raises:
        CleanerError with stage + partial stats on failure.
    """
    from time import perf_counter
    src = Path(path)
    doc_id = _doc_id_for(src)

    # Stats shells
    started = perf_counter()
    stats_extract = StageStats(0.0, 0)
    stats_clean   = StageStats(0.0, 0)
    stats_section = StageStats(0.0, 0)
    stats_chunk   = StageStats(0.0, 0)

    # Resolve min/max
    min_w = int(min_words) if min_words is not None else int(CFG_MIN_WORDS)
    max_w = int(max_words) if max_words is not None else int(CFG_MAX_WORDS)
    if min_w > max_w:
        raise CleanerError(f"min_words ({min_w}) cannot exceed max_words ({max_w})", file=str(src), stage="validate")

    log.info("Cleaner start", extra={
        "file": str(src), "doc_id": doc_id, "min_words": min_w, "max_words": max_w,
        "normalize": NORMALIZE, "extract_rand_encounters": EXTRACT_RANDOM_ENCOUNTERS,
        "acts_enabled": ACT_STRUCTURE_ENABLED,
        "sem_dedup": SEM_ENABLED, "sem_model": SEM_MODEL if SEM_ENABLED else None, "sem_thresh": SEM_THRESH if SEM_ENABLED else None,
        "tox_filter": FILTER_TOXIC, "nsfw_filter": FILTER_NSFW, "filter_action": FILTER_ACTION,
    })

    emit_debug = debug_dir is not None
    dbg_dir = Path(debug_dir) if debug_dir else Path(".cleaner_debug") / doc_id
    if emit_debug:
        dbg_dir.mkdir(parents=True, exist_ok=True)

    # -------- EXTRACT --------
    try:
        t0 = perf_counter()
        from extractor import extract_text_from_any
        raw_text = extract_text_from_any(str(src))
        if not raw_text or not raw_text.strip():
            raise RuntimeError("No extractable text")
        stats_extract.elapsed_sec = perf_counter() - t0
        stats_extract.chars = len(raw_text or "")
        log.info("Stage extract done", extra={"file": str(src), "elapsed_sec": round(stats_extract.elapsed_sec,3), "chars": stats_extract.chars})
        if emit_debug or log.isEnabledFor(logging.DEBUG):
            _write_debug(dbg_dir / f"{doc_id}.raw.txt", f"{doc_id}.raw.txt", raw_text)
    except Exception as e:
        rs = RunStats(str(src), doc_id, None, None, stats_extract, stats_clean, stats_section, stats_chunk, perf_counter()-started)
        log.exception("Extraction failed", extra={"file": str(src)})
        raise CleanerError(f"Extraction failed: {e}", file=str(src), stage="extract", stats=rs.to_dict()) from e

    if not raw_text or not raw_text.strip():
        rs = RunStats(str(src), doc_id, None, None, stats_extract, stats_clean, stats_section, stats_chunk, perf_counter()-started)
        log.error("No extractable text", extra={"file": str(src)})
        raise CleanerError("No extractable text", file=str(src), stage="extract", stats=rs.to_dict())

    # -------- CLEAN --------
    try:
        t0 = perf_counter()
        if _supports_kw(clean_text, "normalize"):
            cleaned = clean_text(raw_text, normalize=NORMALIZE)
        else:
            cleaned = clean_text(raw_text)
        stats_clean.elapsed_sec = perf_counter() - t0
        stats_clean.chars = len(cleaned or "")
        log.info("Stage clean done", extra={"file": str(src), "elapsed_sec": round(stats_clean.elapsed_sec,3), "chars": stats_clean.chars})
        if emit_debug or log.isEnabledFor(logging.DEBUG):
            _write_debug(dbg_dir / f"{doc_id}.clean.txt", f"{doc_id}.clean.txt", cleaned)
    except Exception as e:
        rs = RunStats(str(src), doc_id, None, None, stats_extract, stats_clean, stats_section, stats_chunk, perf_counter()-started)
        log.exception("Cleaning failed", extra={"file": str(src)})
        raise CleanerError(f"Cleaning failed: {e}", file=str(src), stage="clean", stats=rs.to_dict()) from e

    # -------- SECTIONIZE --------
    try:
        t0 = perf_counter()
        if _supports_kw(sectionize, "extract_random_encounters"):
            sections = sectionize(cleaned, extract_random_encounters=EXTRACT_RANDOM_ENCOUNTERS)
        else:
            sections = sectionize(cleaned)

        sections = normalize_sections(sections)
        stats_section.elapsed_sec = perf_counter() - t0
        stats_section.sections = len(sections) if isinstance(sections, list) else 0
        log.info("Stage sectionize done", extra={"file": str(src), "elapsed_sec": round(stats_section.elapsed_sec,3), "sections": stats_section.sections})
        if emit_debug or log.isEnabledFor(logging.DEBUG):
            _write_debug(dbg_dir / f"{doc_id}.sections.json", f"{doc_id}.sections.json", sections)
    except Exception as e:
        rs = RunStats(str(src), doc_id, None, None, stats_extract, stats_clean, stats_section, stats_chunk, perf_counter()-started)
        log.exception("Sectionizing failed", extra={"file": str(src)})
        raise CleanerError(f"Sectionizing failed: {e}", file=str(src), stage="sectionize", stats=rs.to_dict()) from e

    # -------- CHUNK --------
    try:
        t0 = perf_counter()
        if _supports_kw(chunk_sections, "acts_enabled"):
            chunks = chunk_sections(sections, min_words=min_w, max_words=max_w, acts_enabled=ACT_STRUCTURE_ENABLED)
        else:
            chunks = chunk_sections(sections, min_words=min_w, max_words=max_w)
        stats_chunk.elapsed_sec = perf_counter() - t0
        stats_chunk.chunks = len(chunks) if isinstance(chunks, list) else 0
        log.info("Stage chunk done", extra={"file": str(src), "elapsed_sec": round(stats_chunk.elapsed_sec,3), "chunks": stats_chunk.chunks})
    except Exception as e:
        rs = RunStats(str(src), doc_id, None, None, stats_extract, stats_clean, stats_section, stats_chunk, perf_counter()-started)
        log.exception("Chunking failed", extra={"file": str(src)})
        raise CleanerError(f"Chunking failed: {e}", file=str(src), stage="chunk", stats=rs.to_dict()) from e

    # Light ABC acceptance against moments (avg words per chunk)
    try:
        words = [len((c.get('text') or c.get('content') or '').split()) for c in chunks]
        avgw = float(np.mean(words)) if words else 0.0
        target = { 'avgw': (min_w+max_w)/2 }
        def sampler():
            import random
            return { 'avgw': random.uniform(min_w*0.7, max_w*1.3) }
        def dist(s):
            return abs(s['avgw'] - avgw) / max(1.0, target['avgw'])
        abc_accept = approximate_bayesian_computation(dist, sampler, epsilon=0.35, max_draws=40) is not None
    except Exception:
        abc_accept = True

    if not chunks:
        rs = RunStats(str(src), doc_id, None, None, stats_extract, stats_clean, stats_section, stats_chunk, perf_counter()-started)
        log.error("No chunks produced", extra={"file": str(src)})
        raise CleanerError("No chunks produced (check thresholds or parser rules)", file=str(src), stage="chunk", stats=rs.to_dict())

    # ----- Deterministic IDs & provenance -----
    created_at = datetime.utcnow().isoformat() + "Z"
    enriched=[]
    for idx, ch in enumerate(chunks, 1):
        ch2 = dict(ch)
        ch2.setdefault("doc_id", doc_id)
        ch2.setdefault("chunk_index", idx)
        ch2.setdefault("chunk_id", f"{doc_id}:{idx:04d}")
        ch2.setdefault("source_file", src.name)
        ch2.setdefault("created_at", created_at)
        ch2.setdefault("extractor_backend", None)  # could be filled if extractor exposes meta
        ch2.setdefault("ocr_pages", None)
        enriched.append(ch2)

    # ----- Hash-based dedup (exact) -----
    seen_hashes=set()
    deduped=[]
    duplicates=0
    for ch in enriched:
        txt = ch.get("text") or ch.get("content") or ""
        h = hashlib.sha1(txt.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            duplicates += 1
            ch.setdefault("flags",{}); ch["flags"]["duplicate_exact"]=True
            # keep first occurrence, skip subsequent by default
            continue
        seen_hashes.add(h)
        deduped.append(ch)

    # ----- Bias screening / toxicity / NSFW -----
    texts=[c.get("text") or c.get("content") or "" for c in deduped]
    bias_flags=[_screen_bias(t) for t in texts]
    tox_scores=_score_toxicity(texts)  # may be None
    nsfw_flags=_flag_nsfw(texts)       # may be None

    flagged_toxic=0
    flagged_nsfw=0
    screened=[]
    for i, ch in enumerate(deduped):
        flags = ch.setdefault("flags", {})
        # bias hits
        if bias_flags[i]:
            flags["bias_terms"]=bias_flags[i]
        # toxicity
        if tox_scores is not None:
            tscore = float(tox_scores[i])
            flags["toxicity"] = tscore
            if tscore >= 0.8:
                flagged_toxic += 1
                if FILTER_ACTION == "drop":
                    flags["dropped_reason"]="toxicity"
                    continue
                else:
                    flags["flagged_toxic"]=True
        # nsfw
        if nsfw_flags is not None and nsfw_flags[i]:
            flagged_nsfw += 1
            if FILTER_ACTION == "drop":
                flags["dropped_reason"]="nsfw"
                continue
            else:
                flags["flagged_nsfw"]=True

        screened.append(ch)

    # ----- Knowledge tagging (NER + dice) -----
    ents = _tag_knowledge([c.get("text") or c.get("content") or "" for c in screened])
    dice = _find_dice([c.get("text") or c.get("content") or "" for c in screened])
    for ch, e, d in zip(screened, ents, dice):
        ch.setdefault("knowledge", {})
        if e.get("entities"):
            ch["knowledge"]["entities"] = e["entities"]
        if d:
            ch["knowledge"]["dice"] = d

    # ----- Semantic near-dedup (optional) -----
    near_duplicates=0
    final_chunks=screened
    if SEM_ENABLED:
        try:
            from sentence_transformers import SentenceTransformer, util  # type: ignore
            model = SentenceTransformer(SEM_MODEL)
            corpus = [c.get("text") or c.get("content") or "" for c in screened]
            if corpus:
                emb = model.encode(corpus, convert_to_tensor=True, show_progress_bar=False)
                keep_mask=[True]*len(corpus)
                # greedy suppression
                for i in range(len(corpus)):
                    if not keep_mask[i]: continue
                    sims = util.cos_sim(emb[i], emb)[0]  # vector of sims to all
                    for j in range(i+1, len(corpus)):
                        if keep_mask[j] and float(sims[j]) >= SEM_THRESH:
                            keep_mask[j]=False
                            screened[j].setdefault("flags",{})["duplicate_semantic_of"] = screened[i]["chunk_id"]
                            near_duplicates += 1
                final_chunks=[c for k,c in zip(keep_mask, screened) if k]
        except Exception as e:
            log.warning("Semantic dedup unavailable; skipping", exc_info=e)
            final_chunks=screened

    # ----- Debug artifacts -----
    if emit_debug or log.isEnabledFor(logging.DEBUG):
        _write_debug(dbg_dir / f"{doc_id}.chunks.json", f"{doc_id}.chunks.json", final_chunks)

    # ----- Stats / report -----
    total_elapsed = time.perf_counter() - started
    # tokens for stats (from final set)
    all_text=" ".join([c.get("text") or c.get("content") or "" for c in final_chunks])
    tokens=_tokenize(all_text)
    vocab=len(set(tokens))
    ent=_entropy(tokens)
    bdiv=_bigram_diversity(tokens)

    rs = RunStats(
        file=str(src), doc_id=doc_id, extractor_backend=None, ocr_pages=None,
        t_extract=stats_extract, t_clean=stats_clean, t_section=stats_section, t_chunk=stats_chunk,
        total_elapsed_sec=total_elapsed,
        vocab_size=vocab, token_count=len(tokens), char_count=len(all_text),
        entropy_bits_per_token=ent, bigram_diversity=bdiv,
        duplicate_chunks=duplicates, near_duplicates=near_duplicates,
        flagged_toxic=flagged_toxic, flagged_nsfw=flagged_nsfw,
    )

    log.info("Cleaner summary", extra={
        "file": str(src), "doc_id": doc_id, "elapsed_total_sec": round(total_elapsed,3),
        "sections": stats_section.sections, "chunks": stats_chunk.chunks,
        "kept_chunks": len(final_chunks), "exact_dups": duplicates, "near_dups": near_duplicates,
        "vocab": vocab, "token_count": len(tokens), "entropy_bits_per_token": round(ent,4),
        "bigram_diversity": round(bdiv,4), "flagged_toxic": flagged_toxic, "flagged_nsfw": flagged_nsfw,
    })

    if report_path:
        try:
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            payload = rs.to_dict()
            payload['abc_accept'] = bool(abc_accept)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            # Also write per-chunk CSV summary next to report
            rows=[]
            for ch in final_chunks:
                rows.append({
                    'chunk_id': ch.get('chunk_id'),
                    'words': len((ch.get('text') or ch.get('content') or '').split()),
                    'has_entities': bool(ch.get('knowledge',{}).get('entities')),
                    'has_dice': bool(ch.get('knowledge',{}).get('dice')),
                    'flags': ','.join(sorted(ch.get('flags',{}).keys())) if isinstance(ch.get('flags',{}), dict) else ''
                })
            if rows:
                pd.DataFrame(rows).to_csv(Path(report_path).with_suffix('.chunks.csv'), index=False)
            log.info("Wrote quality report", extra={"file": str(report_path)})
        except Exception as e:
            log.warning("Failed writing report", exc_info=e)

    if return_rich:
        return {"chunks": final_chunks, "stats": rs.to_dict()}

    return final_chunks
