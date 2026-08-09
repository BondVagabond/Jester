
import os, re, json, difflib
from typing import Dict, List, Any, Tuple
from utils import normalize_ws

# Lenient mode via env var
LENIENT = os.environ.get("DM_LENIENT", "0") == "1"

# ------- Lexicon loading (themes/tones) -------
def _load_lexicon() -> Dict[str, List[str]]:
    env_path = os.environ.get("DM_LEXICON_PATH")
    candidates = []
    if env_path:
        candidates.append(env_path)
    here = os.path.dirname(__file__)
    candidates.append(os.path.join(here, "keywords.json"))
    for p in candidates:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("themes", [])
            data.setdefault("tones", [])
            return data
        except Exception:
            continue
    return {"themes": [], "tones": []}

_LEXICON = _load_lexicon()

def get_lexicon() -> Dict[str, List[str]]:
    return _LEXICON

def add_keywords(themes: List[str] = None, tones: List[str] = None):
    if themes:
        _LEXICON["themes"].extend([t for t in themes if t not in _LEXICON["themes"]])
    if tones:
        _LEXICON["tones"].extend([t for t in tones if t not in _LEXICON["tones"]])

# ------- Cue patterns -------
CUES = {
    "hook": r"\b(adventure\s+hook|hook|premise|overview|what's happening|summary)\b",
    "stakes": r"\b(stakes?|why it matters|consequences|fate of|doom|fall of)\b",
    "objectives": r"\b(objectives?|goals?|quests?|missions?)\b",
    "timeline": r"\b(timeline|schedule|clock|countdown)\b",
    "investigation": r"\b(clues?|investigat|mystery|suspect|interrogate|trail)\b",
    "heist": r"\b(heist|infiltrat|break-?in|escape|caper|jailbreak)\b",
    "solo": r"\b(go to \d+|turn to \d+|paragraph\s*\d+|choose your own|solo)\b",
    "branch": r"\b(if the (?:characters|players)|if\s+you\s+choose|players may|the party may|choice|decide to|alternatively)\b",
    "readaloud": r"\b(read(?:\s+the)?\s+following\s+aloud|boxed text|area [A-Z]?:)\\b",
    "one_shot": r"\b(1-?hour|one-?shot|mini-?adventure|can be completed in)\b",
}

# ------- Utilities -------
ADJ_SUFFIXES = ("y","ful","ous","ing","ive","al","ic","ish","less","some","esque")
ADJ_SEEDS = {
    "brooding","jaunty","melancholic","surreal","whimsical","grim","grimdark","gritty",
    "tense","suspenseful","noir","moody","brisk","playful","campy","bleak","hopeful",
    "heroic","epic","dark","lighthearted","light","somber","ominous","mysterious","mystic",
    "haunting","eerie","goofy","comedic","satirical","tragic","bittersweet","romantic"
}

THEME_VERBS = ("about","centers on","deals with","concerns","focuses on","explores","revolves around","is about","themes include","theme is","motifs include")
TONE_MARKERS = ("tone","tones","mood","vibe","atmosphere","feel","feels","feeling","genre","intended to be","designed to be")

def _split_list(s: str) -> List[str]:
    if not s: return []
    payload = s.strip()
    payload = re.sub(r"[•·●▪►]", "-", payload)
    payload = re.sub(r"\s+(?:and|&)\s+", ", ", payload, flags=re.I)
    parts = re.split(r",|;|\n|- ", payload)
    items = [p.strip(" .;:—–-") for p in parts if p and p.strip(" .;:—–-")]
    return items

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("light-hearted","lighthearted").replace("light hearted","lighthearted")
    s = s.replace("rom-com","romcom").replace("grim-dark","grimdark")
    s = s.replace("high fantasy","epic fantasy").replace("cosmic-horror","cosmic horror")
    s = re.sub(r"\s{2,}"," ", s)
    return s

def _fuzzy_map(token: str, vocab: List[str], cutoff: float=0.82) -> str:
    if not token: return token
    cand = difflib.get_close_matches(_norm(token), [_norm(v) for v in vocab], n=1, cutoff=cutoff)
    if cand:
        # Return the canonical vocab entry (original casing) that matches
        for v in vocab:
            if _norm(v) == cand[0]:
                return v
    return token

