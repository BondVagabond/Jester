from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("html_cleaner")
if not logger.handlers:
    _fh = logging.FileHandler(os.environ.get("HTML_CLEANER_LOGFILE", "html_cleaner.log"), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_fh)
logger.setLevel(logging.INFO)

try:
    import nltk
    from nltk import ne_chunk, pos_tag, word_tokenize
    from nltk.tree import Tree as NltkTree
except Exception:
    nltk = None
    ne_chunk = pos_tag = word_tokenize = None
    NltkTree = None

try:
    import numpy as np
except Exception:
    np = None


POSITIVE = [
    "session report",
    "play report",
    "actual play",
    "transcript",
    "episode transcript",
    "session recap",
    "recap",
    "session log",
    "play log",
    "campaign diary",
    "table report",
    "initiative",
    "saving throw",
    "we fought",
    "we explored",
    "combat round",
    "round 1",
    "we entered",
    "party",
    "dm:",
    "gm:",
    "keeper:",
    "player:",
    "narrator:",
]

NEGATIVE = [
    "stat block",
    "armor class",
    "challenge rating",
    "legendary actions",
    "lair actions",
    "bestiary",
    "subclass",
    "archetype",
    "feat",
    "spell list",
    "class features",
    "build guide",
    "damage immunities",
    "damage resistances",
    "saving throws:",
    "skills:",
    "senses:",
    "actions:",
]

RE_DIALOGUE_LINE = re.compile(r"^[A-Z][A-Za-z0-9 .'-]{0,30}:\s", re.M)
RE_STAT_LABELS = [
    re.compile(r"\bArmor Class\b", re.I),
    re.compile(r"\bHit Points\b|\bHP\b", re.I),
    re.compile(r"\bSpeed\b\s*\d+\s*(ft\.|feet)", re.I),
    re.compile(r"\bChallenge\s+Rating\b|\bCR\s*\d+", re.I),
    re.compile(r"\bProficiency Bonus\b", re.I),
    re.compile(r"\bSTR\b.*\bDEX\b.*\bCON\b.*\bINT\b.*\bWIS\b.*\bCHA\b", re.I),
    re.compile(r"\bDamage (Immunities|Resistances|Vulnerabilities)\b", re.I),
    re.compile(r"\bSenses\b:\s", re.I),
    re.compile(r"\bActions\b:\s", re.I),
    re.compile(r"\bLegendary Actions\b", re.I),
]
RE_DICE = [
    re.compile(r"\broll(?:s|ed)?\b", re.I),
    re.compile(r"\b\d+d\d+\b"),
    re.compile(r"\bd20\b", re.I),
    re.compile(r"\binitiative\b", re.I),
    re.compile(r"\battack(?:s|ed)?\b", re.I),
    re.compile(r"\bhit(?:s)?\b|\bmiss(?:es)?\b", re.I),
]
RE_SESSION_HEAD = [
    re.compile(r"\b(Session|Episode)\s*\d+\b", re.I),
    re.compile(r"\bRecap\b", re.I),
    re.compile(r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?\]\s*", re.M),
]
RE_TABLE_ROW = re.compile(r"(^\s*\|.*\|\s*$)|(<tr|</tr>|<td|</td>)", re.M | re.I)
RE_OBJECT_PAGE_TITLE = re.compile(r"\b(Statblock|Bestiary|Monster|Class|Subclass|NPC|Feats?)\b", re.I)
RE_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
RE_PLATFORM = re.compile(
    r"(?i)\b(blogspot|reddit|fandom|wikipedia|dandwiki|homebrewery|github|notion|medium|stackexchange|srd)\b"
)


def approximate_bayesian_computation(distance_fn, sampler, epsilon, max_draws):
    for _ in range(max_draws):
        sample = sampler()
        if distance_fn(sample) <= epsilon:
            return sample
    return None


def method_of_simulated_moments(observed, simulate_fn, theta0, steps, lr):
    theta = dict(theta0)
    for _ in range(steps):
        sim = simulate_fn(theta)
        for k, obs in observed.items():
            theta[k] = theta[k] - (lr * (sim.get(k, 0.0) - obs))
    return theta


def extract_ner(text: str) -> List[str]:
    if nltk is None or word_tokenize is None or pos_tag is None or ne_chunk is None or NltkTree is None:
        return []
    try:
        toks = word_tokenize(text)
        tags = pos_tag(toks)
        chunks = ne_chunk(tags, binary=False)
        ents = []
        for chunk in chunks:
            if not isinstance(chunk, NltkTree):
                continue
            label = chunk.label()
            ent = " ".join(tok for tok, _ in chunk.leaves())
            ents.append(f"{label}:{ent}")
        return ents
    except Exception:
        return []


