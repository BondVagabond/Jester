from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from jester.retrieval.contracts import QueryRetriever, RetrievalQuery, RetrievedDocument


@dataclass(frozen=True, slots=True)
class WeightedRetriever:
    name: str
    retriever: QueryRetriever
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError('WeightedRetriever name must not be blank.')
        if self.weight <= 0.0:
            raise ValueError('WeightedRetriever weight must be greater than zero.')


class HybridRetrievalService(QueryRetriever):
    def __init__(self, backends: Iterable[WeightedRetriever]) -> None:
        self._backends = tuple(backends)
        if not self._backends:
            raise ValueError('HybridRetrievalService requires at least one backend.')

    def search(self, query: RetrievalQuery) -> list[RetrievedDocument]:
        combined: dict[tuple[str, str], RetrievedDocument] = {}
        for backend in self._backends:
            for document in backend.retriever.search(query):
                key = (document.doc_id, document.chunk_id)
                weighted_score = document.score * backend.weight
                existing = combined.get(key)
                if existing is None:
                    combined[key] = document.model_copy(update={'score': weighted_score})
                    continue
                combined[key] = existing.model_copy(update={'score': existing.score + weighted_score})

        ranked = list(combined.values())
        ranked.sort(
            key=lambda item: (-item.score, item.doc_id, item.chunk_id, item.title, item.source)
        )
        return ranked[: query.k]