def _canonicalize(candidates: List[str], vocab: List[str]) -> List[str]:
    out = []
    vocab_norm = [ _norm(v) for v in vocab ]
    for c in candidates:
        nc = _norm(c)
        if not nc: continue
        if nc in vocab_norm:
            out.append(vocab[vocab_norm.index(nc)])
        else:
            # try fuzzy map
            mapped = _fuzzy_map(c, vocab)
            out.append(mapped)
    # de-duplicate preserving order
    seen = set(); dedup = []
    for x in out:
        k = _norm(x)
        if k not in seen:
            seen.add(k); dedup.append(x)
    return dedup

def _grab_heading_block(text: str, heading: str) -> List[str]:
    if not text: return []
    pattern = rf"(?im)^\s*{heading}\s*[:\-]?\s*\n?(.+?)(?:\n\s*\n|^\s*[A-Z][^\n]{0,60}\n[-=]{{3,}}|^\s*[A-Z][A-Za-z ]{{2,}}\s*$)"
    blocks = re.findall(pattern, text)
    items = []
    for b in blocks:
        items.extend(_split_list(b))
    return items

def split_sections(text: str) -> List[str]:
    parts = re.split(r'\n(?=[A-Z][^\n]{0,70}\n[-=]{3,}$)|\n{2,}', text or "")
    parts = [normalize_ws(p) for p in parts if p and len(p.strip())>0]
    return parts

def _explicit_label_capture(section: str) -> Tuple[List[str], List[str]]:
    themes = []
    tones = []
    themes += [m[1] for m in re.findall(r"(?i)\b(themes?|motifs?)\W*[:\-]\W*([^\n]+)", section)]
    tones  += [m[1] for m in re.findall(r"(?i)\b(tones?|mood|vibe|genre)\W*[:\-]\W*([^\n]+)", section)]
    for h in ["Themes","Theme","Motifs","Tone","Tones","Mood","Genre"]:
        items = _grab_heading_block(section, h)
        if h.lower() in ("tone","tones","mood","genre"):
            tones.extend(items)
        else:
            themes.extend(items)
    themes = sum([_split_list(x) for x in themes], [])
    tones  = sum([_split_list(x) for x in tones], [])
    return themes, tones

def _lexicon_scan(section: str) -> Tuple[List[str], List[str]]:
    s = (_norm(section) if section else "")
    themes = []
    tones = []
    for kw in _LEXICON.get("themes", []):
        kn = _norm(kw)
        if not kn: continue
        pat = re.compile(rf"(?<!\w){re.escape(kn).replace(' ', r'[\s\-]')}(?!\w)")
        if pat.search(s):
            themes.append(kw)
    for kw in _LEXICON.get("tones", []):
        kn = _norm(kw)
        if not kn: continue
        pat = re.compile(rf"(?<!\w){re.escape(kn).replace(' ', r'[\s\-]')}(?!\w)")
        if pat.search(s):
            tones.append(kw)
    # dedup
    seen=set(); themes_d=[]; 
    for t in themes:
        n=_norm(t)
        if n not in seen:
            seen.add(n); themes_d.append(t)
    seen=set(); tones_d=[]; 
    for t in tones:
        n=_norm(t)
        if n not in seen:
            seen.add(n); tones_d.append(t)
    return themes_d, tones_d

def _lenient_candidates(section: str) -> Tuple[List[str], List[str]]:
    """Heuristic capture outside the lexicon: pull adjectives for tone, noun/adjective phrases for theme."""
    if not LENIENT or not section: 
        return [], []
    text = section.strip()
    # Split into rough sentences
    sentences = re.split(r"(?<=[\.\?\!\;])\s+", text)
    themes_guess = []
    tones_guess = []

    # 1) Sentences with tone markers
    tone_pat = re.compile("|".join([re.escape(x) for x in TONE_MARKERS]), re.I)
    for s in sentences:
        if not tone_pat.search(s): 
            continue
        # grab quoted phrases (often descriptive)
        for q in re.findall(r"[“\"']([^”\"']{3,60})[”\"']", s):
            tones_guess.append(q.strip())
        # adjectives (surface heuristic)
        tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", s)
        for t in tokens:
            tl = t.lower()
            if tl in ADJ_SEEDS or any(tl.endswith(suf) for suf in ADJ_SUFFIXES):
                tones_guess.append(t)

    # 2) Sentences describing "about/centers on/deals with..." etc. → themes
    theme_pat = re.compile("|".join([re.escape(x) for x in THEME_VERBS]), re.I)
    for s in sentences:
        if not theme_pat.search(s): 
            continue
        # quoted contents are good theme candidates
        for q in re.findall(r"[“\"']([^”\"']{3,80})[”\"']", s):
            themes_guess.append(q.strip())
        # basic noun-ish chunks around the verb
        m = re.search(r"(?:about|centers on|deals with|concerns|focuses on|explores|revolves around|is about|themes include|theme is|motifs include)\s+(.+?)(?:[.;]|$)", s, re.I)
        if m:
            seg = m.group(1)
            # split on commas/and to get phrases
            parts = re.split(r",| and |\bor\b", seg, flags=re.I)
            for p in parts:
                # keep 2-6 word phrases; drop obvious stopwords-only
                words = re.findall(r"[A-Za-z][A-Za-z\-']+", p)
                if 2 <= len(words) <= 6:
                    themes_guess.append(" ".join(words))

    # Clean up
    def _dedup_norm(items):
        out=[]; seen=set()
        for x in items:
            x = re.sub(r"\s{2,}"," ", x.strip())
            if not x: 
                continue
            n = _norm(x)
            if n not in seen:
                seen.add(n); out.append(x)
        return out[:12]  # cap to avoid noise
    return _dedup_norm(themes_guess), _dedup_norm(tones_guess)

