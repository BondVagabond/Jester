"""PDF text extraction for the ingestion pipeline.

Extracted from the legacy BatchPDFCleaner CLI so that pipeline.runtime.pipeline
can depend on extraction without importing an argparse-based tool.
"""
from __future__ import annotations

import contextlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

try:
    from pdf2image import convert_from_path  # requires poppler
except ImportError:  # pragma: no cover - optional OCR path
    convert_from_path = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional OCR path
    pytesseract = None

HEADER_FOOTER_MAX_LINES = 3
HEADER_FOOTER_MIN_REPEATS = 0.6  # 60% of pages

@dataclass
class ErrorRecord:
    pdf: str
    stage: str
    detail: str

def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = "\n".join(line.rstrip() for line in s.splitlines())
    return s

def dehyphenate(text: str) -> str:
    return re.sub(r"(\w+)-\n(\w+)", r"\1\2\n", text)

def remove_page_numbers(lines: list[str]) -> list[str]:
    cleaned = []
    for ln in lines:
        if re.fullmatch(r"\s*(?:page|p\.?)?\s*\d+\s*(?:/|\sof\s)?\s*\d*\s*", ln.strip(), flags=re.I):
            continue
        cleaned.append(ln)
    return cleaned

def identify_headers_footers(pages_lines: list[list[str]]) -> dict[str, set]:
    from collections import Counter
    top_counter, bot_counter = Counter(), Counter()
    n = len(pages_lines)
    for lines in pages_lines:
        if not lines:
            continue
        tops = tuple(lines[:HEADER_FOOTER_MAX_LINES])
        bots = tuple(lines[-HEADER_FOOTER_MAX_LINES:]) if len(lines) >= HEADER_FOOTER_MAX_LINES else tuple(lines[-1:])
        top_counter.update(set(tops))
        bot_counter.update(set(bots))
    threshold = max(1, int(HEADER_FOOTER_MIN_REPEATS * n))
    return {
        "headers": {ln for ln, c in top_counter.items() if c >= threshold},
        "footers": {ln for ln, c in bot_counter.items() if c >= threshold},
    }

def ensure_ocr_ready() -> str | None:
    # Return None if ready; else an error message describing what's missing.
    missing = []
    if convert_from_path is None:
        missing.append("pdf2image (and Poppler 'pdftoppm')")
    if pytesseract is None:
        missing.append("pytesseract (and Tesseract OCR)")
    if missing:
        return ("OCR requested but missing: " + ", ".join(missing) +
                ". Install the libs and ensure 'tesseract' and 'pdftoppm' are on PATH.")
    return None

def page_to_text(page) -> str:
    # Per-page safety: never raise out
    with contextlib.suppress(Exception):
        txt = page.extract_text(x_tolerance=1, y_tolerance=1)
        return txt or ""
    return ""

def ocr_single_page(pdf_path: Path, page_index_one_based: int, dpi: int) -> str:
    # Convert and OCR a single page (1-based index for pdf2image)
    assert page_index_one_based >= 1
    images = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        first_page=page_index_one_based,
        last_page=page_index_one_based,
        fmt="png",
        single_file=True
    )
    img = images[0]
    return pytesseract.image_to_string(img)

def extract_pdf_text(
    pdf_path: Path,
    do_ocr: bool = False,
    dpi: int = 300,
    max_pages: int | None = None,
    errors: list[ErrorRecord] | None = None,
) -> tuple[str, list[str], dict[str, any]]:
    per_page_texts: list[str] = []
    cleaned_pages_lines: list[list[str]] = []
    metadata: dict[str, any] = {}
    errors = errors if errors is not None else []

    # sanity: file size and basic existence
    try:
        if pdf_path.stat().st_size == 0:
            raise RuntimeError("Zero-byte file")
    except Exception as e:
        errors.append(ErrorRecord(pdf=str(pdf_path.name), stage="stat", detail=str(e)))
        return "", [], {}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            # --- COMPAT: older pdfplumber may not have is_encrypted ---
            enc = bool(getattr(pdf, "is_encrypted", False))
            if enc:
                # We won’t try to decrypt here (pdfplumber doesn't expose decrypt consistently).
                # We continue; if the file truly requires a password, page access will fail and be logged below.
                logging.info(f"{pdf_path.name}: appears encrypted; will try page access anyway")

            # Metadata is best-effort
            md = pdf.metadata or {}
            metadata = {
                "title": md.get("Title"),
                "author": md.get("Author"),
                "creator": md.get("Creator"),
                "producer": md.get("Producer"),
                "subject": md.get("Subject"),
                "keywords": md.get("Keywords"),
                "creation_date": md.get("CreationDate"),
                "mod_date": md.get("ModDate"),
                "pages": len(pdf.pages),
            }

            page_count = len(pdf.pages)
            limit = min(page_count, max_pages) if max_pages else page_count

            raw_texts = []
            for i in range(limit):
                try:
                    page = pdf.pages[i]
                except Exception as e:
                    errors.append(ErrorRecord(pdf=pdf_path.name, stage=f"read_page_{i+1}", detail=str(e)))
                    raw_texts.append("")  # keep page index alignment
                    continue

                try:
                    raw = page_to_text(page)
                except Exception as e:
                    errors.append(ErrorRecord(pdf=pdf_path.name, stage=f"extract_page_{i+1}", detail=str(e)))
                    raw = ""

                raw_texts.append(raw)

            # OCR only pages that appear empty or near-empty
            if do_ocr:
                missing_msg = ensure_ocr_ready()
                if missing_msg:
                    raise RuntimeError(missing_msg)
                need_ocr = [idx for idx, t in enumerate(raw_texts) if len((t or "").strip()) < 20]
                for idx in need_ocr:
                    try:
                        text_ocr = ocr_single_page(pdf_path, idx + 1, dpi=dpi)
                        raw_texts[idx] = text_ocr or ""
                    except Exception as e:
                        errors.append(ErrorRecord(pdf=pdf_path.name, stage=f"ocr_page_{idx+1}", detail=str(e)))

            # Clean per-page
            for t in raw_texts:
                try:
                    t = normalize_text(t or "")
                    t = dehyphenate(t)
                    lines = [ln for ln in t.splitlines() if ln.strip() != ""]
                    lines = remove_page_numbers(lines)
                    cleaned_pages_lines.append(lines)
                except Exception as e:
                    errors.append(ErrorRecord(pdf=pdf_path.name, stage="clean_page", detail=str(e)))
                    cleaned_pages_lines.append([])

            # Identify headers/footers globally
            hf = identify_headers_footers(cleaned_pages_lines)
            headers, footers = hf["headers"], hf["footers"]

            for lines in cleaned_pages_lines:
                filtered = [ln for ln in lines if ln not in headers and ln not in footers]
                per_page_texts.append("\n".join(filtered).strip())

    except Exception as e:
        # Any failure opening the file, accessing metadata, or reading pages bubbles up here too
        errors.append(ErrorRecord(pdf=pdf_path.name, stage="open_or_metadata", detail=str(e)))
        return "", [], {}

    full_text = "\n\n".join(p for p in per_page_texts if p).strip()
    return full_text, per_page_texts, metadata
