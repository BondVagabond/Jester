from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from jester.api.deps import (
    ServiceContainer,
    get_container,
    get_tenant_id,
    request_context,
    require_rate_limit,
)
from jester.api.schemas import ResponseMeta, TeachingApiRequest, TeachingApiResponse
from jester.app.orchestration import is_degraded, warning_codes

_CONTAINER = Depends(get_container)
_TENANT = Depends(get_tenant_id)
_RATE_LIMIT = Depends(require_rate_limit)

router = APIRouter(prefix='/api/v1/teaching', tags=['teaching'], dependencies=[_RATE_LIMIT])


@router.post('', response_model=TeachingApiResponse)
def create_teaching_response(
    payload: TeachingApiRequest,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> TeachingApiResponse:
    result = container.teaching_application_service.execute(payload.request)
    request_id, trace_id = request_context(request)
    return TeachingApiResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            degraded=is_degraded(result.warnings),
            warnings=warning_codes(result.warnings),
        ),
        lesson=result.response,
    )
