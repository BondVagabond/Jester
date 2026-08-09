from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any

from pipeline.rules.dnd_rules_cleaner import clean_html_text
from pipeline.rules.dnd_rules_parser import chunk_segments, parse_into_segments
from pipeline.rules.dnd_rules_utils import bayes_quality_posterior, score_rulesyness
from training.validation import validate_records

from .models import PIPELINE_VERSION, ApprovedSource, JobRun
from .url_tools import text_content_hash, url_hash

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HTML_RE = re.compile(r"<[a-zA-Z/][^>]*>")
JSON_WRAPPER_LINE_RE = re.compile(r'^\s*[\[\]{}",:]+\s*$')
BOILERPLATE_PHRASES = [
    "not for resale",
    "permission granted to print",
    "copyright",
    "credits",
]


def _base_record(source: ApprovedSource, run: JobRun, stage: str, source_ref: str, content_hash: str) -> dict[str, Any]:
    manifest = source.manifest
    return {
        "stage": stage,
        "source_id": manifest["source_id"],
        "source_type": manifest["source_type"],
        "source": source_ref,
        "license": manifest["license"],
        "license_url": str(manifest.get("license_url") or ""),
        "rights_basis": manifest["rights_basis"],
        "allowed_for_training": manifest["allowed_for_training"],
        "allowed_for_rag": manifest["allowed_for_rag"],
        "eligibility_class": manifest["eligibility_class"],
        "attribution_required": bool(manifest.get("attribution_required", False)),
        "attribution_text": str(manifest.get("attribution_text") or ""),
        "share_alike_required": bool(manifest.get("share_alike_required", False)),
        "removal_required": manifest["removal_required"],
        "collection_date": run.started_at,
        "owner": manifest["owner"],
        "content_hash": content_hash,
        "version": manifest["version"],
        "pipeline_version": PIPELINE_VERSION,
        "provenance_status": manifest["provenance_status"],
        "run_id": run.run_id,
        "job_id": run.job_id,
    }


def _reference_hash(source_ref: str) -> str:
    return hashlib.sha1(source_ref.encode("utf-8", "ignore")).hexdigest()[:16]


def _binary_content_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _normalized_heading(raw_heading: str | None, *, title: str) -> str:
    heading = str(raw_heading or "").strip()
    if heading:
        return heading
    fallback = str(title or "").strip()
    return fallback or "Document"


def _clean_text_with_metrics(extracted_text: str) -> tuple[str, dict[str, Any]]:
    first_pass = clean_html_text(extracted_text)
    lowered_before = extracted_text.lower()
    url_count_before = len(URL_RE.findall(extracted_text))
    html_count_before = len(HTML_RE.findall(extracted_text))
    boilerplate_before = sum(1 for phrase in BOILERPLATE_PHRASES if phrase in lowered_before)

    lines = []
    removed_boilerplate = 0
    for line in first_pass.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if JSON_WRAPPER_LINE_RE.match(stripped):
            continue
        if any(phrase in lowered for phrase in BOILERPLATE_PHRASES):
            removed_boilerplate += 1
            continue
        stripped = URL_RE.sub("", stripped)
        lines.append(stripped)

    cleaned = clean_html_text("\n".join(lines))
    second_pass = clean_html_text(cleaned)
    metrics = {
        "removed_urls": max(0, url_count_before - len(URL_RE.findall(cleaned))),
        "removed_html_tags": max(0, html_count_before - len(HTML_RE.findall(cleaned))),
        "removed_boilerplate": max(removed_boilerplate, boilerplate_before - sum(1 for phrase in BOILERPLATE_PHRASES if phrase in cleaned.lower())),
        "token_delta": len(cleaned.split()) - len(extracted_text.split()),
        "repeated_pass_delta": len(second_pass) - len(cleaned),
        "no_op_transform": cleaned == extracted_text,
    }
    return cleaned, metrics


