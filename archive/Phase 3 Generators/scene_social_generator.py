import os, json, logging, argparse, random, re, sys, glob
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

from seed_utils import SeedStore, SeedError
from context_safety import (
    contains_internal_reference,
    looks_like_artifact_name,
    sanitize_prompt_title,
    scrub_internal_references,
)

# Bayesian helpers from validators
try:
    from validators import approximate_bayesian_computation as ABC
except Exception:
    ABC = None

# ---------------- Logging ----------------
LOGFILE = os.environ.get("SCENE_SOCIAL_LOGFILE", "jester_scene_social.log")
logger = logging.getLogger("scene_social_generator")
if not logger.handlers:
    _fh = logging.FileHandler(LOGFILE, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_fh)
logger.setLevel(logging.INFO)

# ===== Runtime environment integrity check =====
def _assert_env_integrity(require_featuretools: bool = False):
    import importlib, sys
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
            ". Install via `pip install -r requirements.txt`."
        )
    # NLTK resource check
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
            raise RuntimeError(
                f"Missing NLTK resource: {res}. Run the NLTK downloader before executing."
            )

_assert_env_integrity(require_featuretools=False)


# ---------------- Watchdog auto-discovery (search anywhere under Jester) ----------------
if "jester_watchdog" not in sys.modules:
    root_dir = None
    cur = os.path.abspath(__file__)
    while True:
        parent = os.path.dirname(cur)
        if os.path.basename(parent).lower() == "jester":
            root_dir = parent
            break
        if parent == cur:
            break
        cur = parent
    if root_dir and os.path.exists(root_dir):
        matches = glob.glob(os.path.join(root_dir, "**", "jester_watchdog"), recursive=True)
        for m in matches:
            if os.path.isdir(m):
                sys.path.append(os.path.dirname(m))
                break

# ---------------- Redaction & sanitization ----------------

ALLOWED_STARTERS = (
    r"^\\s*You (see|notice|can|spot)\\b",
    r"^\\s*Make (a|an)\\b",
    r"^\\s*Roll\\b",
    r"^\\s*There (are|is)\\b",
)

URL_PATTERN = re.compile(
    r'(?i)\\b(?:https?://|www\\.)[^\\s]+'
)
MARKDOWN_LINK_PATTERN = re.compile(
    r'\\[[^\\]]+\\]\\([^)]+\\)'
)
PLATFORM_TERMS = re.compile(
    r'(?i)\\b(blogspot|reddit|fandom|wikipedia|dandwiki|homebrewery|github|notion|medium|stackexchange|srd)\\b'
)

TOOLING_TERMS = re.compile(
    r'(?i)\\b(jsonl|json|faiss|watchdog|dataset|datasets|metadata|index|indexes|logs?|reports?)\\b'
)

ID_TERMS = re.compile(
    r'(?i)\\b(world|rule):[0-9a-f]{8,}\\b'
)

WIN_PATH = re.compile(r'\\b[A-Za-z]:\\\\\\\\[^\\s"]+')
WIN_PATH_ESC = re.compile(r'\\b[A-Za-z]:\\\\\\\\[^\\s"]+')

def allowed_start(text: str) -> bool:
    head = text.strip()[:120]
    return any(re.match(rx, head, flags=re.IGNORECASE) for rx in ALLOWED_STARTERS)

def strip_urls(text: str) -> str:
    text = MARKDOWN_LINK_PATTERN.sub('', text)
    text = URL_PATTERN.sub('', text)
    return text

def strip_platform_and_tooling(text: str) -> str:
    text = PLATFORM_TERMS.sub('', text)
    text = TOOLING_TERMS.sub('', text)
    text = ID_TERMS.sub('', text)
    text = WIN_PATH.sub('', text)
    text = WIN_PATH_ESC.sub('', text)
    return re.sub(r'\\s{2,}', ' ', text).strip()

def sanitize_context_text(text: str) -> str:
    # Remove urls/markdown links and any obvious source/attribution lines
    text = strip_urls(text)
    # Drop lines that were likely link lists or attributions
    lines = []
    for ln in text.splitlines():
        raw = ln.strip()
        if not raw:
            continue
        if raw.startswith(('-', '*', '•')) and ('://' in raw or 'www.' in raw):
            continue
        if raw.lower().startswith(('source:', 'credit:', 'url:', 'link:')):
            continue
        if PLATFORM_TERMS.search(raw):
            continue
        lines.append(raw)
    text = ' '.join(lines)
    return strip_platform_and_tooling(text)

def redact_internal_refs(text: str) -> str:
    text = strip_urls(text)
    text = strip_platform_and_tooling(text)
    text = scrub_internal_references(text)
    # tidy punctuation
    text = re.sub(r'\\s+([,.;:!?])', r'\\1', text)
    return text.strip()

# ---------------- Context building ----------------
def humantitle(title: str) -> str:
    cleaned = sanitize_prompt_title(title)
    return cleaned or "World Note"