def extract_story_elements(section: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    section = section or ""
    lower = section.lower()

    cap_themes, cap_tones = _explicit_label_capture(section)
    scan_themes, scan_tones = _lexicon_scan(section)
    len_themes, len_tones = _lenient_candidates(section)

    themes_all = _canonicalize(cap_themes + scan_themes + len_themes, _LEXICON.get("themes", []))
    tones_all  = _canonicalize(cap_tones + scan_tones + len_tones, _LEXICON.get("tones", []))

    if themes_all: out["Themes"] = themes_all
    if tones_all:  out["Tones"]  = tones_all

    # Characters list (simple heuristic)
    chars = re.findall(r"\b(NPCs?|Notable NPCs?|Cast|Characters?)\b[:\-]?\s*(.*)", section, re.I)
    if chars:
        items = []
        for c in chars:
            items.extend(_split_list(c[1]))
        out["Characters"] = [x for x in items if x]

    for key, pat in [("Protagonist", r"\bprotagonist[s]?\W*[:\-]\W*([^\n]+)"),
                     ("Antagonist", r"\bantagonist[s]?\W*[:\-]\W*([^\n]+)"),
                     ("Backstory", r"\bbackstory\b[^\n]*:\s*([^\n]+)"),
                     ("Setting", r"\bsetting\b[^\n]*:\s*([^\n]+)"),
                     ("Exposition", r"\bexposition\b[^\n]*:\s*([^\n]+)"),
                     ("Perspective", r"\bperspective\b[^\n]*:\s*([^\n]+)"),
                     ("Style", r"\bstyle\b[^\n]*:\s*([^\n]+)"),
                     ("Inciting incident", r"\binciting (?:incident|event)\b[^\n]*:\s*([^\n]+)"),
                     ("Rising action", r"\brising action\b[^\n]*:\s*([^\n]+)"),
                     ("Climax", r"\bclimax\b[^\n]*:\s*([^\n]+)"),
                     ("Falling action", r"\bfalling action\b[^\n]*:\s*([^\n]+)"),
                     ("Resolution", r"\bresolution|denouement\b[^\n]*:\s*([^\n]+)"),
                     ("Conflict", r"\bconflict(?:s)?(?: and tension)?\b[^\n]*:\s*([^\n]+)") ]:
        m = re.search(pat, section, re.I)
        val = m.group(1).strip() if m else None
        if val: out[key] = val

    cues = {k: bool(re.search(v, lower, re.I)) for k,v in CUES.items()}
    out["cues"] = cues
    return out

def map_to_seven_acts(section: str) -> List[str]:
    acts = []
    s = (section or "").lower()
    import re as _re
    if _re.search(r"\bhook|overview|premise|opening image\b", s): acts.append("Act I: Hook/Opening Image")
    if _re.search(r"\binciting|call to adventure|disaster|kidnapped|attack\b", s): acts.append("Act II: Inciting Incident")
    if _re.search(r"\bfirst (turn|pinch)|leave town|accept the quest|into the forest\b", s): acts.append("Act III: First Turning Point")
    if _re.search(r"\bmidpoint|complication|twist|reversal\b", s): acts.append("Act IV: Midpoint/Complication")
    if _re.search(r"\bsecond (turn|pinch)|darkest moment|betrayal\b", s): acts.append("Act V: Second Turning Point")
    if _re.search(r"\bclimax|final battle|showdown|confront\b", s): acts.append("Act VI: Crisis/Climax")
    if _re.search(r"\bresolution|denouement|after(?:math)?|return\b", s): acts.append("Act VII: Resolution/Denouement")
    return acts
