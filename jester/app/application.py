from __future__ import annotations

from pydantic import Field

from jester.app.contracts.common import AppDto
from jester.app.contracts.live_dm import LiveDmRequest
from jester.app.contracts.prep import PrepRequest
from jester.app.contracts.teaching import TeachingRequest
from jester.app.live_dm import LiveDmService
from jester.app.orchestration import (
    LiveDmServiceResult,
    PrepServiceResult,
    ServiceWarning,
    ServiceWarningCode,
    TeachingServiceResult,
)
from jester.app.prep import PrepService
from jester.app.teaching import TeachingService
from jester.state import SessionConflictError, SessionRecord, SessionRepository


class LiveDmTurnExecution(AppDto):
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    session_revision: int = Field(ge=1)
    result: LiveDmServiceResult


class PrepApplicationService:
    def __init__(self, prep_service: PrepService, session_repository: SessionRepository) -> None:
        self._prep_service = prep_service
        self._session_repository = session_repository

    def execute(self, request: PrepRequest, *, tenant_id: str) -> PrepServiceResult:
        session = None
        if request.session_id is not None:
            session = self._session_repository.load_session_record(request.session_id, tenant_id=tenant_id).session
        return self._prep_service.execute(request, session=session)


class TeachingApplicationService:
    def __init__(self, teaching_service: TeachingService) -> None:
        self._teaching_service = teaching_service

    def execute(self, request: TeachingRequest) -> TeachingServiceResult:
        return self._teaching_service.execute(request)


class LiveDmApplicationService:
    def __init__(self, live_dm_service: LiveDmService, session_repository: SessionRepository) -> None:
        self._live_dm_service = live_dm_service
        self._session_repository = session_repository

    def execute_turn(
        self,
        request: LiveDmRequest,
        *,
        tenant_id: str,
        expected_revision: int | None = None,
        fast_path: bool = False,
        narration_enabled: bool = True,
    ) -> LiveDmTurnExecution:
        record = self._session_repository.load_session_record(request.session_id, tenant_id=tenant_id)
        if expected_revision is not None and expected_revision != record.revision:
            raise SessionConflictError(
                f'Session {record.session_id!r} revision conflict: '
                f'expected {expected_revision}, current {record.revision}.'
            )

        include_narration = request.include_narration and narration_enabled and not fast_path
        live_request = request.model_copy(update={'include_narration': include_narration})
        result = self._live_dm_service.execute_turn(live_request, session=record.session)

        if request.include_narration and not include_narration:
            result = _append_warning(
                result,
                ServiceWarning(
                    code=ServiceWarningCode.NARRATION_DISABLED,
                    message='Narration was disabled for this turn by API fast-path or service configuration.',
                    degraded=False,
                ),
            )

        session_revision = record.revision
        if result.state_mutated:
            saved = self._session_repository.save_session_record(
                SessionRecord(
                    tenant_id=tenant_id,
                    session_id=record.session_id,
                    campaign_id=record.campaign_id,
                    revision=record.revision,
                    payload_sha256=record.payload_sha256,
                    session=record.session,
                ),
                expected_revision=record.revision,
            )
            session_revision = saved.revision

        return LiveDmTurnExecution(
            session_id=record.session_id,
            campaign_id=record.campaign_id,
            session_revision=session_revision,
            result=result,
        )


def _append_warning(result: LiveDmServiceResult, warning: ServiceWarning) -> LiveDmServiceResult:
    existing = result.warnings
    if any(item.code == warning.code and item.message == warning.message for item in existing):
        return result
    warnings = [*existing, warning]
    debug = result.debug.model_copy(update={'warnings': warnings})
    return result.model_copy(update={'warnings': warnings, 'debug': debug})