def summarize_chunk(txt: str, max_len: int = 220) -> str:
    if not txt:
        return ""
    s = sanitize_context_text(txt.replace("\\r\\n", " ").replace("\\n", " ").strip())
    parts = re.split(r'(?<=[.!?])\\s+', s)
    out = parts[0] if parts else s[:max_len]
    if len(out) > max_len:
        out = out[:max_len].rsplit(' ', 1)[0] + '…'
    return out

def format_world_context(items: List[Dict[str, Any]]) -> str:
    lines = []
    for it in items:
        if looks_like_artifact_name(it.get("title")) or looks_like_artifact_name(it.get("source")):
            continue
        title = humantitle(it.get('title',''))
        snippet = summarize_chunk(it.get('page_content',''))
        if snippet:
            lines.append(f"- {title}: {snippet}")
        else:
            lines.append(f"- {title}: (no additional details)")
    return "\\n".join(lines) or "- World Note: The area holds details worth a closer look."

def build_prompt(user_q: str, world_items):
    ctx = format_world_context(world_items)
    return f"""You are the Dungeon Master. Speak in-world to the players.

Context (brief, grounded facts seen/known in-world; all out-of-world links or sources are already removed):
{ctx}

Player asks: {user_q}

Speak like a DM:
- Start with a direct observation ("You see/You notice/You can…").
- 1–3 short sentences. If a check helps, suggest the skill and a brief reason.
- Never include URLs, file names, logs, reports, datasets, ids or paths—players do not see those.
"""

# ---------------- Backends ----------------
def _call_openai(prompt: str, model: str) -> str:
    try:
        import openai
    except ImportError as e:
        raise RuntimeError("OPENAI backend selected but 'openai' package is not installed") from e
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI backend requires OPENAI_API_KEY")
    openai.api_key = api_key
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are the Dungeon Master. Be concise, grounded, and in-world. Do not include any URLs, file names, ids, logs or reports."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=220,
        n=1,
    )
    return resp.choices[0].message["content"].strip()

def _call_mistral(prompt: str, model: str) -> str:
    try:
        from mistralai import Mistral
    except ImportError as e:
        raise RuntimeError("MISTRAL backend selected but 'mistralai' package is not installed") from e
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL backend requires MISTRAL_API_KEY")
    client = Mistral(api_key=api_key)
    resp = client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": "You are the Dungeon Master. Be concise, grounded, and in-world. Do not include any URLs, file names, ids, logs or reports."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=220,
        safe_mode=False,
    )
    return resp.choices[0].message["content"].strip()

def _local_fallback(world_items) -> str:
    titles = [humantitle(it.get("title","")) for it in world_items if it.get("title")]
    snippets = [summarize_chunk(it.get("page_content","")) for it in world_items]
    anchors = [t for t in titles if t][:2]
    hint = snippets[0] if snippets else ""
    core = ", ".join(anchors) if anchors else "the area"
    variants = [
        f"You notice details around {core}. {('Roll Perception to verify: ' + hint) if hint else 'Roll Perception for subtler clues.'}",
        f"You see obvious features near {core}. {('A quick Perception check may reveal: ' + hint) if hint else 'Make a Perception check for more.'}",
        f"You can scan {core} quickly. {('Perception might confirm: ' + hint) if hint else 'Roll Perception to uncover hidden signs.'}",
    ]
    return random.choice(variants)

def call_model(prompt: str, world_items):
    backend = (os.getenv("JESTER_BACKEND") or "LOCAL_FALLBACK").upper()
    model = os.getenv("JESTER_MODEL") or ("gpt-4o-mini" if backend == "OPENAI" else "mistral-small-latest")
    try:
        if backend == "OPENAI":
            return _call_openai(prompt, model)
        elif backend == "MISTRAL":
            return _call_mistral(prompt, model)
        else:
            return _local_fallback(world_items)
    except Exception as e:
        logger.warning("Model backend '%s' failed (%s). Using LOCAL_FALLBACK.", backend, e)
        return _local_fallback(world_items)

def postprocess_answer(text: str, world_items: List[Dict[str, Any]]) -> str:
    cleaned = redact_internal_refs(text)
    if contains_internal_reference(cleaned) or not cleaned:
        logger.warning("Narration contained internal reference after redaction; using LOCAL_FALLBACK.")
        cleaned = _local_fallback(world_items)
    if not allowed_start(cleaned):
        cleaned = "You notice: " + cleaned
    return cleaned.strip()

# --------------- Quality filter (ABC) ---------------
def abc_acceptance(answer: str) -> bool:
    if ABC is None:
        return True
    # Accept answers starting with desired starters and length within [40, 260] chars.
    starters = ("You see", "You notice", "You can", "Make a", "Roll", "There is", "There are")
    def dist_fn(_: object) -> float:
        pen = 0.0
        if not answer.startswith(starters):
            pen += 2.0
        n = len(answer)
        if n < 40 or n > 260:
            pen += 2.0
        return pen
    def sampler():  # not used, ABC wrapper needs it
        return None
    kept = ABC(dist_fn, sampler, epsilon=1.5, max_draws=1)
    return kept is not None

