from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from jester.api.deps import (
    ServiceContainer,
    get_container,
    get_tenant_id,
    request_context,
    require_rate_limit,
)
from jester.api.schemas import ResponseMeta, RetrievalDebugRequest, RetrievalDebugResponse
from jester.retrieval import RetrievalQuery

_CONTAINER = Depends(get_container)
_TENANT = Depends(get_tenant_id)
_RATE_LIMIT = Depends(require_rate_limit)

router = APIRouter(prefix='/api/v1/retrieval', tags=['retrieval'], dependencies=[_RATE_LIMIT])


@router.post('/debug', response_model=RetrievalDebugResponse)
def debug_retrieval(
    payload: RetrievalDebugRequest,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> RetrievalDebugResponse:
    request_id, trace_id = request_context(request)
    response = container.retrieval_orchestrator.retrieve_with_diagnostics(
        RetrievalQuery(
            text=payload.text,
            corpus=payload.corpus,
            filters=payload.filters,
            k=payload.k,
            request_id=request_id,
            tenant_id=tenant_id,
            allow_degraded=payload.allow_degraded,
            debug=True,
        )
    )
    return RetrievalDebugResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            degraded=response.diagnostics.degraded,
            warnings=list(response.diagnostics.failure_messages),
        ),
        retrieval=response,
    )
