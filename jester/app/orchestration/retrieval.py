from __future__ import annotations

from jester.app.orchestration.contracts import (
    RetrievedContext,
    RetrievedContextItem,
    RouteSelection,
    ServiceWarning,
    ServiceWarningCode,
)
from jester.retrieval import QueryRetriever, RetrievalOrchestrator, RetrievalQuery, RetrievalUnavailableError


class RetrievalContextService:
    def __init__(self, retriever: QueryRetriever | None = None) -> None:
        self._retriever = retriever

    def fetch(
        self,
        route: RouteSelection,
        *,
        query_text: str,
        request_id: str | None = None,
        session_id: str | None = None,
        tenant_id: str | None = None,
    ) -> RetrievedContext:
        if self._retriever is None:
            return RetrievedContext(
                route=route,
                query_text=query_text,
                warnings=[
                    ServiceWarning(
                        code=ServiceWarningCode.RETRIEVAL_UNAVAILABLE,
                        message='Retrieval service is not configured for this workspace request.',
                        degraded=True,
                    )
                ],
            )

        if isinstance(self._retriever, RetrievalOrchestrator):
            try:
                response = self._retriever.retrieve_with_diagnostics(
                    RetrievalQuery(
                        text=query_text,
                        corpus=route.corpus_id,
                        k=route.retrieval_top_k,
                        request_id=request_id,
                        session_id=session_id,
                        tenant_id=tenant_id,
                        allow_degraded=True,
                        debug=True,
                    )
                )
            except RetrievalUnavailableError as exc:
                return RetrievedContext(
                    route=route,
                    query_text=query_text,
                    warnings=[
                        ServiceWarning(
                            code=ServiceWarningCode.RETRIEVAL_UNAVAILABLE,
                            message=str(exc),
                            degraded=True,
                        )
                    ],
                )

            warnings: list[ServiceWarning] = []
            if response.diagnostics.degraded:
                message = '; '.join(response.diagnostics.failure_messages) or 'Retrieval degraded during this request.'
                warnings.append(
                    ServiceWarning(
                        code=ServiceWarningCode.RETRIEVAL_DEGRADED,
                        message=message,
                        degraded=True,
                    )
                )
            return RetrievedContext(
                route=route,
                query_text=query_text,
                hits=[
                    RetrievedContextItem(
                        doc_id=hit.doc_id,
                        chunk_id=hit.chunk_id,
                        title=hit.title,
                        source=hit.source,
                        score=hit.score,
                        excerpt=hit.text,
                        corpus_id=hit.corpus_id,
                    )
                    for hit in response.hits
                ],
                warnings=warnings,
                diagnostics=response.diagnostics,
            )

        documents = self._retriever.search(
            RetrievalQuery(
                text=query_text,
                corpus=route.corpus_id,
                k=route.retrieval_top_k,
                request_id=request_id,
                session_id=session_id,
                tenant_id=tenant_id,
            )
        )
        return RetrievedContext(
            route=route,
            query_text=query_text,
            hits=[
                RetrievedContextItem(
                    doc_id=document.doc_id,
                    chunk_id=document.chunk_id,
                    title=document.title,
                    source=document.source,
                    score=document.score,
                    excerpt=document.text,
                    corpus_id=document.corpus_id,
                )
                for document in documents
            ],
        )
