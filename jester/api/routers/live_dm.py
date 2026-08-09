from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from jester.api.deps import (
    ServiceContainer,
    get_container,
    get_tenant_id,
    request_context,
    require_rate_limit,
)
from jester.api.schemas import LiveDmTurnApiResponse, LiveDmTurnCommand, ResponseMeta
from jester.app.orchestration import is_degraded, warning_codes

_CONTAINER = Depends(get_container)
_TENANT = Depends(get_tenant_id)
_RATE_LIMIT = Depends(require_rate_limit)

router = APIRouter(prefix='/api/v1/live-dm', tags=['live_dm'], dependencies=[_RATE_LIMIT])


@router.post('/turns', response_model=LiveDmTurnApiResponse)
def handle_live_dm_turn(
    payload: LiveDmTurnCommand,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> LiveDmTurnApiResponse:
    execution = container.live_dm_application_service.execute_turn(
        payload.request,
        tenant_id=tenant_id,
        expected_revision=payload.expected_revision,
        fast_path=payload.fast_path,
        narration_enabled=container.settings.api.enable_narration,
    )
    request_id, trace_id = request_context(request)
    return LiveDmTurnApiResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            session_id=execution.session_id,
            degraded=is_degraded(execution.result.warnings),
            warnings=warning_codes(execution.result.warnings),
        ),
        response=execution.result.response,
        session_revision=execution.session_revision,
    )
