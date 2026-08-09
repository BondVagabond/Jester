#!/usr/bin/env python3
"""Validate canonical corpus records and enforce stage-specific QA gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

BASE_REQUIRED = {
    "record_id",
    "stage",
    "source_id",
    "source_type",
    "source",
    "license",
    "license_url",
    "rights_basis",
    "allowed_for_training",
    "allowed_for_rag",
    "eligibility_class",
    "attribution_required",
    "attribution_text",
    "share_alike_required",
    "removal_required",
    "collection_date",
    "owner",
    "content_hash",
    "version",
    "pipeline_version",
    "provenance_status",
    "run_id",
    "job_id",
}

DISCOVERY_REQUIRED = {
    "record_id",
    "stage",
    "candidate_source_id",
    "candidate_domain",
    "seed_url",
    "discovered_at",
    "discovery_methods",
    "relevance_score",
    "risk_score",
    "review_status",
    "run_id",
    "job_id",
    "content_hash",
    "pipeline_version",
}

STAGE_REQUIRED = {
    "discovery_candidate": {"candidate_source_id", "candidate_domain", "seed_url", "discovered_at", "discovery_methods", "relevance_score", "risk_score", "review_status"},
    "raw": {"acquisition"},
    "extracted": {"text", "extractor_name", "extractor_version", "page_from", "page_to", "page_errors", "fallback_flags"},
    "cleaned": {"text", "cleaning_metrics", "quality_posterior", "quality_flags", "rejection_flags"},
    "sectionized": {"text", "document_id", "section_id", "section_index", "section_count", "heading"},
    "chunked": {"text", "document_id", "section_id", "chunk_id", "chunk_index", "heading", "char_count", "chunk_size_ceiling"},
    "indexed": {"text", "document_id", "chunk_id", "dataset_id", "index_name", "embedding_model", "vector_store"},
}

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HTML_RE = re.compile(r"<[a-zA-Z/][^>]*>")
JSON_WRAPPER_RE = re.compile(r'^\s*[\[{]\s*(?:\{|\")')
KNOWN_BOILERPLATE = ["not for resale", "permission granted to print", "copyright", "credits"]


def derived_class(record: dict[str, Any]) -> str:
    if record.get("stage") == "discovery_candidate":
        return "candidate"
    if record.get("allowed_for_training") and record.get("allowed_for_rag"):
        return "training_and_retrieval"
    if (not record.get("allowed_for_training")) and record.get("allowed_for_rag"):
        return "retrieval_only"
    if (not record.get("allowed_for_training")) and (not record.get("allowed_for_rag")):
        return "neither"
    return "invalid"


def load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception as exc:
                    raise ValueError(f"{path}:{lineno}: invalid JSONL row: {exc}") from exc
        return rows
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"{path}: unsupported JSON payload type {type(data)!r}")


def validate_shape(record: dict[str, Any], stage: str, path: str, index: int) -> list[str]:
    errors: list[str] = []
    required_base = DISCOVERY_REQUIRED if stage == "discovery_candidate" else BASE_REQUIRED
    missing = sorted(k for k in required_base if k not in record)
    if missing:
        errors.append(f"{path} record[{index}]: missing base fields: {', '.join(missing)}")

    required = STAGE_REQUIRED.get(stage, set())
    missing_stage = sorted(k for k in required if k not in record)
    if missing_stage:
        errors.append(f"{path} record[{index}]: missing stage fields: {', '.join(missing_stage)}")

    if stage != "discovery_candidate":
        actual_class = derived_class(record)
        if record.get("eligibility_class") != actual_class:
            errors.append(
                f"{path} record[{index}]: eligibility_class={record.get('eligibility_class')!r} does not match derived class {actual_class!r}"
            )
        if record.get("license") in (None, "", "unknown") or record.get("rights_basis") in (None, "", "unknown"):
            errors.append(f"{path} record[{index}]: missing or unknown rights fields require quarantine")
        if record.get("attribution_required") and not str(record.get("attribution_text") or "").strip():
            errors.append(f"{path} record[{index}]: attribution_required records must include attribution_text")
    else:
        for score_key in ("relevance_score", "risk_score"):
            value = record.get(score_key)
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                errors.append(f"{path} record[{index}]: {score_key} must be between 0 and 1")

    return errors


def validate_text(record: dict[str, Any], stage: str, path: str, index: int) -> list[str]:
    errors: list[str] = []
    text = record.get("text", "")
    if stage in {"cleaned", "sectionized", "chunked", "indexed"}:
        if URL_RE.search(text):
            errors.append(f"{path} record[{index}]: leaked URL in {stage} text")
        if HTML_RE.search(text):
            errors.append(f"{path} record[{index}]: leaked HTML tag in {stage} text")
        if JSON_WRAPPER_RE.search(text) and '"text"' in text[:200]:
            errors.append(f"{path} record[{index}]: wrapper JSON leakage in {stage} text")
        lowered = text.lower()
        for phrase in KNOWN_BOILERPLATE:
            if phrase in lowered:
                errors.append(f"{path} record[{index}]: boilerplate leakage detected: {phrase!r}")
                break
    return errors


def validate_stage_business_rules(record: dict[str, Any], stage: str, path: str, index: int, max_chars: int, require_training_safe: bool) -> list[str]:
    errors: list[str] = []

    if stage == "discovery_candidate":
        if record.get("review_status") not in {"pending_review", "approved", "rejected", "quarantined"}:
            errors.append(f"{path} record[{index}]: invalid review_status for discovery candidate")
        return errors

    if require_training_safe:
        if record.get("eligibility_class") != "training_and_retrieval":
            errors.append(f"{path} record[{index}]: training export includes non-trainable content")
        if record.get("provenance_status") != "complete":
            errors.append(f"{path} record[{index}]: training export requires complete provenance")
        if record.get("removal_required"):
            errors.append(f"{path} record[{index}]: training export includes removal-blocked content")

    if stage == "cleaned":
        metrics = record.get("cleaning_metrics", {})
        if "no_op_transform" not in metrics:
            errors.append(f"{path} record[{index}]: cleaned record missing cleaning_metrics.no_op_transform")
        for key in ("removed_urls", "removed_html_tags", "removed_boilerplate", "token_delta", "repeated_pass_delta"):
            if key not in metrics:
                errors.append(f"{path} record[{index}]: cleaned record missing cleaning_metrics.{key}")

    if stage == "sectionized":
        heading = record.get("heading")
        if heading in (None, "") and not record.get("allow_empty_heading", False):
            errors.append(f"{path} record[{index}]: sectionized record has null or empty heading")
        section_count = int(record.get("section_count", 0) or 0)
        page_from = int(record.get("page_from", 1) or 1)
        page_to = int(record.get("page_to", page_from) or page_from)
        if page_to > page_from and section_count <= 1 and not record.get("section_exempt", False):
            errors.append(f"{path} record[{index}]: multi-page document collapsed to <= 1 section")

    if stage == "chunked":
        heading = record.get("heading")
        if heading in (None, "") and not record.get("allow_empty_heading", False):
            errors.append(f"{path} record[{index}]: chunked record has null or empty heading")
        char_count = int(record.get("char_count", 0) or 0)
        ceiling = int(record.get("chunk_size_ceiling", max_chars) or max_chars)
        actual = len(record.get("text", ""))
        if char_count != actual:
            errors.append(f"{path} record[{index}]: char_count={char_count} does not match actual={actual}")
        if actual > ceiling or actual > max_chars:
            errors.append(f"{path} record[{index}]: oversized chunk actual={actual} ceiling={ceiling}")

    if stage == "extracted" and record.get("page_errors") and not record.get("fallback_flags"):
        errors.append(f"{path} record[{index}]: page errors require explicit fallback or error flags")

    return errors


def validate_document_aggregates(records: list[dict[str, Any]], stage: str, path: str) -> list[str]:
    errors: list[str] = []
    if stage not in {"sectionized", "chunked"}:
        return errors

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        doc_id = str(record.get("document_id") or record.get("source_id") or "unknown")
        grouped[doc_id].append(record)

    for doc_id, group in grouped.items():
        page_from = min(int(r.get("page_from", 1) or 1) for r in group)
        page_to = max(int(r.get("page_to", page_from) or page_from) for r in group)
        if stage == "sectionized":
            section_count = max(int(r.get("section_count", 0) or 0) for r in group)
            if page_to > page_from and section_count <= 1 and not any(r.get("section_exempt", False) for r in group):
                errors.append(f"{path}: document_id={doc_id!r} collapsed to <= 1 section across a multi-page span")
        if stage == "chunked":
            if len(group) <= 1 and page_to > page_from and not any(r.get("chunk_exempt", False) for r in group):
                errors.append(f"{path}: document_id={doc_id!r} collapsed to <= 1 chunk across a multi-page span")
    return errors


def validate_record(record: dict[str, Any], stage: str, path: str = "<memory>", index: int = 1, max_chars: int = 1800, require_training_safe: bool = False) -> list[str]:
    errors: list[str] = []
    if record.get("stage") != stage:
        errors.append(f"{path} record[{index}]: stage={record.get('stage')!r} does not match expected {stage!r}")
        return errors
    errors.extend(validate_shape(record, stage, path, index))
    errors.extend(validate_text(record, stage, path, index))
    errors.extend(validate_stage_business_rules(record, stage, path, index, max_chars=max_chars, require_training_safe=require_training_safe))
    return errors


def validate_records(records: list[dict[str, Any]], stage: str, path: str = "<memory>", max_chars: int = 1800, require_training_safe: bool = False) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records, 1):
        errors.extend(validate_record(record, stage, path=path, index=index, max_chars=max_chars, require_training_safe=require_training_safe))
    errors.extend(validate_document_aggregates(records, stage, path))
    return errors


def iter_paths(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_dir():
            yield from sorted(candidate.rglob("*.json"))
            yield from sorted(candidate.rglob("*.jsonl"))
        else:
            yield candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate staged corpus records.")
    parser.add_argument("paths", nargs="+", help="JSON/JSONL file(s) or directories.")
    parser.add_argument("--stage", required=True, choices=sorted(STAGE_REQUIRED), help="Expected record stage.")
    parser.add_argument("--max-chars", type=int, default=1800, help="Hard chunk ceiling used by QA gates.")
    parser.add_argument("--require-training-safe", action="store_true", help="Fail any record not eligible for training.")
    args = parser.parse_args()

    total_errors = 0
    checked_files = 0
    for path in iter_paths(args.paths):
        try:
            records = load_records(path)
        except Exception as exc:
            print(f"ERROR {exc}")
            total_errors += 1
            continue
        checked_files += 1
        errors = validate_records(records, args.stage, path=str(path), max_chars=args.max_chars, require_training_safe=args.require_training_safe)
        for msg in errors:
            print(f"ERROR {msg}")
        if not errors:
            print(f"OK    {path}")
        total_errors += len(errors)

    print(f"SUMMARY files_checked={checked_files} errors={total_errors}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
