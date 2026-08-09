
from __future__ import annotations
import argparse, time, sys, json, logging
from pathlib import Path
from typing import List

from tqdm import tqdm
import numpy as np
import pandas as pd

from html_extractor import extract_from_path
from html_cleaner import normalize_text, load_extra_keywords, feature_extract, classify_transcript_like

logger = logging.getLogger("html_pipeline")
if not logger.handlers:
    import os
    _fh = logging.FileHandler(os.environ.get("HTML_PIPELINE_LOGFILE", "html_pipeline.log"), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_fh)
logger.setLevel(logging.INFO)

from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

def resolve_files(in_dir: Path, glob: str) -> List[Path]:
    return sorted(in_dir.rglob(glob))

def _fit_unsupervised_model(feat_rows: List[dict]):
    """Fit a simple 2-component GMM on features to get a rough transcript-vs-other split.
    """
    if not feat_rows:
        return None, None
    X = []
    for f in feat_rows:
        X.append([
            f["dialogue_lines"], f["dice_hits"], f["session_hits"], f["pos_kw_hits"],
            f["statblock_hits"], f["table_hits"], f["neg_kw_hits"], int(f["title_object_cue"]),
            f.get("ner_count", 0), f["n_words"]
        ])
    X = np.array(X, dtype=float)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    gmm = GaussianMixture(n_components=2, covariance_type="full", random_state=0)
    gmm.fit(Xs)
    return scaler, gmm

def main(argv=None):
    p = argparse.ArgumentParser(description="HTML/TXT/JSON -> cleaned JSONL pipeline (Bayesian-enhanced)")
    p.add_argument("--in-dir", required=True, help="Input directory of files")
    p.add_argument("--glob", default="**/*.html", help="Glob for files (e.g., **/*.html, **/*.txt, **/*.json, **/*.jsonl)")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--save-text", action="store_true", help="Also save raw extracted text as .txt")
    p.add_argument("--save-clean", action="store_true", help="Also save cleaned text as .clean.txt")
    p.add_argument("--include", action="append", default=[], help="Substring filter; may repeat")
    p.add_argument("--fit-gmm", action="store_true", help="Fit a 2-component GMM on-the-fly to improve scoring")
    args = p.parse_args(argv)

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = out_dir / "_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Resolve keyword overrides relative to this tool, not the caller's cwd.
    pos, neg = load_extra_keywords(Path(__file__).resolve().parent)

    files = resolve_files(in_dir, args.glob)
    if args.include:
        files = [f for f in files if any(sub.lower() in str(f).lower() for sub in args.include)]

    out_all = (artifact_dir / "reports.jsonl").open("w", encoding="utf-8")
    out_clean = (artifact_dir / "reports_clean.jsonl").open("w", encoding="utf-8")
    out_reject = (artifact_dir / "reports_rejects.jsonl").open("w", encoding="utf-8")

    kept = 0
    rejected = 0
    ts_now = int(time.time())

    # First pass (optional): gather features to fit unsupervised model
    scaler = gmm = None
    if args.fit_gmm:
        feat_rows = []
        for f in tqdm(files, desc="Pre-scan for features"):
            try:
                title, text, _domain = extract_from_path(str(f))
                norm = normalize_text(text)
                feats = feature_extract(norm, title, pos, neg)
                feat_rows.append(feats)
            except Exception:
                continue
        scaler, gmm = _fit_unsupervised_model(feat_rows)
        if scaler is not None:
            logger.info("GMM fitted on %d samples.", len(feat_rows))

    for f in tqdm(files, desc="Processing files"):
        try:
            title, text, domain = extract_from_path(str(f))
            norm = normalize_text(text)

            feats = feature_extract(norm, title, pos, neg)
            ok, conf, tag_reason, dbg = classify_transcript_like(feats, scaler, gmm)

            rec = {
                "url": str(f),
                "title": title,
                "text": norm,
                "ts": ts_now,
                "source_domain": domain,
                "is_target": ok,
                "confidence": round(conf, 3),
                "confidence_str": f"{conf:.3f}",
                "features": feats,
                "bayes": {"bf10": dbg.get("bf10"), "conf_heur": dbg.get("conf_heur"), "conf_bayes": dbg.get("conf_bayes"), "conf_gmm": dbg.get("conf_gmm"), "gmm_log": dbg.get("gmm_log")},
            }
            if not ok:
                rec["reject_reason"] = tag_reason

            # write streams
            line = json.dumps(rec, ensure_ascii=False)
            out_all.write(line + "\n")
            if ok:
                out_clean.write(line + "\n")
                kept += 1
            else:
                out_reject.write(line + "\n")
                rejected += 1

            # optional sidecar saves
            if args.save_text:
                (out_dir / (f.stem + ".txt")).write_text(text, encoding="utf-8")
            if args.save_clean:
                (out_dir / (f.stem + ".clean.txt")).write_text(norm, encoding="utf-8")

        except Exception as e:
            rec = {"url": str(f), "error": repr(e), "ts": ts_now, "source_domain": "localfile",
                   "is_target": False, "confidence": 0.0, "reject_reason": "exception"}
            out_all.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_reject.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rejected += 1

    out_all.close(); out_clean.close(); out_reject.close()
    print(f"Done. Files: {len(files)} | kept: {kept} | rejected: {rejected} | out: {out_dir}")
    # Build overall summary CSV from reports_clean.jsonl
    try:
        clean_path = artifact_dir / 'reports_clean.jsonl'
        if clean_path.exists():
            rows = [json.loads(l) for l in clean_path.read_text(encoding='utf-8').splitlines() if l.strip()]
            pd.DataFrame(rows).to_csv(artifact_dir / 'reports_clean.csv', index=False)
    except Exception as _e:
        logger.warning('Could not write reports_clean.csv: %s', _e)

if __name__ == "__main__":
    if sys.platform.startswith("win"):
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
