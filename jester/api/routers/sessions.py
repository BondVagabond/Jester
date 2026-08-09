from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from jester.api.deps import (
    ServiceContainer,
    get_container,
    get_tenant_id,
    request_context,
    require_rate_limit,
)
from jester.api.schemas import (
    BootstrapSessionRequest,
    BootstrapSessionResponse,
    ResponseMeta,
    SessionListResponse,
    SessionRecordResponse,
    SessionSummary,
    SessionViewerOption,
    UpsertSessionRequest,
    VisibleSessionRecordResponse,
)
from jester.app.sessions import SessionViewerOption as SessionViewerOptionResult

_CONTAINER = Depends(get_container)
_TENANT = Depends(get_tenant_id)
_RATE_LIMIT = Depends(require_rate_limit)

router = APIRouter(prefix='/api/v1/sessions', tags=['sessions'], dependencies=[_RATE_LIMIT])


@router.post('/bootstrap', response_model=BootstrapSessionResponse)
def bootstrap_session(
    payload: BootstrapSessionRequest,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> BootstrapSessionResponse:
    result = container.session_service.bootstrap_demo_session(
        tenant_id=tenant_id,
        template_id=payload.template_id,
        session_name=payload.session_name,
        start_in_combat=payload.start_in_combat,
    )
    request_id, trace_id = request_context(request)
    return BootstrapSessionResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            session_id=result.session_id,
            degraded=False,
        ),
        session=result.session,
        revision=result.revision,
        campaign_id=result.campaign_id,
        session_id=result.session_id,
        viewer_options=[_to_viewer_option(item) for item in result.viewer_options],
    )


@router.put('/{session_id}', response_model=SessionRecordResponse)
def upsert_session(
    session_id: str,
    payload: UpsertSessionRequest,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> SessionRecordResponse:
    if payload.session.session_id != session_id:
        raise HTTPException(status_code=400, detail='Body session_id must match the route session_id.')

    saved = container.session_service.upsert_session(
        tenant_id=tenant_id,
        session=payload.session,
        expected_revision=payload.expected_revision,
    )
    request_id, trace_id = request_context(request)
    return SessionRecordResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            session_id=saved.session_id,
            degraded=False,
        ),
        session=saved.session,
        revision=saved.revision,
        campaign_id=saved.campaign_id,
        session_id=saved.session_id,
    )


@router.get('/{session_id}', response_model=SessionRecordResponse)
def get_session(
    session_id: str,
    request: Request,
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> SessionRecordResponse:
    record = container.session_service.load_session_record(session_id, tenant_id=tenant_id)
    request_id, trace_id = request_context(request)
    return SessionRecordResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            session_id=record.session_id,
            degraded=False,
        ),
        session=record.session,
        revision=record.revision,
        campaign_id=record.campaign_id,
        session_id=record.session_id,
    )


@router.get('/{session_id}/view', response_model=VisibleSessionRecordResponse)
def get_visible_session(
    session_id: str,
    request: Request,
    viewer_id: str | None = Query(default=None),
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> VisibleSessionRecordResponse:
    result = container.session_service.load_visible_session(
        session_id,
        tenant_id=tenant_id,
        viewer_id=viewer_id,
    )
    request_id, trace_id = request_context(request)
    return VisibleSessionRecordResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            session_id=result.session_id,
            degraded=False,
        ),
        session_id=result.session_id,
        campaign_id=result.campaign_id,
        revision=result.revision,
        view=result.view,
        viewer_options=[_to_viewer_option(item) for item in result.viewer_options],
    )


@router.get('', response_model=SessionListResponse)
def list_sessions(
    request: Request,
    campaign_id: str | None = Query(default=None),
    container: ServiceContainer = _CONTAINER,
    tenant_id: str = _TENANT,
) -> SessionListResponse:
    sessions = container.session_service.list_sessions(tenant_id=tenant_id, campaign_id=campaign_id)
    request_id, trace_id = request_context(request)
    return SessionListResponse(
        meta=ResponseMeta(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            degraded=False,
        ),
        sessions=[
            SessionSummary(
                session_id=item.session_id,
                campaign_id=item.campaign_id,
                revision=item.revision,
                name=item.name,
            )
            for item in sessions
        ],
    )


def _to_viewer_option(option: SessionViewerOptionResult) -> SessionViewerOption:
    return SessionViewerOption(
        viewer_id=option.viewer_id,
        label=option.label,
        role=option.role,
    )
