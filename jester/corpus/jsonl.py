from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from jester.corpus.models import CorpusDocument, RawCorpusDocument
from jester.ingestion.filtering import IngestionFilter, IngestionPolicy, SourceMetadata
from jester.processing.sanitizer import SanitizationError, sanitize_content, sanitize_title

logger = logging.getLogger(__name__)


class JsonlIntegrityError(ValueError):
    """Raised when a JSONL corpus file is malformed."""


def load_corpus_jsonl(
    path: Path,
    *,
    policy: IngestionPolicy | None = None,
) -> list[CorpusDocument]:
    """Load and sanitize corpus records from JSONL."""

    ingestion_filter = IngestionFilter(policy or IngestionPolicy())
    documents: list[CorpusDocument] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JsonlIntegrityError(
                    f"Invalid JSON at {path}:{line_number}: {exc.msg}"
                ) from exc

            try:
                raw_document = RawCorpusDocument.model_validate(payload)
            except ValidationError as exc:
                raise JsonlIntegrityError(
                    f"Invalid corpus document at {path}:{line_number}: {exc}"
                ) from exc

            source_path = Path(raw_document.source)
            metadata = SourceMetadata(
                title=raw_document.title,
                source_id=raw_document.doc_id,
                corpus=raw_document.corpus,
                tags=raw_document.tags,
            )
            if not ingestion_filter.is_valid_source(source_path, metadata=metadata):
                logger.info(
                    "Skipping denied source",
                    extra={
                        "source": str(source_path),
                        "doc_id": raw_document.doc_id,
                        "line_number": line_number,
                    },
                )
                continue

            try:
                title = sanitize_title(raw_document.title or raw_document.doc_id)
            except SanitizationError:
                logger.info(
                    "Skipping unsanitizable title",
                    extra={
                        "title": raw_document.title,
                        "doc_id": raw_document.doc_id,
                        "line_number": line_number,
                    },
                )
                continue

            text = sanitize_content(raw_document.text)
            if not text:
                logger.info(
                    "Skipping empty sanitized text",
                    extra={
                        "doc_id": raw_document.doc_id,
                        "line_number": line_number,
                    },
                )
                continue

            documents.append(
                CorpusDocument(
                    doc_id=raw_document.doc_id,
                    chunk_id=raw_document.chunk_id,
                    title=title,
                    text=text,
                    source=str(source_path),
                    corpus=raw_document.corpus,
                    tags=raw_document.tags,
                )
            )

    return documents
