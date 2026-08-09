#!/usr/bin/env python3
import argparse
import concurrent.futures as futures
import fnmatch
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pipeline.pdf import ErrorRecord, ensure_ocr_ready, extract_pdf_text

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except Exception:
    _HAS_TQDM = False

# -------------------------- Tunables/Heuristics --------------------------
DEFAULT_WORKERS = min(4, os.cpu_count() or 1)

# ------------------------------- Data -------------------------------------
@dataclass
class FileResult:
    pdf: str
    pages: int = 0
    chunks: int = 0
    txt_path: Optional[str] = None
    jsonl_path: Optional[str] = None
    duration_sec: float = 0.0
    status: str = "ok"  # ok | skipped | error
    message: Optional[str] = None

# ---------------------------- Utilities -----------------------------------
def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, path)

def chunk_text(text: str, max_chars: int = 2000, overlap: int = 200) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        # try to avoid mid-sentence/mid-line cuts
        cut = text.rfind("\n", start, end)
        if cut == -1 or cut <= start + 0.5 * max_chars:
            cut = text.rfind(". ", start, end)
        if cut == -1 or cut <= start + 0.5 * max_chars:
            cut = end
        chunks.append(text[start:cut].strip())
        if cut == n:
            break
        start = max(cut - overlap, 0)
    return [c for c in chunks if c]

def filter_names(names: List[Path], include: List[str], exclude: List[str]) -> List[Path]:
    out = []
    for p in names:
        name = p.name
        if include and not any(fnmatch.fnmatch(name, pat) for pat in include):
            continue
        if exclude and any(fnmatch.fnmatch(name, pat) for pat in exclude):
            continue
        out.append(p)
    return out

def readable_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and os.access(path, os.R_OK)

def writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".__write_test__"
        with test.open("w") as f:
            f.write("ok")
        test.unlink(missing_ok=True)
        return True
    except Exception:
        return False

