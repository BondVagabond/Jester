from __future__ import annotations

from typing import Protocol

from jester.retrieval._common import tokenize
from jester.retrieval.contracts import RetrievalHit, RetrievalQuery


class RetrievalReranker(Protocol):
    strategy_name: str

    def rerank(self, query: RetrievalQuery, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        ...


class LexicalCoverageReranker:
    def __init__(self, *, weight: float = 0.15) -> None:
        if weight < 0.0:
            raise ValueError('Reranker weight must be greater than or equal to zero.')
        self._weight = weight
        self.strategy_name = 'lexical_coverage'

    def rerank(self, query: RetrievalQuery, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        query_terms = set(tokenize(query.text))
        if not query_terms or not hits or self._weight == 0.0:
            return _sort_hits(hits)

        reranked: list[RetrievalHit] = []
        for hit in hits:
            document_terms = set(tokenize(f'{hit.title} {hit.text}'))
            coverage = len(query_terms & document_terms) / len(query_terms)
            rerank_score = coverage * self._weight
            score_breakdown = hit.score_breakdown.model_copy(
                update={'rerank_score': rerank_score}
            )
            reranked.append(
                hit.model_copy(
                    update={
                        'score': score_breakdown.fused_score + rerank_score,
                        'score_breakdown': score_breakdown,
                    }
                )
            )
        return _sort_hits(reranked)


def _sort_hits(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    return sorted(
        hits,
        key=lambda item: (-item.score, item.doc_id, item.chunk_id, item.title, item.source),
    )