def _build_section_and_chunk_records(
    *,
    source: ApprovedSource,
    run: JobRun,
    source_ref: str,
    doc_key: str,
    doc_id: str,
    title: str,
    sections: Sequence[dict[str, Any]],
    max_chunk_chars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_sections: list[dict[str, Any]] = []
    for section in sections:
        text = str(section.get("text") or "").strip()
        if not text:
            continue
        page_from = int(section.get("page_from", 1) or 1)
        page_to = int(section.get("page_to", page_from) or page_from)
        normalized_sections.append(
            {
                "heading": _normalized_heading(section.get("heading"), title=title),
                "text": text,
                "page_from": page_from,
                "page_to": page_to,
                "section_exempt": bool(section.get("section_exempt", False)),
                "chunk_exempt": bool(section.get("chunk_exempt", False)),
            }
        )

    section_count = len(normalized_sections)
    section_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    chunk_index = 1

    for section_index, section in enumerate(normalized_sections, 1):
        heading = section["heading"]
        text = section["text"]
        page_from = section["page_from"]
        page_to = section["page_to"]
        section_hash = text_content_hash(text)
        section_id = f"section:{source.source_id}:{doc_key}:{section_index:04d}"
        section_record = {
            **_base_record(source, run, "sectionized", source_ref, section_hash),
            "record_id": section_id,
            "document_id": doc_id,
            "section_id": section_id,
            "section_index": section_index,
            "section_count": section_count,
            "heading": heading,
            "title": title,
            "text": text,
            "page_from": page_from,
            "page_to": page_to,
            "allow_empty_heading": False,
        }
        if section["section_exempt"]:
            section_record["section_exempt"] = True
        section_records.append(section_record)

        section_chunks = chunk_segments([(heading, text)], max_chars=max_chunk_chars)
        for _chunk_heading, chunk_text in section_chunks:
            chunk_text = str(chunk_text or "").strip()
            if not chunk_text:
                continue
            chunk_hash = text_content_hash(chunk_text)
            chunk_id = f"chunk:{source.source_id}:{doc_key}:{chunk_index:04d}"
            chunk_record = {
                **_base_record(source, run, "chunked", source_ref, chunk_hash),
                "record_id": chunk_id,
                "document_id": doc_id,
                "section_id": section_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "heading": heading,
                "title": title,
                "text": chunk_text,
                "char_count": len(chunk_text),
                "chunk_size_ceiling": max_chunk_chars,
                "page_from": page_from,
                "page_to": page_to,
                "allow_empty_heading": False,
            }
            if section["chunk_exempt"]:
                chunk_record["chunk_exempt"] = True
            chunk_records.append(chunk_record)
            chunk_index += 1

    return section_records, chunk_records


def _sections_from_cleaned_text(
    *,
    cleaned_text: str,
    title: str,
    page_count: int,
    cleaned_pages: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    parsed_sections = [
        {
            "heading": heading,
            "text": text,
            "page_from": 1,
            "page_to": max(1, page_count),
        }
        for heading, text in parse_into_segments(cleaned_text)
        if str(text or "").strip()
    ]
    if parsed_sections and (page_count <= 1 or len(parsed_sections) > 1):
        return parsed_sections, None

    if page_count > 1 and cleaned_pages is not None:
        page_sections = []
        for index, page_text in enumerate(cleaned_pages, 1):
            page_text = str(page_text or "").strip()
            if not page_text:
                continue
            page_sections.append(
                {
                    "heading": f"Page {index}",
                    "text": page_text,
                    "page_from": index,
                    "page_to": index,
                }
            )
        if page_sections:
            return page_sections, "page_section_fallback"

    if parsed_sections:
        return parsed_sections, None
    if cleaned_text.strip():
        return [
            {
                "heading": title or "Document",
                "text": cleaned_text,
                "page_from": 1,
                "page_to": max(1, page_count),
            }
        ], None
    return [], None


def process_html_document(
    *,
    source: ApprovedSource,
    run: JobRun,
    url: str,
    normalized_url: str,
    final_url: str,
    title: str,
    html: str,
    html_path: str,
    extracted_text: str,
    extractor_name: str,
    discovery_reason: str,
    http_status: int,
    max_chunk_chars: int = 1200,
) -> dict[str, Any]:
    doc_key = url_hash(normalized_url)
    doc_id = f"doc:{source.source_id}:{doc_key}"
    raw_hash = text_content_hash(html)
    raw_record = {
        **_base_record(source, run, "raw", url, raw_hash),
        "record_id": f"raw:{source.source_id}:{doc_key}",
        "acquisition": {
            "url": url,
            "normalized_url": normalized_url,
            "final_url": final_url,
            "http_status": http_status,
            "title": title,
            "raw_html_path": html_path,
            "discovery_reason": discovery_reason,
        },
    }

    extracted_hash = text_content_hash(extracted_text)
    extracted_record = {
        **_base_record(source, run, "extracted", url, extracted_hash),
        "record_id": f"extracted:{source.source_id}:{doc_key}",
        "document_id": doc_id,
        "title": title,
        "text": extracted_text,
        "extractor_name": extractor_name,
        "extractor_version": PIPELINE_VERSION,
        "page_from": 1,
        "page_to": 1,
        "page_errors": [],
        "fallback_flags": [],
    }

    cleaned_text, cleaning_metrics = _clean_text_with_metrics(extracted_text)
    quality_posterior, quality_flags = bayes_quality_posterior(cleaned_text)
    cleaned_hash = text_content_hash(cleaned_text)
    cleaned_record = {
        **_base_record(source, run, "cleaned", url, cleaned_hash),
        "record_id": f"cleaned:{source.source_id}:{doc_key}",
        "document_id": doc_id,
        "title": title,
        "text": cleaned_text,
        "page_from": 1,
        "page_to": 1,
        "cleaning_metrics": cleaning_metrics,
        "quality_posterior": round(float(quality_posterior), 4),
        "quality_flags": quality_flags,
        "rejection_flags": [],
        "rules_score": round(float(score_rulesyness(cleaned_text)), 4),
    }

    sections, _section_fallback = _sections_from_cleaned_text(cleaned_text=cleaned_text, title=title, page_count=1)
    section_records, chunk_records = _build_section_and_chunk_records(
        source=source,
        run=run,
        source_ref=url,
        doc_key=doc_key,
        doc_id=doc_id,
        title=title,
        sections=sections,
        max_chunk_chars=max_chunk_chars,
    )

    validation_errors: list[str] = []
    if not extracted_text.strip():
        validation_errors.append(f"{url}: extracted text is empty")
    if not cleaned_text.strip():
        validation_errors.append(f"{url}: cleaned text is empty")
    if not section_records:
        validation_errors.append(f"{url}: sectionization produced no records")
    if not chunk_records:
        validation_errors.append(f"{url}: chunking produced no records")
    validation_errors.extend(validate_records([extracted_record], "extracted", path=url))
    validation_errors.extend(validate_records([cleaned_record], "cleaned", path=url, max_chars=max_chunk_chars))
    validation_errors.extend(validate_records(section_records, "sectionized", path=url, max_chars=max_chunk_chars))
    validation_errors.extend(validate_records(chunk_records, "chunked", path=url, max_chars=max_chunk_chars))

    return {
        "raw": [raw_record],
        "extracted": [extracted_record],
        "cleaned": [cleaned_record],
        "sectionized": section_records,
        "chunked": chunk_records,
        "validation_errors": validation_errors,
    }


def process_text_document(
    *,
    source: ApprovedSource,
    run: JobRun,
    source_ref: str,
    text: str,
    title: str | None = None,
    original_filename: str | None = None,
    acquisition_method: str,
    content_type: str = "text/plain",
    max_chunk_chars: int = 1200,
    document_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from pathlib import Path

    source_label = str(source_ref)
    doc_key = _reference_hash(source_label)
    doc_id = f"doc:{source.source_id}:{doc_key}"
    resolved_title = str(title or Path(source_ref).stem or "Document")

    raw_hash = text_content_hash(text)
    raw_record = {
        **_base_record(source, run, "raw", source_label, raw_hash),
        "record_id": f"raw:{source.source_id}:{doc_key}",
        "acquisition": {
            "artifact_kind": source.manifest["source_type"],
            "acquisition_method": acquisition_method,
            "source_ref": source_label,
            "content_type": content_type,
            "byte_size": len(text.encode("utf-8", "ignore")),
            "original_filename": original_filename or Path(source_ref).name,
        },
    }

    extracted_hash = text_content_hash(text)
    extracted_record = {
        **_base_record(source, run, "extracted", source_label, extracted_hash),
        "record_id": f"extracted:{source.source_id}:{doc_key}",
        "document_id": doc_id,
        "title": resolved_title,
        "text": text,
        "extractor_name": "runtime.local_text",
        "extractor_version": PIPELINE_VERSION,
        "page_from": 1,
        "page_to": 1,
        "page_errors": [],
        "fallback_flags": [],
    }
    if document_metadata:
        extracted_record["document_metadata"] = document_metadata

    cleaned_text, cleaning_metrics = _clean_text_with_metrics(text)
    quality_posterior, quality_flags = bayes_quality_posterior(cleaned_text)
    cleaned_hash = text_content_hash(cleaned_text)
    cleaned_record = {
        **_base_record(source, run, "cleaned", source_label, cleaned_hash),
        "record_id": f"cleaned:{source.source_id}:{doc_key}",
        "document_id": doc_id,
        "title": resolved_title,
        "text": cleaned_text,
        "page_from": 1,
        "page_to": 1,
        "cleaning_metrics": cleaning_metrics,
        "quality_posterior": round(float(quality_posterior), 4),
        "quality_flags": quality_flags,
        "rejection_flags": [],
        "rules_score": round(float(score_rulesyness(cleaned_text)), 4),
    }
    if document_metadata:
        cleaned_record["document_metadata"] = document_metadata

    sections, _section_fallback = _sections_from_cleaned_text(cleaned_text=cleaned_text, title=resolved_title, page_count=1)
    section_records, chunk_records = _build_section_and_chunk_records(
        source=source,
        run=run,
        source_ref=source_label,
        doc_key=doc_key,
        doc_id=doc_id,
        title=resolved_title,
        sections=sections,
        max_chunk_chars=max_chunk_chars,
    )

    validation_errors: list[str] = []
    if not text.strip():
        validation_errors.append(f"{source_label}: extracted text is empty")
    if not cleaned_text.strip():
        validation_errors.append(f"{source_label}: cleaned text is empty")
    if not section_records:
        validation_errors.append(f"{source_label}: sectionization produced no records")
    if not chunk_records:
        validation_errors.append(f"{source_label}: chunking produced no records")
    validation_errors.extend(validate_records([extracted_record], "extracted", path=source_label))
    validation_errors.extend(validate_records([cleaned_record], "cleaned", path=source_label, max_chars=max_chunk_chars))
    validation_errors.extend(validate_records(section_records, "sectionized", path=source_label, max_chars=max_chunk_chars))
    validation_errors.extend(validate_records(chunk_records, "chunked", path=source_label, max_chars=max_chunk_chars))

    return {
        "raw": [raw_record],
        "extracted": [extracted_record],
        "cleaned": [cleaned_record],
        "sectionized": section_records,
        "chunked": chunk_records,
        "validation_errors": validation_errors,
    }


def process_pdf_document(
    *,
    source: ApprovedSource,
    run: JobRun,
    source_ref: str,
    pdf_bytes: bytes,
    raw_pdf_path: str,
    title: str | None = None,
    original_filename: str | None = None,
    http_status: int | None = None,
    content_type: str | None = None,
    acquisition_method: str,
    max_chunk_chars: int = 1200,
    do_ocr: bool = False,
    ocr_dpi: int = 300,
    max_pdf_pages: int | None = None,
) -> dict[str, Any]:
    from pathlib import Path

    from pipeline.pdf import extract_pdf_text

    source_label = str(source_ref or raw_pdf_path)
    doc_key = _reference_hash(source_label)
    doc_id = f"doc:{source.source_id}:{doc_key}"

    raw_hash = _binary_content_hash(pdf_bytes)
    raw_record = {
        **_base_record(source, run, "raw", source_label, raw_hash),
        "record_id": f"raw:{source.source_id}:{doc_key}",
        "acquisition": {
            "artifact_kind": "pdf",
            "acquisition_method": acquisition_method,
            "source_ref": source_label,
            "http_status": http_status,
            "content_type": content_type or "application/pdf",
            "byte_size": len(pdf_bytes),
            "raw_pdf_path": raw_pdf_path,
            "original_filename": original_filename or Path(raw_pdf_path).name,
        },
    }

    extraction_errors: list[Any] = []
    pdf_path = Path(raw_pdf_path)
    cleanup_temp = False
    if not pdf_path.exists():
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        cleanup_temp = True
    try:
        extracted_text, per_page_texts, metadata = extract_pdf_text(
            pdf_path=pdf_path,
            do_ocr=do_ocr,
            dpi=ocr_dpi,
            max_pages=max_pdf_pages,
            errors=extraction_errors,
        )
    finally:
        if cleanup_temp:
            try:
                pdf_path.unlink(missing_ok=True)
            except Exception:
                pass
    metadata_page_count = int(metadata.get("pages") or 0)
    if max_pdf_pages is not None and metadata_page_count:
        metadata_page_count = min(metadata_page_count, int(max_pdf_pages))
    page_count = max(len(per_page_texts), metadata_page_count, 1)
    resolved_title = str(title or metadata.get("title") or Path(raw_pdf_path).stem)
    page_errors = [
        {
            "pdf": str(getattr(err, "pdf", "") or Path(raw_pdf_path).name),
            "stage": str(getattr(err, "stage", "unknown")),
            "detail": str(getattr(err, "detail", "")),
        }
        for err in extraction_errors
    ]
    fallback_flags: list[str] = []
    if do_ocr:
        fallback_flags.append("ocr_enabled")
    if page_errors:
        fallback_flags.append("page_errors_present")

    extracted_hash = text_content_hash(extracted_text)
    extracted_record = {
        **_base_record(source, run, "extracted", source_label, extracted_hash),
        "record_id": f"extracted:{source.source_id}:{doc_key}",
        "document_id": doc_id,
        "title": resolved_title,
        "text": extracted_text,
        "extractor_name": "BatchPDFCleaner.extract_pdf_text",
        "extractor_version": PIPELINE_VERSION,
        "page_from": 1,
        "page_to": page_count,
        "page_errors": page_errors,
        "fallback_flags": fallback_flags,
        "document_metadata": metadata,
    }

    cleaned_text, cleaning_metrics = _clean_text_with_metrics(extracted_text)
    cleaned_pages: list[str] = []
    for page_text in per_page_texts:
        page_cleaned, _page_metrics = _clean_text_with_metrics(page_text)
        cleaned_pages.append(page_cleaned)

    quality_posterior, quality_flags = bayes_quality_posterior(cleaned_text)
    cleaned_hash = text_content_hash(cleaned_text)
    cleaned_record = {
        **_base_record(source, run, "cleaned", source_label, cleaned_hash),
        "record_id": f"cleaned:{source.source_id}:{doc_key}",
        "document_id": doc_id,
        "title": resolved_title,
        "text": cleaned_text,
        "page_from": 1,
        "page_to": page_count,
        "cleaning_metrics": cleaning_metrics,
        "quality_posterior": round(float(quality_posterior), 4),
        "quality_flags": quality_flags,
        "rejection_flags": [],
        "rules_score": round(float(score_rulesyness(cleaned_text)), 4),
        "document_metadata": metadata,
    }

    sections, section_fallback = _sections_from_cleaned_text(
        cleaned_text=cleaned_text,
        title=resolved_title,
        page_count=page_count,
        cleaned_pages=cleaned_pages,
    )
    if section_fallback:
        extracted_record["fallback_flags"] = list(dict.fromkeys([*extracted_record["fallback_flags"], section_fallback]))

    section_records, chunk_records = _build_section_and_chunk_records(
        source=source,
        run=run,
        source_ref=source_label,
        doc_key=doc_key,
        doc_id=doc_id,
        title=resolved_title,
        sections=sections,
        max_chunk_chars=max_chunk_chars,
    )

    validation_errors: list[str] = []
    if not extracted_text.strip():
        validation_errors.append(f"{source_label}: extracted text is empty")
    if not cleaned_text.strip():
        validation_errors.append(f"{source_label}: cleaned text is empty")
    if not section_records:
        validation_errors.append(f"{source_label}: sectionization produced no records")
    if not chunk_records:
        validation_errors.append(f"{source_label}: chunking produced no records")
    validation_errors.extend(validate_records([extracted_record], "extracted", path=source_label))
    validation_errors.extend(validate_records([cleaned_record], "cleaned", path=source_label, max_chars=max_chunk_chars))
    validation_errors.extend(validate_records(section_records, "sectionized", path=source_label, max_chars=max_chunk_chars))
    validation_errors.extend(validate_records(chunk_records, "chunked", path=source_label, max_chars=max_chunk_chars))

    return {
        "raw": [raw_record],
        "extracted": [extracted_record],
        "cleaned": [cleaned_record],
        "sectionized": section_records,
        "chunked": chunk_records,
        "validation_errors": validation_errors,
    }
