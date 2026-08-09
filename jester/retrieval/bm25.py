from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jester.corpus.jsonl import load_corpus_jsonl
from jester.corpus.models import CorpusDocument
from jester.ingestion.filtering import IngestionPolicy
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
class _IndexedDocument:
    document: CorpusDocument
    term_frequencies: Counter[str]
    length: int


class BM25RetrievalService(RetrievalService, QueryRetriever, RetrievalBackend):
    """Deterministic BM25 retrieval over sanitized in-memory documents."""

    def __init__(
        self,
        documents: Iterable[CorpusDocument],
        *,
        corpus_id: str | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        indexed = tuple(self._build_index(document) for document in documents)
        if not indexed:
            raise ValueError('BM25RetrievalService requires at least one document.')

        discovered_corpora = {
            document.document.corpus or 'default'
            for document in indexed
        }
        resolved_corpus = corpus_id or (next(iter(discovered_corpora)) if len(discovered_corpora) == 1 else 'multi')
        self.backend_name = f'bm25:{resolved_corpus}'
        self._corpus_ids = frozenset(discovered_corpora if corpus_id is None else {corpus_id})
        self._indexed_documents = indexed
        self._document_count = len(indexed)
        self._average_length = sum(item.length for item in indexed) / self._document_count
        self._k1 = k1
        self._b = b
        document_frequencies: Counter[str] = Counter()
        for item in indexed:
            document_frequencies.update(item.term_frequencies.keys())
        self._document_frequencies = document_frequencies

    @classmethod
    def from_jsonl(
        cls,
        path: Path,
        *,
        policy: IngestionPolicy | None = None,
        corpus_id: str | None = None,
    ) -> BM25RetrievalService:
        return cls(load_corpus_jsonl(path, policy=policy), corpus_id=corpus_id)

    def status(self) -> BackendStatus:
        return BackendStatus(
            backend_name=self.backend_name,
            available=True,
            degraded=False,
            index_version='in-memory',
        )

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
        start = time.perf_counter()
        if query.corpus is not None and query.corpus not in self._corpus_ids:
            return BackendSearchResult(
                backend_name=self.backend_name,
                hits=[],
                latency_ms=0,
                available=True,
                degraded=False,
            )

        query_terms = tokenize(query.text)
        if not query_terms:
            return BackendSearchResult(
                backend_name=self.backend_name,
                hits=[],
                latency_ms=0,
                available=True,
                degraded=False,
            )

        ranked: list[RetrievalHit] = []
        for indexed_document in self._indexed_documents:
            document = indexed_document.document
            if query.corpus is not None and document.corpus != query.corpus:
                continue
            if not matches_filters(document, query.filters):
                continue
            score = self._score(query_terms, indexed_document)
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

    @staticmethod
    def _build_index(document: CorpusDocument) -> _IndexedDocument:
        terms = build_term_frequencies(document)
        return _IndexedDocument(
            document=document,
            term_frequencies=terms,
            length=sum(terms.values()),
        )

    def _score(self, query_terms: tuple[str, ...], document: _IndexedDocument) -> float:
        total = 0.0
        for term in query_terms:
            frequency = document.term_frequencies.get(term, 0)
            if frequency == 0:
                continue
            document_frequency = self._document_frequencies.get(term, 0)
            idf = math.log(
                1.0 + (self._document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            normalization = 1.0 - self._b + self._b * (document.length / self._average_length)
            numerator = frequency * (self._k1 + 1.0)
            denominator = frequency + self._k1 * normalization
            total += idf * (numerator / denominator)
        return total