def write_outputs(
    text: str,
    meta: Dict[str, any],
    pdf_path: Path,
    out_dir: Path,
    chunk_chars: int,
    overlap: int,
) -> Tuple[Path, Path, int]:
    stem = pdf_path.stem
    txt_path = out_dir / f"{stem}.txt"
    jsonl_path = out_dir / f"{stem}.jsonl"

    chunks = chunk_text(text, max_chars=chunk_chars, overlap=overlap)

    # Write atomically
    atomic_write_text(txt_path, text)

    with (jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")).open("w", encoding="utf-8") as f:
        for i, ch in enumerate(chunks):
            rec = {
                "id": f"{stem}::chunk_{i:04d}",
                "source_pdf": pdf_path.name,
                "chunk_index": i,
                "text": ch,
                "metadata": {**{k: v for k, v in meta.items() if v}, "total_chunks": len(chunks)},
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(jsonl_path.with_suffix(jsonl_path.suffix + ".tmp"), jsonl_path)

    return txt_path, jsonl_path, len(chunks)

# -------------------------- Orchestration ---------------------------------
def process_one(
    pdf_path: Path,
    out_dir: Path,
    ocr: bool,
    dpi: int,
    chunk_chars: int,
    overlap: int,
    max_pages: Optional[int],
    skip_existing: bool,
    dry_run: bool,
    error_sink: List[ErrorRecord],
) -> FileResult:
    start = time.time()
    stem = pdf_path.stem
    txt = out_dir / f"{stem}.txt"
    jsonl = out_dir / f"{stem}.jsonl"

    if skip_existing and txt.exists() and jsonl.exists():
        return FileResult(pdf=pdf_path.name, status="skipped", message="outputs already exist")

    if dry_run:
        return FileResult(pdf=pdf_path.name, status="skipped", message="dry-run (no writes)")

    try:
        text, per_page, meta = extract_pdf_text(
            pdf_path=pdf_path,
            do_ocr=ocr,
            dpi=dpi,
            max_pages=max_pages,
            errors=error_sink
        )

        if not text:
            # still write tiny placeholders? prefer to report as error
            return FileResult(
                pdf=pdf_path.name,
                status="error",
                message="no extractable text (try --ocr or check encryption)"
            )

        txt_path, jsonl_path, n_chunks = write_outputs(
            text=text,
            meta=meta,
            pdf_path=pdf_path,
            out_dir=out_dir,
            chunk_chars=chunk_chars,
            overlap=overlap,
        )
        dur = time.time() - start
        return FileResult(
            pdf=pdf_path.name,
            pages=len(per_page),
            chunks=n_chunks,
            txt_path=str(txt_path),
            jsonl_path=str(jsonl_path),
            duration_sec=dur,
            status="ok",
        )
    except Exception as e:
        error_sink.append(ErrorRecord(pdf=pdf_path.name, stage="write_or_process", detail=str(e)))
        return FileResult(pdf=pdf_path.name, status="error", message=str(e))

# ------------------------------- CLI --------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PDF → clean text & JSONL chunks for AI training (robust).")
    p.add_argument("-i", "--input", type=str, default="pdfs", help="Input folder (PDFs).")
    p.add_argument("-o", "--output", type=str, default="processed", help="Output folder.")
    p.add_argument("--ocr", action="store_true", help="Enable OCR for image-only pages.")
    p.add_argument("--dpi", type=int, default=300, help="DPI for OCR rasterization.")
    p.add_argument("--chunk-chars", type=int, default=2000, help="Max chars per chunk.")
    p.add_argument("--overlap", type=int, default=200, help="Chars overlap between chunks.")
    p.add_argument("--include", action="append", default=[], help="Glob to include (e.g., '*.pdf'); can repeat.")
    p.add_argument("--exclude", action="append", default=[], help="Glob to exclude; can repeat.")
    p.add_argument("--skip-existing", action="store_true", help="Skip files whose .txt and .jsonl already exist.")
    p.add_argument("--dry-run", action="store_true", help="List what would be processed; do not write.")
    p.add_argument("--max-files", type=int, default=None, help="Limit how many PDFs to process.")
    p.add_argument("--max-pages", type=int, default=None, help="Limit pages per PDF (for testing).")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Number of worker threads (>=1).")
    p.add_argument("--log-file", type=str, default=None, help="Optional log file path.")
    p.add_argument("--error-report", type=str, default=None, help="Write errors.jsonl to this path.")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p.parse_args()

# -------------------------- Main & Lifecycle ------------------------------
_STOP = False

def _sigint_handler(signum, frame):
    global _STOP
    _STOP = True
    logging.warning("Received interrupt. Finishing in-flight tasks then stopping…")

def main():
    args = parse_args()

    # Logging config (console + optional file)
    handlers = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        try:
            Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
        except Exception as e:
            print(f"WARNING: could not open log file: {e}", file=sys.stderr)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        handlers=handlers
    )

    # Basic environment diagnostics
    logging.info(f"Python: {sys.executable}")
    try:
        logging.info(f"Script: {Path(__file__).resolve()}")
    except Exception:
        pass

    in_dir = Path(args.input)
    out_dir = Path(args.output)

    if not readable_dir(in_dir):
        logging.error(f"Input directory not readable or does not exist: {in_dir}")
        sys.exit(2)
    if not writable_dir(out_dir):
        logging.error(f"Output directory not writable: {out_dir}")
        sys.exit(3)

    # Recursively find PDFs under input directory
    all_pdfs = sorted([p for p in in_dir.rglob("*.pdf") if p.is_file()])
    all_pdfs = filter_names(all_pdfs, args.include, args.exclude)

    if args.max_files:
        all_pdfs = all_pdfs[: max(0, args.max_files)]

    logging.info(f"Input:  {in_dir.resolve()}")
    logging.info(f"Output: {out_dir.resolve()}")
    logging.info(f"Found {len(all_pdfs)} PDF(s) to process")

    if not all_pdfs:
        logging.warning(f"No PDFs found in {in_dir} (after filters).")
        sys.exit(0)

    if args.ocr:
        msg = ensure_ocr_ready()
        if msg:
            logging.error(msg)
            sys.exit(4)

    # Trap Ctrl+C
    signal.signal(signal.SIGINT, _sigint_handler)

    error_sink: List[ErrorRecord] = []
    results: List[FileResult] = []

    iterable = all_pdfs
    if _HAS_TQDM and not args.verbose:
        iterable = tqdm(iterable, desc="Processing PDFs", unit="pdf")

    # Always at least 1 worker
    workers = max(1, int(args.workers or 1))

    def _task(pdf_path: Path) -> FileResult:
        if _STOP:
            return FileResult(pdf=pdf_path.name, status="skipped", message="stopped")
        logging.info(f"Processing: {pdf_path}")
        return process_one(
            pdf_path=pdf_path,
            out_dir=out_dir,
            ocr=args.ocr,
            dpi=args.dpi,
            chunk_chars=args.chunk_chars,
            overlap=args.overlap,
            max_pages=args.max_pages,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            error_sink=error_sink,
        )

    if workers == 1:
        for p in iterable:
            if _STOP:
                break
            res = _task(p)
            results.append(res)
            if res.status == "ok":
                logging.info(f"Saved: {res.txt_path} and {res.jsonl_path} ({res.chunks} chunks)")
            elif res.status == "error":
                logging.error(f"Error: {res.pdf} — {res.message}")
    else:
        with futures.ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {ex.submit(_task, p): p for p in iterable}
            for fut in futures.as_completed(future_map):
                res = fut.result()
                results.append(res)
                if res.status == "ok":
                    logging.info(f"Saved: {res.txt_path} and {res.jsonl_path} ({res.chunks} chunks)")
                elif res.status == "error":
                    logging.error(f"Error: {res.pdf} — {res.message}")
                if _STOP:
                    break

    # Summary
    oks = [r for r in results if r.status == "ok"]
    errs = [r for r in results if r.status == "error"]
    skips = [r for r in results if r.status == "skipped"]

    total_chunks = sum(r.chunks for r in oks)
    logging.info("-" * 60)
    logging.info(f"Done. OK: {len(oks)} | Errors: {len(errs)} | Skipped: {len(skips)} | Total chunks: {total_chunks}")

    # Error report (JSONL)
    if args.error_report:
        try:
            Path(args.error_report).parent.mkdir(parents=True, exist_ok=True)
            with open(args.error_report, "w", encoding="utf-8") as f:
                for e in error_sink:
                    f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
            logging.info(f"Wrote error report: {args.error_report} ({len(error_sink)} issues)")
        except Exception as e:
            logging.error(f"Could not write error report: {e}")

if __name__ == "__main__":
    main()
