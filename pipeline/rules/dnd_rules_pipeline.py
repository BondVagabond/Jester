
import csv
import json
import logging
import math
import os
import sys
from collections import Counter
from pathlib import Path

from dnd_rules_cleaner import clean_html_text, clean_pdf_text
from dnd_rules_extractor import extract_html_text, extract_pdf_text
from dnd_rules_parser import chunk_segments, parse_into_segments
from dnd_rules_utils import bigrams, make_record, tokenize

LOG = logging.getLogger("dnd_rules")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
LOG.addHandler(handler)
LOG.setLevel(logging.INFO)

def _process_pdf(path: str, page_from: int = 1, page_to: int | None = None,
                 max_chars: int = 900, min_clean_chars: int = 120, min_quality: float = 0.55):
    try:
        raw, pfrom, pto = extract_pdf_text(path, page_from=page_from, page_to=page_to)
        LOG.info(f"PDF read: {path} pages={pfrom}-{pto} raw_chars={len(raw)}")
        if not raw.strip():
            LOG.warning(f"EMPTY_RAW_PDF: {path}")
            return []
        cleaned = clean_pdf_text(raw)
        LOG.info(f"PDF cleaned: {path} clean_chars={len(cleaned)}")
        if len(cleaned) < min_clean_chars:
            LOG.warning(f"SHORT_CLEAN_PDF({len(cleaned)} chars): {path}")
        segs = parse_into_segments(cleaned)
        LOG.info(f"PDF parsed: {path} segments={len(segs)}")
        chunks = chunk_segments(segs, max_chars=max_chars)
        LOG.info(f"PDF chunked: {path} chunks={len(chunks)}")
        recs = [make_record(path, pfrom, pto, h, c, "rules") for (h, c) in chunks]
        return recs
    except Exception as e:
        LOG.error(f"PDF_ERROR: {path} :: {e}", exc_info=True)
        return []

def _process_html(path: str, max_chars: int = 900, min_clean_chars: int = 120, min_quality: float = 0.55):
    try:
        raw = extract_html_text(path)
        LOG.info(f"HTML read: {path} raw_chars={len(raw)}")
        if not raw.strip():
            LOG.warning(f"EMPTY_RAW_HTML: {path}")
            return []
        cleaned = clean_html_text(raw)
        LOG.info(f"HTML cleaned: {path} clean_chars={len(cleaned)}")
        if len(cleaned) < min_clean_chars:
            LOG.warning(f"SHORT_CLEAN_HTML({len(cleaned)} chars): {path}")
        segs = parse_into_segments(cleaned)
        LOG.info(f"HTML parsed: {path} segments={len(segs)}")
        chunks = chunk_segments(segs, max_chars=max_chars)
        LOG.info(f"HTML chunked: {path} chunks={len(chunks)}")
        recs = [make_record(path, 1, 1, h, c, "rules") for (h, c) in chunks]
        return recs
    except Exception as e:
        LOG.error(f"HTML_ERROR: {path} :: {e}", exc_info=True)
        return []

def _compute_noise_terms(records: list[dict], threshold: float, top_k: int = 120) -> dict[str, list[dict]]:
    """Find tokens/bigrams over-represented in LOW-quality vs HIGH-quality chunks using smoothed log-odds."""
    lows = [r for r in records if r.get("quality_posterior", 0.0) < threshold]
    highs = [r for r in records if r.get("quality_posterior", 0.0) >= threshold]

    def counts(items: list[dict]) -> tuple[Counter, Counter]:
        tok_c = Counter()
        bi_c  = Counter()
        for r in items:
            toks = tokenize(r.get("text",""))
            tok_c.update(set(toks))  # document freq-ish
            bi_c.update(set(bigrams(toks)))
        return tok_c, bi_c

    low_tok, low_bi = counts(lows)
    high_tok, high_bi = counts(highs)

    def rank(counter_low: Counter, counter_high: Counter) -> list[tuple[str, float, int, int]]:
        vocab = set(counter_low) | set(counter_high)
        ranked = []
        # Laplace smoothing
        for term in vocab:
            a = counter_low.get(term, 0) + 1
            b = counter_high.get(term, 0) + 1
            # log-odds favoring LOW
            score = math.log(a / b)
            ranked.append((term, score, counter_low.get(term, 0), counter_high.get(term, 0)))
        ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)  # top: most overrepresented in LOW
        return ranked[:top_k]

    top_low_tokens = rank(low_tok, high_tok)
    top_low_bigrams = rank(low_bi, high_bi)

    return {
        "tokens": [
            {"term": t, "log_odds_low": round(s, 4), "low_df": lo, "high_df": hi}
            for t, s, lo, hi in top_low_tokens
        ],
        "bigrams": [
            {"term": t, "log_odds_low": round(s, 4), "low_df": lo, "high_df": hi}
            for t, s, lo, hi in top_low_bigrams
        ],
        "stats": {
            "n_low": len(lows),
            "n_high": len(highs),
            "threshold": threshold
        }
    }