# --------------- Output path handling ---------------
def resolve_output_path(path_str: str, on_exists: str) -> Path:
    p = Path(path_str)
    if not p.exists():
        return p
    mode = (on_exists or "prompt").lower()
    if mode == "overwrite":
        return p
    if mode == "append":
        return p
    if mode == "timestamp":
        stem, suf = p.stem, p.suffix
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return p.with_name(f"{stem}_{ts}{suf}")
    if mode == "suffix":
        stem, suf = p.stem, p.suffix
        i = 1
        while True:
            cand = p.with_name(f"{stem} ({i}){suf}")
            if not cand.exists():
                return cand
            i += 1
    if sys.stdin and sys.stdin.isatty():
        ans = input(f"Output file exists: {p}\\nOverwrite (o), Append (a), Timestamp (t), Suffix (s), or Abort (x)? [o/a/t/s/x]: ").strip().lower()
        if ans.startswith("o"):
            return p
        if ans.startswith("a"):
            return p
        if ans.startswith("t"):
            stem, suf = p.stem, p.suffix
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            return p.with_name(f"{stem}_{ts}{suf}")
        if ans.startswith("s"):
            stem, suf = p.stem, p.suffix
            i = 1
            while True:
                cand = p.with_name(f"{stem} ({i}){suf}")
                if not cand.exists():
                    return cand
                i += 1
        raise RuntimeError("Aborted by user due to existing output file.")
    raise RuntimeError(f"Output file '{p}' exists. Pass --on_exists overwrite|append|timestamp|suffix|fail (default prompt).")

# ---------------- Watchdog integration ----------------
def run_watchdog_if_available(output_jsonl_path: str, report_prefix: str):
    try:
        from jester_watchdog.watchdog import run_watchdog, write_reports
        res = run_watchdog(inputs=[output_jsonl_path], required_keys=["seed","prompt","assistant"])
        write_reports(report_prefix, res)
        logger.info("Watchdog report written to prefix: %s", report_prefix)
    except Exception as e:
        logger.warning("Watchdog unavailable or failed: %s", e)

# ---------------- Main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world_index", required=True)
    ap.add_argument("--world_store", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--world_k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--on_exists", default="prompt", help="What to do if output exists: prompt|overwrite|append|timestamp|suffix|fail")
    ap.add_argument("--watchdog_prefix", default=None, help="If set, write watchdog JSON/HTML with this prefix")
    args = ap.parse_args()

    random.seed(args.seed)
    store = SeedStore(index_path=args.world_index, store_path=args.world_store)

    out_path = resolve_output_path(args.out, args.on_exists)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    append_mode = (out_path.exists() and args.on_exists.lower()=="append")
    mode = "a" if append_mode else "w"
    wrote = 0
    with open(out_path, mode, encoding="utf-8") as f:
        for i in range(args.count):
            try:
                world_items = store.sample_by_type("world", k=args.world_k)
                for it in world_items:
                    if not it.get("id") or not it.get("type"):
                        raise SeedError(f"Missing id/type in world item: keys={list(it.keys())[:10]}")

                user_q = f"Q{i+1}: What do I notice as I enter?"
                prompt = build_prompt(user_q, world_items)
                raw = call_model(prompt, world_items)
                assistant = postprocess_answer(raw, world_items)

                # ABC acceptance filter
                ok = abc_acceptance(assistant)
                record = {
                    "seed": {"world_ids": [it["id"] for it in world_items]},
                    "prompt": prompt,
                    "assistant": assistant,
                    "debug": {
                        "backend": os.getenv("JESTER_BACKEND") or "LOCAL_FALLBACK",
                        "had_internal_refs": raw != redact_internal_refs(raw),
                        "abc_accept": ok
                    }
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")
                wrote += 1

            except SeedError as e:
                logger.error("Seeding error on item %d: %s", i, e)
                raise
            except Exception as e:
                logger.exception("Generation error on item %d: %s", i, e)
                continue

    logger.info("Wrote %d items -> %s", wrote, out_path)

    # Write brief summary CSV next to output
    try:
        import pandas as _pd
        recs = []
        with open(out_path, 'r', encoding='utf-8') as _f:
            for line in _f:
                if line.strip():
                    recs.append(json.loads(line))
        df = _pd.DataFrame([
            {
                'world_n': len(r.get('seed',{}).get('world_ids', [])),
                'abc_accept': r.get('debug',{}).get('abc_accept')
            } for r in recs
        ])
        csv_path = str(Path(out_path).with_suffix('.summary.csv'))
        df.to_csv(csv_path, index=False)
        logger.info('Summary CSV -> %s', csv_path)
    except Exception as _e:
        logger.warning('Could not write summary CSV: %s', _e)

    if args.watchdog_prefix:
        run_watchdog_if_available(str(out_path), args.watchdog_prefix)

if __name__ == "__main__":
    main()
