from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from jester.corpus.models import CorpusDocument
from jester.retrieval._common import build_term_frequencies, matches_filters, tokenize
from jester.retrieval.contracts import (
    BackendSearchResult,
    BackendStatus,
    FilterValue,
    QueryRetriever,
    RetrievalBackend,
    RetrievalHit,
    RetrievalQuery,
    RetrievalScoreBreakdown,
    RetrievalService,
    RetrievedDocument,
)


@dataclass(frozen=True, slots=True)
class _IndexedVectorDocument:
    document: CorpusDocument
    weights: dict[str, float]
    magnitude: float


class VectorIndexBackend:
    def __init__(
        self,
        *,
        backend_name: str = 'vector',
        available: bool = True,
        detail: str | None = None,
    ) -> None:
        self.backend_name = backend_name
        self._available = available
        self._detail = detail

    def status(self, *, index_version: str) -> BackendStatus:
        return BackendStatus(
            backend_name=self.backend_name,
            available=self._available,
            degraded=not self._available,
            index_version=index_version,
            detail=self._detail,
        )

    def search(
        self,
        *,
        query: RetrievalQuery,
        corpus_ids: frozenset[str],
        index_version: str,
        indexed_documents: tuple[_IndexedVectorDocument, ...],
    ) -> BackendSearchResult:
        _ = index_version
        if not self._available:
            return BackendSearchResult(
                backend_name=self.backend_name,
                available=False,
                degraded=True,
                error=self._detail or 'Vector backend is unavailable.',
            )

        if query.corpus is not None and query.corpus not in corpus_ids:
            return BackendSearchResult(
                backend_name=self.backend_name,
                hits=[],
                latency_ms=0,
                available=True,
                degraded=False,
            )

        start = time.perf_counter()
        query_weights, query_magnitude = _vectorize_text(query.text)
        if query_magnitude == 0.0:
            return BackendSearchResult(
                backend_name=self.backend_name,
                hits=[],
                latency_ms=0,
                available=True,
                degraded=False,
            )

        ranked: list[RetrievalHit] = []
        for indexed_document in indexed_documents:
            document = indexed_document.document
            if query.corpus is not None and document.corpus != query.corpus:
                continue
            if not matches_filters(document, query.filters):
                continue
            score = _cosine_similarity(
                query_weights,
                query_magnitude,
                indexed_document.weights,
                indexed_document.magnitude,
            )
            if score <= 0.0:
                continue
            ranked.append(
                RetrievalHit(
                    doc_id=document.doc_id,
                    chunk_id=document.chunk_id,
                    title=document.title,
                    text=document.text,
                    score=score,
                    source=document.source,
                    tags=document.tags,
                    corpus_id=document.corpus,
                    score_breakdown=RetrievalScoreBreakdown(
                        fused_score=score,
                        backend_scores={self.backend_name: score},
                        backend_ranks={},
                    ),
                )
            )

        ranked.sort(
            key=lambda item: (-item.score, item.doc_id, item.chunk_id, item.title, item.source)
        )
        stabilized_hits = [
            hit.model_copy(
                update={
                    'score_breakdown': hit.score_breakdown.model_copy(
                        update={'backend_ranks': {self.backend_name: rank}}
                    )
                }
            )
            for rank, hit in enumerate(ranked[: query.k], start=1)
        ]
        latency_ms = int((time.perf_counter() - start) * 1000)
        return BackendSearchResult(
            backend_name=self.backend_name,
            hits=stabilized_hits,
            latency_ms=latency_ms,
            available=True,
            degraded=False,
        )


class VectorRetrievalService(RetrievalService, QueryRetriever, RetrievalBackend):
    def __init__(
        self,
        documents: Iterable[CorpusDocument],
        *,
        corpus_id: str | None = None,
        backend: VectorIndexBackend | None = None,
        index_version: str = 'token-vector-v1',
    ) -> None:
        indexed = tuple(_build_index(document) for document in documents)
        if not indexed:
            raise ValueError('VectorRetrievalService requires at least one document.')

        discovered_corpora = {
            document.document.corpus or 'default'
            for document in indexed
        }
        resolved_corpus = corpus_id or (next(iter(discovered_corpora)) if len(discovered_corpora) == 1 else 'multi')
        self._corpus_ids = frozenset(discovered_corpora if corpus_id is None else {corpus_id})
        self._index_version = index_version
        self._indexed_documents = indexed
        self._backend = backend or VectorIndexBackend(backend_name=f'vector:{resolved_corpus}')
        self.backend_name = self._backend.backend_name

    def status(self) -> BackendStatus:
        return self._backend.status(index_version=self._index_version)

    def search(self, query: RetrievalQuery) -> list[RetrievedDocument]:
        response = self.search_with_diagnostics(query)
        return [hit.as_document() for hit in response.hits]

    def retrieve(
        self,
        query: str,
        *,
        corpus: str | None = None,
        filters: dict[str, FilterValue] | None = None,
        k: int = 5,
    ) -> list[RetrievedDocument]:
        return self.search(RetrievalQuery(text=query, corpus=corpus, filters=filters, k=k))

    def search_with_diagnostics(self, query: RetrievalQuery) -> BackendSearchResult:
        return self._backend.search(
            query=query,
            corpus_ids=self._corpus_ids,
            index_version=self._index_version,
            indexed_documents=self._indexed_documents,
        )


def _build_index(document: CorpusDocument) -> _IndexedVectorDocument:
    weights, magnitude = _vectorize_terms(build_term_frequencies(document))
    return _IndexedVectorDocument(document=document, weights=weights, magnitude=magnitude)


def _vectorize_text(text: str) -> tuple[dict[str, float], float]:
    counts: Counter[str] = Counter(tokenize(text))
    tokens = list(counts.keys())
    for left, right in zip(tokens, tokens[1:], strict=False):
        counts[f'{left}_{right}'] += 1
    return _vectorize_terms(counts)


def _vectorize_terms(counts: Counter[str]) -> tuple[dict[str, float], float]:
    if not counts:
        return {}, 0.0
    total = float(sum(counts.values()))
    weights = {term: count / total for term, count in counts.items()}
    magnitude = math.sqrt(sum(weight * weight for weight in weights.values()))
    return weights, magnitude


def _cosine_similarity(
    query_weights: dict[str, float],
    query_magnitude: float,
    document_weights: dict[str, float],
    document_magnitude: float,
) -> float:
    if query_magnitude == 0.0 or document_magnitude == 0.0:
        return 0.0
    dot = 0.0
    smaller = query_weights if len(query_weights) < len(document_weights) else document_weights
    larger = document_weights if smaller is query_weights else query_weights
    for term, weight in smaller.items():
        dot += weight * larger.get(term, 0.0)
    return dot / (query_magnitude * document_magnitude)
