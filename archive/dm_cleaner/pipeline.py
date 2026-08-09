
from __future__ import annotations
import argparse, logging, sys, os, json
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("pipeline")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

def _collect_inputs(root: Path, pattern: str) -> List[Path]:
    """Collect files using Path.rglob. pattern may be a single glob or comma-separated list."""
    paths: List[Path] = []
    globs = [g.strip() for g in pattern.split(",") if g.strip()] or ["**/*"]
    for g in globs:
        g_norm = g.replace("\\\\", "/").replace("\\", "/")
        paths.extend(root.rglob(g_norm))
    uniq, seen = [], set()
    for p in paths:
        if p.is_file():
            s = str(p.resolve())
            if s not in seen:
                seen.add(s); uniq.append(p)
    return sorted(uniq)

def _write_jsonl(path: Path, records: List[Dict[str, Any]], pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, indent=(2 if pretty else None)) + "\n")

def _write_json(path: Path, records: List[Dict[str, Any]], pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=(2 if pretty else None))

def main(argv=None):
    # Late import to avoid import-time failures in environments missing optional resources.
    from cleaner import process_file, CleanerError  # type: ignore

    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, help="Root folder to search")
    ap.add_argument("--input-glob", default="**/*", help="Glob or comma-separated globs (e.g. **/*.jsonl,**/*.json)")
    ap.add_argument("--output-dir", required=True, help="Output directory")
    ap.add_argument("--min-words", type=int, default=None, help="Min words per chunk (overrides config)")
    ap.add_argument("--max-words", type=int, default=None, help="Max words per chunk (overrides config)")
    ap.add_argument("--format", choices=["auto","json","jsonl"], default="auto", help="Output format (default auto=jsonl)")
    ap.add_argument("--pretty-json", action="store_true", help="Pretty print JSON/JSONL")
    args = ap.parse_args(argv)

    root = Path(args.input_dir)
    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)

    files = _collect_inputs(root, args.input_glob)
    if not files:
        logger.warning("No inputs found. Searched: %s with glob '%s'.", root, args.input_glob)
        print(f"No inputs found. Searched: {root} with glob '{args.input_glob}'.")
        sys.exit(0)

    # Environment-driven extras (from GUI)
    report_dir_env = os.environ.get("DM_REPORT_DIR", "").strip()
    debug_dir_env  = os.environ.get("DM_DEBUG_DIR", "").strip()

    fmt = args.format
    if fmt == "auto":
        fmt = "jsonl"

    artifact_dir = out_dir / "_artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = artifact_dir / "manifest.jsonl"
    manifest_csv  = artifact_dir / "manifest.csv"

    total_files = total_chunks = errors = 0
    rows = []

    for f in files:
        try:
            total_files += 1
            report_path = None
            if report_dir_env:
                rp = Path(report_dir_env) / (f.stem + ".report.json")
                report_path = str(rp)
            debug_path = None
            if debug_dir_env:
                dp = Path(debug_dir_env) / f.stem
                debug_path = str(dp)

            res = process_file(
                str(f),
                min_words=args.min_words,
                max_words=args.max_words,
                return_rich=True,
                debug_dir=debug_path,
                report_path=report_path,
            )

            chunks = list(res.get("chunks", []))
            stats  = dict(res.get("stats", {}))
            doc_id = stats.get("doc_id") or f.stem

            # Choose output path
            safe = Path(doc_id).name
            if fmt == "jsonl":
                out_path = out_dir / f"{safe}.jsonl"
                _write_jsonl(out_path, chunks, pretty=args.pretty_json)
            else:
                out_path = out_dir / f"{safe}.json"
                _write_json(out_path, chunks, pretty=args.pretty_json)

            # Manifest
            with manifest_path.open("a", encoding="utf-8") as mf:
                for ch in chunks:
                    line = json.dumps({
                        "doc_id": doc_id,
                        "chunk_id": ch.get("chunk_id"),
                        "source_file": str(f),
                        "out_file": str(out_path),
                    }, ensure_ascii=False)
                    mf.write(line + "\n")
                    rows.append({
                        "doc_id": doc_id,
                        "chunk_id": ch.get("chunk_id"),
                        "source_file": str(f),
                        "out_file": str(out_path),
                    })
                    total_chunks += 1

            logger.info("Processed %s → %s (%d chunks)", f, out_path, len(chunks))

        except CleanerError as ce:
            errors += 1
            logger.error("Failed on %s at stage %s: %s", f, getattr(ce, "stage", "?"), ce)
            with manifest_path.open("a", encoding="utf-8") as mf:
                mf.write(json.dumps({"source_file": str(f), "error": str(ce), "stage": getattr(ce, "stage", None)}) + "\n")
        except Exception as e:
            errors += 1
            logger.exception("Failed on %s: %s", f, e)
            with manifest_path.open("a", encoding="utf-8") as mf:
                mf.write(json.dumps({"source_file": str(f), "error": str(e)}) + "\n")

    # CSV mirror of manifest
    if rows:
        try:
            import pandas as pd  # type: ignore
            pd.DataFrame(rows).to_csv(manifest_csv, index=False)
        except Exception:
            with manifest_csv.open("w", encoding="utf-8") as fcsv:
                fcsv.write("doc_id,chunk_id,source_file,out_file\n")
                for r in rows:
                    fcsv.write(",".join([
                        (r.get("doc_id") or ""),
                        (r.get("chunk_id") or ""),
                        (r.get("source_file") or "").replace(",", " "),
                        (r.get("out_file") or "").replace(",", " "),
                    ]) + "\n")

    print(f"Done. {total_files} file(s) processed, {total_chunks} chunk(s) written. Errors: {errors}.")
    sys.exit(0 if errors == 0 else 2)

if __name__ == "__main__":
    main()
