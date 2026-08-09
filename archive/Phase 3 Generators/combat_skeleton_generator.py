import os, json, logging, argparse, random, re, sys, glob, math
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Callable

from seed_utils import SeedStore, SeedError
from context_safety import (
    looks_like_artifact_name,
    object_contains_internal_reference,
    sanitize_prompt_title,
)

# Bayesian helpers from validators (shared)
try:
    from validators import approximate_bayesian_computation as ABC, method_of_simulated_moments as MSM
except Exception:
    ABC = MSM = None

# ---------------- Logging ----------------
LOGFILE = os.environ.get("COMBAT_SKELETON_LOGFILE", "jester_combat.log")
logger = logging.getLogger("combat_skeleton_generator")
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

# ---------------- Prompt building ----------------
def format_items(items: List[Dict[str, Any]]):
    def humantitle(title: str) -> str:
        cleaned = sanitize_prompt_title(title)
        return cleaned or "World Note"
    def summarize_chunk(txt: str, max_len: int = 160) -> str:
        if not txt:
            return ""
        s = txt.replace("\\r\\n", " ").replace("\\n", " ").strip()
        parts = re.split(r'(?<=[.!?])\\s+', s)
        out = parts[0] if parts else s[:max_len]
        if len(out) > max_len:
            out = out[:max_len].rsplit(' ', 1)[0] + '…'
        return out
    lines = []
    for it in items:
        if looks_like_artifact_name(it.get("title")) or looks_like_artifact_name(it.get("source")):
            continue
        lines.append(f"- {humantitle(it.get('title',''))}: {summarize_chunk(it.get('page_content',''))}")
    return "\\n".join(lines) or "- World Note: No clean contextual notes available."

