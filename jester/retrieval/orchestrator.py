from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from jester.retrieval.bm25 import BM25RetrievalService
from jester.retrieval.cache import RetrievalCache
from jester.retrieval.contracts import (
    BackendSearchResult,
    BackendStatus,
    QueryRetriever,
    RetrievalBackend,
    RetrievalHit,
    RetrievalQuery,
    RetrievalScoreBreakdown,
    RetrievalUnavailableError,
    RetrievedDocument,
)
from jester.retrieval.corpus_registry import CorpusRegistry, RegisteredCorpus
from jester.retrieval.diagnostics import BackendDiagnostic, RetrievalDiagnostics, RetrievalResponse
from jester.retrieval.provenance import attach_hit_provenance, merge_provenance
from jester.retrieval.reranker import LexicalCoverageReranker, RetrievalReranker
from jester.retrieval.vector import VectorIndexBackend, VectorRetrievalService

RetrieverFactory = Callable[[RegisteredCorpus], RetrievalBackend]


@dataclass(frozen=True, slots=True)
class _BackendSpec:
    weight: float
    backend: RetrievalBackend


class RetrievalOrchestrator(QueryRetriever):
    def __init__(
        self,
        corpus_registry: CorpusRegistry,
        *,
        bm25_factory: RetrieverFactory | None = None,
        vector_factory: RetrieverFactory | None = None,
        bm25_weight: float = 1.0,
        vector_weight: float = 0.85,
        reranker: RetrievalReranker | None = None,
        cache: RetrievalCache | None = None,
        cache_ttl_seconds: int = 60,
        rank_fusion_constant: int = 60,
    ) -> None:
        if bm25_weight <= 0.0:
            raise ValueError('bm25_weight must be greater than zero.')
        if vector_weight <= 0.0:
            raise ValueError('vector_weight must be greater than zero.')
        if cache_ttl_seconds < 0:
            raise ValueError('cache_ttl_seconds must be greater than or equal to zero.')
        if rank_fusion_constant < 1:
            raise ValueError('rank_fusion_constant must be greater than or equal to 1.')

        self._corpus_registry = corpus_registry
        self._bm25_factory = bm25_factory or _default_bm25_factory
        self._vector_factory = vector_factory or _default_vector_factory
        self._bm25_weight = bm25_weight
        self._vector_weight = vector_weight
        self._reranker = reranker or LexicalCoverageReranker()
        self._cache = cache
        self._cache_ttl_seconds = cache_ttl_seconds
        self._rank_fusion_constant = rank_fusion_constant
        self._backends = self._build_backend_index()

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalHit]:
        return self.retrieve_with_diagnostics(query).hits

    def retrieve_with_diagnostics(self, query: RetrievalQuery) -> RetrievalResponse:
        if query.enable_cache and self._cache is not None:
            cached = self._cache.get(query)
            if cached is not None:
                diagnostics = cached.diagnostics.model_copy(update={'cache_hit': True})
                return cached.model_copy(update={'diagnostics': diagnostics})

        corpus_ids = self._resolve_corpus_ids(query)
        raw_results: list[BackendSearchResult] = []
        backend_diagnostics: list[BackendDiagnostic] = []
        failure_messages: list[str] = []

        for corpus_id in corpus_ids:
            for spec in self._backends.get(corpus_id, []):
                result = spec.backend.search_with_diagnostics(query)
                raw_results.append(result)
                backend_diagnostics.append(
                    BackendDiagnostic(
                        backend_name=result.backend_name,
                        corpus_id=corpus_id,
                        latency_ms=result.latency_ms,
                        available=result.available,
                        degraded=result.degraded,
                        hits_returned=len(result.hits),
                        rejected_artifacts=list(result.rejected_artifacts),
                        error=result.error,
                    )
                )
                if result.error is not None:
                    failure_messages.append(f'{result.backend_name}: {result.error}')

        available_results = [result for result in raw_results if result.available]
        if not available_results:
            diagnostics = RetrievalDiagnostics(
                request_id=query.request_id,
                session_id=query.session_id,
                tenant_id=query.tenant_id,
                query_text=query.text,
                requested_k=query.k,
                corpora_considered=corpus_ids,
                filters_applied=query.filters,
                cache_hit=False,
                degraded=True,
                failure_messages=failure_messages or ['No retrieval backends were available.'],
                backend_diagnostics=backend_diagnostics,
                rerank_strategy=self._reranker.strategy_name,
            )
            response = RetrievalResponse(hits=[], diagnostics=diagnostics)
            if query.allow_degraded:
                if query.enable_cache and self._cache is not None:
                    self._cache.set(query, response, self._cache_ttl_seconds)
                return response
            raise RetrievalUnavailableError('; '.join(diagnostics.failure_messages))

        hits = self._merge_results(corpus_ids, available_results)
        reranked_hits = self._reranker.rerank(query, hits)[: query.k]
        diagnostics = RetrievalDiagnostics(
            request_id=query.request_id,
            session_id=query.session_id,
            tenant_id=query.tenant_id,
            query_text=query.text,
            requested_k=query.k,
            corpora_considered=corpus_ids,
            filters_applied=query.filters,
            cache_hit=False,
            degraded=any(result.degraded for result in raw_results),
            failure_messages=failure_messages,
            backend_diagnostics=backend_diagnostics,
            rerank_strategy=self._reranker.strategy_name,
        )
        response = RetrievalResponse(hits=reranked_hits, diagnostics=diagnostics)
        if query.enable_cache and self._cache is not None:
            self._cache.set(query, response, self._cache_ttl_seconds)
        return response

    def search(self, query: RetrievalQuery) -> list[RetrievedDocument]:
        return [hit.as_document() for hit in self.retrieve(query)]

    def backend_statuses(self) -> list[BackendStatus]:
        statuses = [spec.backend.status() for specs in self._backends.values() for spec in specs]
        return sorted(statuses, key=lambda item: (item.backend_name, item.index_version or ''))

    def _resolve_corpus_ids(self, query: RetrievalQuery) -> list[str]:
        if query.corpus is not None:
            registered = self._corpus_registry.get(query.corpus)
            if not registered.definition.allowed:
                raise RetrievalUnavailableError(f'Corpus {query.corpus!r} is not allowed for retrieval.')
            return [query.corpus]
        return [registered.definition.corpus_id for registered in self._corpus_registry.list_allowed()]

    def _build_backend_index(self) -> dict[str, list[_BackendSpec]]:
        backends: dict[str, list[_BackendSpec]] = {}
        for registered in self._corpus_registry.list_allowed():
            corpus_id = registered.definition.corpus_id
            backends[corpus_id] = [
                _BackendSpec(weight=self._bm25_weight, backend=self._bm25_factory(registered)),
                _BackendSpec(weight=self._vector_weight, backend=self._vector_factory(registered)),
            ]
        return backends

    def _merge_results(
        self,
        corpus_ids: list[str],
        results: list[BackendSearchResult],
    ) -> list[RetrievalHit]:
        backend_weights = self._backend_weights(corpus_ids)
        merged: dict[tuple[str, str], RetrievalHit] = {}
        for result in results:
            weight = backend_weights.get(result.backend_name, 1.0)
            for rank, hit in enumerate(result.hits, start=1):
                contribution = weight * (1.0 / (self._rank_fusion_constant + rank))
                with_provenance = attach_hit_provenance(
                    hit,
                    backend_name=result.backend_name,
                    corpus_registry=self._corpus_registry,
                )
                key = (with_provenance.doc_id, with_provenance.chunk_id)
                existing = merged.get(key)
                if existing is None:
                    score_breakdown = with_provenance.score_breakdown.model_copy(
                        update={'fused_score': contribution}
                    )
                    merged[key] = with_provenance.model_copy(
                        update={
                            'score': contribution,
                            'score_breakdown': score_breakdown,
                        }
                    )
                    continue

                breakdown = RetrievalScoreBreakdown(
                    fused_score=existing.score_breakdown.fused_score + contribution,
                    rerank_score=existing.score_breakdown.rerank_score,
                    backend_scores={
                        **existing.score_breakdown.backend_scores,
                        **with_provenance.score_breakdown.backend_scores,
                    },
                    backend_ranks={
                        **existing.score_breakdown.backend_ranks,
                        **with_provenance.score_breakdown.backend_ranks,
                    },
                )
                merged[key] = existing.model_copy(
                    update={
                        'score': breakdown.fused_score + breakdown.rerank_score,
                        'score_breakdown': breakdown,
                        'provenance': merge_provenance(existing.provenance, with_provenance.provenance),
                        'corpus_id': existing.corpus_id or with_provenance.corpus_id,
                    }
                )

        return sorted(
            merged.values(),
            key=lambda item: (-item.score, item.doc_id, item.chunk_id, item.title, item.source),
        )

    def _backend_weights(self, corpus_ids: list[str]) -> dict[str, float]:
        weights: dict[str, float] = {}
        for corpus_id in corpus_ids:
            for spec in self._backends.get(corpus_id, []):
                weights[spec.backend.backend_name] = spec.weight
        return weights


def _default_bm25_factory(registered: RegisteredCorpus) -> RetrievalBackend:
    return BM25RetrievalService(
        registered.documents,
        corpus_id=registered.definition.corpus_id,
    )


def _default_vector_factory(registered: RegisteredCorpus) -> RetrievalBackend:
    backend = VectorIndexBackend(
        backend_name=f'vector:{registered.definition.corpus_id}',
        available=True,
        detail=None,
    )
    return VectorRetrievalService(
        registered.documents,
        corpus_id=registered.definition.corpus_id,
        backend=backend,
        index_version=registered.definition.version,
    )
