from __future__ import annotations

from pydantic import Field

from jester.app.contracts.common import AppDto, ViewerRole
from jester.app.contracts.live_dm import VisibleSessionView
from jester.app.session_templates import SessionTemplateId, build_demo_session
from jester.app.visibility import build_visible_session_view
from jester.domain import Session
from jester.state import SessionRecord, SessionRepository


class SessionViewerOption(AppDto):
    viewer_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: ViewerRole


class SessionBootstrapResult(AppDto):
    session: Session
    revision: int = Field(ge=1)
    campaign_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    viewer_options: list[SessionViewerOption] = Field(default_factory=list)


class VisibleSessionRecordResult(AppDto):
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    view: VisibleSessionView
    viewer_options: list[SessionViewerOption] = Field(default_factory=list)


class SessionSummaryResult(AppDto):
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)


class SessionService:
    def __init__(self, repository: SessionRepository) -> None:
        self._repository = repository

    def bootstrap_demo_session(
        self,
        *,
        tenant_id: str,
        template_id: SessionTemplateId,
        session_name: str | None,
        start_in_combat: bool,
    ) -> SessionBootstrapResult:
        session = build_demo_session(
            template_id=template_id,
            session_name=session_name,
            start_in_combat=start_in_combat,
        )
        saved = self._repository.create_session(session, tenant_id=tenant_id)
        return SessionBootstrapResult(
            session=saved.session,
            revision=saved.revision,
            campaign_id=saved.campaign_id,
            session_id=saved.session_id,
            viewer_options=_viewer_options(saved.session),
        )

    def upsert_session(
        self,
        *,
        tenant_id: str,
        session: Session,
        expected_revision: int | None,
    ) -> SessionRecord:
        return self._repository.save_session_record(
            SessionRecord(
                tenant_id=tenant_id,
                session_id=session.session_id,
                campaign_id=session.campaign_id,
                revision=1,
                payload_sha256='pending',
                session=session,
            ),
            expected_revision=expected_revision,
        )

    def load_session_record(self, session_id: str, *, tenant_id: str) -> SessionRecord:
        return self._repository.load_session_record(session_id, tenant_id=tenant_id)

    def load_visible_session(
        self,
        session_id: str,
        *,
        tenant_id: str,
        viewer_id: str | None,
    ) -> VisibleSessionRecordResult:
        record = self._repository.load_session_record(session_id, tenant_id=tenant_id)
        return VisibleSessionRecordResult(
            session_id=record.session_id,
            campaign_id=record.campaign_id,
            revision=record.revision,
            view=build_visible_session_view(record.session, viewer_id),
            viewer_options=_viewer_options(record.session),
        )

    def list_sessions(self, *, tenant_id: str, campaign_id: str | None) -> list[SessionSummaryResult]:
        records = self._repository.list_session_records(tenant_id=tenant_id, campaign_id=campaign_id)
        return [
            SessionSummaryResult(
                session_id=record.session_id,
                campaign_id=record.campaign_id,
                revision=record.revision,
                name=record.session.name,
            )
            for record in records
        ]


def _viewer_options(session: Session) -> list[SessionViewerOption]:
    return [
        SessionViewerOption(viewer_id=session.dm_id, label='Dungeon Master', role=ViewerRole.DM),
        *[
            SessionViewerOption(
                viewer_id=player_character.controller_id,
                label=f'{player_character.name} (Player)',
                role=ViewerRole.PLAYER,
            )
            for player_character in session.player_characters.values()
        ],
    ]