def load_extra_keywords(root: Path) -> Tuple[List[str], List[str]]:
    pos = POSITIVE[:]
    neg = NEGATIVE[:]
    candidates = [
        root / "keywords.json",
        Path(__file__).resolve().parent / "keywords.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            pos += [s for s in data.get("positive", []) if isinstance(s, str)]
            neg += [s for s in data.get("negative", []) if isinstance(s, str)]
            break
        except Exception:
            logger.warning("Could not load keyword overrides from %s", candidate)
            break
    return pos, neg


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = RE_URL.sub("", text)
    text = RE_PLATFORM.sub("", text)
    text = re.sub(r"[\t\u00A0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    boiler = re.compile(r"^(share this|related posts|navigation|comments\s*\(\d+\))$", re.I)
    lines = [ln for ln in lines if not boiler.match(ln)]
    return "\n".join(lines).strip()


def count_matches(text: str, patterns) -> int:
    if hasattr(patterns, "findall"):
        patterns = [patterns]
    return sum(len(p.findall(text)) for p in patterns)


def dialogue_density(text: str, head_lines: int = 800) -> int:
    head = "\n".join(text.splitlines()[:head_lines])
    return len(RE_DIALOGUE_LINE.findall(head))


def table_density(text: str) -> int:
    return len(RE_TABLE_ROW.findall(text))


def kw_hits(text: str, words: List[str]) -> int:
    low = text.lower()
    return sum(1 for w in words if w.lower() in low)


def feature_extract(text: str, title: str | None, pos_words: List[str], neg_words: List[str]) -> Dict[str, Any]:
    feats: Dict[str, Any] = {}
    feats["n_words"] = len(text.split())
    feats["dialogue_lines"] = dialogue_density(text)
    feats["dice_hits"] = count_matches(text, RE_DICE)
    feats["session_hits"] = count_matches(text, RE_SESSION_HEAD)
    feats["statblock_hits"] = count_matches(text, RE_STAT_LABELS)
    feats["table_hits"] = table_density(text)
    feats["pos_kw_hits"] = kw_hits(text, pos_words)
    feats["neg_kw_hits"] = kw_hits(text, neg_words)
    feats["title_object_cue"] = bool(RE_OBJECT_PAGE_TITLE.search(title or ""))
    feats["ner_count"] = len(extract_ner(text))
    return feats


def _heuristic_score(feats: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 0.0
    reasons = []

    if feats["dialogue_lines"] >= 10:
        score += 3.0
        reasons.append("dialogue-heavy")
    elif feats["dialogue_lines"] >= 4:
        score += 1.5
        reasons.append("dialogue-some")

    if feats["dice_hits"] >= 5:
        score += 2.0
        reasons.append("many-dice-mentions")
    elif feats["dice_hits"] >= 1:
        score += 0.8
        reasons.append("some-dice-mentions")

    if feats["session_hits"] >= 2:
        score += 1.5
        reasons.append("session/episode-markers")
    elif feats["session_hits"] == 1:
        score += 0.7
        reasons.append("session-marker")

    if feats["pos_kw_hits"] >= 2:
        score += 1.0
        reasons.append("pos-kw")
    elif feats["pos_kw_hits"] == 1:
        score += 0.4
        reasons.append("pos-kw-lite")

    if feats["statblock_hits"] >= 6:
        score -= 4.0
        reasons.append("many-statblock-labels")
    elif feats["statblock_hits"] >= 3:
        score -= 2.0
        reasons.append("some-statblock-labels")
    elif feats["statblock_hits"] >= 1 and feats["dialogue_lines"] <= 2:
        score -= 0.7
        reasons.append("statblock-terms-low-dialogue")

    if feats["table_hits"] >= 20:
        score -= 2.5
        reasons.append("table-heavy")
    elif feats["table_hits"] >= 8:
        score -= 1.0
        reasons.append("some-tables")

    if feats["neg_kw_hits"] >= 3:
        score -= 1.5
        reasons.append("neg-kw")
    elif feats["neg_kw_hits"] == 2:
        score -= 0.8
        reasons.append("neg-kw-lite")

    if feats["title_object_cue"]:
        score -= 0.8
        reasons.append("object-page-title")

    return score, reasons


def _bayes_factor_from_feats(feats: Dict[str, Any]) -> float:
    def bern_ll(k: float, p: float) -> float:
        k = max(0.0, min(1.0, k))
        p = max(1e-6, min(0.999999, p))
        return (k * math.log(p)) + ((1 - k) * math.log(1 - p))

    s_dialogue = min(1.0, feats["dialogue_lines"] / 12.0)
    s_dice = min(1.0, feats["dice_hits"] / 6.0)
    s_session = min(1.0, feats["session_hits"] / 3.0)
    s_poskw = min(1.0, feats["pos_kw_hits"] / 3.0)
    n_stat = min(1.0, feats["statblock_hits"] / 6.0)
    n_table = min(1.0, feats["table_hits"] / 24.0)
    n_negkw = min(1.0, feats["neg_kw_hits"] / 3.0)
    n_title = 1.0 if feats["title_object_cue"] else 0.0

    ll1 = (
        bern_ll(s_dialogue, 0.8)
        + bern_ll(s_dice, 0.7)
        + bern_ll(s_session, 0.6)
        + bern_ll(s_poskw, 0.6)
        + bern_ll(1.0 - n_stat, 0.7)
        + bern_ll(1.0 - n_table, 0.6)
        + bern_ll(1.0 - n_negkw, 0.65)
        + bern_ll(1.0 - n_title, 0.7)
    )

    ll0 = (
        bern_ll(s_dialogue, 0.2)
        + bern_ll(s_dice, 0.3)
        + bern_ll(s_session, 0.2)
        + bern_ll(s_poskw, 0.3)
        + bern_ll(1.0 - n_stat, 0.3)
        + bern_ll(1.0 - n_table, 0.4)
        + bern_ll(1.0 - n_negkw, 0.35)
        + bern_ll(1.0 - n_title, 0.3)
    )

    return math.exp(ll1 - ll0)


def _gmm_score(feats: Dict[str, Any], scaler: Optional[Any], gmm: Optional[Any]) -> Optional[float]:
    if np is None or gmm is None:
        return None

    xs = np.array(
        [[
            feats["dialogue_lines"],
            feats["dice_hits"],
            feats["session_hits"],
            feats["pos_kw_hits"],
            feats["statblock_hits"],
            feats["table_hits"],
            feats["neg_kw_hits"],
            int(feats["title_object_cue"]),
            feats["ner_count"],
            feats["n_words"],
        ]],
        dtype=float,
    )
    X = scaler.transform(xs) if scaler is not None else xs
    try:
        return float(gmm.score(X))
    except Exception:
        return None


def classify_transcript_like(
    feats: Dict[str, Any],
    scaler: Optional[Any] = None,
    gmm: Optional[Any] = None,
) -> Tuple[bool, float, str, Dict[str, Any]]:
    n = feats["n_words"]
    if n < 120:
        return False, 0.05, "too-short", {"bf10": 0.0, "gmm": None}

    base, reasons = _heuristic_score(feats)
    conf_heur = max(0.0, min(1.0, 0.5 + (base / 6.0)))

    bf10 = _bayes_factor_from_feats(feats)
    conf_bayes = bf10 / (1.0 + bf10)

    gmm_log = _gmm_score(feats, scaler, gmm)
    if gmm_log is not None:
        clipped = max(-20.0, min(20.0, gmm_log))
        conf_gmm = 1.0 / (1.0 + math.exp((-clipped) / 4.0))
    else:
        conf_gmm = None

    if conf_gmm is not None:
        conf = (0.4 * conf_heur) + (0.4 * conf_bayes) + (0.2 * conf_gmm)
    else:
        conf = (0.6 * conf_heur) + (0.4 * conf_bayes)

    def sampler():
        import random

        return {
            "dialogue": random.choice([2.0, 5.0, 8.0, 12.0]),
            "dice": random.choice([0.0, 1.0, 3.0, 6.0]),
        }

    def dist(x):
        return (abs(x["dialogue"] - feats["dialogue_lines"]) / 12.0) + (
            abs(x["dice"] - feats["dice_hits"]) / 6.0
        )

    kept = approximate_bayesian_computation(dist, sampler, epsilon=1.2, max_draws=40)
    if kept is None:
        conf *= 0.85
        reasons.append("abc-reject-lite")

    is_target = (conf >= 0.55) or (base >= 0.6 and bf10 > 2.0)
    tag = ",".join(reasons) if reasons else ("ok" if is_target else "low-score")
    debug = {
        "bf10": float(bf10),
        "conf_heur": conf_heur,
        "conf_bayes": conf_bayes,
        "conf_gmm": conf_gmm,
        "gmm_log": gmm_log,
    }
    return is_target, float(conf), tag, debug


__all__ = [
    "POSITIVE",
    "NEGATIVE",
    "approximate_bayesian_computation",
    "method_of_simulated_moments",
    "extract_ner",
    "load_extra_keywords",
    "normalize_text",
    "count_matches",
    "dialogue_density",
    "table_density",
    "kw_hits",
    "feature_extract",
    "classify_transcript_like",
]
