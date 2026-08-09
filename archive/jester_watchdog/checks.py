
from typing import List, Dict, Any, Tuple, Optional
from .utils import tokenize_words, jaccard_ngrams, cosine_similarity, shannon_entropy, char_repetition_ratio, matches_stock_opener, hash_prompt
import re, json

class CheckResult:
    def __init__(self, name: str, level: str, message: str, extra: dict=None, indices: List[Tuple[int,int]]=None):
        self.name = name
        self.level = level  # INFO/WARN/ERROR
        self.message = message
        self.extra = extra or {}
        self.indices = indices or []  # for pairwise flags

    def to_dict(self):
        return {
            "name": self.name,
            "level": self.level,
            "message": self.message,
            "extra": self.extra,
            "indices": self.indices,
        }

def check_seed_integrity(records: List[dict]) -> CheckResult:
    missing = []
    for i, r in enumerate(records):
        seed = r.get("seed", {})
        wids = seed.get("world_ids") or []
        if any(x in (None, "", "null") for x in wids) or len(wids) == 0:
            missing.append(i)
    level = "INFO" if not missing else "ERROR"
    msg = "All records have world_ids" if not missing else f"{len(missing)} records missing/empty world_ids"
    return CheckResult("seed_integrity", level, msg, {"count_missing": len(missing)}, indices=[(i,i) for i in missing])

def check_prompt_diversity(records: List[dict], jaccard_thresh: float=0.9, sample_cap:int=300) -> CheckResult:
    # flag near-duplicate prompts (suggests bad batching / reused context)
    pairs = []
    N = len(records)
    cap = min(N, sample_cap)
    for i in range(cap):
        for j in range(i+1, cap):
            s = jaccard_ngrams(records[i].get("prompt",""), records[j].get("prompt",""), n=3)
            if s >= jaccard_thresh:
                pairs.append((i,j))
    level = "INFO" if not pairs else "WARN"
    return CheckResult("prompt_diversity", level, f"{len(pairs)} near-duplicate prompt pairs (>= {jaccard_thresh})", {"pairs": len(pairs)}, indices=pairs)

def check_output_similarity(records: List[dict], jaccard_thresh: float=0.85, sample_cap:int=300) -> CheckResult:
    pairs = []
    N = len(records)
    cap = min(N, sample_cap)
    for i in range(cap):
        ai = records[i].get("assistant","")
        for j in range(i+1, cap):
            aj = records[j].get("assistant","")
            s = jaccard_ngrams(ai, aj, n=3)
            if s >= jaccard_thresh:
                pairs.append((i,j))
    level = "INFO" if not pairs else "WARN"
    return CheckResult("output_similarity_jaccard", level, f"{len(pairs)} near-duplicate output pairs (>= {jaccard_thresh})", {"pairs": len(pairs)}, indices=pairs)

def check_stock_openers(records: List[dict]) -> CheckResult:
    hits = []
    for i, r in enumerate(records):
        a = r.get("assistant","")
        if matches_stock_opener(a):
            hits.append(i)
    lvl = "INFO" if not hits else "WARN"
    return CheckResult("stock_openers", lvl, f"{len(hits)} responses match stock openers", {"count": len(hits)}, indices=[(i,i) for i in hits])

def check_entropy_repetition(records: List[dict]) -> CheckResult:
    vals = []
    reps = []
    for r in records:
        toks = tokenize_words(r.get("assistant",""))
        vals.append(shannon_entropy(toks))
        reps.append(char_repetition_ratio(r.get("assistant",""), span=6))
    import statistics
    info = {
        "entropy_mean": statistics.mean(vals) if vals else 0.0,
        "entropy_stdev": statistics.pstdev(vals) if vals else 0.0,
        "repeat_mean": statistics.mean(reps) if reps else 0.0,
        "repeat_stdev": statistics.pstdev(reps) if reps else 0.0,
    }
    level = "INFO"
    if info["repeat_mean"] > 0.25:
        level = "WARN"
    return CheckResult("entropy_repetition", level, "Entropy/Repeat stats computed", info)

def check_schema_presence(records: List[dict], required_keys: List[str]=None) -> CheckResult:
    if not required_keys:
        return CheckResult("schema_presence", "INFO", "No required_keys configured")
    missing = []
    for i, r in enumerate(records):
        payload = r
        if not all(k in payload for k in required_keys):
            missing.append(i)
    lvl = "INFO" if not missing else "ERROR"
    return CheckResult("schema_presence", lvl, f"{len(missing)} records missing required top-level keys", {"required": required_keys, "missing_count": len(missing)}, indices=[(i,i) for i in missing])

def check_debug_safeguards(records: List[dict]) -> CheckResult:
    hits = []
    for i, r in enumerate(records):
        dbg = r.get("debug", {})
        if dbg.get("safeguard_used"):
            hits.append(i)
    lvl = "INFO" if not hits else "WARN"
    return CheckResult("debug_safeguards", lvl, f"{len(hits)} records flagged safeguard_used", {"count": len(hits)}, indices=[(i,i) for i in hits])

def check_cache_collisions(records: List[dict]) -> CheckResult:
    # same prompt hash, different outputs -> good caching; same prompt hash, same output too many times => suspicious
    bucket = {}
    for i, r in enumerate(records):
        p = r.get("prompt","")
        h = hash_prompt(p)
        bucket.setdefault(h, []).append(i)
    heavy = {h: idxs for h, idxs in bucket.items() if len(idxs) >= 3}
    lvl = "INFO" if not heavy else "WARN"
    return CheckResult("cache_prompts", lvl, f"{len(heavy)} prompt-hash buckets have 3+ items", {"buckets": {k: len(v) for k,v in heavy.items()}})

AVAILABLE_CHECKS = [
    check_seed_integrity,
    check_schema_presence,
    check_prompt_diversity,
    check_output_similarity,
    check_stock_openers,
    check_entropy_repetition,
    check_debug_safeguards,
    check_cache_collisions,
]