def build_prompt(world_items, rule_items) -> str:
    return f"""You are a D&D 5e combat assistant. Reply with **ONLY** a single JSON object on one line.

World notes:
{format_items(world_items)}

Rules notes:
{format_items(rule_items)}

Requirements for the JSON:
- Keys: "intent" (e.g., "attack", "cast", "dash", "disengage"), and "dice_requests" (array of strings like "1d20+5", "1d8+3").
- Optionally: "targets" (array of strings), "notes" (string).
- No prose, no preamble, no code fences, no explanations. JSON only.
Example: {{"intent":"attack","dice_requests":["1d20+7","1d8+4"],"targets":["nearest bandit"],"notes":"Longsword slash"}}
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
            {"role":"system","content":"Output strictly JSON only. No prose."},
            {"role":"user","content":prompt},
        ],
        temperature=0.3,
        max_tokens=180,
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
            {"role":"system","content":"Output strictly JSON only. No prose."},
            {"role":"user","content":prompt},
        ],
        temperature=0.3,
        max_tokens=180,
        safe_mode=False,
    )
    return resp.choices[0].message["content"].strip()

def _local_fallback(world_items, rule_items) -> Dict[str, Any]:
    anchors = []
    for it in (world_items + rule_items):
        t = sanitize_prompt_title(it.get("title") or "")
        if t:
            anchors.append(t.split()[0])
    rnd = random.Random()
    intents = ["attack","cast","dash","disengage","help","shove"]
    intent = rnd.choice(intents)
    if intent == "attack":
        dice = [rnd.choice(["1d20+5","1d20+6","1d20+7"]), rnd.choice(["1d8+3","1d6+4","1d10+3"])]
    elif intent == "cast":
        dice = [rnd.choice(["1d20+4","1d20+5"]), rnd.choice(["2d6","3d4+2","2d8"])]
    else:
        dice = [rnd.choice(["1d20+2","1d20+3"])]
    notes = " ".join(anchors[:3]) if anchors else "improv action"
    return {"intent": intent, "dice_requests": dice, "notes": notes}

def call_model(prompt: str, world_items, rule_items) -> str:
    backend = (os.getenv("JESTER_BACKEND") or "LOCAL_FALLBACK").upper()
    model = os.getenv("JESTER_MODEL") or ("gpt-4o-mini" if backend=="OPENAI" else "mistral-small-latest")
    try:
        if backend == "OPENAI":
            return _call_openai(prompt, model)
        elif backend == "MISTRAL":
            return _call_mistral(prompt, model)
        else:
            return json.dumps(_local_fallback(world_items, rule_items), ensure_ascii=False)
    except Exception as e:
        logger.warning("Model backend '%s' failed (%s). Using LOCAL_FALLBACK.", backend, e)
        return json.dumps(_local_fallback(world_items, rule_items), ensure_ascii=False)

# ---------------- Parsing / Validation ----------------
class MechanicsParseError(RuntimeError): pass

def parse_mechanics_block(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(json)?\\s*|\\s*```$", "", text, flags=re.IGNORECASE)
    try:
        obj = json.loads(text)
    except Exception as e:
        raise MechanicsParseError(f"Invalid JSON mechanics: {e}")
    if not isinstance(obj, dict):
        raise MechanicsParseError("Mechanics must be a JSON object")
    if "intent" not in obj or "dice_requests" not in obj:
        raise MechanicsParseError("Missing required keys: 'intent' and/or 'dice_requests'")
    if not isinstance(obj["dice_requests"], list) or not all(isinstance(x, str) for x in obj["dice_requests"]):
        raise MechanicsParseError("'dice_requests' must be a list of strings")
    if object_contains_internal_reference(obj):
        raise MechanicsParseError("Mechanics contains internal file or artifact references")
    return obj

# --------------- Quality gates (ABC/MSM) ---------------
def _target_moments(record: Dict[str, Any]) -> Dict[str, float]:
    dice = record.get("dice_requests", [])
    n_dice = len(dice)
    avg_len = sum(len(d) for d in dice) / max(1, n_dice)
    return {"n_dice": float(n_dice), "avg_len": float(avg_len)}

def _simulate_moments(theta: Dict[str, float]) -> Dict[str, float]:
    # very simple simulator
    n_dice = max(1, int(round(theta.get("n_dice", 2))))
    avg_len = max(5.0, theta.get("avg_len", 6.0))
    return {"n_dice": float(n_dice), "avg_len": float(avg_len)}

def msm_accept(record: Dict[str, Any]) -> bool:
    if MSM is None:
        return True
    obs = _target_moments(record)
    theta0 = {"n_dice": 2.0, "avg_len": 6.0}
    theta_hat = MSM(obs, _simulate_moments, theta0, steps=40, lr=0.2)
    # Accept if close in L1
    gap = sum(abs(obs[k]-theta_hat[k]) for k in obs.keys())
    return gap <= 1.5

def abc_accept(record: Dict[str, Any]) -> bool:
    if ABC is None:
        return True
    target = _target_moments(record)
    def sampler():
        return {"n_dice": random.choice([1.0,2.0,3.0]), "avg_len": random.choice([6.0,8.0,10.0])}
    def dist(x):
        return abs(x["n_dice"]-target["n_dice"]) + abs(x["avg_len"]-target["avg_len"])
    kept = ABC(dist, sampler, epsilon=3.0, max_draws=50)
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
        ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
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
            ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
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
    ap.add_argument("--rules_index", required=True)
    ap.add_argument("--rules_store", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--world_k", type=int, default=2)
    ap.add_argument("--rules_k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--on_exists", default="prompt", help="What to do if output exists: prompt|overwrite|append|timestamp|suffix|fail")
    ap.add_argument("--watchdog_prefix", default=None)
    args = ap.parse_args()

    random.seed(args.seed)
    wstore = SeedStore(index_path=args.world_index, store_path=args.world_store)
    rstore = SeedStore(index_path=args.rules_index, store_path=args.rules_store)

    out_path = resolve_output_path(args.out, args.on_exists)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    append_mode = (out_path.exists() and args.on_exists.lower()=="append")
    mode = "a" if append_mode else "w"

    wrote = 0
    with open(out_path, mode, encoding="utf-8") as f:
        for i in range(args.count):
            try:
                world_items = wstore.sample_by_type("world", k=args.world_k)
                rule_items = rstore.sample_by_type("rule", k=args.rules_k)
                for it in [*world_items, *rule_items]:
                    if not it.get("id") or not it.get("type"):
                        raise SeedError(f"Missing id/type in item: keys={list(it.keys())[:10]}")

                prompt = build_prompt(world_items, rule_items)
                raw = call_model(prompt, world_items, rule_items)

                safeguard_used = False
                try:
                    mech = parse_mechanics_block(raw)
                except Exception as e:
                    logger.error("Item %d mechanics parse failed: %s. Using LOCAL_FALLBACK.", i, e)
                    mech = _local_fallback(world_items, rule_items)
                    safeguard_used = True

                # Bayesian quality gates
                accept = msm_accept(mech) and abc_accept(mech)
                if not accept:
                    logger.info("Item %d rejected by MSM/ABC gate; regenerating once with fallback.", i)
                    mech = _local_fallback(world_items, rule_items)
                    accept2 = msm_accept(mech) and abc_accept(mech)
                    if not accept2:
                        logger.info("Item %d second attempt still below threshold; keeping with debug flag.", i)

                record = {
                    "seed": {
                        "world_ids": [it["id"] for it in world_items],
                        "rule_ids": [it["id"] for it in rule_items],
                    },
                    "prompt": prompt,
                    "assistant": json.dumps(mech, ensure_ascii=False),
                    "mechanics": mech,
                    "debug": {"safeguard_used": safeguard_used, "quality_gate": accept},
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")
                wrote += 1
            except (SeedError) as e:
                logger.error("Item %d failed (seed): %s", i, e)
                raise
            except Exception as e:
                logger.exception("Unexpected error on item %d: %s", i, e)
                continue

    logger.info("Wrote %d items -> %s", wrote, out_path)

    # Write brief summary CSV next to output
    try:
        import pandas as _pd
        # load the jsonl we just wrote
        recs = []
        with open(out_path, 'r', encoding='utf-8') as _f:
            for line in _f:
                if line.strip():
                    recs.append(json.loads(line))
        df = _pd.DataFrame([
            {
                'world_n': len(r.get('seed',{}).get('world_ids', [])),
                'rule_n': len(r.get('seed',{}).get('rule_ids', [])),
                'has_quality_gate': bool(r.get('debug',{}).get('quality_gate'))
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
