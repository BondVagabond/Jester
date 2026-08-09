from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from jester.api.deps import (
    ServiceContainer,
    get_container,
    get_tenant_id,
    request_context,
    require_rate_limit,
)
from jester.api.schemas import PrepApiRequest, PrepApiResponse, ResponseMeta
from jester.app.orchestration import is_degraded, warning_codes

_CONTAINER = Depends(get_container)
_TENANT = Depends(get_tenant_id)
_RATE_LIMIT = Depends(require_rate_limit)

router = APIRouter(prefix='/api/v1/prep', tags=['prep'], dependencies=[_RATE_LIMIT])


@router.post('', response_model=PrepApiResponse)
def create_prep_artifact(
    payload: PrepApiRequest,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> PrepApiResponse:
    result = container.prep_application_service.execute(payload.request, tenant_id=tenant_id)
    request_id, trace_id = request_context(request)
    return PrepApiResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            session_id=payload.request.session_id,
            degraded=is_degraded(result.warnings),
            warnings=warning_codes(result.warnings),
        ),
        prep=result.response,
    )