def run_pipeline(inputs: list[str], sample_pages: int = 0,
                 out_jsonl: str = "out.jsonl", max_chars: int = 900,
                 min_quality: float = 0.55, noise_report_path: str | None = None) -> int:
    out_dir = os.path.dirname(out_jsonl) or "."
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    all_records: list[dict] = []
    LOG.info(f"Starting pipeline on {len(inputs)} files -> {out_jsonl}")
    with open(out_jsonl, "w", encoding="utf-8") as out:
        for path in inputs:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".pdf":
                page_to = None if sample_pages in (0, None) else sample_pages
                recs = _process_pdf(path, page_from=1, page_to=page_to, max_chars=max_chars, min_quality=min_quality)
            elif ext in (".html", ".htm"):
                recs = _process_html(path, max_chars=max_chars, min_quality=min_quality)
            else:
                LOG.info(f"SKIP (ext): {path}")
                continue

            # Write only kept chunks but retain all for noise-term analysis
            for r in recs:
                all_records.append(r)
                if r.get("quality_posterior", 0.0) >= min_quality:
                    out.write(json.dumps(r, ensure_ascii=False) + "\n")
                    n += 1

    LOG.info(f"Pipeline complete. Total chunks written: {n} (threshold={min_quality})")

    # Noise terms report
    if noise_report_path:
        LOG.info("Computing noise-terms report...")
        rep = _compute_noise_terms(all_records, min_quality, top_k=120)
        # JSON
        with open(noise_report_path, "w", encoding="utf-8") as jf:
            json.dump(rep, jf, ensure_ascii=False, indent=2)
        # CSVs next to JSON
        base = os.path.splitext(noise_report_path)[0]
        tok_csv = base + "_tokens.csv"
        bi_csv = base + "_bigrams.csv"
        with open(tok_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["term","log_odds_low","low_df","high_df"])
            for row in rep["tokens"]:
                w.writerow([row["term"], row["log_odds_low"], row["low_df"], row["high_df"]])
        with open(bi_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["term","log_odds_low","low_df","high_df"])
            for row in rep["bigrams"]:
                w.writerow([row["term"], row["log_odds_low"], row["low_df"], row["high_df"]])
        LOG.info(f"Noise-terms written: {noise_report_path}, {tok_csv}, {bi_csv}")

    return n

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract and clean D&D rulebook text into JSONL (rules-oriented, small chunks) with noise-terms report")
    parser.add_argument("--in-dir", required=True, help="Folder with PDFs or HTML files (recursively)")
    parser.add_argument("--out", required=True, help="Path for JSONL output file")
    parser.add_argument("--pages", type=int, default=0, help="Number of pages to extract from each PDF (0 = ALL)")
    parser.add_argument("--max-chars", type=int, default=900, help="Max characters per chunk (rules are short)")
    parser.add_argument("--min-chars", type=int, default=120, help="Warn if cleaned text is shorter than this")
    parser.add_argument("--min-quality", type=float, default=0.55, help="Minimum Bayesian posterior to keep a chunk")
    parser.add_argument("--noise-report", type=str, default=None, help="Optional path for noise terms JSON report")
    args = parser.parse_args()

    in_dir = Path(args.in_dir)
    files = [str(p) for p in in_dir.rglob("*") if p.suffix.lower() in (".pdf", ".html", ".htm")]
    print(f"Found {len(files)} files in {in_dir}")
    total = run_pipeline(
        files,
        sample_pages=args.pages,
        out_jsonl=args.out,
        max_chars=args.max_chars,
        min_quality=args.min_quality,
        noise_report_path=args.noise_report
    )
    print(f"✅ Done! Extracted {total} rule chunks -> {args.out}")
