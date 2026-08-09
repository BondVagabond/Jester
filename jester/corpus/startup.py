# ruff: noqa: I001
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from jester.corpus.normalization import (
    CorpusNormalizationError,
    CorpusProfile,
    NormalizedCorpusChunk,
    normalize_corpus_payload,
)
from jester.ingestion.filtering import IngestionFilter, IngestionPolicy, SourceMetadata
from jester.retrieval import CorpusDefinition, CorpusRegistry, CorpusRegistryError

if TYPE_CHECKING:
    from jester.config.settings import CorpusSettings, CorpusSourceSettings

logger = logging.getLogger(__name__)


class CorpusStartupError(RuntimeError):
    """Raised when startup corpora cannot be loaded safely."""


def build_corpus_registry(
    settings: CorpusSettings,
    *,
    ingestion_policy: IngestionPolicy,
) -> CorpusRegistry:
    registry = CorpusRegistry()
    for source in settings.sources:
        chunks = load_registered_corpus(source, policy=ingestion_policy)
        documents = [chunk.to_document() for chunk in chunks]
        if not documents:
            raise CorpusStartupError(
                f'Corpus {source.corpus_id!r} loaded zero usable documents from {source.path}. '
                'Startup corpora must not be empty.'
            )
        try:
            registry.register(
                CorpusDefinition(
                    corpus_id=source.corpus_id,
                    version=source.version,
                    source_type=source.source_type,
                    index_metadata={
                        'profile': source.profile,
                        'path': str(source.path),
                        'document_count': len(documents),
                    },
                    allowed=source.allowed,
                ),
                documents,
            )
        except CorpusRegistryError as exc:
            raise CorpusStartupError(str(exc)) from exc

    if settings.require_non_empty and not registry.list_allowed():
        raise CorpusStartupError('No allowed corpora were registered at startup.')
    return registry


def load_registered_corpus(
    source: CorpusSourceSettings,
    *,
    policy: IngestionPolicy,
) -> list[NormalizedCorpusChunk]:
    ingestion_filter = IngestionFilter(policy)
    chunks: list[NormalizedCorpusChunk] = []

    with source.path.open('r', encoding='utf-8-sig') as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorpusStartupError(
                    f'Invalid JSON in corpus {source.corpus_id!r} at {source.path}:{line_number}: {exc.msg}'
                ) from exc

            try:
                chunk = normalize_corpus_payload(
                    payload,
                    corpus_name=source.corpus_id,
                    profile=CorpusProfile(source.profile),
                    default_source_prefix=source.corpus_id,
                )
            except CorpusNormalizationError as exc:
                raise CorpusStartupError(
                    f'Could not normalize corpus row for {source.corpus_id!r} at '
                    f'{source.path}:{line_number}: {exc}'
                ) from exc

            metadata = SourceMetadata(
                title=chunk.title,
                source_id=chunk.doc_id,
                corpus=chunk.corpus_name,
                tags=chunk.tags,
            )
            if not ingestion_filter.is_valid_source(Path(chunk.source), metadata=metadata):
                logger.warning(
                    'startup_corpus_row_rejected',
                    extra={
                        'corpus_id': source.corpus_id,
                        'path': str(source.path),
                        'line_number': line_number,
                        'doc_id': chunk.doc_id,
                        'source': chunk.source,
                    },
                )
                continue

            chunks.append(chunk)

    return chunks
